import copy
from collections.abc import Mapping


class SocialGift:
    DAY_SECONDS = 86400
    DEFAULT_DAILY_GIFTS = 10
    DEFAULT_MAIL_TTL = 7 * DAY_SECONDS
    DEFAULT_REQUEST_TTL = 7 * DAY_SECONDS

    def __init__(self, players, config=None):
        self.config = dict(config or {})
        self.players = {}
        self.requests = {}
        self.mails = {}
        self._friends = {}
        self._gift_ids = set()
        self._daily_counts = {}
        self._latest_time = 0
        self._latest_day = 0

        restored_friends = {}
        for player_id, data in players.items():
            record = {
                "online": bool(data.get("online", False)),
                "items": dict(data.get("items") or {}),
            }
            self.players[player_id] = record
            self._friends[player_id] = set()
            self.mails[player_id] = []

            raw_friends = data.get("friends") or ()
            restored_friends[player_id] = list(raw_friends)

            raw_mails = data.get("mail")
            if raw_mails is None:
                raw_mails = data.get("mailbox") or ()
            for raw_mail in raw_mails:
                mail = copy.deepcopy(raw_mail)
                if "mail_id" not in mail:
                    if "gift_id" not in mail:
                        raise ValueError("mail is missing an identifier")
                    mail["mail_id"] = mail["gift_id"]
                self.mails[player_id].append(mail)
                self._gift_ids.add(mail["mail_id"])

            used = data.get("daily_used", data.get("gifts_today", 0))
            if used:
                self._daily_counts[player_id] = {0: int(used)}

        for player_id, raw_friends in restored_friends.items():
            for friend_id in raw_friends:
                if friend_id in self.players and friend_id != player_id:
                    self._friends[player_id].add(friend_id)
                    self._friends[friend_id].add(player_id)

    def request_friend(self, requester, target, now=None):
        self._require_player(requester)
        self._require_player(target)
        if requester == target:
            raise ValueError("cannot send a friend request to yourself")

        now = self._observe_time(now)
        self._prune_requests(now)

        if target in self._friends[requester]:
            raise ValueError("players are already friends")
        if (requester, target) in self.requests or (
            target,
            requester,
        ) in self.requests:
            raise ValueError("friend request already pending")

        ttl = self._request_ttl()
        expires = None if ttl is None else now + ttl
        self.requests[(requester, target)] = {
            "requester": requester,
            "target": target,
            "sent_at": now,
            "expires": expires,
        }
        return True

    def accept_friend(self, requester, player, now=None):
        self._require_player(requester)
        self._require_player(player)
        if requester == player:
            raise ValueError("cannot accept your own friend request")

        if now is None:
            now = self._latest_time
        else:
            now = self._observe_time(now)
        self._prune_requests(now)

        request = self.requests.get((requester, player))
        if request is None:
            raise ValueError("friend request does not exist")
        expires = request["expires"]
        if expires is not None and now >= expires:
            del self.requests[(requester, player)]
            raise ValueError("friend request has expired")
        if player in self._friends[requester]:
            raise ValueError("players are already friends")

        del self.requests[(requester, player)]
        self._friends[requester].add(player)
        self._friends[player].add(requester)
        return True

    def unfriend(self, a, b):
        self._require_player(a)
        self._require_player(b)
        if a == b:
            raise ValueError("cannot remove yourself as a friend")
        if b not in self._friends[a]:
            raise ValueError("players are not friends")

        self._friends[a].remove(b)
        self._friends[b].remove(a)
        return True

    def friends(self, player):
        self._require_player(player)
        return sorted(self._friends[player])

    def send_gift(self, gift_id, sender, receiver, items, now=None):
        self._require_player(sender)
        self._require_player(receiver)
        now = self._observe_time(now)
        if sender == receiver:
            raise ValueError("cannot send a gift to yourself")
        if receiver not in self._friends[sender]:
            raise ValueError("gifts can only be sent between friends")
        if gift_id in self._gift_ids:
            raise ValueError("duplicate gift id")
        if not isinstance(items, Mapping) or not items:
            raise ValueError("gift items must be a non-empty mapping")

        gift_items = {}
        sender_items = self.players[sender]["items"]
        for item, quantity in items.items():
            if (
                not isinstance(quantity, int)
                or isinstance(quantity, bool)
                or quantity <= 0
            ):
                raise ValueError("item quantities must be positive integers")
            if sender_items.get(item, 0) < quantity:
                raise ValueError("insufficient item quantity")
            gift_items[item] = quantity

        day = now // self.DAY_SECONDS
        daily_limit = self._daily_gift_limit()
        day_counts = self._daily_counts.setdefault(sender, {})
        if daily_limit is not None and day_counts.get(day, 0) >= daily_limit:
            raise ValueError("daily gift limit reached")

        for item, quantity in gift_items.items():
            sender_items[item] -= quantity

        if self.players[receiver]["online"]:
            self._add_items(self.players[receiver]["items"], gift_items)
        else:
            ttl = self._mail_ttl()
            expires = None if ttl is None else now + ttl
            self.mails[receiver].append(
                {
                    "mail_id": gift_id,
                    "gift_id": gift_id,
                    "sender": sender,
                    "receiver": receiver,
                    "items": dict(gift_items),
                    "sent_at": now,
                    "expires": expires,
                    "status": "unread",
                }
            )

        self._gift_ids.add(gift_id)
        day_counts[day] = day_counts.get(day, 0) + 1
        return gift_id

    def claim(self, player, mail_id, now=None):
        self._require_player(player)
        now = self._observe_time(now)

        mail = self._find_mail(player, mail_id)
        if mail.get("sender") not in self.players:
            raise ValueError("mail sender does not exist")
        if mail["status"] != "unread":
            raise ValueError("mail cannot be claimed")
        expires = mail.get("expires")
        if expires is not None and now >= expires:
            self._expire_mail(mail)
            raise ValueError("mail has expired")

        self._add_items(self.players[player]["items"], mail["items"])
        mail["status"] = "claimed"
        return copy.deepcopy(mail)

    def expire(self, now=None):
        now = self._observe_time(now)
        expired = []
        for mailbox in self.mails.values():
            for mail in mailbox:
                if (
                    mail["status"] == "unread"
                    and mail.get("expires") is not None
                    and now >= mail["expires"]
                ):
                    self._expire_mail(mail)
                    expired.append(mail["mail_id"])
        return expired

    def inbox(self, player):
        self._require_player(player)
        mails = sorted(
            self.mails.get(player, ()),
            key=lambda mail: mail["sent_at"],
        )
        return copy.deepcopy(mails)

    def state(self):
        players = {}
        for player_id, record in self.players.items():
            day_counts = self._daily_counts.get(player_id, {})
            players[player_id] = {
                "online": record["online"],
                "items": copy.deepcopy(record["items"]),
                "friends": sorted(self._friends[player_id]),
                "mail": copy.deepcopy(
                    sorted(
                        self.mails.get(player_id, ()),
                        key=lambda mail: mail["sent_at"],
                    )
                ),
                "daily_used": day_counts.get(self._latest_day, 0),
            }
        return {"players": players}

    def _require_player(self, player):
        if player not in self.players:
            raise ValueError(f"unknown player: {player}")
        return self.players[player]

    def _observe_time(self, now):
        if now is None:
            now = self._latest_time
        if now >= self._latest_time:
            self._latest_time = now
            self._latest_day = now // self.DAY_SECONDS
        self._prune_requests(now)
        return now

    def _prune_requests(self, now):
        for key, request in list(self.requests.items()):
            expires = request["expires"]
            if expires is not None and now >= expires:
                del self.requests[key]

    def _request_ttl(self):
        for key in (
            "friend_request_ttl",
            "request_ttl",
            "friend_ttl",
            "request_expiry",
        ):
            if key in self.config:
                return self.config[key]
        return self.DEFAULT_REQUEST_TTL

    def _mail_ttl(self):
        for key in ("mail_ttl", "gift_mail_ttl", "mailbox_ttl"):
            if key in self.config:
                return self.config[key]
        return self.DEFAULT_MAIL_TTL

    def _daily_gift_limit(self):
        for key in ("daily_gifts", "daily_limit", "gift_daily_limit"):
            if key in self.config:
                return self.config[key]
        return self.DEFAULT_DAILY_GIFTS

    def _find_mail(self, player, mail_id):
        for mail in self.mails.get(player, ()):
            if mail["mail_id"] == mail_id:
                return mail
        raise ValueError(f"unknown mail: {mail_id}")

    def _expire_mail(self, mail):
        if mail["status"] != "unread":
            return False
        mail["status"] = "expired"
        sender = mail.get("sender")
        if sender in self.players:
            self._add_items(self.players[sender]["items"], mail["items"])
        return True

    @staticmethod
    def _add_items(inventory, items):
        for item, quantity in items.items():
            inventory[item] = inventory.get(item, 0) + quantity
