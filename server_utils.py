class BlackjackDeck(object):
    def __init__(self):
        self.values = map(str, range(1,10)) + ['T','J','Q','K']
        self.suits = ['H','S','C','D']
        self.num_decks = 2
        self.shuffle()
    def shuffle(self):
        self.cards = deque( list(itertools.product(self.values, self.suits)) * self.num_decks )
        random.shuffle(self.cards)
    def deal(self,n):
        return [self.cards.popleft() for x in range(n)]

class BlackjackHand(object):
    def __init__(self, cards):
        self.cards=cards
    def hit(self, card):
        self.cards += card
    def value(self):
        val = 0
        ace_present = False
        for card in self.cards:
            if card[0] == 'A':
                ace_present = True
            val += 10 if card[0] in ['T','J','Q','K'] else int(card[0])
        if ace_present and val + 10 <= 21:
            val += 10
        return val

class BlackjackError(Exception):
    pass

class BlackjackGame(object):
    '''So what I ended up doing is making an on_timeout callable attribute, 
    along with a timer attribute. All 'state' methods return a tuple of 
    (msg to send, next timeout in seconds, (player id,error), (player id,error), ...)
    They also check the timer at every call to see if they should actually run yet or if 
    the server only returned because of a chat message or something. 
    This is troublesome because that means they will ALWAYS wait until the timeout is up
    before running. A solution might be to have the server do some checking before it calls
    'on_timeout'. This would require the server to become time-aware, however.'''
    
    def __init__(self, timeout):
        self.MAX_PLAYERS = 6
        self.MIN_BET = 5
        self.players = {} #seat num: (id,cash) pairs
        self.deck = BlackjackDeck()
        self.bets = {} #seat num:bet pairs
        self.hands = {} #seat num:BlackjackHand pairs
        self.whose_turn=1 #index into self.players
        self.state = 'waiting for players'
        self.logger = logging.getLogger(__name__)
        self.timeout=timeout
        self.split_store = False
        self.on_timeout = lambda: None #function for the server to call on timeout
        self.trigger = lambda id_, mess_type, mess_args: False #predicate function :
        #Has the trigger event happened?
        self.on_trigger = lambda: None #function for the server to call when the
        #trigger predicate is true.
        
    def add_player(self, id_, cash):
        '''Add a player to the game, unless one is running
        returns (like all BlackjackGame methods) a tuple of msg-to-send and the next timeout in seconds'''
        if self.in_progress():
            raise BlackjackError('A game is already in progress. Cannot add player {}'.format(id_))
        try:
            next_seat = min(set(range(1,self.MAX_PLAYERS + 1)) - set(self.players.keys()))
            self.players[next_seat] = (id_,cash)
            self.state = 'waiting to start game'
            self.on_timeout = self.ask_for_bets
        except ValueError as e: #we get a value error when we take min([])
            raise ValueError('The table is already full; cannot add another player')

    def ask_for_bets(self):
        '''ask to send an ante message, reset the timer'''
        if not self.players:
            return self.drop_game()
        self.state = 'waiting for antes'
        msg = '[ante|{:0>10}'.format(self.MIN_BET)
        self.on_timeout = self.deal
        return (msg, self.timeout, ())        

    def deal(self, shuf=True):
        '''First check if everyone made a bet. If not, drop them
        Modify state to represent initial deal.
        return the deal msg for the server to pass to clients.
        Should also change the state'''

        for non_compliant in (set(self.players.keys()) - set(self.bets.keys())):
            self.drop_player(non_compliant)
        if not self.players:
            return self.drop_game()

        if shuf: 
            self.deck.shuffle()

        self.hands['dealer'] = Blackjackhand(self.deck.deal(2))
        msg = ['[deal']
        msg.append(self.hands['dealer'].cards[0]) #only reveal one dealer card
        msg.append('shufy' if shuf else 'shufn')

        for seat_num in range(1,self.MAX_PLAYERS + 1):
            if seat_num in self.players:
                self.cards[seat_num] = BlackjackHand(self.deck.deal(2))
                msg.append('{player[0]:<12},{player[1]:0>10},{cards[0]},{cards[1]}'.format(player=self.players[seat_num], cards=self.hands[seat_num].cards))
            else:
                msg.append('')
        msg[-1] += ']' #closing brace to message
        self.whose_turn=1
        if self.hands['dealer'].cards[0][0] == 'A': #dealer has ace showing
            self.state = 'waiting for insurance'
            self.on_timeout = self.ensure_insurance
            return ('|'.join(msg), self.timeout, ())
        self.state = 'playing out turns'
        self.on_timeout = self.player_turn
        return ('|'.join(msg), 0, ()) 
        #timeout of 0 says to go to player_turn right away

    def ensure_insurance(self):
        for non_compliant in (set(self.players.keys()) - set(self.bets.keys())):
            self.drop_player(non_compliant)
        if not self.players:
            return self.drop_game()
        self.state = 'playing out turns'
        return self.player_turn()

    def player_turn(self):
        if self.whose_turn > self.MAX_PLAYERS:
            return self.payout()
        if self.whose_turn not in self.players or self.hands[self.whose_turn].value() >= 21:
            self.whose_turn += 1
            return (None, 0, ()) # a timeout of 0 returns right away,
            # so the server will call player_turn again
        msg = '[turn|{}]'.format(self.players[self.whose_turn][0])
        #Sorry for the confusing on_timeout. The idea is that if we haven't
        # heard a turn msg from a player before the bell rings, we should drop them.
        self.on_timeout = lambda : self.drop_player(self.whose_turn)
        return (msg, self.timeout, ())

    def player_action(self,action):
        '''process a [turn|action] message, changing the internal state 
        queue up a stat message, set timeout to 0 and on_timeout to player_turn if it's the next player's turn, 
        set timeout to self.timeout if we're remaining on this player's turn.
        precondition: the turn message must have originated from the player whose turn it is.
        
        probably we want to refactor this into a function for each action'''
        msg = '[stat|{id_}|{action}|{card}|{bust}|{bet}]'
        params = {
                'id_':self.players[self.whose_turn][0],
                'bet':self.bets[self.whose_turn],
                'action':action
                }
        if action == 'hitt':
            new_card = self.deck.deal(1)[0]
            self.hands[self.whose_turn].cards += new_card
            params['card'] = new_card
            if self.hands[self.whose_turn].value() >= 21:
                if self.split_store:
                    raise BlackjackError('handle bust after split')
                else:
                    self.whose_turn += 1
                    self.on_timeout = self.player_turn
                    timeout = 0 # move onto next player right away
            else: #give the player another TIMEOUT secs before we drop them
                timeout = 30 
        elif action == 'stay':
            if self.split_store:
                raise BlackjackError('handle second hand after split')
            else:
                params['card'] = 'xx'
                self.whose_turn += 1
                timeout = 0 #move onto next player right away
                self.on_timeout = self.player_turn
        elif action == 'down':
            if len(self.hands[self.whose_turn].cards) > 2:
                #a player may only double down on their first move
                raise BlackjackError("I'm not prepared for that!")
            new_card = self.deck.deal(1)[0]
            self.hands[self.whose_turn].cards += new_card
            params['card'] = new_card
            params['bet'] *= 2
            self.bets[self.whose_turn] *= 2
            self.whose_turn += 1
            self.on_timeout = self.player_turn
            timeout = 0 # move on right away
        elif action == 'splt':
            if len(self.hands[self.whose_turn].cards) > 2 or self.split_store:
                raise BlackjackError('splits only allowed on first turns and only once')
            if self.hands[self.whose_turn].cards[0][0] != self.hands[self.whose_turn].cards[1][0]:
                raise BlackjackError('splits only allowed on cards of same value!')
            new_card = self.deck.deal(1)[0]
            params['card'] = new_card
            #save off second card
            self.split_store = self.hands[self.whose_turn].cards[1]
            self.hands[self.whose_turn].cards[1] = new_card
            timeout = 30

        params['bust'] = 'busty' if self.hands[self.whose_turn].value() > 21 else 'bustn'
        return msg.format(**params)

    def payout(self):
        msg = ['[endg']
        dealer_val = self.hands['dealer'].value()
        for seat_num in range(1,self.MAX_PLAYERS):
            if seat_num not in self.players:
                msg.append('')
                continue
            id_, cash = self.players[seat_num]
            player_val = self.hands[seat_num].value()
            if player_val > dealer_val:
                result = 'WON'
                cash += self.bets[seat_num]
            elif player_val < dealer_val:
                result = 'LOS'
                cash -= self.bets[seat_num]
            else:
                result = 'TIE'
            self.players[seat_num] = (id_, cash)
            msg.append('{id_:<12},{result},{cash:0>10}'.format(
                id_, result, cash))
        msg[-1] += ']'
        raise BlackjackError("Make sure that the server reads off the values of cash")
        return '|'.join(msg)
    
    def in_progress(self):
        return self.state in ['waiting for players', 'waiting to start game']


    def drop_player(self, player):
        #remember that player_turn expects us to check and reset the timer here.
        raise BlackjackError("I'm not prepared for that! Only well-behaved clients for the time-being.")

