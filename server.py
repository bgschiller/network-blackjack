#!/usr/bin/env python
import socket as s
import traceback
from select import select
from helpers import MessageBuffer
from collections import deque, defaultdict
import signal
import sys
import argparse

class Client(object):
    def __init__(self, sock):
        self.sock = sock
        self.mbuffer = MessageBuffer(sock)
        self.strikes = 0
        self.id_ = ''

    #def __del__(self):
    #    del self.mbuffer

class BlackjackDeck(object):
    def __init__(self):
        self.values = map(str, range(1,10)) + ['T','J','Q','K']
        self.suits = ['H','S','C','D']
        self.num_decks = 2
        self.shuffle()
    def shuffle(self):
        self.cards = deque(itertools.product(self.values, self.suits)) * self.num_decks
        random.shuffle(self.cards)
    def deal(self, n):
        return [self.cards.popleft() for x in range(n)]

class BlackjackHand(object):
    def __init__(self, cards):
        self.cards=cards
    def hit(self, card):
        self.cards += card

class BlackjackGame(object):
    '''What if BlackjackGame keeps a list of valid actions, 
    and maybe also has a 'apply' method, than changes state
    to reflect to occurence of an 'action'. An action might be
    (1,'hit'), or (4,'doubledown'), a (seatnum,actionname) pair.
    Or maybe we provide an is_valid function? That would have to be 
    modified with local variables all the time...
    OR, we could keep a defaultdict so that valid[playerno][action] held the
    truth value of is_valid.'''

    def __init__(self, players):
        self.players = players #seat num: (id,cash) pairs
        self.deck = BlackjackDeck()
        self.bets = {} #seat num:bet pairs
        self.cards = {} #seat num:BlackjackHand pairs
        self.whose_turn=0 #index into self.players

class BlackjackServer(object):
    def __init__(self, port=36709, timeout=30):
        self.host = ''
        self.port = port #look this up
        self.timeout = timeout

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

    def broadcast(self, msg):
        for client in self.clients.keys():
            try:
                client.sendall(msg)
            except Exception as e:
                traceback.print_exc()
                self.drop_client(client)

    def handle_join(self, sock, id_):
        if not self.game_in_progress() and len(self.players) < 6:
            location = 'tabl'
            self.players.append((sock, id_))
        else:
            location = 'lbby'
            self.waiting.append((sock, id_))
        try:
            sock.sendall('[conn|{timeout}|{location}|{cash:0>10}]'.format(
                timeout=self.timeout,
                location=location,
                cash=1000))
            self.clients[sock].id_ = id_
            self.any_players = True
        except Exception as e:
            traceback.print_exc()
            self.drop_client(sock)
            return

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
            if self.clients[sock].strikes >= 3:
                self.drop_client(sock)

    def drop_client(self, sock):
        save_id = self.clients[sock].id_
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
        exit(0)

    def serve(self):
        while True:
            print 'watching {} clients'.format(len(self.watched_socks) - 1)
            try:
                inputready, _, _ = select(self.watched_socks, [], [], None) 
            except Exception as e:
                traceback.print_exc()
                break
            #omitting timeout means select will block until input arrives
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

    BlackjackServer(**args).serve()
