import bisect
import copy


class ReplayAnalytics:
    def __init__(self, replays, config=None):
        self.replays = replays
        self.config = config or {}
        self._bookmarks = {}

    def _get_replay(self, replay_id):
        replay = self.replays.get(replay_id)
        if replay is None:
            raise ValueError("unknown replay: {0}".format(replay_id))
        return replay

    def seek(self, replay_id, t):
        replay = self._get_replay(replay_id)
        if t is None or t < 0:
            raise ValueError("seek time must be non-negative")

        duration = replay["duration"]
        clamped = False
        if t > duration:
            t = duration
            clamped = True

        keyframes = replay["keyframes"]
        index = bisect.bisect_right(keyframes, t) - 1
        if index < 0:
            raise ValueError("no keyframe at or before the target time")
        keyframe = keyframes[index]

        result = {
            "t": t,
            "keyframe": keyframe,
            "keyframe_index": index,
            "replay_cost": t - keyframe,
            "clamped": clamped,
        }
        if index + 1 < len(keyframes):
            next_keyframe = keyframes[index + 1]
            result["next_keyframe"] = next_keyframe
            result["time_to_next"] = next_keyframe - t
        else:
            result["next_keyframe"] = None
            result["time_to_next"] = None
        return result

    def bookmark(self, replay_id, bookmark_id, t, note, player):
        replay = self._get_replay(replay_id)
        duration = replay["duration"]
        if t is None or t < 0 or t > duration:
            raise ValueError("bookmark time must be within replay duration")
        if note is None or not str(note).strip():
            raise ValueError("bookmark note must not be empty")

        for entries in self._bookmarks.values():
            if any(entry["bookmark_id"] == bookmark_id for entry in entries):
                raise ValueError("bookmark_id already exists: {0}".format(bookmark_id))

        entries = self._bookmarks.setdefault(replay_id, [])
        cap = self.config.get("max_bookmarks")
        if cap is not None:
            owned = sum(1 for entry in entries if entry["player"] == player)
            if owned >= cap:
                raise ValueError("bookmark limit reached for player: {0}".format(player))

        record = {
            "bookmark_id": bookmark_id,
            "replay_id": replay_id,
            "t": t,
            "note": note,
            "player": player,
        }
        entries.append(record)
        return copy.deepcopy(record)

    def bookmarks(self, replay_id):
        entries = self._bookmarks.get(replay_id, [])
        ordered = sorted(entries, key=lambda entry: entry["t"])
        return copy.deepcopy(ordered)

    def remove_bookmark(self, replay_id, bookmark_id, player):
        entries = self._bookmarks.get(replay_id)
        if not entries:
            raise ValueError("bookmark not found: {0}".format(bookmark_id))
        for index, entry in enumerate(entries):
            if entry["bookmark_id"] == bookmark_id:
                if entry["player"] != player:
                    raise ValueError("only the creator can remove this bookmark")
                del entries[index]
                if not entries:
                    del self._bookmarks[replay_id]
                return True
        raise ValueError("bookmark not found: {0}".format(bookmark_id))

    def heatmap(self, replay_id=None, bucket=None, window=None):
        if bucket is None:
            bucket = self.config.get("bucket", 10)
        if bucket is None or bucket <= 0:
            raise ValueError("bucket must be a positive number")
        if window is not None:
            window_start, window_end = window
            if window_start > window_end:
                raise ValueError("window start must not be greater than end")

        if replay_id is not None:
            replays = {replay_id: self._get_replay(replay_id)}
        else:
            replays = self.replays

        counts = {}
        for replay in replays.values():
            for event in replay.get("events", []):
                if window is not None and not (window_start <= event["t"] < window_end):
                    continue
                if "x" not in event or "y" not in event:
                    continue
                x = event["x"]
                y = event["y"]
                if x is None or y is None:
                    continue
                cell_x = int(x // bucket)
                cell_y = int(y // bucket)
                key = "{0},{1}".format(cell_x, cell_y)
                counts[key] = counts.get(key, 0) + 1
        return counts

    def state(self):
        grouped = {}
        for replay_id, entries in self._bookmarks.items():
            grouped[replay_id] = sorted(
                copy.deepcopy(entries), key=lambda entry: entry["t"]
            )
        return {"bookmarks": copy.deepcopy(grouped)}
