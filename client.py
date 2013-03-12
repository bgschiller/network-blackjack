#!/usr/bin/env python
import socket as s
from utils import MessageBuffer, ChatHandler, BlackjackHand, BlackjackPlayer, escape_chars, colors, validate_name
from client_ui import ConsoleUI, AutoUI, IntelligentUI
from select import select
from collections import defaultdict
import sys
import signal
import argparse
import logging



class BlackjackClient(object):

    MAX_PLAYERS = 6

    def __init__(self, host='', port=36709, name=None, ui = ConsoleUI):
        
        self.host = host
        self.port = port
        self.ui = ui(self.send_chat)

        if name is None:
            self.name = validate_name(self.ui.get_player_name())
        else:
            self.name = validate_name(name)


        self.m_handlers = defaultdict(lambda: self.handle_default)
        self.m_handlers['join'] = self.handle_join
        self.m_handlers['chat'] = self.ui.show_chat
        self.m_handlers['ante'] = self.handle_ante
        self.m_handlers['deal'] = self.handle_deal
        self.m_handlers['turn'] = self.handle_turn
        self.m_handlers['stat'] = self.handle_stat
        self.m_handlers['endg'] = self.handle_endg
        self.all_messages = self.m_handlers.keys()
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
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        # create formatter and add it to the handlers
        format_style = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        formatter = logging.Formatter(colors.DIM + format_style + colors.ENDC)
        formatter_no_color = logging.Formatter(format_style)
        fh.setFormatter(formatter)
        ch.setFormatter(formatter)
        # add the handlers to the logger
        self.logger.addHandler(fh)
        self.logger.addHandler(ch)


        self.logger.info('about to make chat handler')
        c_handler = ChatHandler(self.server.sendall)
        c_handler.setLevel(logging.INFO)
        c_handler.setFormatter(formatter_no_color)
        self.logger.addHandler(c_handler)
        self.game_in_progress = False
        self.players = False
        self.location='lobby'

    def send(self, msg):
        self.logger.debug('sending out {}'.format(msg))
        self.server.sendall(msg)

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
        self.send('[exit]')
        exit(ret_code)
    def handle_default(self, *args):
        self.logger.error('uknown message, args: {}'.format(args))

    def handle_join(self, id, timeout,cash, seat_number):
        self.timeout = timeout
        self.cash = cash
        self.location = 'lobby' if seat_number==0 else 'table'
        self.ui.new_join(id, timeout, cash, seat_number)

    def handle_ante(self, min_bet):
        self.game_in_progress = True
        ante = self.ui.get_ante(min_bet)
        self.send('[ante|{:0>10}]'.format(ante))

    def handle_deal(self, dealer_card, shuf, *player_info):
        self.players = {}
        self.seat_to_name = [None]
        self.players['SERVER      '] = BlackjackPlayer(
                id = 'SERVER      ', 
                cards = [dealer_card], 
                cash = None, 
                seat = self.MAX_PLAYERS + 1)
        for ix, info in enumerate(player_info):
            if info:
                id_, cash, card1, card2 = info.split(',')
                self.logger.debug('adding "{}" to players'.format(id_))
                self.players[id_] = BlackjackPlayer(
                        id=id_,
                        cards = [card1,card2],
                        cash = int(cash),
                        seat = ix)
                self.seat_to_name.append(id_)
            else:
                self.seat_to_name.append(None)
        #this creates another reference to the same object
        #(changes made here will reflect in the ui)
        self.ui.players = self.players
        self.ui.seat_to_name = self.seat_to_name
        self.ui.deal(shuf)

    def handle_turn(self, name):
        if name == self.name:
            action = self.ui.get_turn_action()
            self.send('[turn|{}]'.format(action))
            #we need to do ALL the turns here
        else:
            self.ui.display_turn(name)

    def handle_stat(self, id, action, card, bust, bet):
        if action == 'splt':
            self.players[id].split_store = self.players[id].hand.cards[1]
            del self.players[id].hand.cards[1]
        if card != 'xx':
            self.players[id].hand.cards.append(card)
        self.ui.display_stat(id,action,card,bust,bet)
        if action in ['stay','down'] or self.players[id].hand.value() >= 21:
            #end of their turn, unless they split
            if self.players[id].split_store:
                self.players[id].hand.cards = [self.players[id].split_store]
                self.players[id].split_store = False


    def handle_endg(self, *player_info):
        for ix, info in enumerate(player_info):
            if info:
                id, result, cash = info.split(',')
                cash = int(cash)
                self.logger.debug('type of self.cash is {}'.format(type(self.players[id].cash)))
                #test how well we've been keeping track of 
                if self.players[id].cash != cash:
                    self.logger.warn('discrepancy in cash amounts! Server has {}. Client has {}...'.format(cash, self.players[id].cash))
                    self.players[id].cash = cash

            else:
                #delete the player locally
                if self.seat_to_name[ix + 1] is not None:
                    del self.players[self.seat_to_name[ix + 1]]
                self.seat_to_name[ix+1] = None
        self.ui.end_game(player_info)
        self.game_in_progress = False
            
    def drop_game(self):
        self.players = {}
        self.seat_to_name = []
        self.game_in_progress = False

    def send_chat(self, chat_line):
        '''callback function for ui'''
        self.server.sendall('[chat|{text}]'.format(
            text=chat_line.translate(escape_chars)))
    

    def join(self):
        self.server.connect((self.host,self.port))
        self.send('[join|{_id:<12}]'.format(_id=self.name))
        self.s_buffer=MessageBuffer(self.server)

    def wait_for_ante(self):
        self.logger.debug('top of wait_for_ante')
        while not self.game_in_progress:
            input_socks, _, _ = select(self.watched_socks, [], [])
            for stream in input_socks:
                if stream == self.server:
                    self.process_messages(['chat','exit','join','ante','deal'])
                else:
                    self.ui.send_chat()

    def wait_for_deal(self):
        self.logger.debug('top of wait_for_deal')
        while not self.players:
            input_socks, _, _ = select(self.watched_socks, [], [])
            for stream in input_socks:
                if stream == self.server:
                    self.process_messages(['chat','exit','join','deal','turn'])
                else:
                    self.ui.send_chat()
        if self.players['SERVER      '].hand.value() == 11:
            #we have to opportunity to buy insurance
            amount = self.ui.get_insurance()
            self.send('[insu|{:0>10}]'.format(amount))

    def play_out_turns(self):
        self.logger.debug('top of play_out_turns')
        while self.game_in_progress:
            input_socks, _, _ = select(self.watched_socks, [], [])
            for stream in input_socks:
                if stream == self.server:
                    self.process_messages(['chat','exit','join','turn','stat','endg'])
                else:
                    self.ui.send_chat()
        
    def wait_to_play(self):
        self.logger.debug('top of wait_to_play')
        while self.location == 'lobby':
            input_socks, _,_ = select(self.watched_socks, [], [])
            for stream in input_socks:
                if stream == self.server:
                    self.process_messages(self.all_messages)
                else:
                    self.ui.send_chat()

    def main(self):
        self.join()
        self.wait_to_play()
        self.logger.debug('game is starting!')
        while True:
            self.wait_for_ante()
            self.wait_for_deal()
            self.play_out_turns()
            self.drop_game()

if __name__=='__main__':
    parser = argparse.ArgumentParser(
        description='A client for the CSCI 367 network blackjack game')
    parser.add_argument(
            '-s','--server', 
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
    parser.add_argument(
            '-u','--ui',
            default='console',
            type=str,
            help='type of user interface. Options are "console" and "auto"',
            metavar='ui_type',
            dest='ui')
    ui_map = {
            'console':ConsoleUI,
            'auto':AutoUI,
            'intelligent':IntelligentUI
            }
    try:
        args = vars(parser.parse_args())
        args['ui'] = ui_map[args['ui']]
    except:
        exit(1) 
    BlackjackClient(**args).main()
