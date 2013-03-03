from collections import deque
from itertools import dropwhile
import socket as s
import re
import logging

READSIZE = 1024
MESS_RE = re.compile(r'\[.*?\]',re.MULTILINE) #maybe the flag is not needed?
MAX_LEN = 1024

logger = logging.getLogger('blackjack.helpers')
class MessageBufferException(Exception):
    pass

class MessageBuffer(object):
    def __init__(self, sock):
        self.messages = deque([])
        self._buffer = ''
        self.sock = sock

    def update(self):
        new_data = self.sock.recv(READSIZE)
        logger.debug('just off the wire: "{}" (length of {})'.format(new_data, len(new_data)))
        if len(new_data) == 0 or new_data[0] == '\x04': #0x04 is EOT
            self.sock.close()
            raise MessageBufferException('here in MessageBuffer, we believe the socket is closed')
        new_data = new_data.strip('\r\n\x04') #0x04 is EOT
        self._buffer += new_data
        new_messages = re.findall(MESS_RE, self._buffer)
        for message in new_messages:
            mess_args = message.strip('[]').split('|')
            m_type, mess_args = mess_args[0], mess_args[1:]
            self.messages.append([m_type,mess_args])

        self._buffer = ''.join(dropwhile(lambda x: x != '[', 
                re.sub(MESS_RE, '', self._buffer)))
        if len(self._buffer) > MAX_LEN:
            self._buffer = '' #ignore messages longer than MAX_LEN

class ChatHandler(logging.Handler):
    def __init__(self, broadcast, name):
        logging.Handler.__init__(self)
        self.broadcast = broadcast
        self.name = name

    def emit(self, record):
        self.broadcast('[chat|{:<12}|{}'.format(self.name, str(record).strip('[]|,')))


