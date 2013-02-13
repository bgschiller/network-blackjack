#!/usr/bin/env python
import socket as s
import traceback
from select import select
from helpers import MessageBuffer
from collections import deque, defaultdict
import signal
import sys

class Client(object):
    def __init__(self, sock):
        self.sock = sock
        self.mbuffer = MessageBuffer(sock)
        self.strikes = 0
        self.id_ = ''

    def __del__(self):
        del self.mbuffer


class BlackjackServer(object):
    def __init__(self):
        self.host = ''
        self.port = 36799 #look this up
        self.timeout = 30

        self.m_handlers = {} #CMND:func(client, *args) pairs
        self.clients = {} #sock:Client pairs
        
        self.m_handlers['join'] = self.handle_join
        self.m_handlers['chat'] = self.handle_chat
        self.m_handlers['exit'] = self.drop_client

        self.server = s.socket(s.AF_INET, s.SOCK_STREAM)
        self.server.bind((self.host,self.port))
        self.server.listen(5) #what is this?

        signal.signal(signal.SIGINT, self.sighandler)

        self.watched_socks = [self.server]

    def handle_join(self, sock, id_):
        try:
            sock.sendall('[conn|{timeout}|{location}|{cash:0>10}]'.format(
                timeout=self.timeout,
                location='lbby',
                cash=1000))
            self.clients[sock].id_ = id_
        except Exception as e:
            traceback.print_exc()
            self.drop_client(sock)

        self.clients[sock].id_ = id_

    def handle_chat(self, sock, text):
        if self.clients[sock]: #clients must tell us their name before they can chat
            clients = self.clients.keys() #we mustn't change self.clients during iteration!
            for client in clients:
                try:
                    client.sendall('[chat|{id_}|{text}]'.format(
                        id_=self.clients[sock].id_,
                        text=text))
                except Exception as e:
                    traceback.print_exc()
                    self.drop_client(sock)
        else:
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
        if sock in self.clients:
            print('dropping {}, id: {}'.format(sock, self.clients[sock].id_))
            del self.clients[sock]
        if sock in self.watched_socks:
            self.watched_socks.remove(sock)

    def sighandler(self, signum, frame):
        print('Shutting down server...')
        for client in self.clients:
            client.close()
        self.server.close()

    def serve(self):
        
        while True:
            print 'watching {} clients'.format(len(self.watched_socks) - 1)
            try:
                inputready, _, _ = select(self.watched_socks, [], []) 
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
    BlackjackServer().serve()
