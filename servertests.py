#!/usr/bin/env python
import string
import pexpect
import sys
import random
import argparse
import os
from utils import colors

def is_server_running(host,port):
    '''Try to connect to the server, send a join and expect a conn'''
    try:
        client = pexpect.spawn('telnet {} {}'.format(host,port),
                logfile=sys.stdout)
        # setting logfile to sys.stdout prints the IO for the child process to the screen
        client.expect('Connected',timeout=2)
        client.sendline('[join|Brian       ]')
        client.expect('join')
        client.sendline('[exit]')
        client.kill(9)
        return True
    except (pexpect.TIMEOUT, pexpect.EOF):
        return False
def simple_test(host, port):
    '''Server should function properly up to the deal and first turn message, then exit.'''
    try:
        client = pexpect.spawn('telnet {} {}'.format(host,port),
                logfile=sys.stdout)
        client.expect('Connected',timeout=2)
        name = ''.join(random.sample(string.lowercase,12))
        client.sendline('[join|{}]'.format(name))
        client.expect('join')
        client.expect('ante')
        client.sendline('[ante|0000000100]')
        client.expect('deal')
        client.expect_exact('turn|{}'.format(name))
        client.sendline('[exit]')
        client.kill(9)
        return True
    except (pexpect.TIMEOUT, pexpect.EOF):
        return False

def resilient_server(host, port):
    '''Sends a bunch of junk across the wire. Test passes if the server closes this socket and remains available for other connections'''
    client = pexpect.spawn('telnet {} {}'.format(host,port))
    for i in range(20):
        random_string = os.urandom(45).strip('\x1d') 
        #\x1d is Ctrl-], the escape character for telnet
        try:
            client.sendline(random_string)
        except:
            pass
    return is_server_running(host,port)

def big_spender(host,port):
    '''Tries to make a $2000 bet, which should be too large'''
    try:
        client = pexpect.spawn('telnet {} {}'.format(host,port),
                logfile=sys.stdout)
        client.expect('Connected',timeout=2)
        name = ''.join(random.sample(string.lowercase, 12))
        client.sendline('[join|{}]'.format(name))
        client.expect('join')
        client.expect('ante')
        client.sendline('[ante|0000002000]')
        if client.expect(['errr','deal']) == 1:
            return False
        client.sendline('[exit]')
        return True
    except (pexpect.TIMEOUT, pexpect.EOF):
        return False

def long_winded(host,port):
    '''Client tries to send a chat that is too long.'''
    try:
        watson = pexpect.spawn('telnet {} {}'.format(host,port),
                logfile=sys.stdout)
        watson.expect('Connected',timeout=2)
        watson.sendline('[join|JohnWatson  ]')
        watson.expect('join')
        watson.sendline('[chat|' + '''When I glance over my notes and records of the Sherlock Holmes
        cases between the years '82 and '90, I am faced by so many which
        present strange and interesting features that it is no easy
        matter to know which to choose and which to leave. Some, however,
        have already gained publicity through the papers, and others have
        not offered a field for those peculiar qualities which my friend
        possessed in so high a degree, and which it is the object of
        these]''')
        watson.expect_exact('[errr|1|Chat message too long. Must be 450 characters or less.]',timeout=2)
        watson.sendline('[exit]')
        return True
    except (pexpect.TIMEOUT, pexpect.EOF):
        return False

def confused_player(host,port):
    '''This player doesn't know when it's their turn'''
    try:
        bob = pexpect.spawn('telnet {} {}'.format(host,port),
                logfile=sys.stdout)
        bob.expect('Connected',timeout=2)
        bob.sendline('[join|GrandpaBob   ]')
        bob.expect('join')
        bob.sendline('[turn|hitt]')
        bob.expect_exact("[errr|1|It's not your turn!]',timeout=2")
        bob.sendline('[exit]')
        return True
    except( pexpect.TIMEOUT, pexpect.EOF):
        return False

def big_spender2(host,port):
    '''Tries to make a $600 bet, then double down'''
    try:
        client = pexpect.spawn('telnet {} {}'.format(host,port),
                logfile=sys.stdout)
        client.expect('Connected',timeout=2)
        name = ''.join(random.sample(string.lowercase,12))
        client.sendline('[join|{}]'.format(name))
        client.expect('join')
        client.expect('ante')
        client.sendline('[ante|0000000600]')
        client.expect_exact('[turn|{}]'.format(name))
        client.sendline('[turn|down]')
        client.expect_exact("[errr|1|You don't have enough cash to double down.]",
                timeout=2)
        client.sendline('[exit]')
        return True
    except (pexpect.TIMEOUT, pexpect.EOF):
        return False


        

tests = [is_server_running, simple_test, resilient_server, big_spender,
        long_winded, confused_player, big_spender2]
def main():
    '''To run these tests, start your server running and pass along the host and port.'''
    parser = argparse.ArgumentParser(
            description='Test scripts for CSCI 367 network blackjack game')
    parser.add_argument('-p','--port',
            default=36709,
            type=int,
            help='the port where the server is listening',
            metavar='port',
            dest='port')
    parser.add_argument(
            '-s','--server',
            default='localhost',
            type=str,
            help='the host where the server is listening',
            metavar='host',
            dest='host')
    parser.add_argument(
            '-t','--tough',
            dest='rigor', action='store_const',
            const='tough', default='lenient',
            help='stop testing after any test fails')

    args = vars(parser.parse_args())
    
    for test in tests:
        print colors.OKBLUE + 'running test "{}"'.format(test.__name__)
        print test.__doc__ + colors.ENDC
        if test(args['host'],args['port']):
            print colors.OKGREEN + 'test passed' + colors.ENDC
        else:
            print colors.FAIL + 'test failed' + colors.ENDC
            if args['rigor'] == 'tough':
                break

if __name__ == '__main__':
    main()
