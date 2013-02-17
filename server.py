#!/usr/bin/env python
import socket as s
import traceback
from select import select
from helpers import MessageBuffer
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

class BlackjackDeck(object):
    def __init__(self):
        self.values = map(str, range(1,10)) + ['T','J','Q','K']
        self.suits = ['H','S','C','D']
        self.num_decks = 2
        self.shuffle()
    def shuffle(self):
        self.cards = deque( list(itertools.product(self.values, self.suits)) * self.num_decks )
        random.shuffle(self.cards)
    def deal(self,n):
        return [self.cards.popleft() for x in range(n)]

class BlackjackHand(object):
    def __init__(self, cards):
        self.cards=cards
    def hit(self, card):
        self.cards += card
    def value(self):
        val = 0
        ace_present = False
        for card in self.cards:
            if card[0] == 'A':
                ace_present = True
            val += 10 if card[0] in ['T','J','Q','K'] else int(card[0])
        if ace_present and val + 10 <= 21:
            val += 10
        return val

class BlackjackError(Exception):
    pass

class BlackjackGame(object):
    '''So what I ended up doing is making an on_timeout callable attribute, 
    along with a timer attribute. All 'state' methods return a tuple of 
    (msg to send, next timeout in seconds, (player id,error), (player id,error), ...)
    They also check the timer at every call to see if they should actually run yet or if 
    the server only returned because of a chat message or something. 
    This is troublesome because that means they will ALWAYS wait until the timeout is up
    before running. A solution might be to have the server do some checking before it calls
    'on_timeout'. This would require the server to become time-aware, however.'''
    
    def __init__(self, timeout):
        self.MAX_PLAYERS = 6
        self.MIN_BET = 5
        self.players = {} #seat num: (id,cash) pairs
        self.deck = BlackjackDeck()
        self.bets = {} #seat num:bet pairs
        self.hands = {} #seat num:BlackjackHand pairs
        self.whose_turn=1 #index into self.players
        self.state = 'waiting for players'
        self.logger = logging.getLogger(__name__)
        self.timeout=timeout
        self.split_store = False
        self.on_timeout = False
        
    def add_player(self, id_, cash):
        '''Add a player to the game, unless one is running
        returns (like all BlackjackGame methods) a tuple of msg-to-send and the next timeout in seconds'''
        if self.in_progress():
            raise BlackjackError('A game is already in progress. Cannot add player {}'.format(id_))
        try:
            next_seat = min(set(range(1,self.MAX_PLAYERS + 1)) - set(self.players.keys()))
            self.players[next_seat] = (id_,cash)
            self.state = 'waiting to start game'
            if not self.timer:
                self.timer = datetime.now() + timedelta(seconds=timeout)
                self.on_timeout = self.get_bets
                return (None, self.timeout)
            else:
                return (None, (self.timer - datetime.now()).seconds)
        except ValueError as e: #we get a value error when we take min([])
            raise ValueError('The table is already full; cannot add another player')

    def ask_for_bets(self):
        '''ask to send an ante message, reset the timer'''
        if not self.players:
            return self.drop_game()
        if self.timer < datetime.now(): 
            #if we haven't reached a timeout yet, update the server on our wait time, then return
            return (None, (self.timer - datetime.now()).seconds)
        self.state = 'waiting for antes'
        msg = '[ante|{:0>}'.format(self.MIN_BET)
        self.timer = datetime.now() + timedelta(seconds=timeout)
        self.on_timeout = self.deal
        return (msg, self.timeout)        

    def deal(self, shuf=True):
        '''First check if everyone made a bet. If not, drop them
        Modify state to represent initial deal.
        return the deal msg for the server to pass to clients.
        Should also change the state'''
        if self.timer < datetime.now(): 
            #if we haven't reached a timeout yet, update the server on our wait time, then return
            return (None, (self.timer - datetime.now()).seconds)

        for non_compliant in (set(self.players.keys()) - set(self.bets.keys())):
            self.drop_player(non_compliant)
        if not self.players:
            return self.drop_game()

        if shuf: 
            self.deck.shuffle()

        self.hands['dealer'] = Blackjackhand(self.deck.deal(2))
        msg = ['[deal']
        msg.append(self.hands['dealer'].cards[0]) #only reveal one dealer card
        msg.append('shufy' if shuf else 'shufn')

        for seat_num in range(1,self.MAX_PLAYERS + 1):
            if seat_num in self.players:
                self.cards[seat_num] = BlackjackHand(self.deck.deal(2))
                msg.append('{player[0]:<12},{player[1]:0>10},{cards[0]},{cards[1]}'.format(player=self.players[seat_num], cards=self.hands[seat_num].cards))
            else:
                msg.append('')
        msg[-1] += ']' #closing brace to message
        self.whose_turn=1
        self.timer = datetime.now() + timedelta(seconds=self.timeout)
        if self.hands['dealer'].cards[0][0] == 'A': #dealer has ace showing
            self.state = 'waiting for insurance'
            self.on_timeout = self.ensure_insurance
            return ('|'.join(msg), self.timeout)
        self.on_timeout = self.player_turn
        return ('|'.join(msg), self.timeout)

    def ensure_insurance(self):
        if self.timer < datetime.now(): 
            #if we haven't reached a timeout yet, update the server on our wait time, then return
            return (None, (self.timer - datetime.now()).seconds)
        for non_compliant in (set(self.players.keys()) - set(self.bets.keys())):
            self.drop_player(non_compliant)
        if not self.players:
            return self.drop_game()
        self.state = 'playing out turns'
        return self.player_turn()

    def player_turn(self):
        if self.whose_turn > self.MAX_PLAYERS:
            return self.payout()
        if self.whose_turn not in self.players or self.hands[self.whose_turn].value() >= 21:
            self.whose_turn += 1
            return (None, 0) # a timeout of 0 returns right away,
            # so the server will call player_turn again
        msg = '[turn|{}]'.format(self.players[self.whose_turn][0])
        #Sorry for the confusing on_timeout. The idea is that if we haven't
        # heard a turn msg from a player before the bell rings, we should drop them.
        self.on_timeout = lambda : self.drop_player(self.whose_turn)
        self.timer = datetime.now() + timedelta(seconds=self.timeout)
        return (msg, self.timeout)

    def player_action(self,action):
        '''process a [turn|action] message, changing the internal state 
        queue up a stat message, set timeout to 0 and on_timeout to player_turn if it's the next player's turn, 
        set timeout to self.timeout if we're remaining on this player's turn.
        precondition: the turn message must have originated from the player whose turn it is.
        
        probably we want to refactor this into a function for each action'''
        msg = '[stat|{id_}|{action}|{card}|{bust}|{bet}]'
        params = {
                'id_':self.players[self.whose_turn][0],
                'bet':self.bets[self.whose_turn],
                'action':action
                }
        if action == 'hitt':
            new_card = self.deck.deal(1)[0]
            self.hands[self.whose_turn].cards += new_card
            params['card'] = new_card
            if self.hands[self.whose_turn].value() >= 21:
                if self.split_store:
                    raise BlackjackError('handle bust after split')
                else:
                    self.whose_turn += 1
                    self.on_timeout = self.player_turn
                    self.timer = datetime.now() # move onto next player right away
            else: #give the player another TIMEOUT secs before we drop them
                self.timer = datetime.now() + timedelta(seconds=self.timeout)
        elif action == 'stay':
            if self.split_store:
                raise BlackjackError('handle second hand after split')
            else:
                params['card'] = 'xx'
                self.whose_turn += 1
                self.timer = datetime.now() #move onto next player right away
                self.on_timeout = self.player_turn
        elif action == 'down':
            if len(self.hands[self.whose_turn].cards) > 2:
                #a player may only double down on their first move
                raise BlackjackError("I'm not prepared for that!")
            new_card = self.deck.deal(1)[0]
            self.hands[self.whose_turn].cards += new_card
            params['card'] = new_card
            params['bet'] *= 2
            self.bets[self.whose_turn] *= 2
            self.whose_turn += 1
            self.on_timeout = self.player_turn
            self.timer = datetime.now() # move on right away
        elif action == 'splt':
            if len(self.hands[self.whose_turn].cards) > 2 or self.split_store:
                raise BlackjackError('splits only allowed on first turns and only once')
            if self.hands[self.whose_turn].cards[0][0] != self.hands[self.whose_turn].cards[1][0]:
                raise BlackjackError('splits only allowed on cards of same value!')
            new_card = self.deck.deal(1)[0]
            params['card'] = new_card
            #save off second card
            self.split_store = self.hands[self.whose_turn].cards[1]
            self.hands[self.whose_turn].cards[1] = new_card
            self.timer = datetime.now() + timedelta(seconds=self.timeout)

        params['bust'] = 'busty' if self.hands[self.whose_turn].value() > 21 else 'bustn'
        return msg.format(**params)

    def payout(self):
        msg = ['[endg']
        dealer_val = self.hands['dealer'].value()
        for seat_num in range(1,self.MAX_PLAYERS):
            if seat_num not in self.players:
                msg.append('')
                continue
            id_, cash = self.players[seat_num]
            player_val = self.hands[seat_num].value()
            if player_val > dealer_val:
                result = 'WON'
                cash += self.bets[seat_num]
            elif player_val < dealer_val:
                result = 'LOS'
                cash -= self.bets[seat_num]
            else:
                result = 'TIE'
            self.players[seat_num] = (id_, cash)
            msg.append('{id_:<12},{result},{cash:0>10}'.format(
                id_, result, cash))
        msg[-1] += ']'
        raise BlackjackError("Make sure that the server reads off the values of cash")
        return '|'.join(msg)
    
    def in_progress(self):
        return self.state in ['waiting for players', 'waiting to start game']


    def drop_player(self, player):
        #remember that player_turn expects us to check and reset the timer here.
        raise BlackjackError("I'm not prepared for that! Only well-behaved clients for the time-being.")

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

    def serve(self):
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
                    except Exception as e:
                        traceback.print_exc()
                        self.drop_client(sock)
            if self.game.on_timeout:
                self.game.on_timeout()
    
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
