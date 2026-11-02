import random

cards = {
    "Ace": 1,
    "2": 2,
    "3": 3,
    "4": 4,
    "5": 5,
    "6": 6,
    "7": 7,
    "8": 8,
    "9": 9,
    "10": 10,
    "Jack": 11,
    "Queen": 12,
    "King": 13,
}
suits = ["Hearts", "Diamonds", "Clubs", "Spades"]
deck = [(rank, suit, value) for rank, value in cards.items() for suit in suits]


class Game:
    def __init__(self, players):
        names = [name.strip() for name in players if name and name.strip()]
        if len(names) < 2:
            raise ValueError("At least two players are required to start the game.")
        if len({name.casefold() for name in names}) != len(names):
            raise ValueError("Player names must be unique.")
        random.shuffle(names)
        deck_temp = deck.copy()
        random.shuffle(deck_temp)
        self.deck = deck_temp
        self.players = [Player(name, i) for i, name in enumerate(names)]
        self.current_player_index = 0
        self.pot = 0
        self.winner = None
        self.start_round()

    def start_round(self):
        self.current_player_index = 0
        self.deck = deck.copy()
        random.shuffle(self.deck)
        for player in self.players:
            player.hand = [self.deck.pop() for _ in range(2)]
            player.money -= 20
            self.pot += 20

    def draw_card(self, player):
        if self.deck:
            player.drawn_card = self.deck.pop()
        else:
            player.drawn_card = None

    def check_winner(self, reason=None):
        active_players = [p for p in self.players if p.money > 0]
        if len(active_players) == 1:
            self.winner = active_players[0]
            event = {
                "type": "GAME_OVER",
                "winner": self.winner.name,
                "message": f"{self.winner.name} is the last player standing and wins the game!",
            }
            if reason:
                event["reason"] = reason
            return event
        return None

    @property
    def current_player(self):
        return self.players[self.current_player_index]

    def next_player(self):
        next_index = self.current_player_index + 1
        event = None
        if next_index >= len(self.players):
            self.start_round()
            event = {
                "type": "ROUND_STARTED",
                "message": "A new round has started. All players have been dealt new hands.",
                "current_player": self.current_player.name,
            }
        self.current_player_index = next_index % len(self.players)
        if event is not None:
            return event
        else:
            return None

    def _state_event(self):
        return {
            "type": "GAME_STATE",
            "state": self.to_dict(),
        }

    def to_dict(self):
        return {
            "players": [
                {
                    "name": player.name,
                    "money": player.money,
                    "hand": player.hand,
                    "drawn_card": player.drawn_card,
                }
                for player in self.players
            ],
            "current_player": self.current_player.name,
            "pot": self.pot,
            "winner": self.winner.name if self.winner else None,
        }

    def handle_action(self, player_name, action, data=None):
        if self.winner:
            raise ValueError("The game is over; no further actions can be taken.")
        player = self.current_player
        if player.name != player_name:
            raise ValueError(
                f"It is not {player_name}'s turn; it is {player.name}'s turn."
            )

        action = action.strip().upper()
        events = []
        if action == "PASS":
            self.next_player()
            event = {
                "type": "PLAYER_PASSED",
                "previous_player": player.name,
                "next_player": self.current_player.name,
            }
            events.append(event)
            events.append(self._state_event())
            return events
        if action == "BET":
            amount = data.get("amount")
            choice = data.get("choice")
            if amount is None or choice is None:
                raise ValueError(
                    "Both 'amount' and 'choice' must be provided for a bet."
                )
            if isinstance(amount, str) and amount.lower() == "all_in":
                amount = min(player.money, self.pot)
            if amount <= 0:
                raise ValueError("Bet amount must be a positive number.")
            if amount > player.money:
                raise ValueError("You do not have enough money to make that bet.")
            if amount > self.pot:
                raise ValueError("Bet cannot exceed the current pot.")
            if choice not in ["higher", "lower", "between"]:
                raise ValueError(
                    "Choice must be one of 'higher', 'lower', or 'between'."
                )
            if choice in ["higher", "lower"] and player.hand[0][2] == player.hand[1][2]:
                raise ValueError(
                    "Cannot bet on 'higher' or 'lower' when both cards are the same."
                )
            self.draw_card(player)
            event = {
                "type": "CARD_DRAWN",
                "player": player.name,
                "drawn_card": player.drawn_card,
            }
            events.append(event)
            if choice == "higher":
                if player.drawn_card[2] > max(player.hand[0][2], player.hand[1][2]):
                    player.money += amount
                    self.pot -= amount
                    event = {
                        "type": "PLAYER_WON",
                        "player": player.name,
                        "amount": amount,
                    }
                    events.append(event)
                else:
                    player.money -= amount
                    self.pot += amount
                    event = {
                        "type": "PLAYER_LOST",
                        "player": player.name,
                        "amount": amount,
                    }
                    events.append(event)
            elif choice == "lower":
                if player.drawn_card[2] < min(player.hand[0][2], player.hand[1][2]):
                    player.money += amount
                    self.pot -= amount
                    event = {
                        "type": "PLAYER_WON",
                        "player": player.name,
                        "amount": amount,
                    }
                    events.append(event)
                else:
                    player.money -= amount
                    self.pot += amount
                    event = {
                        "type": "PLAYER_LOST",
                        "player": player.name,
                        "amount": amount,
                    }
                    events.append(event)
            elif choice == "between":
                low_card = min(player.hand[0][2], player.hand[1][2])
                high_card = max(player.hand[0][2], player.hand[1][2])
                if low_card < player.drawn_card[2] < high_card:
                    player.money += amount
                    self.pot -= amount
                    event = {
                        "type": "PLAYER_WON",
                        "player": player.name,
                        "amount": amount,
                    }
                    events.append(event)
                else:
                    player.money -= amount
                    self.pot += amount
                    event = {
                        "type": "PLAYER_LOST",
                        "player": player.name,
                        "amount": amount,
                    }
                    events.append(event)
            if self.pot <= 0:
                self.start_round()
            next_player_event = self.next_player()
            if next_player_event:
                events.append(next_player_event)
            events.append(self._state_event())
            if self.check_winner():
                events.append(self.check_winner())
            return events

        else:
            raise ValueError(f"Unknown action: {action}")


class Player:
    def __init__(self, name, player_no):
        self.money = 1000
        self.player_no = player_no
        self.name = name
        self.hand = []
        self.drawn_card = None
