import pexpect
import sys
import random
import argparse
import os
class bcolors(object):
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'

    def disable(self):
        self.HEADER = ''
        self.OKBLUE = ''
        self.OKGREEN = ''
        self.WARNING = ''
        self.FAIL = ''
        self.ENDC = ''

def is_server_running(host,port):
    '''Try to connect to the server, send a join and expect a conn'''
    try:
        client = pexpect.spawn('telnet {} {}'.format(host,port),
                logfile=sys.stdout)
        # setting logfile to sys.stdout prints the IO for the child process to the screen
        client.sendline('[join|tom         ]')
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
        client.sendline('[join|Brian       ]')
        client.expect('join')
        client.expect('ante')
        client.sendline('[ante|0000000008]')
        client.expect('deal')
        client.expect('turn\|Brian')
        client.sendline('[exit]')
        client.kill(9)
        return True
    except (pexpect.TIMEOUT, pexpect.EOF):
        return False

def resilient_server(host, port):
    '''Sends a bunch of junk across the wire. Test passes if the server closes this socket and remains available for other connections'''
    client = pexpect.spawn('telnet {} {}'.format(host,port), logfile=sys.stdout)
    while client.isalive():
        random_string = os.urandom(45).strip('\x1d') 
        #\x1d is Ctrl-], the escape character for telnet
        client.sendline(random_string)
    return is_server_running(host,port)

tests = [is_server_running, simple_test, resilient_server]
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
        print bcolors.OKBLUE + 'running test "{}"'.format(test.__name__)
        print test.__doc__ + bcolors.ENDC
        if test(args['host'],args['port']):
            print bcolors.OKGREEN + 'test passed' + bcolors.ENDC
        else:
            print bcolors.FAIL + 'test failed' + bcolors.ENDC
            if args['rigor'] == 'tough':
                break

if __name__ == '__main__':
    main()
