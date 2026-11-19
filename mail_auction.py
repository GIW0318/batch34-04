import copy
import math


class MailAuction:
    def __init__(self, wallet, items):
        self.wallet = {player: amount for player, amount in wallet.items()}
        self.items = {player: list(player_items) for player, player_items in items.items()}
        self.auctions = {}
        self.mails = []
        self._next_auction_id = 1
        self._next_mail_id = 1

    @staticmethod
    def _require_positive_integer(value, name):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"{name} must be a positive integer")
        return value

    @staticmethod
    def _require_positive_duration(value):
        if isinstance(value, bool):
            raise ValueError("duration must be positive")
        if isinstance(value, int):
            if value <= 0:
                raise ValueError("duration must be positive")
            return value
        if isinstance(value, float) and math.isfinite(value) and value > 0:
            return value
        raise ValueError("duration must be positive")

    @staticmethod
    def _is_at_or_after(now, deadline):
        try:
            return now >= deadline
        except TypeError as exc:
            raise ValueError("invalid time") from exc

    @staticmethod
    def _deadline_after(now, duration):
        try:
            return now + duration
        except TypeError as exc:
            raise ValueError("invalid time") from exc

    def _new_mail(
        self,
        kind,
        sender,
        receiver,
        item,
        amount,
        now,
        expires_at,
    ):
        mail = {
            "id": f"m{self._next_mail_id}",
            "kind": kind,
            "sender": sender,
            "receiver": receiver,
            "item": item,
            "amount": amount,
            "status": "unpaid",
            "created_at": now,
            "expires_at": expires_at,
        }
        self._next_mail_id += 1
        self.mails.append(mail)
        return mail

    def _find_auction(self, auction_id):
        auction = self.auctions.get(auction_id)
        if auction is None:
            raise ValueError("unknown auction")
        return auction

    def _find_mail(self, player, mail_id):
        for mail in self.mails:
            if mail["id"] == mail_id and mail["receiver"] == player:
                return mail
        raise ValueError("unknown mail")

    def _return_item(self, mail):
        owner = mail.get("sender")
        if owner is not None:
            self.items.setdefault(owner, []).append(mail["item"])

    def _expire_mail(self, mail):
        if mail["status"] != "unpaid":
            return False
        if mail["kind"] not in ("cod", "return"):
            return False
        self._return_item(mail)
        mail["status"] = "expired"
        return True

    def _expire_due_mails(self, now):
        expired = False
        for mail in self.mails:
            if mail["status"] != "unpaid" or mail["kind"] not in ("cod", "return"):
                continue
            expires_at = mail.get("expires_at")
            if expires_at is not None and self._is_at_or_after(now, expires_at):
                expired = self._expire_mail(mail) or expired
        return expired

    def _close_auction(self, auction, now):
        expires_at = self._deadline_after(now, 10)
        bids = auction["bids"]
        if not bids:
            auction["status"] = "expired"
            auction["closed_at"] = now
            self._new_mail(
                "return",
                auction["seller"],
                auction["seller"],
                auction["item"],
                0,
                now,
                expires_at,
            )
            return

        winner = bids[-1]["bidder"]
        amount = bids[-1]["amount"]
        auction["status"] = "closed"
        auction["closed_at"] = now
        auction["winner"] = winner
        auction["winning_bid"] = amount
        auction["high_bid"] = amount
        self._new_mail(
            "cod",
            auction["seller"],
            winner,
            auction["item"],
            amount,
            now,
            expires_at,
        )

    def list_item(self, seller, item, start_price, now, duration=10):
        self._require_positive_integer(start_price, "start_price")
        duration = self._require_positive_duration(duration)
        deadline = self._deadline_after(now, duration)
        if seller not in self.items or item not in self.items[seller]:
            raise ValueError("seller does not own item")

        self.items[seller].remove(item)
        auction_id = f"a{self._next_auction_id}"
        self._next_auction_id += 1
        self.auctions[auction_id] = {
            "id": auction_id,
            "seller": seller,
            "item": item,
            "start_price": start_price,
            "deadline": deadline,
            "status": "open",
            "bids": [],
            "high_bid": None,
            "winner": None,
            "winning_bid": None,
        }
        return auction_id

    def bid(self, auction_id, bidder, amount, now):
        auction = self._find_auction(auction_id)
        self._require_positive_integer(amount, "amount")
        if auction["status"] != "open":
            raise ValueError("auction is not open")
        if self._is_at_or_after(now, auction["deadline"]):
            raise ValueError("auction has ended")
        if bidder == auction["seller"]:
            raise ValueError("seller cannot bid")
        if bidder not in self.wallet:
            raise ValueError("unknown bidder")
        if amount < auction["start_price"]:
            raise ValueError("bid is below start price")
        if auction["high_bid"] is not None and amount <= auction["high_bid"]:
            raise ValueError("bid must exceed current high bid")
        if amount > self.wallet[bidder]:
            raise ValueError("insufficient funds")

        auction["bids"].append(
            {"bidder": bidder, "amount": amount, "time": now}
        )
        auction["high_bid"] = amount
        return amount

    def close(self, auction_id, now):
        auction = self._find_auction(auction_id)
        if auction["status"] != "open":
            raise ValueError("auction is not open")
        if not self._is_at_or_after(now, auction["deadline"]):
            raise ValueError("auction has not ended")
        self._close_auction(auction, now)
        return auction_id

    @staticmethod
    def _auction_order(auction_id):
        suffix = auction_id[1:]
        return (0, int(suffix)) if suffix.isdigit() else (1, auction_id)

    def tick(self, now):
        due = sorted(
            (
                auction_id
                for auction_id, auction in self.auctions.items()
                if auction["status"] == "open"
                and self._is_at_or_after(now, auction["deadline"])
            ),
            key=self._auction_order,
        )
        for auction_id in due:
            self._close_auction(self.auctions[auction_id], now)
        self._expire_due_mails(now)
        return due

    def send_cod(self, sender, receiver, item, price, now, ttl=10):
        self._require_positive_integer(price, "price")
        ttl = self._require_positive_duration(ttl)
        expires_at = self._deadline_after(now, ttl)
        if sender == receiver:
            raise ValueError("sender and receiver must differ")
        if sender not in self.items or item not in self.items[sender]:
            raise ValueError("sender does not own item")

        self.items[sender].remove(item)
        mail = self._new_mail(
            "cod",
            sender,
            receiver,
            item,
            price,
            now,
            expires_at,
        )
        return mail["id"]

    def mailbox(self, player):
        return copy.deepcopy(
            [mail for mail in self.mails if mail["receiver"] == player]
        )

    def _claim_cod(self, player, mail, now):
        expires_at = mail.get("expires_at")
        if expires_at is not None and self._is_at_or_after(now, expires_at):
            self._expire_mail(mail)
            raise ValueError("mail has expired")
        if self.wallet.get(player, 0) < mail["amount"]:
            raise ValueError("insufficient funds")

        self.wallet[player] -= mail["amount"]
        self.items.setdefault(player, []).append(mail["item"])
        mail["status"] = "claimed"
        mail["claimed_at"] = now
        self._new_mail(
            "payout",
            player,
            mail["sender"],
            None,
            mail["amount"],
            now,
            None,
        )

    def _claim_payout(self, player, mail, now):
        self.wallet[player] = self.wallet.get(player, 0) + mail["amount"]
        mail["status"] = "claimed"
        mail["claimed_at"] = now

    def _claim_return(self, player, mail, now):
        expires_at = mail.get("expires_at")
        if expires_at is not None and self._is_at_or_after(now, expires_at):
            self._expire_mail(mail)
            raise ValueError("mail has expired")
        self.items.setdefault(player, []).append(mail["item"])
        mail["status"] = "claimed"
        mail["claimed_at"] = now

    def claim(self, player, mail_id, now):
        mail = self._find_mail(player, mail_id)
        if mail["status"] != "unpaid":
            raise ValueError("mail cannot be claimed")

        if mail["kind"] == "cod":
            self._claim_cod(player, mail, now)
        elif mail["kind"] == "payout":
            self._claim_payout(player, mail, now)
        elif mail["kind"] == "return":
            self._claim_return(player, mail, now)
        else:
            raise ValueError("unknown mail kind")
        return copy.deepcopy(mail)

    def balance(self, player):
        return self.wallet.get(player, 0)

    def inventory(self, player):
        return list(self.items.get(player, []))

    def state(self):
        inventories = copy.deepcopy(self.items)
        mailboxes = {}
        for mail in self.mails:
            mailboxes.setdefault(mail["receiver"], []).append(
                copy.deepcopy(mail)
            )
        return {
            "wallet": copy.deepcopy(self.wallet),
            "items": inventories,
            "inventory": copy.deepcopy(inventories),
            "auctions": copy.deepcopy(self.auctions),
            "mails": mailboxes,
            "mailboxes": copy.deepcopy(mailboxes),
        }
