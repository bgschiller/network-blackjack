#!/usr/bin/env python
import socket as s
import traceback
from select import select
from utils import MessageBuffer, MessageBufferException, ChatHandler, BlackjackDeck, BlackjackHand, BlackjackError, escape_chars
from collections import deque, defaultdict
from time import time
import signal
import sys
import argparse
import json
import logging


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
        #a dumb client who never manages to get out of the lobby queue,
        #but receives all the messages that the clients do.


        #logging stuff
        self.logger = logging.getLogger('blackjack')
        self.logger.setLevel(logging.DEBUG)

        # create file handler which logs even debug messages
        fh = logging.FileHandler('server.log')
        fh.setLevel(logging.DEBUG)
        # create console handler with a higher log level
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        # create formatter and add it to the handlers
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        fh.setFormatter(formatter)
        ch.setFormatter(formatter)
        # add the handlers to the logger
        self.logger.addHandler(fh)
        self.logger.addHandler(ch)


        c_handler = ChatHandler(self.broadcast, 'SERVER')
        c_handler.setLevel(logging.INFO)
        c_handler.setFormatter(formatter)
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
        self.bets = {}
        self.occupied_seats = {}
        self.hands = {}
        self.insu = {}
        self.deck = BlackjackDeck()
        self.lobby = deque()
        self.state='waiting to start game'
        self.game_in_progress = False

    def broadcast(self, msg):
        for client in self.clients.keys():
            try:
                client.sendall(msg)
            except Exception as e:
                self.logger.debug(traceback.format_exc())
                self.drop_client(client)

    def empty_seat(self):
        return min(set(range(1,self.MAX_PLAYERS + 1)).difference(
            {seat for sock,seat in self.occupied_seats.iteritems() }))

    def handle_join(self, sock, id_):
        #split this to a handle_join, midgame, and a handle_join
        self.clients[sock].id_ = id_
        self.accounts[id_] = self.accounts.get(id_, 1000) #default to 1000
        if not self.game_in_progress and len(self.occupied_seats) < 6:
            location = 'tabl'
            empty_seat = self.empty_seat()
            self.occupied_seats[sock] = empty_seat
        else:
            location = 'lbby'
            self.lobby.append(sock)
        try:
            self.broadcast('[join|{id_}|{timeout}|{location}|{cash:0>10}|{seat}]'.format(
                id_=id_,
                timeout=self.timeout,
                location=location,
                cash=self.accounts[id_],
                seat=0 if sock not in self.occupied_seats else self.occupied_seats[sock]))
        except Exception as e:
            self.logger.debug(traceback.format_exc())
            self.drop_client(sock)

    def handle_chat(self, sock, text):
        if self.clients[sock]: 
            self.broadcast('[chat|{id_}|{text}]'.format(
                id_=self.clients[sock].id_,
                text=text))
        else: #clients must tell us their name before they can chat
            self.scold(sock,reason='You must send a JOIN before you can do anything else')
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
            #we have to cast to dict because defaultdict cannot be pickled.
            json.dump(self.accounts,account_f)
        exit(0)

    def accept_client(self):
        client, address = self.server.accept()
        self.watched_socks.append(client)
        self.clients[client] = Client(client)
        self.logger.debug('accepted client with sock {}'.format(client))

    def wait_for_players(self):
        print('waiting for clients to join...')
        while not self.occupied_seats:
            inputready, _, _ = select(self.watched_socks, [], [])
            for sock in inputready:
                if sock == self.server:
                    self.accept_client()
                elif sock in self.lobby or sock in self.occupied_seats:
                    self.process_message(sock, allowed_types=['chat','exit'])
                else:
                    self.process_message(sock, allowed_types=['join'])
        print('waiting for more players...')
        start = time()
        while time() - start < self.join_wait and self.occupied_seats and len(self.occupied_seats) < self.MAX_PLAYERS:
            this_timeout = max(self.join_wait - (time() - start), 0) 
            inputready, _, _ = select(self.watched_socks, [], [], this_timeout)
            for sock in inputready:
                if sock == self.server:
                    self.accept_client()
                elif sock in self.occupied_seats:
                    self.process_message(sock, allowed_types=['chat','exit'])
                else:
                    self.process_message(sock, allowed_types=['join'])

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
                    self.process_message(sock,['chat','exit','ante'])
                else:
                    self.process_message(sock,['join','chat','exit'])
        for no_ante_player in (set(self.occupied_seats.keys()) - set(self.bets.keys())):
            self.drop_client(no_ante_player)

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
        if self.hands['dealer'].cards[0][0] == 'A': #dealer has ace showing
            self.wait_for_insurance()
           
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
                    self.process_message(sock,['chat','exit','insu'])
                else:
                    self.process_message(sock,['join','chat','exit'])
        for no_insu_player in (set(self.occupied_seats.keys()) - set(self.insu.keys())):
            self.drop_client(no_insu_player, 'timeout waiting for insu')

    def play_out_turns(self):
        if not self.occupied_seats:
            return self.drop_game()
        self.player_done = False
        for player in sorted(self.occupied_seats, key=lambda p: self.occupied_seats[p]):
            self.broadcast('[turn|{:<12}]'.format(self.clients[player].id_))
            self.split_store = False
            while not self.player_done and player in self.occupied_seats:
                start = time()
                self.player_moved = False
                while time() - start < self.timeout and not self.player_moved and player in self.occupied_seats:
                    this_timeout = max(self.timeout - (time() - start), 0)
                    inputready, _, _ = select(self.watched_socks, [], [], this_timeout)
                    for sock in inputready:
                        if sock == self.server:
                            self.accept_client()
                        elif sock == player:
                            self.process_message(player,['chat','exit','turn'])
                        else:
                            self.process_message(sock, ['join','chat','exit'])
                if not self.player_moved:
                    self.drop_client(player, 'timeout waiting for turn')

    def handle_turn(self,sock,action):
        action_handlers = {
                'hitt':self.action_hitt,
                'stay':self.action_stay,
                'down':self.action_down,
                'splt':self.action_split
            }
        self.player_moved = True
        action_handlers[action](sock)
        #note: we can't settle the accounts because we haven't learned the dealer's bet

    def action_hitt(self,player):
        new_card = self.deck.deal(1)[0]
        player_id = self.clients[player].id_

        self.hands[player].cards.append(new_card)
        
        hand_value = self.hands[player].value()
        if hand_value >= 21:
            self.player_done = True
        
        msg = '[stat|{id_}|hitt|{card}|{bust}|{bet}]'.format(
                id_=player_id,
                card=new_card,
                bust = 'busty' if hand_value > 21 else 'bustn',
                bet = self.bets[player])
        self.broadcast(msg)
        
    def action_stay(self,player):
        self.player_done = True
        self.player_moved = True
        msg = '[stat|{id_}|stay|xx|bustn|{bet}]'.format(
                id_=self.clients[player].id_,
                bet=self.bets[player])
        self.broadcast(msg)

    def action_down(self,player):
        self.player_moved = True
        if len(self.hands[player].cards) > 2:
            return self.scold(player, 'You may only double down on your first turn')
        player_id = self.clients[player].id_
        if self.accounts[player_id] < self.bets[player]:
            return self.scold(player, "You don't have enough money to double down!")

        self.player_done = True
        new_card = self.deck.deal(1)[0]
        self.hands[player].cards += new_card
        self.accounts[player_id] -= self.bets[player]
        self.bets[player] *= 2
        
        msg = '[down|{id_}|down|{card}|{bust}|{bet}]'.format(
                id_=player_id,
                card=new_card,
                bust= 'busty' if self.hands[player].value() > 21 else 'bustn',
                bet=self.bets[player])
        self.broadcast(msg)

    def action_split(self,player):
        raise BlackjackError('Cannot handle splits!')

    def payout(self):
        msg = ['[endg']
        dealer_val = self.hands['dealer'].value()
        for seat_num in range(1,self.MAX_PLAYERS):
            seated_player = [sock for sock,seat in self.occupied_seats.iteritems() if seat == seat_num]
            if seated_player == []:
                msg.append('')
                continue
            player = seated_player[0]
            player_val = self.hands[player].value()
            player_id = self.clients[player].id_
            if player_val > dealer_val:
                result = 'WON'
                self.accounts[player_id] += 2*self.bets[player]
            elif player_val < dealer_val:
                result = 'LOS'
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
        amount = int(amount)
        if amount > self.bets[sock]/2:
            self.scold(sock, 'Insurance must be no more than half your bet, rounded down. '
                    + 'You bet ${} and asked for ${} insurance'.format(
                        self.bets[sock], amount))
            return
        self.insu[sock] = amount

    def process_message(self, sock, allowed_types):
        try:
            self.clients[sock].mbuffer.update()
            message_queue = self.clients[sock].mbuffer.messages
            while len(message_queue) > 0:
                m_type, mess_args = self.clients[sock].mbuffer.messages.popleft()
                if m_type in allowed_types:
                    try:
                        self.m_handlers[m_type](sock, *mess_args)
                        if sock in self.clients:
                            self.clients[sock].strikes = 0  #all sins are forgiven
                    except Exception as e:
                        self.logger.error('tried to process message {}|{} and hit exception:\n{}'.format(m_type, mess_args, traceback.format_exc()))
                else:
                    self.scold(sock, 'Only {} are valid commands while state is {}'.format(allowed_types, self.state) +
                            'You sent a "{}"'.format(m_type))
        except MessageBufferException:
            self.drop_client(sock, reason='socket is closed')

        
    def handle_ante(self, sock, amount):
        amount = int(amount)
        if amount < self.MIN_BET:
            self.scold(sock, 'The minimum ante is {}. You gave {}'.format(
                self.MIN_BET, amount))
        self.bets[sock] = amount
        self.accounts[self.clients[sock].id_] -= amount
        #take the money right away. pay up if they win.

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

    def drop_game(self):
        self.game_in_progress = False
        self.logger.info('no more players! starting a new game...')
        self.bets = {}
        self.hands = {}
        self.insu = {}
        while len(self.occupied_seats) < self.MAX_PLAYERS and len(self.lobby) > 0:
            self.occupied_seats[self.lobby.popleft()] = self.empty_seat()
            
    def scold(self, sock, reason):
        try:
            self.clients[sock].strikes += 1
            sock.sendall('[errr|{strike}|{reason}]'.format(
                strike=self.clients[sock].strikes,
                reason=reason.translate(escape_chars)))
            if self.clients[sock].strikes >= self.MAX_STRIKES:
                self.drop_client(sock)
        except Exception as e:
            self.logger.debug(traceback.format_exc())
            self.drop_client(sock)
 
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
    BlackjackServer(**args).serve()
