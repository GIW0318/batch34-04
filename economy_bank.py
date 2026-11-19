class EconomyBank:
    def __init__(self, accounts, config=None):
        self.accounts = accounts
        self.config = config or {}
        self.orders = {}
        self.trades = []
        self.fees_collected = 0

    def place_order(self, order_id, player, side, item, price, qty, now):
        return None

    def cancel_order(self, order_id, player, now):
        return None

    def deposit(self, player, amount, now):
        return None

    def withdraw(self, player, amount, now):
        return None

    def accrue(self, now):
        return None

    def state(self):
        return {}
