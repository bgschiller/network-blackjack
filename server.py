#!/usr/bin/env python
import socket as s
import traceback
from select import select
from helpers import MessageBuffer
from server_utils import BlackjackGame
from collections import deque, defaultdict
from datetime import datetime, timedelta
import signal
import sys
import argparse
import pickle
import itertools
import random
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
        self.m_handlers = {} #CMND:func(client, *args) pairs
        self.clients = {} #sock:Client pairs
        
        self.m_handlers['join'] = self.handle_join
        self.m_handlers['chat'] = self.handle_chat
        self.m_handlers['exit'] = self.drop_client

        self.server = s.socket(s.AF_INET, s.SOCK_STREAM)
        self.server.setsockopt(s.SOL_SOCKET, s.SO_REUSEADDR, 1)
        self.server.bind((self.host,self.port))
        self.server.listen(5) #what is this?

        signal.signal(signal.SIGINT, self.sighandler)

        self.watched_socks = [self.server]
        self.players = []
        self.waiting = deque()
        self.state='waiting to start game'
        self.game = BlackjackGame(timeout)

    def broadcast(self, msg):
        for client in self.clients.keys():
            try:
                client.sendall(msg)
            except Exception as e:
                traceback.print_exc()
                self.drop_client(client)

    def handle_join(self, sock, id_):
        if not self.game.in_progress() and len(self.players) < 6:
            location = 'tabl'
            self.players.append((sock, id_))
            self.game.add_player(id_,self.accounts[id_])
        else:
            location = 'lbby'
            self.waiting.append((sock, id_))
        try:
            sock.sendall('[conn|{timeout}|{location}|{cash:0>10}]'.format(
                timeout=self.timeout,
                location=location,
                cash=self.accounts[id_]))
            self.clients[sock].id_ = id_
            self.any_players = True
        except Exception as e:
            traceback.print_exc()
            self.drop_client(sock)

    def handle_chat(self, sock, text):
        if self.clients[sock]: 
            self.broadcast('[chat|{id_}|{text}]'.format(
                id_=self.clients[sock].id_,
                text=text))
        else: #clients must tell us their name before they can chat
            self.clients[sock].strikes += 1
            try:
                client.sendall('[errr|{strike}|{reason}]'.format(
                    strike=self.clients[sock].strikes,
                    reason='You must send a JOIN before you can do anything else'))
            except Exception as e:
                traceback.print_exc()
                self.drop_client(sock)
            if self.clients[sock].strikes >= self.MAX_STRIKES:
                self.drop_client(sock)

    def handle_turn(self, sock, action):
        try:
            if self.clients[sock].id_ != self.game.players[self.game.whose_turn][0]:
                self.clients[sock].strikes += 1
                sock.sendall('[errr|{strike}|{reason}]'.format(
                    strike=self.clients[sock].strikes,
                    reason='Not your turn!'))
        except Exception as e:
            traceback.print_exc()
            self.drop_client(sock)
        if self.clients[sock].strikes >= self.MAX_STRIKES:
            self.drop_client(sock)
        stat_msg = self.game.player_action(action)

    def drop_client(self, sock):
        save_id = 'an unknown client' if not sock in self.clients else self.clients[sock].id_
        if sock in self.clients:
            print('dropping {}, id: {}'.format(sock, self.clients[sock].id_))
            del self.clients[sock]
            self.broadcast('[exit|{id_}]'.format(id_=save_id))
        if sock in self.watched_socks:
            self.watched_socks.remove(sock)

        if len(self.clients) == 0:
            self.any_players = False

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
        while not self.players:
            inputready, _, _ = select(self.watched_socks, [], [])
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
        while time() - start < self.timeout:
            this_timeout = max(self.timeout - (time() - start), 0) 
            inputready, _, _ = select(self.watched_socks, [], [], this_timeout)
            for sock in inputready:
                if sock == self.server:
                    self.accept_client()
                else:
                    self.process_message(sock, 
                            allowed_types=['join','chat','exit'])
    def get_antes(self):
        if not self.players:
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
                else:
                    self.process_message(sock,['join','chat','exit','ante'])
        for no_ante_player in (set(self.players.keys()) - set(self.bets.keys())):
            self.drop_player(no_ante_player)

    def deal(self, shuf=True):
        if not self.players:
            return self.drop_game()
        if shuf:
            self.deck.shuffle()

        self.hands['dealer'] = Blackjackhand(self.deck.deal(2))
        msg = ['[deal']
        msg.append(self.hands['dealer'].cards[0]) # only reveal one dealer card
        msg.append('shufy' if shuf else 'shufn')

        for seat_num in range(1,self.MAX_PLAYERS + 1):
            whose_seat = [s for s,p in self.players.iter_items() if p.seat == seat_num]
            if whose_seat == []:
                msg.append('')
            else:
                player = whose_seat[0]
                self.hands[player] = BlackjackHand(self.deck.deal(2))
                msg.append('{player.id_:<12},{player.cash:0>10},{cards[0]},{cards[1]}'format(player=self.players[player], cards=self.hands[player].cards))
        msg[-1] += ']' #closing brace to message
        self.broadcast('|'.join(msg))
        if self.hands['dealer'].cards[0][0] == 'A': #dealer has ace showing
            self.wait_for_insurance()
           
    def wait_for_insurance(self):
        self.state='waiting for insurace'
        start = time()
        while time() - start < self.timeout and len(self.insu) < len(self.players):
            this_timeout = max(self.timeout - (time() - start), 0)
            inputready, _, _ = select(self.watched_socks, [], [], this_timeout)
            for sock in inputready:
                if sock == self.server:
                    self.accept_client()
                else:
                    self.process_message(sock,['join','chat','exit','insu'])
        for no_insu_player in (set(self.players.keys()) - set(self.insu.keys())):
            self.drop_player(no_insu_player, 'timeout waiting for insu')

    def play_out_turns(self):
        for player in sorted(self.players, key=lambda p: self.players[p].seat_num):
            self.broadcast('[turn|{:<12}]'.format(self.clients[player].id_))
            self.split_store = False
            while player in self.players and not self.player_done:
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
                    self.drop_player(player, 'timeout waiting for turn')

    def handle_turn(self,sock,action):
        action_handlers = {
                'hitt':self.action_hitt,
                'stay':self.action_stay,
                'down':self.action_down,
                'splt':self.action_split
            }
        self.player_moved = True
        action_handlers[action](sock)

    def action_hitt(self,player):
        new_card = self.deck.deal(1)[0]
        player_id = self.clients[player].id_

        self.hands[player].cards += new_card

        if self.hands[player].value() >= 21:
            self.accounts[player_id] -= self.bets[player]
            self.player_done = True
        
        msg = '[stat|{id_}|hitt|{card}|{bust}|{bet}]'.format(
                id_=player_id,
                card=new_card,
                bust = 'busty' if self.hands[player].value() > 21 else 'bustn',
                bet = self.bets[player])
        self.broadcast(msg)
        

    def handle_insu(self, sock, amount):
        if sock not in self.players:
            self.scold(sock, "You're not a player!")
            return
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
                    logger.error('tried to process message {}|{} and hit exception:\n{}'.format(traceback.format_exc()))
            else:
                self.scold(sock 'Only {} are valid commands while state is {}'.format(allowed_types, self.state) +
                        'You sent a "{}"'.format(m_type))

        
    def handle_ante(self, sock, amount):
        if sock not in self.players:
            self.scold(sock, "You're not playing!")
            return
        amount = int(amount)
        if amount < self.MIN_BET:
            self.scold(sock, 'The minimum ante is {}. You gave {}'.format(
                self.MIN_BET, amount))
        self.bets[sock] = amount

    def serve(self):
        self.wait_for_players()
        self.get_antes()
        self.deal()

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
 

    def mainloop(self):
        timeout = None
        while True:
            print 'watching {} clients'.format(len(self.watched_socks) - 1)
            try:
                inputready, _, _ = select(self.watched_socks, [], [], timeout) 
            except Exception as e:
                traceback.print_exc()
                break
            for sock in inputready:
                if sock == self.server:
                    client, address = self.server.accept()
                    self.watched_socks.append(client)
                    self.clients[client] = Client(client)
                else: #it's an existing client
                    try:
                        self.clients[sock].mbuffer.update()
                        while len(self.clients[sock].mbuffer.messages) > 0:
                            m_type, mess_args = self.clients[sock].mbuffer.messages.popleft()
                            self.m_handlers[m_type](sock, *mess_args)
                            if self.game.trigger(
                                    self.clients[sock].id_, m_type, mess_args):
                                print 'ought to be handling {}'.format(
                                        self.game.on_trigger())
                    except Exception as e:
                        traceback.print_exc()
                        self.drop_client(sock)
            else: #if we returned because of a timeout
                print 'ought to be handling {}'.format(self.game.on_timeout())
    
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
