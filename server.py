#!/usr/bin/env python
import socket as s
import traceback
from select import select
from helpers import MessageBuffer, ChatHandler
from server_utils import BlackjackDeck,BlackjackHand, BlackjackError
from collections import deque, defaultdict
from datetime import datetime, timedelta
import signal
import sys
import argparse
import pickle
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
    def __init__(self, accounts, port=36709, timeout=30):
        self.host = ''
        self.port = port
        self.timeout = timeout
        self.accounts = accounts

        #logging stuff
        self.logger = logging.getLogger('blackjack')
        formatter = logging.Formatter('%(name)-12s: %(levelname)-8s %(message)s')

        #this is a hack to initialize ChatHandler
        #logging.handlers.ChatHandler = ChatHandler
        c_handler = ChatHandler(self.broadcast)
        c_handler.setLevel(logging.INFO)
        c_handler.setFormatter(formatter)
        self.logger.addHandler(c_handler)

        console = logging.StreamHandler()
        console.setLevel(logging.DEBUG)
        console.setFormatter(formatter)
        self.logger.addHandler(c_handler)

        f_handler = logging.FileHandler('server.log')
        f_handler.setLevel(logging.WARN)
        f_handler.setFormatter(formatter)
        self.logger.addHandler(f_handler)


        self.clients = {} #sock:Client pairs
        
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
        self.occupied_seats = {}
        self.lobby = deque()
        self.state='waiting to start game'

    def broadcast(self, msg):
        for client in self.clients.keys():
            try:
                client.sendall(msg)
            except Exception as e:
                traceback.print_exc()
                self.drop_client(client)

    def empty_seat(self):
        return min(set(range(1,self.MAX_PLAYERS + 1)).set_minus(
            {p.seat for s,p in self.occupied_seats.iter_items() }))

    def handle_join(self, sock, id_):
        #split this to a handle_join, midgame, and a handle_join
        if not self.game_in_progress() and len(self.occupied_seats) < 6:
            location = 'tabl'
            empty_seat = self.empty_seat()
            self.occupied_seats[sock]
        else:
            location = 'lbby'
            self.lobby.append((sock, id_))
        try:
            sock.sendall('[conn|{timeout}|{location}|{cash:0>10}]'.format(
                timeout=self.timeout,
                location=location,
                cash=self.accounts[id_]))
            self.clients[sock].id_ = id_
        except Exception as e:
            traceback.print_exc()
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
            self.logger.info('dropping {}, id: {} because: {}'.format(sock, self.clients[sock].id_, reason if reason is not None else '(no reason given)'))
            del self.clients[sock]
            self.broadcast('[exit|{id_}]'.format(id_=save_id))
        if sock in self.watched_socks:
            self.watched_socks.remove(sock)
        if sock in self.occupied_seats:
            del self.occupied_seats[sock]

    def sighandler(self, signum, frame):
        print('Shutting down server...')
        for client in self.clients:
            client.close()
        self.server.close()
        with open('blackjack_accounts','w') as account_f:
            #we have to cast to dict because defaultdict cannot be pickled.
            pickle.dump(dict(self.accounts),account_f)
        exit(0)

    def accept_client(self):
        client, address = self.server.accept()
        self.watched_socks.append(client)
        self.clients[client] = Client(client)

    def wait_for_players(self):
        print('waiting for clients to join...')
        while not self.occupied_seats:
            inputready, _, _ = select(self.watched_socks, [], [])
            for sock in inputready:
                if sock == self.server:
                    self.accept_client()
                else: #it's an existing client
                    self.clients[sock].mbuffer.update()
                    while len(self.clients[sock].mbuffer.messages) > 0:
                        m_type, mess_args = self.clients[sock].mbuffer.messages.popleft()
                        if m_type == 'join':
                            self.handle_join(sock, mess_args)
                        else:
                            self.scold(sock,
                                    'you must join before you may participate')
        print('waiting for more players...')
        start = time()
        while time() - start < self.timeout and len(self.occupied_seats) < self.MAX_PLAYERS:
            this_timeout = max(self.timeout - (time() - start), 0) 
            inputready, _, _ = select(self.watched_socks, [], [], this_timeout)
            for sock in inputready:
                if sock == self.server:
                    self.accept_client()
                else:
                    self.process_message(sock, 
                            allowed_types=['join','chat','exit'])
    def get_antes(self):
        if not self.occupied_seats:
            return self.drop_game()
        self.state = 'waiting for antes'
        self.broadcast('[ante|{:0>10}'.format(self.MIN_BET))
        start = time()
        while time() - start < self.timeout:
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

        self.hands['dealer'] = Blackjackhand(self.deck.deal(2))
        msg = ['[deal']
        msg.append(self.hands['dealer'].cards[0]) # only reveal one dealer card
        msg.append('shufy' if shuf else 'shufn')

        for seat_num in range(1,self.MAX_PLAYERS + 1):
            seated_player = [s for s,p in self.occupied_seats.iter_items() if p.seat == seat_num]
            if seated_player == []:
                msg.append('')
            else:
                player = seated_player[0]
                self.hands[player] = BlackjackHand(self.deck.deal(2))
                msg.append('{id_:<12},{cash:0>10},{cards[0]},{cards[1]}'.format(
                    id_=self.clients[player], 
                    cash=self.accounts[player],
                    cards=self.hands[player].cards))
        msg[-1] += ']' #closing brace to message
        self.broadcast('|'.join(msg))
        if self.hands['dealer'].cards[0][0] == 'A': #dealer has ace showing
            self.wait_for_insurance()
           
    def wait_for_insurance(self):
        self.state='waiting for insurace'
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
        for player in sorted(self.occupied_seats, key=lambda p: self.occupied_seats[p]):
            self.broadcast('[turn|{:<12}]'.format(self.clients[player].id_))
            self.split_store = False
            while player in self.occupied_seats and not self.player_done:
                start = time()
                self.player_moved = False
                while time() - start < self.timeout and not self.player_moved:
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

        self.hands[player].cards += new_card
        
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
            seated_player = [s for s,p in self.occupied_seats.iter_items() if p.seat == seat_num]
            if seated_player == []:
                msg.append('')
                continue
            player = seated_player[0]
            player_val = self.hands[player].value()
            if player_val > dealer_val:
                result = 'WON'
                self.accounts[player] += 2*self.bets[player]
            elif player_val < dealer_val:
                result = 'LOS'
            else:
                result = 'TIE'
                self.accounts[player] += self.bets[player]
            msg.append('{id_:<12},{result},{cash:0>10}'.format(
                id_=self.clients[player].id_,
                result=result,
                cash=self.accounts[player]))
        msg[-1] += ']'
        self.broadcast(msg)

    def handle_insu(self, sock, amount):
        amount = int(amount)
        if amount > self.bets[sock]/2:
            self.scold(sock, 'Insurance must be no more than half your bet, rounded down. '
                    + 'You bet ${} and asked for ${} insurance'.format(
                        self.bets[sock], amount))
            return
        self.insu[sock] = amount

    def process_message(self, sock, allowed_types):
        self.clients[sock].mbuffer.update()
        while len(self.clients[sock].mbuffer.messages) > 0:
            m_type, mess_args = self.clients[sock].mbuffer.messages.popleft()
            if m_type in allowed_types:
                try:
                    self.m_handlers[m_type](sock, *mess_args)
                except Exception as e:
                    self.logger.error('tried to process message {}|{} and hit exception:\n{}'.format(traceback.format_exc()))
            else:
                self.scold(sock, 'Only {} are valid commands while state is {}'.format(allowed_types, self.state) +
                        'You sent a "{}"'.format(m_type))

        
    def handle_ante(self, sock, amount):
        amount = int(amount)
        if amount < self.MIN_BET:
            self.scold(sock, 'The minimum ante is {}. You gave {}'.format(
                self.MIN_BET, amount))
        self.bets[sock] = amount
        self.accounts[sock] -= amount
        #take the money right away. pay up if they win.

    def serve(self):
        while True:
            self.wait_for_players()
            self.get_antes()
            self.deal()
            self.play_out_turns()
            self.payout()
            self.drop_game()

    def drop_game(self):
        self.logger.info('no more players! starting a new game...')
        self.bets = {}
        self.hands = {}
        while len(self.occupied_seats) < self.MAX_PLAYERS and len(self.lobby) > 0:
            self.occupied_seats[self.lobby.popleft()] = self.empty_seat()
            
    def scold(self, sock, reason):
        try:
            self.clients[sock].strikes += 1
            sock.sendall('[errr|{strike}|{reason}]'.format(
                strike=self.clients[sock].strikes,
                reason=reason))
            if self.clients[sock].strikes >= self.MAX_STRIKES:
                self.drop_client(sock)
        except Exception as e:
            traceback.print_exc()
            self.drop_client(sock)
 
if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='A server for the CSCI 367 network blackjack game', 
        add_help=False)
    parser.add_argument(
            '-p','--port',
            default=36709,
            type=int,
            help='the port where the server is listening',
            metavar='port',
            dest='port')
    parser.add_argument(
            '-t','--timeout',
            default=30,
            type=int,
            help='the timeout we wait to allow a client to act',
            metavar='timeout',
            dest='timeout')

    args = vars(parser.parse_args())
    accounts = defaultdict(lambda : 1000)
    try:
        with open('blackjack_accounts','r') as account_f:
            accounts.update(pickle.load(account_f))
    except IOError:
        pass
    args['accounts'] = accounts

    BlackjackServer(**args).serve()
