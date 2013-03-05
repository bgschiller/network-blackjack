import sys
from utils import escape_chars
     
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
        name = raw_input('What is your name? ').translate(None, '[]|,\n')
        self.name = name
        return name if len(name) <= 12 else name[:12]

    def send_chat(self):
        chat_line = sys.stdin.readline().strip('\r\n')
        self.chat_callback(chat_line)
    
    def new_join(self, id, timeout, location, cash, seat_number):
        print ('{} has joined the room. location: {}, cash: {} seat: {}'.format(id, location, cash, seat_number))

    def get_ante(self, min_bet):
        bet = 0
        min_bet = int(min_bet)
        while bet < min_bet:
            bet = int(raw_input('What is your bet? (min {})'.format(min_bet)))
            if bet < min_bet:
                print ('That bet is too small.')
        return bet

    def deal(self, shuf):
        print('Cards are dealt: (dealer {} before this hand)'.format(
            'shuffled' if shuf == 'shufy' else 'did not shuffle'))
        print ('Dealer: {}'.format(self.players['SERVER      '].hand.cards))
        for name in self.seat_to_name:
            if name is None: 
                continue
            print('{name} (${cash}): {cards}'.format(
                name=name,
                cash=self.players[name].cash,
                cards=self.players[name].hand.cards))
    def get_turn_action(self):
        valid_moves = ['hitt','stay','down','splt']
        print("It's your turn! choose one of {}".format(valid_moves))
        action = None
        while action not in valid_moves:
            action = raw_input()
            if not action in valid_moves:
                print("that's no good! choose one of {}".format(valid_moves))
        return action
    def display_turn(self, name):
        print("it's {}'s turn!".format(name.strip()))

    def display_stat(self, id, action, card, bust, bet):
        print('{} {}'.format(id, action))
        if card != 'xx':
            print('they were dealt a {}'.format(card))
        print('their card value is now {}'.format(self.players[id].hand.value()))
        if bust == 'busty':
            print('(they busted)')

    def end_game(self, player_info):
        print('end of game')
        print(player_info)

