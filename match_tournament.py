class MatchTournament:
    def __init__(self, window=100, champion_reward=100, runner_up_reward=50, semi_reward=20):
        self.window = window
        self.champion_reward = champion_reward
        self.runner_up_reward = runner_up_reward
        self.semi_reward = semi_reward

        self.queue = []
        self.ratings = {}
        self.registered = set()
        self.matches = {}
        self.match_order = []
        self._match_counter = 0

        self.started = False
        self.finished = False
        self.rounds = []
        self.champion = None
        self.rewards = {}

    def _ensure_mutation_allowed(self):
        if self.finished:
            raise ValueError("tournament has finished; only queries are allowed")

    def enqueue(self, player, rating):
        self._ensure_mutation_allowed()
        if not isinstance(player, str) or not player.strip():
            raise ValueError("player name must be a non-blank string")
        if isinstance(rating, bool) or not isinstance(rating, (int, float)) or rating < 0:
            raise ValueError("rating must be a non-negative number")
        if player in self.registered:
            raise ValueError("player is already registered")

        self.registered.add(player)
        self.ratings[player] = rating
        self.queue.append(player)
        return None

    def leave(self, player):
        self._ensure_mutation_allowed()
        if player not in self.queue:
            raise ValueError("player is not in the queue")
        self.queue.remove(player)
        return None

    def pair(self):
        self._ensure_mutation_allowed()
        formed = []
        remaining = list(self.queue)
        self.queue = []

        while remaining:
            player = remaining.pop(0)
            opponent = None
            for candidate in remaining:
                if abs(self.ratings[player] - self.ratings[candidate]) <= self.window:
                    opponent = candidate
                    break
            if opponent is None:
                self.queue.append(player)
                continue

            remaining.remove(opponent)
            self._match_counter += 1
            match_id = "m%d" % self._match_counter
            self.matches[match_id] = {"a": player, "b": opponent, "winner": None}
            self.match_order.append(match_id)
            formed.append((player, opponent))

        return formed

    def start(self):
        self._ensure_mutation_allowed()
        if self.queue:
            raise ValueError("queue must be empty before the tournament can start")
        first_round = list(self.match_order)
        match_count = len(first_round)
        if match_count == 0 or (match_count & (match_count - 1)) != 0:
            raise ValueError("first round match count must be a power of two")

        round_count = match_count.bit_length()
        self.rounds = [first_round]
        self.rounds.extend([] for _ in range(round_count - 1))
        self.started = True
        return {"size": match_count * 2, "rounds": round_count}

    def _round_index_of(self, match_id):
        for index, round_matches in enumerate(self.rounds):
            if match_id in round_matches:
                return index
        raise ValueError("unknown match: %s" % match_id)

    def report(self, match_id, winner):
        self._ensure_mutation_allowed()
        if not self.started:
            raise ValueError("tournament has not started")
        match = self.matches.get(match_id)
        if match is None:
            raise ValueError("unknown match: %s" % match_id)
        if match["winner"] is not None:
            raise ValueError("match already has a winner")
        if winner not in (match["a"], match["b"]):
            raise ValueError("winner must be one of the match participants")

        match["winner"] = winner
        round_index = self._round_index_of(match_id)
        round_matches = self.rounds[round_index]
        round_complete = all(self.matches[mid]["winner"] is not None for mid in round_matches)

        if not round_complete:
            return None

        if round_index == len(self.rounds) - 1:
            self.champion = winner
            self.finished = True
            self._settle_rewards(round_matches)
            return None

        next_round = []
        for index in range(0, len(round_matches), 2):
            first_winner = self.matches[round_matches[index]]["winner"]
            second_winner = self.matches[round_matches[index + 1]]["winner"]
            self._match_counter += 1
            next_id = "m%d" % self._match_counter
            self.matches[next_id] = {"a": first_winner, "b": second_winner, "winner": None}
            self.match_order.append(next_id)
            next_round.append(next_id)
        self.rounds[round_index + 1] = next_round
        return None

    def _settle_rewards(self, final_matches):
        final_id = final_matches[0]
        final = self.matches[final_id]
        champion = final["winner"]
        runner_up = final["b"] if final["a"] == champion else final["a"]

        semi_losers = []
        if len(self.rounds) >= 2:
            semi_round = self.rounds[-2]
            for semi_id in semi_round:
                semi = self.matches[semi_id]
                semi_losers.append(semi["b"] if semi["a"] == semi["winner"] else semi["a"])

        for player in self.registered:
            if player == champion:
                self.rewards[player] = self.champion_reward
            elif player == runner_up:
                self.rewards[player] = self.runner_up_reward
            elif player in semi_losers:
                self.rewards[player] = self.semi_reward
            else:
                self.rewards[player] = 0

    def reward(self, player):
        if player not in self.registered:
            raise ValueError("unknown player: %s" % player)
        return self.rewards.get(player, 0)

    def state(self):
        import copy

        return {
            "queue": copy.deepcopy(self.queue),
            "matches": copy.deepcopy(self.matches),
            "bracket": {
                "rounds": copy.deepcopy(self.rounds),
                "champion": self.champion,
                "finished": self.finished,
            },
        }
