import copy


class WorldEventChain:
    def __init__(self, phases, quests):
        self._phases = [dict(phase) for phase in phases]
        self._quests = [dict(quest) for quest in quests]
        self._quest_index = {
            quest["id"]: index for index, quest in enumerate(self._quests)
        }
        self._phase = 0
        self._progress = 0
        self._players = {}

    def join(self, player):
        if not isinstance(player, str) or not player.strip():
            raise ValueError("player name must not be blank")
        if player in self._players:
            raise ValueError("player has already joined")
        self._players[player] = {
            "tokens": 0,
            "completed": [],
            "claimed": [],
        }

    def complete_quest(self, player, quest_id):
        participant = self._require_player(player)
        try:
            quest_index = self._quest_index[quest_id]
        except (KeyError, TypeError):
            raise ValueError("quest does not exist")

        if quest_id in participant["completed"]:
            raise ValueError("quest has already been completed")
        if len(participant["completed"]) != quest_index:
            raise ValueError("quests must be completed in order")

        quest = self._quests[quest_index]
        if quest["phase"] > self._phase:
            raise ValueError("quest phase is not unlocked")

        participant["completed"].append(quest_id)
        participant["tokens"] += quest["tokens"]
        self._progress += quest["goal"]
        self._advance_phases()

        return {
            "tokens": quest["tokens"],
            "phase": self._phase,
            "progress": self._progress,
        }

    def phase(self):
        return self._phase

    def progress(self):
        return self._progress

    def claim_phase(self, player, phase_index):
        participant = self._require_player(player)
        if (
            not isinstance(phase_index, int)
            or isinstance(phase_index, bool)
            or phase_index < 0
            or phase_index >= len(self._phases)
        ):
            raise ValueError("invalid phase index")
        if phase_index >= self._phase:
            raise ValueError("phase has not been completed")
        if phase_index in participant["claimed"]:
            raise ValueError("phase reward has already been claimed")

        reward = self._phases[phase_index]["tokens"]
        participant["claimed"].append(phase_index)
        participant["claimed"].sort()
        participant["tokens"] += reward
        return reward

    def balance(self, player):
        return self._require_player(player)["tokens"]

    def state(self):
        return copy.deepcopy(
            {
                "phase": self._phase,
                "progress": self._progress,
                "players": self._players,
            }
        )

    def _require_player(self, player):
        try:
            return self._players[player]
        except (KeyError, TypeError):
            raise ValueError("player has not joined") from None

    def _advance_phases(self):
        while (
            self._phase < len(self._phases)
            and self._progress >= self._phases[self._phase]["goal"]
        ):
            self._progress -= self._phases[self._phase]["goal"]
            self._phase += 1
