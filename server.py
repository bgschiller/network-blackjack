#!/usr/bin/env python
import socket as s
import traceback
from select import select
from helpers import MessageBuffer
from collections import deque, defaultdict
import signal
import sys
import argparse
import pickle

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
    def deal(self,n):
        return [self.cards.popleft() for x in range(n)]

class BlackjackHand(object):
    def __init__(self, cards):
        self.cards=cards
    def hit(self, card):
        self.cards += card

class BlackjackError(Exception):
    pass

class BlackjackGame(object):
    '''What if BlackjackGame keeps a list of valid actions, 
    and maybe also has a 'apply' method, than changes state
    to reflect to occurence of an 'action'. An action might be
    (1,'hit'), or (4,'doubledown'), a (seatnum,actionname) pair.
    Or maybe we provide an is_valid function? That would have to be 
    modified with local variables all the time...
    OR, we could keep a defaultdict so that valid[playerno][action] held the
    truth value of is_valid.'''

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
    def add_player(self, id_, cash):
        '''Add a player to the game, unless one is running
        returns (like all BlackjackGame methods) a tuple of msg-to-send and the next timeout in seconds'''
        if not self.state in ['waiting for players','waiting to start game']:
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
        return self.player_turn()

    def player_turn(self):
        if self.hands[self.whose_turn].has_blackjack():
            self.whose_turn += 1
            return (None, 0) # a timeout of 0 returns right away. 
            #Then the server will call player_turn again
        msg = '[turn|{}]'.format(self.players[self.whose_turn][0])
        #Sorry for the confusing on_timeout. The idea is that if we haven't
        # heard a turn msg from a player before the bell rings, we should drop them.
        self.on_timeout = lambda : self.drop_player(self.whose_turn)
        self.timer = datetime.now() + timedelta(seconds=self.timeout)
        return (msg, self.timeout)

    def player_action(self,id_):
        '''process a [turn|action] message, changing the internal state 
        queue up a stat message,
        set timeout'''

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
        self.game = BlackjackGame()

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
        with open('blackjack_accounts','w') as account_f:
            #we have to cast to dict because defaultdict cannot be pickled.
            pickle.dump(dict(self.accounts),account_f)
        exit(0)

    def serve(self):
        while True:
            print 'watching {} clients'.format(len(self.watched_socks) - 1)
            timeout = self.timeout if self.game.time_sensitive() else None
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
