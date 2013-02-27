import pexpect
import sys
import random

client = pexpect.spawn('telnet localhost 36709',logfile=sys.stdout)
client.sendline('[join|Brian       ]')
client.expect('conn')
client.expect('ante')
client.sendline('[ante|0000000008]')
client.expect('deal')
client.sendline('[exit]')
client.expect('exit')
client.expect('Brian       ')
