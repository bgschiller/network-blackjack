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
            this_to = max(self.timeout - (time() - start), 0) 
            inputready, _, _ = select(self.watched_socks, [], [], this_to)
            if sock == self.server:
                self.accept_client()
            else:
                self.clients[sock].mbuffer.update()
                while len(self.clients[sock].mbuffer.messages) >0:
                    m_type, mess_args = self.clients[sock].mbuffer.messages.popleft()
                    if m_type in ['join','chat', 'exit']:
                        self.m_handlers[m_type](sock, *mess_args)
                    else:
                        self.scold(sock, 'Only join, chat, and exit are valid commands while we are waiting for players. ' +
                            'You sent a "{}"'.format(m_type))
    
    def serve(self):
        self.wait_for_players()

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
