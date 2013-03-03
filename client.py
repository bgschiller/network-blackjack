#!/usr/bin/env python
import socket as s
from utils import MessageBuffer, ChatHandler, BlackjackHand, BlackjackPlayer
from client_ui import ConsoleUI
from select import select
from collections import defaultdict
import sys
import signal
import argparse
import logging

class BlackjackClient(object):

    MAX_PLAYERS = 6

    def __init__(self, host='', port=36709, name=None):
        
        self.host = host
        self.port = port
        self.ui = ConsoleUI(self.send_chat)

        if name is None:
            self.name = self.ui.get_player_name()
        else:
            self.name = name
            self.ui.name = name 


        self.m_handlers = defaultdict(lambda: self.handle_default)
        self.m_handlers['join'] = self.handle_join
        self.m_handlers['chat'] = self.ui.show_chat

        self.server = s.socket(s.AF_INET, s.SOCK_STREAM)
        
        self.watched_socks = [self.server]
        if self.ui.chat_at_stdin:
            self.watched_socks.append(sys.stdin)
        
        signal.signal(signal.SIGINT, self.exit)


        #logging stuff
        self.logger = logging.getLogger('blackjack')
        self.logger.setLevel(logging.DEBUG)

        # create file handler which logs even debug messages
        fh = logging.FileHandler('client.log')
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


        self.logger.info('about to make chat handler')
        c_handler = ChatHandler(self.server.sendall, self.name)
        c_handler.setLevel(logging.INFO)
        c_handler.setFormatter(formatter)
        self.logger.addHandler(c_handler)
        self.game_in_progress = False
        self.hands = False

    def process_messages(self, expected_types):
        self.s_buffer.update()
        while self.s_buffer.messages:
            m_type, mess_args = self.s_buffer.messages.popleft()
            if m_type in expected_types:
                self.m_handlers[m_type](*mess_args)
            else:
                self.logger.error('Unexpected message: {} with args {}'.format(m_type, mess_args))
                self.exit(ret_code=127)


    def exit(self,signum=None, frame=None, ret_code=0):
        self.server.sendall('[exit]')
        exit(ret_code)
    def handle_default(self, *args):
        self.logger.error('uknown message, args: {}'.format(args))

    def handle_join(self, id, timeout,location,cash, seat_number):
        self.timeout = timeout
        self.location = location
        self.cash = cash
        self.ui.new_join(id, timeout, location, cash, seat_number)

    def handle_ante(self, min_bet):
        self.game_in_progress = True
        ante = self.ui.get_ante(min_bet)
        self.server.sendall('[ante|{:0>10}]'.format(ante))

    def handle_deal(self, dealer_card, shuf, *player_info):
        self.players = {}
        self.seat_to_name = []
        self.players['SERVER      '] = BlackjackPlayer(
                id = 'SERVER      ', 
                cards = [dealer_card], 
                cash = None, 
                seat = self.MAX_PLAYERS + 1)
        for info in player_info:
            if info:
                id_, cash, card1, card2 = info.split(',')
                self.players[id_] = BlackjackPlayer(
                        id=id_,
                        cards = [card1,card2],
                        cash = int(cash),
                        seat = ix)
                self.seat_to_name.append(id_)
        self.ui.deal(shuf, self.players, self.seat_to_name)
    def send_chat(self, chat_line):
        '''callback function for ui'''
        self.server.sendall('[chat|{text}]'.format(
            text=chat_line.strip('[]|')))

    def join(self):
        self.server.connect((self.host,self.port))
        self.server.sendall('[join|{_id:<12}]'.format(_id=self.name))
        self.s_buffer=MessageBuffer(self.server)

    def wait_for_ante(self):
        while not self.game_in_progress:
            input_socks, _, _ = select(self.watched_socks, [], [])
            for stream in input_socks:
                if stream == self.server:
                    self.process_messages(['chat','exit','join','ante'])
                else:
                    self.ui.send_chat()

    def wait_for_deal(self):
        while not self.hands:
            input_socks, _, _ = select(self.watched_socks, [], [])
            for stream in input_socks:
                if stream == self.server:
                    self.process_messages(['chat','exit','join','deal'])
                else:
                    self.ui.send_chat()

    def main(self):
        self.join()
        self.wait_for_ante()
        self.wait_for_deal()
        while True:
            input_socks, _, _ = select(self.watched_socks,[],[])
            for stream in input_socks:
                if stream == self.server:
                    self.s_buffer.update()
                else: #line from stdin indicates a chat message
                    self.ui.send_chat()
            while self.s_buffer.messages:
                m_type, mess_args = self.s_buffer.messages.popleft()
                self.m_handlers[m_type](*mess_args)

if __name__=='__main__':
    parser = argparse.ArgumentParser(
        description='A client for the CSCI 367 network blackjack game', 
        add_help=False)
    parser.add_argument(
            '-h','--host', 
            default='', 
            help='the host where the server resides', 
            metavar='host', 
            dest='host')
    parser.add_argument(
            '-p','--port',
            default=36709,
            type=int,
            help='the port where the server is listening',
            metavar='port',
            dest='port')
    parser.add_argument(
            '-n','--name',
            default=None,
            help='username to use',
            metavar='username',
            dest='name')
    try:
        args = vars(parser.parse_args())
    except:
        parser.print_help()
        exit(1) 
    BlackjackClient(**args).main()
