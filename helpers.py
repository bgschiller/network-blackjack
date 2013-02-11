from collections import deque
from itertools import dropwhile
import socket as s
import re

READSIZE = 1024
MESS_RE = re.compile(r'\[.*?\]',re.MULTILINE) #maybe the flag is not needed?
MAX_LEN = 1024

class MessageBuffer(object):
    def __init__(self, sock):
        self.messages = deque([])
        self._buffer = ''
        self.sock = sock

    def update(self):
        self._buffer += filter(lambda x: x != '\n', self.sock.recv(1024))
        new_messages = re.findall(MESS_RE, self._buffer)
        for message in new_messages:
            mess_args = message.strip('[]').split('|')
            m_type, mess_args = mess_args[0], mess_args[1:]
            self.messages.append([m_type,mess_args])

        self._buffer = ''.join(dropwhile(lambda x: x != '[', 
                re.sub(MESS_RE, '', self._buffer)))
        if len(self._buffer) > MAX_LEN:
            self._buffer = '' #ignore messages longer than MAX_LEN
