#!/usr/bin/env python
import socket as s
from helpers import MessageBuffer
from client_ui import ConsoleUI
from select import select
import sys

host = ''
port = 36799

m_handlers = {}

def handle_chat(id_, text):
    print('{id_}> {text}'.format(
            id_=id_.rstrip(),
            text=text))

def handle_conn(timeout,location,cash):
    print('Connection established!')
    print('{} {} {}'.format(timeout,location,cash))

m_handlers['conn'] = handle_conn
m_handlers['chat'] = handle_chat

def send_chat(chat_line):
    '''callback function for gui'''
    server.sendall('[chat|{text}]'.format(
        text=chat_line.strip('[]|')))

ui = ConsoleUI(send_chat)

server = s.socket(s.AF_INET, s.SOCK_STREAM)
server.connect((host,port))

name = ui.get_player_name()

server.sendall('[join|{_id:<12}]'.format(_id=name))
s_buffer=MessageBuffer(server)

watched_socks = [server]
if ui.chat_at_stdin:
    watched_socks.append(sys.stdin)

while True:
    input_socks, _, _ = select(watched_socks,[],[])
    for stream in input_socks:
        if stream == server:
            s_buffer.update()
        else: #line from stdin indicates a chat message
            ui.send_chat()
    while s_buffer.messages:
        m_type, mess_args = s_buffer.messages.popleft()
        m_handlers[m_type](*mess_args)


