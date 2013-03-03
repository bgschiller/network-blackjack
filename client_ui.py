import sys
     
class ConsoleUI(object):

    def __init__(self, send_chat_msg,name = None):
        '''send_chat_msg is a callback that takes a line of text and
        sends it through the server socket. (we need a callback because the GUI 
        will be triggered by a GUI event rather than a true file descriptor. 
        For the simple ConsoleUI, we have no events, so we need the client code
        to watch sys.stdin for us and then call send_chat. ugly.)'''
        self.chat_callback = send_chat_msg
        self.chat_at_stdin = True
        self.name = name

    def show_chat(self, id_, text):
        print('{id_}> {text}'.format(
            id_=id_.rstrip(),
            text=text))

    def get_player_name(self):
        name = raw_input('What is your name? ').strip('[]|, \n')
        self.name = name
        return name if len(name) <= 12 else name[:12]

    def send_chat(self):
        chat_line = sys.stdin.readline().strip('\r\n')
        self.chat_callback(chat_line)
    
    def new_join(id, timeout, location, cash, seat_number):
        print ('{} has joined the room. location: {}, cash: {} seat: {}'.format(id, location, cash, seat_number))

    def get_ante(self, min_bet):
        bet = 0
        while bet < min_bet:
            bet = int(raw_input('What is your bet? (min {})'.format(min_bet)))
            if bet < min_bet:
                print ('That bet is too small.')
        return bet

    def deal(self, shuf, players, seat_to_name):
        print('Cards are dealt: (dealer {} before this hand)'.format(
            'shuffled' if shuf == 'shufy' else 'did not shuffle'))
        print ('Dealer: {}'.format(players['SERVER      '].hand.cards))
        for name in seat_to_name:
            print('{name} (${cash}): {cards}'.format(
                name=name,
                cash=players[name].cash,
                cards=players[name].hand.cards))

