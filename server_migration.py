class ServerMigration:
    def __init__(self, servers, characters, config=None):
        self.servers = servers
        self.characters = characters
        self.config = config or {}
        self.transfers = {}
        self.mailboxes = {}

    def request(self, transfer_id, character, target, now, ttl=60):
        return None

    def confirm(self, transfer_id, now):
        return None

    def cancel(self, transfer_id, now):
        return None

    def expire(self, now):
        return None

    def claim(self, character, mail_id, now):
        return None

    def mailbox(self, character):
        return []

    def state(self):
        return {}
