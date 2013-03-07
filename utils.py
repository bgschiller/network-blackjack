from collections import deque
from string import maketrans
import itertools
import socket as s
import re
import logging
import random
import traceback

READSIZE = 512
MESS_RE = re.compile(r'\[.*?\]',re.MULTILINE) #maybe the flag is not needed?
MAX_LEN = 512

class colors(object):
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    YELLOW = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    DIM = '\033[90m'
    PURPLE = '\033[95m'

    def disable(self):
        self.HEADER = ''
        self.OKBLUE = ''
        self.OKGREEN = ''
        self.YELLOW = ''
        self.FAIL = ''
        self.ENDC = ''
        self.DIM = ''
        self.PURPLE = ''

#module-level constant exported to (at least) client, server
escape_chars = maketrans('|[]','!{}')

logger = logging.getLogger('blackjack.utils')
class MessageBufferException(Exception):
    pass

class MessageBuffer(object):
    def __init__(self, sock):
        self.messages = deque([])
        self._buffer = ''
        self.sock = sock

    def update(self):
        try:
            new_data = self.sock.recv(READSIZE)
        except:
            logger.error(traceback.format_exc())
            raise MessageBufferException('socket appears to be closed')
        logger.debug('just off the wire: "{}" (length of {})'.format(new_data, len(new_data)))
        if len(new_data) == 0 or new_data[0] == '\x04': #0x04 is EOT
            self.sock.close()
            raise MessageBufferException('here in MessageBuffer, we believe the socket is closed')
        new_data = new_data.translate(None,'\r\n\x04') #0x04 is EOT
        self._buffer += new_data
        new_messages = re.findall(MESS_RE, self._buffer)
        for message in new_messages:
            mess_args = message.translate(None,'[]').split('|')
            m_type, mess_args = mess_args[0], mess_args[1:]
            self.messages.append([m_type,mess_args])

        self._buffer = ''.join(itertools.dropwhile(lambda x: x != '[', 
                re.sub(MESS_RE, '', self._buffer)))
        if len(self._buffer) > MAX_LEN:
            self._buffer = '' #ignore messages longer than MAX_LEN
            raise MessageBufferException('This socket is sending waaay too much data.')


class ChatHandler(logging.Handler):
    def __init__(self, broadcast, name=None):
        logging.Handler.__init__(self)
        self.broadcast = broadcast
        self.name = name

    def emit(self, record):
        contents = self.format(record).translate(escape_chars)
        if self.name:
            self.broadcast('[chat|{:<12}|{}]'.format(self.name, contents))
        else:
            self.broadcast('[chat|{}]'.format(contents))

class BlackjackPlayer(object):
    def __init__(self, id, cards, cash, seat):
        self.id_ = id
        self.hand = BlackjackHand(cards)
        self.cash = cash
        self.seat = seat

class BlackjackDeck(object):
    def __init__(self):
        self.values = map(str, range(1,10)) + ['T','J','Q','K']
        self.suits = ['H','S','C','D']
        self.num_decks = 2
        self.shuffle()
    def shuffle(self):
        self.cards = deque( map(lambda tup: ''.join(tup) ,itertools.product(self.values, self.suits)) * self.num_decks )
        random.shuffle(self.cards)
    def deal(self,n):
        return [self.cards.popleft() for x in range(n)]

class BlackjackHand(object):
    def __init__(self, cards):
        self.cards=cards
    def value(self):
        val = 0
        ace_present = False
        for card in self.cards:
            if card[0] == '1':
                ace_present = True
            val += 10 if card[0] in ['T','J','Q','K'] else int(card[0])
        if ace_present and val + 10 <= 21:
            val += 10
        return val

class BlackjackError(Exception):
    pass

