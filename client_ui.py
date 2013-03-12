import sys
import random
import pickle
from collections import defaultdict
from utils import escape_chars, colors,BlackjackHand,validate_name

class ConsoleUI(object):

    def __init__(self, send_chat_msg,name = None):
        '''send_chat_msg is a callback that takes a line of text and
        sends it through the server socket. (we need a callback because the GUI 
        will be triggered by a GUI event rather than a true file descriptor. 
        For the simple ConsoleUI, we have no events, so we need the client code
        to watch sys.stdin for us and then call send_chat. ugly.)'''
        self.chat_callback = send_chat_msg
        self.chat_at_stdin = True
        self.name = None if name is None else validate_name(name)
        self.players = {}

    def show_chat(self, id_, text):
        print(colors.YELLOW + '{id_}> {text}'.format(
            id_=id_.rstrip(),
            text=text) + colors.ENDC)

    def get_player_name(self):
        name = raw_input(colors.OKBLUE + 'What is your name? ' + colors.ENDC).translate(None, '[]|,\n')
        self.name = validate_name(name)
        return self.name

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
            try:
                self.bet = int(raw_input(colors.OKBLUE + 'What is your bet? (min {})'.format(min_bet) + colors.ENDC))
                if self.bet < min_bet:
                    print (colors.FAIL + 'That bet is too small.' + colors.ENDC)

            except ValueError:
                print( colors.FAIL + "That's not a number!" + colors.ENDC)
                self.bet = 0
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
        print('players is {}'.format(self.players))
        print('self.name is {}'.format(self.name))
        print( colors.OKBLUE + "It's your turn! You have {} choose one of {}".format(
            self.players[self.name].hand.value(),
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
        self.first_turn = False
        return action
        
class IntelligentUI(AutoUI):
    possible_names = ['NonTrivialAI']
    split_strategies = { #doubled_card:{dealer_card:action}
            '1':defaultdict(lambda: 'splt'),
            '2':defaultdict(lambda: 'hitt', {
                '4':'splt',
                '5':'splt',
                '6':'splt',
                '7':'splt'}),
            '3':defaultdict(lambda: 'hitt', {
                '4':'splt',
                '5':'splt',
                '6':'splt',
                '7':'splt'}),
            '4':defaultdict(lambda: 'hitt'),
            '6':defaultdict(lambda: 'splt',{
                '7':'hitt',
                '8':'hitt',
                '9':'hitt',
                'T':'hitt',
                '1':'hitt'}),
            '7':defaultdict(lambda: 'splt',{
                '8':'hitt',
                '9':'hitt',
                'T':'hitt',
                '1':'hitt'}),
            '8':defaultdict(lambda: 'splt'),
            '9':defaultdict(lambda: 'splt',{
                '7':'stay',
                'T':'stay',
                '1':'stay'}),
            }
    ace_present_strategies = {#othercardsum:{dealer_card:action}
            2:defaultdict(lambda:'hitt', {
                '5':'down',
                '6':'down'}),
            3:defaultdict(lambda:'hitt',{
                '4':'down',
                '5':'down',
                '6':'down'}),
            4:defaultdict(lambda:'hitt',{
                '4':'down',
                '5':'down',
                '6':'down'}),
            5:defaultdict(lambda:'hitt',{
                '4':'down',
                '5':'down',
                '6':'down'}),
            6:defaultdict(lambda:'hitt',{
                '3':'down',
                '4':'down',
                '5':'down',
                '6':'down'}),
            7:defaultdict(lambda:'down',{
                '7':'stay',
                '8':'stay',
                '9':'hitt',
                'T':'hitt'}),
            8:defaultdict(lambda:'stay',{
                '6':'down'}),
            9:defaultdict(lambda: 'stay'),
            10:defaultdict(lambda: 'stay')
            }
    general_strategies = {#cardsum:{dealer_card:action}
            4:defaultdict(lambda: 'hitt'),
            5:defaultdict(lambda: 'hitt'),
            6:defaultdict(lambda: 'hitt'),
            7:defaultdict(lambda: 'hitt'),
            8:defaultdict(lambda: 'hitt'),
            9:defaultdict(lambda: 'down',{
                '7':'hitt',
                '8':'hitt',
                '9':'hitt',
                'T':'hitt',
                '1':'hitt'}),
            10:defaultdict(lambda: 'down',{
                'T':'hitt',
                '1':'hitt'}),
            11:defaultdict(lambda: 'down'),
            12:defaultdict(lambda: 'hitt',{
                '4':'stay',
                '5':'stay',
                '6':'stay'}),
            13:defaultdict(lambda: 'stay',{
                '7':'hitt',
                '8':'hitt',
                '9':'hitt',
                'T':'hitt',
                '1':'hitt'}),
            14:defaultdict(lambda: 'stay',{
                '7':'hitt',
                '8':'hitt',
                '9':'hitt',
                'T':'hitt',
                '1':'hitt'}),
            15:defaultdict(lambda: 'stay',{
                '7':'hitt',
                '8':'hitt',
                '9':'hitt',
                'T':'hitt',
                '1':'hitt'}),
            16:defaultdict(lambda: 'stay',{
                '7':'hitt',
                '8':'hitt',
                '9':'hitt',
                'T':'hitt',
                '1':'hitt'}),
            17:defaultdict(lambda:'stay'),
            18:defaultdict(lambda:'stay'),
            19:defaultdict(lambda:'stay'),
            20:defaultdict(lambda:'stay'),
            21:defaultdict(lambda:'stay')
        }


    def __init__(self, *args, **kwargs):
        AutoUI.__init__(self, *args, **kwargs)
         
    def strategy(self, dealer_card, my_hand):
        my_hand = BlackjackHand(my_hand.cards) #make a local copy
        #replace J,Q,K with their value
        if dealer_card in ['J','Q','K']:
            dealer_card = 'T'
        if self.first_turn and my_hand.cards[0][0] == my_hand.cards[1][0]:
            #possible split
            if my_hand.cards[0][0] in self.split_strategies:
                return self.split_strategies[my_hand.cards[0][0]][dealer_card]

        for ix, card in enumerate(my_hand.cards):
            if card[0] in ['J','Q','K']:
                my_hand.cards[ix] = 'T' + card[1]


        if '1' in [card[0] for card in my_hand.cards]:
            #ace is present
            other_cards = sum(map(int,
                map(lambda c: '10' if c=='T' else c,
                    filter(lambda c: c != '1', 
                        map(lambda c: c[0], my_hand.cards)))))
            if other_cards in self.ace_present_strategies :
                preference = self.ace_present_strategies[other_cards][dealer_card]
                if not self.first_turn and preference == 'down':
                    return 'stay' if other_cards >= 7 else 'hitt'
                return preference
        card_sum = sum(map(int,
            map(lambda c: '10' if c=='T' else c,
                map(lambda c: c[0], my_hand.cards))))
        if card_sum in self.general_strategies:
            preference = self.general_strategies[card_sum][dealer_card]
            if not self.first_turn and preference == 'down':
                return 'hitt'
            return preference
        else:
            print colors.FAIL + "I don't know what to do!!!"
            print 'my_hand={}'.format(my_hand)
            print 'dealer_card={}'.format(dealer_card)
            print colors.ENDC
            return 'stay'

    def get_insurance(self):
        print colors.OKBLUE + 'What insurance would you like?' + colors.ENDC, 0
        return 0

    def get_turn_action(self):
        my_hand = self.players[self.name].hand
        dealer_card = self.players['SERVER      '].hand.cards[0][0]
        action = self.strategy(dealer_card, my_hand)
        print colors.OKBLUE + "It's your turn! you have {}".format(my_hand.value()) + colors.ENDC, action
        self.first_turn = False
        return action
  

