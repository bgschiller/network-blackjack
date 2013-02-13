#!/usr/bin/env python
import socket as s
from helpers import MessageBuffer
from client_ui import ConsoleUI
from select import select
import sys
import signal

class BlackjackClient(object):
    def __init__(self, host='', port=36799):
        self.host = host
        self.port = port

        self.ui = ConsoleUI(self.send_chat)

        self.m_handlers = {}
        self.m_handlers['conn'] = self.handle_conn
        self.m_handlers['chat'] = self.ui.show_chat

        self.server = s.socket(s.AF_INET, s.SOCK_STREAM)
        
        self.watched_socks = [self.server]
        if self.ui.chat_at_stdin:
            self.watched_socks.append(sys.stdin)
        
        signal.signal(signal.SIGINT, self.exit)

    def exit(self,signum, frame):
        self.server.sendall('[exit]')
        

    def handle_conn(self, timeout,location,cash):
        print('Connection established!')
        self.timeout = timeout
        self.location = location
        self.cash = cash
        print('{} {} {}'.format(timeout,location,cash))

    def send_chat(self, chat_line):
        '''callback function for ui'''
        self.server.sendall('[chat|{text}]'.format(
            text=chat_line.strip('[]|')))

    def join(self):
        self.server.connect((self.host,self.port))
        self.name = self.ui.get_player_name()
        self.server.sendall('[join|{_id:<12}]'.format(_id=self.name))
        self.s_buffer=MessageBuffer(self.server)

    def main(self):
        self.join()
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
    BlackjackClient().main()
