#!/usr/bin/env python
import socket as s
from helpers import MessageBuffer
from select import select
import sys

host = ''
port = 36799

m_handlers = {}

def handle_chat(id_, text):
    print('{id_}> {text}'.format(
            id_=id_,
            text=text))

def handle_conn(timeout,location,cash):
    print('Connection established!')
    print('{} {} {}'.format(timeout,location,cash))

m_handlers['CONN'] = handle_conn
m_handlers['CHAT'] = handle_chat

server = s.socket(s.AF_INET, s.SOCK_STREAM)
server.connect((host,port))

name = raw_input('What is your name?')
name = name.strip('[]|, ')
name = name if len(name) < 12 else name[:12]
server.sendall('[JOIN|{_id:<12}]'.format(_id=name))
s_buffer=MessageBuffer(server)

while True:
    input_socks, _, _ = select([server, sys.stdin],[],[])
    for stream in input_socks:
        if stream == server:
            s_buffer.update()
        else:#line from stdin
            chat_line = sys.stdin.readline()
            server.sendall('[CHAT|{text}]'.format(
                text=chat_line.strip('[]|')))
    while s_buffer.messages:
        m_type, mess_args = s_buffer.messages.popleft()
        m_handlers[m_type](*mess_args)


