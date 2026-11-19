PASS_COST = 200
FREE_REWARD_BASE = 40
PREMIUM_REWARD_BASE = 100
REWARD_PER_TIER = 10


class SeasonShop:
    def __init__(self, tiers, offers, rotation, season="s1"):
        if not tiers or not rotation:
            raise ValueError("tiers and rotation must be non-empty")

        self.tiers = list(tiers)
        self.offer_defs = {key: dict(value) for key, value in offers.items()}
        self.rotation = [list(day) for day in rotation]
        self.season = season
        self.players = {}
        self.day = 0
        self.stock = {}
        self._restock()

    def _restock(self):
        self.stock = {
            offer_id: self.offer_defs[offer_id]["stock"]
            for offer_id in self.rotation[self.day]
        }

    def _player(self, player):
        try:
            return self.players[player]
        except (KeyError, TypeError):
            raise ValueError("unknown player: %r" % (player,)) from None

    @staticmethod
    def _is_int(value):
        return isinstance(value, int) and not isinstance(value, bool)

    def _level_for(self, xp):
        level = 0
        for threshold in self.tiers:
            if xp >= threshold:
                level += 1
            else:
                break
        return level

    def join(self, player, coins=100):
        if not isinstance(player, str) or not player.strip():
            raise ValueError("player name must be a non-empty string")
        if player in self.players:
            raise ValueError("player already joined: %r" % (player,))
        if not self._is_int(coins) or coins < 0:
            raise ValueError("initial coins must be a non-negative integer")

        self.players[player] = {
            "xp": 0,
            "coins": coins,
            "pass": False,
            "claimed": {"free": [], "premium": []},
        }

    def add_xp(self, player, amount):
        record = self._player(player)
        if not self._is_int(amount) or amount <= 0:
            raise ValueError("xp amount must be a positive integer")

        record["xp"] = min(record["xp"] + amount, self.tiers[-1])
        return self._level_for(record["xp"])

    def level(self, player):
        return self._level_for(self._player(player)["xp"])

    def buy_pass(self, player):
        record = self._player(player)
        if record["pass"]:
            raise ValueError("season pass already owned")
        if record["coins"] < PASS_COST:
            raise ValueError("insufficient coins for season pass")

        record["coins"] -= PASS_COST
        record["pass"] = True

    def claim(self, player, tier, track="free"):
        record = self._player(player)
        if track not in ("free", "premium"):
            raise ValueError("unknown track: %r" % (track,))
        if not self._is_int(tier) or tier < 1 or tier > len(self.tiers):
            raise ValueError("tier out of range: %r" % (tier,))
        if self._level_for(record["xp"]) < tier:
            raise ValueError("tier %d not reached" % tier)
        if track == "premium" and not record["pass"]:
            raise ValueError("season pass required for premium track")

        claimed = record["claimed"][track]
        if tier in claimed:
            raise ValueError("tier %d already claimed on %s track" % (tier, track))

        base = FREE_REWARD_BASE if track == "free" else PREMIUM_REWARD_BASE
        reward = base + REWARD_PER_TIER * tier
        record["coins"] += reward
        claimed.append(tier)
        return reward

    def offers(self):
        result = []
        for offer_id in self.rotation[self.day]:
            offer = self.offer_defs[offer_id]
            result.append(
                {
                    "id": offer_id,
                    "price": offer["price"],
                    "stock": self.stock[offer_id],
                    "requires_level": offer["requires_level"],
                }
            )
        return result

    def buy(self, player, offer_id, qty=1):
        record = self._player(player)
        if not self._is_int(qty) or qty <= 0:
            raise ValueError("quantity must be a positive integer")
        if offer_id not in self.stock:
            raise ValueError("offer not available today: %r" % (offer_id,))

        offer = self.offer_defs[offer_id]
        if self._level_for(record["xp"]) < offer["requires_level"]:
            raise ValueError("level requirement not met")
        if self.stock[offer_id] < qty:
            raise ValueError("not enough stock")

        total = offer["price"] * qty
        if record["coins"] < total:
            raise ValueError("insufficient coins")

        record["coins"] -= total
        self.stock[offer_id] -= qty
        return total

    def advance_day(self):
        self.day = (self.day + 1) % len(self.rotation)
        self._restock()
        return self.day

    def balance(self, player):
        return self._player(player)["coins"]

    def state(self):
        players = {}
        for name, record in self.players.items():
            players[name] = {
                "xp": record["xp"],
                "level": self._level_for(record["xp"]),
                "coins": record["coins"],
                "pass": record["pass"],
                "claimed": {
                    "free": list(record["claimed"]["free"]),
                    "premium": list(record["claimed"]["premium"]),
                },
            }
        return {"season": self.season, "day": self.day, "players": players}
