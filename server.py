#!/usr/bin/env python
import socket as s
import traceback
from select import select
from utils import MessageBuffer, MessageBufferException, ChatHandler, BlackjackDeck, BlackjackHand, BlackjackError, escape_chars, colors, validate_name
from collections import deque, defaultdict
from time import time
import signal
import sys
import argparse
import json
import logging
import string


class Client(object):
    def __init__(self, sock):
        self.sock = sock
        self.mbuffer = MessageBuffer(sock)
        self.strikes = 0
        self.id_ = ''

    #def __del__(self):
    #    del self.mbuffer


class BlackjackServer(object):
    def __init__(self, port=36709, timeout=30, join_wait=30, max_tcp=None):
        self.MAX_PLAYERS = 6
        self.MIN_BET = 4
        self.MAX_STRIKES = 3
        self.MAX_CHAT_LEN = 450

        self.host = ''
        self.port = port
        self.timeout = timeout
        self.join_wait = join_wait
        self.max_tcp = max_tcp
        self.accounts = {}
        #persistent accounts
        try:
            with open('blackjack_accounts','r') as account_f:
                self.accounts.update(json.load(account_f))
                for k in self.accounts:
                    self.accounts[k] = int(self.accounts[k])
        except IOError:
            pass # don't worry if the file isn't there.

        #the chat handler depends on self.clients, so it is very important to
        #define self.clients first
        self.clients = {} #sock:Client pairs

        #TODO add a special client sock here to implement the gui. This can be 
        #a dumb client who never manages to get out of the lobby queue, (because they're not in it)
        #but receives all the messages that the clients do.


        #logging stuff
        self.logger = logging.getLogger('blackjack')
        self.logger.setLevel(logging.DEBUG)

        fh = logging.FileHandler('server.log')
        fh.setLevel(logging.DEBUG)
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        # create formatter and add it to the handlers
        format_style = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        formatter = logging.Formatter(colors.DIM + format_style + colors.ENDC)
        formatter_no_color = logging.Formatter(format_style)
        fh.setFormatter(formatter_no_color)
        ch.setFormatter(formatter)
        # add the handlers to the logger
        self.logger.addHandler(fh)
        self.logger.addHandler(ch)


        c_handler = ChatHandler(self.broadcast, 'SERVER')
        c_handler.setLevel(logging.INFO)
        c_handler.setFormatter(formatter_no_color)
        self.logger.addHandler(c_handler)
        
        self.m_handlers = {} #CMND:func(client, *args) pairs
        self.m_handlers['join'] = self.handle_join
        self.m_handlers['chat'] = self.handle_chat
        self.m_handlers['exit'] = self.handle_exit
        self.m_handlers['turn'] = self.handle_turn
        self.m_handlers['insu'] = self.handle_insu
        self.m_handlers['ante'] = self.handle_ante

        self.server = s.socket(s.AF_INET, s.SOCK_STREAM)
        self.server.setsockopt(s.SOL_SOCKET, s.SO_REUSEADDR, 1)
        self.server.bind((self.host,self.port))
        self.server.listen(5) #what is this?

        signal.signal(signal.SIGINT, self.sighandler)

        self.watched_socks = [self.server]
        self.bets = {} #sock:ante pairs. These are updated for a split or down
        self.occupied_seats = {} #sock:seat_number pairs; the current players
        self.hands = {} #sock:BlackjackHand pairs, plus one 'dealer':BlackjackHand
        self.insu = defaultdict(lambda: 0) #The amount of insurance we owe everyone.
        self.results = defaultdict(lambda : 0) #a dollar score for each player. 
        #positive is a win, negative a tie 
        self.deck = BlackjackDeck() 
        self.lobby = deque() 
        self.state='waiting to start game'
        self.game_in_progress = False
        self.split_store = False 

    def broadcast(self, msg):
        self.logger.debug('sending message: {}'.format(msg))
        clients = self.clients.keys()
        for client in clients:
            try:
                if client in clients:
                    client.sendall(msg)
                else:
                    self.logger.debug('static iteration on a dynamic list')
            except Exception as e:
                self.logger.debug(traceback.format_exc())
                self.drop_client(client, reason='here in broadcast, sock appears to be closed')

    def empty_seat(self):
        return min(set(range(1,self.MAX_PLAYERS + 1)).difference(
            {seat for sock,seat in self.occupied_seats.iteritems() }))

    def handle_join(self, sock, id_):
        if id_ != validate_name(id_):
            return self.scold(sock, 'Id must be twelve characters long, right padded with spaces if necessary. You gave "{name}", try "{name:<12}"'.format(name=id_), fatal=True)
        #split this to a handle_join, midgame, and a handle_join
        if id_ in [self.clients[client].id_ for client in self.clients]:
            if sock == [client for client in self.clients if self.client[client].id_==id_][0]:
                return self.scold(sock, "You've already joined!")
            return self.scold(sock, "ID {} is already in use.".format(id_))
        if id_ == 'SERVER      ':
            return self.scold(sock, '"SERVER      " is a reserved name and cannot be used.')
        if not (all(c in (string.ascii_letters + string.digits + ' ') for c in id_) and
                id_[0] in string.ascii_letters):
            self.logger.debug('invalid name : "{}"'.format(id_))
            return self.scold(sock, "ID must be alphanumeric and start with a letter.")
        self.clients[sock].id_ = id_
        self.accounts[id_] = self.accounts.get(id_, 1000) #default to 1000
        if not self.game_in_progress and len(self.occupied_seats) < 6 and self.accounts[id_] > self.MIN_BET:
            location = 'tabl'
            empty_seat = self.empty_seat()
            self.occupied_seats[sock] = empty_seat
        else:
            location = 'lbby'
            self.lobby.append(sock)
        self.broadcast('[join|{id_}|{timeout}|{cash:0>10}|{seat}]'.format(
            id_=id_,
            timeout=self.timeout,
            cash=self.accounts[id_],
            seat=0 if sock not in self.occupied_seats else self.occupied_seats[sock]))

    def handle_chat(self, sock, text):
        if len(text)> self.MAX_CHAT_LEN:
            return self.scold(sock, reason="Chat message too long. Must be {} characters or less.".format(self.MAX_CHAT_LEN))
        if self.clients[sock].id_: 
            self.broadcast('[chat|{id_}|{text}]'.format(
                id_=self.clients[sock].id_,
                text=text))
            return True
        else: #clients must tell us their name before they can chat
            return self.scold(sock,reason='You must first join with a player ID.')
        
    def handle_exit(self,sock):
        self.drop_client(sock,reason='They sent an exit')

    def drop_client(self, sock, reason=None):
        save_id = 'an unknown client' if not sock in self.clients else self.clients[sock].id_
        if sock in self.clients:
            del self.clients[sock]
            self.broadcast('[exit|{id_}]'.format(id_=save_id))
        self.logger.info('dropping {}, id: {} because: {}'.format(sock, save_id, reason if reason is not None else '(no reason given)'))
        if sock in self.watched_socks:
            self.watched_socks.remove(sock)
        if sock in self.occupied_seats:
            del self.occupied_seats[sock]
        if sock in self.insu:
            del self.insu[sock]
        if sock in self.bets:
            del self.bets[sock]

    def sighandler(self, signum, frame):
        print('Shutting down server...')
        for client in self.clients:
            client.close()
        self.server.close()
        with open('blackjack_accounts','w') as account_f:
            json.dump(self.accounts,account_f)
        exit(0)

    def accept_client(self):
        client, address = self.server.accept()
        self.watched_socks.append(client)
        self.clients[client] = Client(client)
        self.logger.debug('accepted client with sock {}'.format(client))

    def wait_for_players(self):
        while not self.occupied_seats:
            print('waiting for clients to join...')
            inputready, _, _ = select(self.watched_socks, [], [])
            for sock in inputready:
                if sock == self.server:
                    self.accept_client()
                elif sock in self.lobby or sock in self.occupied_seats:
                    self.process_messages(sock, allowed_types=['chat','exit'])
                else:
                    self.process_messages(sock, allowed_types=['join'])
        print('waiting for more players...')
        start = time()
        while time() - start < self.join_wait and self.occupied_seats and len(self.occupied_seats) < self.MAX_PLAYERS:
            this_timeout = max(self.join_wait - (time() - start), 0) 
            inputready, _, _ = select(self.watched_socks, [], [], this_timeout)
            for sock in inputready:
                if sock == self.server:
                    self.accept_client()
                elif sock in self.occupied_seats:
                    self.process_messages(sock, allowed_types=['chat','exit'])
                else:
                    self.process_messages(sock, allowed_types=['join'])

    def get_antes(self):
        if not self.occupied_seats:
            return self.drop_game()
        self.state = 'waiting for antes'
        self.logger.debug('state is {}'.format(self.state))
        self.broadcast('[ante|{:0>10}]'.format(self.MIN_BET))
        start = time()
        while time() - start < self.timeout and len(self.bets) < len(self.occupied_seats):
            this_timeout = max(self.timeout - (time() - start), 0)
            inputready, _, _ = select(self.watched_socks, [], [], this_timeout)
            for sock in inputready:
                if sock == self.server:
                    self.accept_client()
                elif sock in self.occupied_seats:
                    self.process_messages(sock,['chat','exit','ante'])
                else:
                    self.process_messages(sock,['join','chat','exit'])
        for no_ante_player in (set(self.occupied_seats.keys()) - set(self.bets.keys())):
            self.drop_client(no_ante_player, reason='failed to send an ante')

    def deal(self, shuf=True):
        if not self.occupied_seats:
            return self.drop_game()
        if shuf:
            self.deck.shuffle()

        self.hands['dealer'] = BlackjackHand(self.deck.deal(2))
        msg = ['[deal']
        msg.append(self.hands['dealer'].cards[0]) # only reveal one dealer card
        msg.append('shufy' if shuf else 'shufn')

        for seat_num in range(1,self.MAX_PLAYERS + 1):
            seated_player = [sock for sock,seat in self.occupied_seats.iteritems() if seat == seat_num]
            if seated_player == []:
                msg.append('')
            else:
                player = seated_player[0]
                self.hands[player] = BlackjackHand(self.deck.deal(2))
                player_id = self.clients[player].id_
                msg.append('{id_:<12},{cash:0>10},{cards[0]},{cards[1]}'.format(
                    id_=player_id, 
                    cash=self.accounts[player_id],
                    cards=self.hands[player].cards))
        msg[-1] += ']' #closing brace to message
        self.broadcast('|'.join(msg))
        if self.hands['dealer'].cards[0][0] == '1': #dealer has ace showing
            self.wait_for_insurance()
            if self.hands['dealer'].value() == 21:
                #game can end now
                for player in self.occupied_seats:
                    self.evaluate_hand(player)
                self.payout()
                self.drop_game()

           
    def wait_for_insurance(self):
        self.state='waiting for insurace'
        self.logger.debug('state is {}'.format(self.state))
        start = time()
        while time() - start < self.timeout and len(self.insu) < len(self.occupied_seats):
            this_timeout = max(self.timeout - (time() - start), 0)
            inputready, _, _ = select(self.watched_socks, [], [], this_timeout)
            for sock in inputready:
                if sock == self.server:
                    self.accept_client()
                elif sock in self.occupied_seats:
                    self.process_messages(sock,['chat','exit','insu'])
                else:
                    self.process_messages(sock,['join','chat','exit'])

    def play_out_turns(self):
        if not self.occupied_seats:
            return self.drop_game()
        dealer_moves = self.play_dealer_turn() #find out what the dealer will have at the end of the game
        #Now we can modify everyone's cash in situ, rather than waiting till the end.

        self.player_done = False
        for player in sorted(self.occupied_seats, key=lambda p: self.occupied_seats[p]):
            self.split_store = False
            while not self.player_done and player in self.occupied_seats:
                self.broadcast('[turn|{:<12}]'.format(self.clients[player].id_))
                start = time()
                self.player_moved = False
                while time() - start < self.timeout and not self.player_moved and player in self.occupied_seats:
                    this_timeout = max(self.timeout - (time() - start), 0)
                    inputready, _, _ = select(self.watched_socks, [], [], this_timeout)
                    for sock in inputready:
                        if sock == self.server:
                            self.accept_client()
                        elif sock == player:
                            self.process_messages(player,['chat','exit','turn'])
                        else:
                            self.process_messages(sock, ['join','chat','exit'])
                if not self.player_moved:
                    self.drop_client(player, 'timeout waiting for turn')
        #disclose dealer moves here:
        for move in dealer_moves:
            self.broadcast(move)

    def play_dealer_turn(self):
        #send the stat message for the dealer's second card
        dealer_moves = ['[turn|SERVER      ]']
        msg = '[stat|SERVER      |{action}|{card}|{bust}|0000000000]'
        dealer_moves.append(msg.format(
                action='hitt',
                card=self.hands['dealer'].cards[1],
                bust='bustn'))
        my_hand = self.hands['dealer']
        while True:
            if my_hand.value() <= 16 or ('1' in [card[0] for card in my_hand.cards] and my_hand.value() <= 17):
                new_card = self.deck.deal(1)[0]
                my_hand.cards.append(new_card)
                val = my_hand.value()
                dealer_moves.append('[turn|SERVER      ]')
                dealer_moves.append(msg.format(
                    action='hitt',
                    card=new_card,
                    bust='bustn' if val <= 21 else 'busty'))
                if val > 21:
                    break #bust!
            else:
                dealer_moves.append('[turn|SERVER      ]')
                dealer_moves.append(msg.format(
                    action='stay',
                    card='xx',
                    bust='bustn'))
                break
        return dealer_moves
                


    def handle_turn(self,sock,action):
        action_handlers = {
                'hitt':self.action_hitt,
                'stay':self.action_stay,
                'down':self.action_down,
                'splt':self.action_split
            }
        self.player_moved = True
        if action in action_handlers:
            return action_handlers[action](sock)
        else:
            return self.scold(sock, 'Invalid action. Valid actions are hitt, stay, down, or splt.')


    def action_hitt(self,player):
        new_card = self.deck.deal(1)[0]
        player_id = self.clients[player].id_

        self.hands[player].cards.append(new_card)
        
        hand_value = self.hands[player].value()
                
        msg = '[stat|{id_}|hitt|{card}|{bust}|{bet}]'.format(
                id_=player_id,
                card=new_card,
                bust = 'busty' if hand_value > 21 else 'bustn',
                bet = self.bets[player])
        self.broadcast(msg)
        if hand_value >= 21:
            self.player_done = True
            self.evaluate_hand(player)
        return True

    def evaluate_hand(self,player):
        hand_value = self.hands[player].value()
        player_id = self.clients[player].id_
        dealer_hand = self.hands['dealer'].value()
        self.logger.debug('player has {} dealer has {}'.format(hand_value, dealer_hand))

        if hand_value > 21 or (dealer_hand <= 21 and dealer_hand > hand_value): #lose!
            self.results[player_id] -= self.bets[player]
            self.logger.debug('{} lost'.format(player_id))
        elif hand_value == 21 and dealer_hand != 21:
            self.results[player_id] += 2.5*self.bets[player]
            #from spec: "If a player gets a blackjack (and beat the dealer) they win 1.5x their initial bet in addition to their initial bet"
            self.logger.debug('{} won'.format(player_id))
        elif hand_value > dealer_hand or dealer_hand > 21:
            self.results[player_id] += 2*self.bets[player]
            self.logger.debug('{} won'.format(player_id))
        else:#tie
            self.logger.debug('{} tied'.format(player_id))

        if self.split_store:
            self.player_done = False
            self.logger.debug('player has finished the first half of a split turn.' + 
                    'their hand WAS {}'.format(self.hands[player].cards))
            self.hands[player].cards = [self.split_store]
            self.split_store = False
            self.logger.debug('now it is {}'.format(self.hands[player].cards))
            self.action_hitt(player)
            
    def action_stay(self,player):
        self.player_done = True
        msg = '[stat|{id_}|stay|xx|bustn|{bet}]'.format(
                id_=self.clients[player].id_,
                bet=self.bets[player])
        self.broadcast(msg)
        self.evaluate_hand(player)
        return True

    def action_down(self,player):
        if len(self.hands[player].cards) > 2 or self.split_store:
            return self.scold(player, 'Cannot "double" after first turn.')
        player_id = self.clients[player].id_
        if self.accounts[player_id] < self.bets[player]:
            return self.scold(player, "You don't have enough cash to double down")

        new_card = self.deck.deal(1)[0]
        self.hands[player].cards.append(new_card)
        self.logger.debug('inside action_down, taking extra {}. accounts : {} -> {}'.format(
            self.bets[player], self.accounts[player_id], self.accounts[player_id] - self.bets[player]))
        self.accounts[player_id] -= self.bets[player]
        self.logger.debug('doubling bet: {} -> {}'.format(
            self.bets[player],
            self.bets[player]*2))
        self.bets[player] *= 2
        msg = '[stat|{id_}|down|{card}|{bust}|{bet}]'.format(
                id_=player_id,
                card=new_card,
                bust= 'busty' if self.hands[player].value() > 21 else 'bustn',
                bet=self.bets[player])
        self.broadcast(msg)
        self.player_done = True
        self.evaluate_hand(player)
        return True

    def action_split(self,player):
        if len(self.hands[player].cards) > 2 or self.split_store:
            return self.scold(player, 'Cannot "split" after first turn.') 
        if self.hands[player].cards[0][0] != self.hands[player].cards[1][0]:
            return self.scold(player, 'Card values must be equal to split.')

        player_id = self.clients[player].id_
        self.split_store = self.hands[player].cards[1]
        new_card = self.deck.deal(1)[0]
        self.hands[player].cards[1] = new_card
        msg = '[stat|{id_}|splt|{card}|bustn|{bet}]'.format(
            id_=player_id,
            card = new_card,
            bet = self.bets[player])
        self.broadcast(msg)
        return True



    def payout(self):
        msg = ['[endg']
        #pay out insurance
        for sock in self.insu:
            player_id = self.clients[sock].id_
            #insurance is already tripled.
            self.accounts[player_id] += self.insu[sock]

        for seat_num in range(1,self.MAX_PLAYERS + 1):
            seated_player = [sock for sock,seat in self.occupied_seats.iteritems() if seat == seat_num]
            if seated_player == []:
                msg.append('')
                continue
            player = seated_player[0]
            player_id = self.clients[player].id_
            player_val = self.results[player_id]
            if player_val > 0:
                result = 'WON'
                self.accounts[player_id] += 2*self.bets[player]
            elif player_val < 0:
                result = 'LOS'
                #we've already taken their money
            else:
                result = 'TIE'
                self.accounts[player_id] += self.bets[player]
            msg.append('{id_:<12},{result},{cash:0>10}'.format(
                id_=player_id,
                result=result,
                cash=self.accounts[player_id]))
        msg[-1] += ']'
        self.broadcast('|'.join(msg))

    def handle_insu(self, sock, amount):
        try:
            amount = int(amount)
        except:
            return self.scold(sock, "That's not a number!")
        if amount > self.bets[sock]/2:
            return self.scold(sock, "Amount must be an integer, no more than half your bet, and less than or equal to your cash.")
        player_id = self.clients[sock].id_
        if amount > self.accounts[player_id]:
            return self.scold(sock, "You don't have enough money to buy that much insurance")
        self.accounts[player_id] -= amount
        if len(self.hands['dealer'].cards) == 2 and self.hands['dealer'].value() == 21:
            #this is the amount we will pay that player in insurance
            self.insu[sock] = 3*amount
        else:
            self.insu[sock] = 0
        return True

    def process_messages(self, sock, allowed_types):
        try:
            self.clients[sock].mbuffer.update()
            message_queue = self.clients[sock].mbuffer.messages
            while len(message_queue) > 0 and sock in self.clients:
                m_type, mess_args = self.clients[sock].mbuffer.messages.popleft()
                if m_type in allowed_types:
                    try:
                        if self.m_handlers[m_type](sock, *mess_args):
                            self.forgive(sock)
                    except TypeError:
                        self.scold(sock, "Too many pipes!")
                    except Exception as e:
                        self.logger.error('tried to process message {}|{} and hit exception:\n{}'.format(m_type, mess_args, traceback.format_exc()))
                else:
                    self.scold(sock, 'Only {} are valid commands while state is {}'.format(allowed_types, self.state) +
                            ' You sent a "{}"'.format(m_type))
        except MessageBufferException:
            self.drop_client(sock, reason='here in process_messages. socket is closed')

        
    def handle_ante(self, sock, amount):
        try:
            amount = int(amount)
        except ValueError:
            return self.scold(sock, "amount must be an integer, at least {}, and less than or equal to your cash.".format(self.MIN_BET))
        if amount < self.MIN_BET or amount > self.accounts[self.clients[sock].id_]:
            return self.scold(sock, "amount must be an integer, at least {}, and less than or equal to your cash.".format(self.MIN_BET))

        self.bets[sock] = amount
        self.accounts[self.clients[sock].id_] -= amount
        #take the money right away. pay up if they win.
        return True

    def serve(self):
        while True:
            self.wait_for_players()
            self.game_in_progress = True
            self.get_antes()
            if self.game_in_progress:
                self.deal()
            if self.game_in_progress:
                self.play_out_turns()
            if self.game_in_progress:
                self.payout()
            if self.game_in_progress:
                self.drop_game()

    def remove_from_game(self,player):
        self.logger.debug('moving player {} from game to lobby'.format(
            self.clients[player].id_))
        for d in [self.occupied_seats, self.bets, self.hands, self.insu, self.results]:
            if player in d:
                del d[player]
        self.broadcast('[join|{id_}|{timeout}|{cash}|0]'.format(
                id_=self.clients[player].id_,
                timeout=self.timeout,
                cash=self.accounts[self.clients[player].id_]))

    def forgive(self, player):
        self.clients[player].strikes = 0

    def drop_game(self):
        self.game_in_progress = False
        self.logger.info('starting a new game...')
        self.bets = {}
        self.hands = {}
        self.insu = {}
        self.results = defaultdict(lambda : 0)
        self.split_store = False
        for player in self.occupied_seats:
            if self.accounts[self.clients[player].id_] < self.MIN_BET:
                #this player can't afford to play, but they could still watch
                self.remove_from_game(player)

        while len(self.occupied_seats) < self.MAX_PLAYERS and len(self.lobby) > 0:
            new_player = self.lobby.popleft()
            if self.accounts[self.clients[new_player].id_] < self.MIN_BET:
                #This player can't afford to play, but they could still watch.
                continue
            seat_num = self.empty_seat()
            self.occupied_seats[new_player] = seat_num
            self.broadcast('[join|{id_}|{timeout}|{cash}|{seat_num}]'.format(
                id_=self.clients[new_player].id_,
                timeout=self.timeout,
                cash=self.accounts[self.clients[new_player].id_],
                seat_num=seat_num))
            
    def scold(self, sock, reason, fatal=False):
        try:
            self.clients[sock].strikes += 1
            msg = '[errr|{strike}|{reason}]'.format(
                strike=self.clients[sock].strikes,
                reason=reason.translate(escape_chars))
            self.logger.debug('sending {} (fatal error)'.format(msg))
            sock.sendall(msg)
            if self.clients[sock].strikes >= self.MAX_STRIKES:
                self.drop_client(sock, reason='too many strikes')
            elif fatal:
                self.drop_client(sock,reason='fatal error "{}"'.format(reason))
        except Exception as e:
            self.logger.debug(traceback.format_exc())
            self.drop_client(sock, reason='here in scold, sock appears to be closed')
        finally:
            return False
 
if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='A server for the CSCI 367 network blackjack game')
    parser.add_argument(
            '-p','--port',
            default=36709,
            type=int,
            help='the port where the server is listening',
            metavar='port',
            dest='port')
    parser.add_argument(
            '-t','--timeout',
            default=2,
            type=int,
            help='the timeout we wait to allow a client to act',
            metavar='timeout_secs',
            dest='timeout')
    parser.add_argument(
            '-j', '--join-wait',
            default=2,
            type=int,
            help='the time to wait for joins before starting a game',
            metavar='join_wait_secs',
            dest='join_wait')
    parser.add_argument(
            '-m', '--max-connections',
            default=None,
            help='Maximum number of TCP connections to maintain',
            metavar='num_connections',
            dest='max_tcp')

    args = vars(parser.parse_args())
    while True:
        try:
            b= BlackjackServer(**args)
            b.serve()
        except:
            b.logger.fatal(traceback.format_exc())
        
