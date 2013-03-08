import sys
import random
import pickle
from utils import escape_chars, colors

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
        self.players = {}

    def show_chat(self, id_, text):
        print(colors.YELLOW + '{id_}> {text}'.format(
            id_=id_.rstrip(),
            text=text) + colors.ENDC)

    def get_player_name(self):
        name = raw_input(colors.OKBLUE + 'What is your name? ' + colors.ENDC).translate(None, '[]|,\n')
        self.name = '{:<12}'.format(name)
        return name if len(name) <= 12 else name[:12]

    def send_chat(self):
        chat_line = sys.stdin.readline().strip('\r\n')
        self.chat_callback(chat_line)

    def get_insurance(self):
        insu = self.bet
        max_insu = self.bet / 2
        while insu > max_insu or insu < 0:
            insu = raw_input(colors.OKBLUE + 'What insurance would you like? (blank for 0)' + colors.ENDC)
            if insu == '':
                return 0
            try:
                insu = int(insu)
            except:
                print(colors.FAIL + "That's not an integer!" + colors.ENDC)
                continue
            if insu > max_insu:
                print (colors.FAIL + 'your bet is {}. You can only buy insurance up to half your bet.'.format(self.bet) + colors.ENDC)
            elif insu < 0:
                print (colors.FAIL + 'no negative insurance!' + colors.ENDC)
            else:
                return insu

    def new_join(self, id, timeout, cash, seat_number):
        print (colors.YELLOW + '{} has joined the room. cash: {} seat: {}'.format(id, cash, seat_number) + colors.ENDC)

    def get_ante(self, min_bet):
        self.bet = 0
        min_bet = int(min_bet)
        while self.bet < min_bet:
            self.bet = int(raw_input(colors.OKBLUE + 'What is your bet? (min {})'.format(min_bet) + colors.ENDC))
            if self.bet < min_bet:
                print (colors.FAIL + 'That bet is too small.' + colors.ENDC)
        return self.bet

    def deal(self, shuf):
        print(colors.OKGREEN + 'Cards are dealt: (dealer {} before this hand)'.format(
            'shuffled' if shuf == 'shufy' else 'did not shuffle') + colors.ENDC)
        print (colors.OKGREEN + 'Dealer: {}'.format(self.players['SERVER      '].hand.cards) + colors.ENDC)
        for name in self.seat_to_name:
            if name is None: 
                continue
            print(colors.OKGREEN + '{name} (${cash}): {cards}'.format(
                name=name,
                cash=self.players[name].cash,
                cards=self.players[name].hand.cards) + colors.ENDC)
    def get_turn_action(self):
        valid_moves = ['hitt','stay','down','splt']
        print( colors.OKBLUE + "It's your turn! You have {} choose one of {}".format(
            self.players['{:<12}'.format(self.name)].hand.value(),
            valid_moves) + colors.ENDC)
        action = None
        while action not in valid_moves:
            action = raw_input()
            if not action in valid_moves:
                print( colors.FAIL + "that's no good! choose one of {}".format(valid_moves) + colors.ENDC)
        return action
    def display_turn(self, name):
        print(colors.OKGREEN + "it's {}'s turn!".format(name.strip()) + colors.ENDC)

    def display_stat(self, id, action, card, bust, bet):
        print(colors.OKGREEN + '{} {}'.format(id, action) + colors.ENDC)
        if card != 'xx':
            print(colors.OKGREEN + '{} was dealt a {}'.format(id,card) + colors.ENDC)
        print(colors.OKGREEN + 'their card value is now {}'.format(self.players[id].hand.value()) + colors.ENDC)
        if bust == 'busty':
            print(colors.FAIL + '(they busted)' + colors.ENDC)

    def end_game(self, player_info):
        print('end of game')
        print(player_info)


class AutoUI(ConsoleUI):
    possible_names = ['Brian']
    
    def __init__(self, *args, **kwargs):
        ConsoleUI.__init__(self, *args, **kwargs)
        self.first_turn = True
        #we only want to split or double down on the first turn
        with open('witty_things.txt','r') as f:
            self.witty_things = pickle.load(f)

    def send_chat(self):
        chat_line = sys.stdin.readline().strip('\r\n')
        if chat_line:
            self.chat_callback(chat_line)
        else:
            wittiness = random.choice(self.witty_things)
            for line in wittiness.split('\n'):
                self.chat_callback(line)
        
    def get_player_name(self):
        self.name = random.choice(self.possible_names)
        print colors.OKBLUE + 'What is your name?' + colors.ENDC, self.name
        self.name = '{:<12}'.format(self.name)
        return self.name if len(self.name) <= 12 else self.name[:12]

    def get_insurance(self):
        insu = random.randint(0,self.bet/2)
        print colors.OKBLUE + 'What insurance would you like?' + colors.ENDC, insu
        return insu
    
    def get_ante(self, min_bet):
        min_bet = int(min_bet)
        self.bet = random.randint(min_bet, min_bet*4)
        print colors.OKBLUE + 'What is your bet? (min {})'.format(min_bet) + colors.ENDC, self.bet
        return self.bet

    def get_turn_action(self):
        my_hand = self.players[self.name].hand
        ace_present = '1' in [card[0] for card in my_hand.cards]
        if my_hand.value() <= 16 or (ace_present and my_hand.value() <= 17):
            action = 'hitt'
        else:
            action = 'stay'
        print colors.OKBLUE + "It's your turn! you have {}".format(my_hand.value()) + colors.ENDC, action
        return action
        
