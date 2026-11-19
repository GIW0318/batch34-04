class SpawnQuest:
    def __init__(self, zones, quests, players):
        self.zones = zones
        self.quests = quests
        self.players = players
        self.alive = {}
        self.progress = {player: {} for player in players}
        self.zone_used = {zone: 0 for zone in zones}

    def _player(self, player):
        if player not in self.players:
            raise ValueError(f"unknown player: {player}")
        self.progress.setdefault(player, {})
        return self.players[player]

    def _release(self, spawn_id):
        if spawn_id not in self.alive:
            raise ValueError(f"unknown spawn id: {spawn_id}")
        spawn = self.alive.pop(spawn_id)
        self.zone_used[spawn["zone"]] -= spawn["cost"]
        return spawn

    def spawn(self, zone, spawn_id, monster, now):
        if spawn_id in self.alive:
            raise ValueError(f"duplicate spawn id: {spawn_id}")
        if zone not in self.zones:
            raise ValueError(f"unknown zone: {zone}")

        zone_config = self.zones[zone]
        if monster not in zone_config["monsters"]:
            raise ValueError(f"unknown monster: {monster}")

        monster_config = zone_config["monsters"][monster]
        cost = monster_config["cost"]
        if self.zone_used[zone] + cost > zone_config["budget"]:
            raise ValueError(f"zone budget exceeded: {zone}")

        alive_in_zone = sum(
            1 for spawn in self.alive.values() if spawn["zone"] == zone
        )
        if alive_in_zone >= zone_config["max_alive"]:
            raise ValueError(f"zone alive cap reached: {zone}")

        self.alive[spawn_id] = {
            "spawn_id": spawn_id,
            "zone": zone,
            "monster": monster,
            "cost": cost,
            "time": now,
        }
        self.zone_used[zone] += cost

    def kill(self, spawn_id, killer, now):
        if spawn_id not in self.alive:
            raise ValueError(f"unknown spawn id: {spawn_id}")
        player = self._player(killer)

        spawn = self._release(spawn_id)
        monster_config = self.zones[spawn["zone"]]["monsters"][spawn["monster"]]

        items = player.setdefault("items", {})
        for item, amount in monster_config.get("loot", {}).items():
            items[item] = items.get(item, 0) + amount

        for quest_id, progress in self.progress[killer].items():
            if progress["status"] != "in_progress":
                continue
            quest = self.quests[quest_id]
            if (
                quest["zone"] == spawn["zone"]
                and quest["monster"] == spawn["monster"]
                and progress["progress"] < quest["count"]
            ):
                progress["progress"] += 1

    def despawn(self, spawn_id, now):
        self._release(spawn_id)

    def accept(self, player, quest_id, now):
        self._player(player)
        if quest_id not in self.quests:
            raise ValueError(f"unknown quest: {quest_id}")
        if quest_id in self.progress[player]:
            raise ValueError(f"quest already accepted: {quest_id}")

        self.progress[player][quest_id] = {
            "progress": 0,
            "status": "in_progress",
            "accepted_at": now,
        }

    def abandon(self, player, quest_id):
        self._player(player)
        progress = self.progress[player].get(quest_id)
        if progress is None or progress["status"] != "in_progress":
            raise ValueError(f"quest not in progress: {quest_id}")
        del self.progress[player][quest_id]

    def turn_in(self, player, quest_id, now):
        player_data = self._player(player)
        if quest_id not in self.quests:
            raise ValueError(f"unknown quest: {quest_id}")

        progress = self.progress[player].get(quest_id)
        if progress is None or progress["status"] != "in_progress":
            raise ValueError(f"quest not in progress: {quest_id}")

        quest = self.quests[quest_id]
        if progress["progress"] < quest["count"]:
            raise ValueError(f"quest objectives not met: {quest_id}")

        progress["status"] = "completed"
        player_data["gold"] = player_data.get("gold", 0) + quest["reward"]

    def objectives(self, player):
        self._player(player)
        objectives = []
        for quest_id in sorted(self.progress[player]):
            progress = self.progress[player][quest_id]
            quest = self.quests[quest_id]
            objectives.append(
                {
                    "quest_id": quest_id,
                    "target": quest["monster"],
                    "progress": progress["progress"],
                    "required": quest["count"],
                    "status": progress["status"],
                }
            )
        return objectives

    def state(self):
        zones = {}
        for zone_id, zone_config in self.zones.items():
            zones[zone_id] = {
                "used": self.zone_used[zone_id],
                "budget": zone_config["budget"],
                "max_alive": zone_config["max_alive"],
                "alive": sorted(
                    spawn_id
                    for spawn_id, spawn in self.alive.items()
                    if spawn["zone"] == zone_id
                ),
            }

        players = {}
        for player_id, player_data in self.players.items():
            players[player_id] = {
                "gold": player_data.get("gold", 0),
                "items": dict(player_data.get("items", {})),
                "quests": {
                    quest_id: {
                        "progress": progress["progress"],
                        "required": self.quests[quest_id]["count"],
                        "status": progress["status"],
                    }
                    for quest_id, progress in sorted(
                        self.progress.get(player_id, {}).items()
                    )
                },
            }
        return {"zones": zones, "players": players}
