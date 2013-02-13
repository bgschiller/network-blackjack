import sys
     
class ConsoleUI(object):

    def __init__(self, send_chat_msg):
        '''send_chat_msg is a callback that takes a line of text and
        sends it through the server socket. (we need a callback because the GUI 
        will be triggered by a GUI event rather than a true file descriptor. 
        For the simple ConsoleUI, we have no events, so we need the client code
        to watch sys.stdin for us and then call send_chat. ugly.)'''
        self.chat_callback = send_chat_msg
        self.chat_at_stdin = True

    def show_chat(self, id_, text):
        print('{id_}> {text}'.format(
            id_=id_.rstrip(),
            text=text))

    def get_player_name(self):
        name = raw_input('What is your name? ').strip('[]|, \n')
        return name if len(name) <= 12 else name[:12]

    def send_chat(self):
        chat_line = sys.stdin.readline().strip('\r\n')
        self.chat_callback(chat_line)

