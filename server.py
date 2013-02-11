#!/usr/bin/env python
import socket as s
from select import select
from helpers import MessageBuffer
from collections import deque
import signal
host = ''
port = 36799 #look this up

m_handlers = {}
names = {}


def handle_join(client, _id):
    client.sendall('[CONN|{timeout}|{location}|{cash:0>10}]'.format(
        timeout=30,
        location='LBBY',
        cash=1000))
    names[client] = _id

def handle_chat(client, text):
    print('inside handle_chat! id={}, text={}'.format(names[client],text))
    if client in names: 
        for out in names:
            out.sendall('[CHAT|{_id}|{text}]'.format(
                _id=names[client],
                text=text))
    else:
        client.sendall('[ERRR|{strike}|{reason}]'.format(
            strike=1,
            reason='You must send a JOIN before you can do anything else'))

m_handlers['JOIN'] = handle_join
m_handlers['CHAT'] = handle_chat

def sighandler(signum, frame):
    print('Shutting down server...')
    for out in names:
        out.close()

def main():
    signal.signal(signal.SIGINT, sighandler)
    server = s.socket(s.AF_INET, s.SOCK_STREAM)
    server.bind((host,port))
    server.listen(5) #what is this?

    watched_socks = [server] 
    
    buffers = {}

    while True:
        print 'watching {} clients'.format(len(watched_socks) - 1)
        try:
            inputready, _, _ = select(watched_socks, [], []) 
        except Exception as e:
            print e
            break
        #omitting timeout means select will block until input arrives
        for sock in inputready:
            if sock == server:
                client, address = server.accept()
                watched_socks.append(client)
                buffers[client] = MessageBuffer(client)
            else: #it's a client
                try:
                    buffers[sock].update()
                    while len(buffers[sock].messages) > 0:
                        m_type, mess_args = buffers[sock].messages.popleft()
                        m_handlers[m_type](sock, *mess_args)
                except Exception as e:
                    print e
                    print 'deleting {}'.format(names[sock])
                    del names[sock]
                    del buffers[sock]

if __name__ == '__main__':
    main()
