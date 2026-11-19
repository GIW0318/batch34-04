class CameraReplay:
    def __init__(self, colliders, config=None):
        self.colliders = colliders
        self.config = config or {}
        self.rigs = {}
        self.tracks = {}

    def solve(self, target, direction, distance=None):
        return None

    def snap(self, rig_id, target, direction, t):
        return None

    def step(self, rig_id, target, direction, t):
        return None

    def timeline(self, rig_id, lo=0.0, hi=None):
        return []

    def replay_seek(self, rig_id, t):
        return None

    def state(self):
        return {}
import math


class CameraReplay:
    def __init__(self, colliders, config=None):
        self.colliders = colliders
        self.config = config or {}
        self.rigs = {}
        self.tracks = {}
        smooth = self.config.get("smooth")
        if smooth is not None and not (0.0 <= float(smooth) <= 1.0):
            raise ValueError("smooth must be within [0, 1]")

    def _cfg(self, key, default):
        return self.config[key] if key in self.config else default

    def solve(self, target, direction, distance=None):
        if distance is None:
            distance = self._cfg("distance", 6.0)
        if distance is None or distance <= 0:
            raise ValueError("distance must be positive")

        direction = tuple(float(v) for v in direction)
        target = tuple(float(v) for v in target)
        length = math.sqrt(sum(v * v for v in direction))
        if length == 0:
            raise ValueError("direction must not be a zero vector")
        unit = tuple(v / length for v in direction)

        desired = tuple(p + d * distance for p, d in zip(target, unit))
        min_distance = float(self._cfg("min_distance", 1.0))
        padding = float(self._cfg("padding", 0.0))

        nearest = distance
        for collider in self.colliders:
            center = (
                float(collider["x"]),
                float(collider["y"]),
                float(collider["z"]),
            )
            radius = float(collider["r"])
            offset = tuple(c - p for c, p in zip(center, target))
            projection = sum(o * d for o, d in zip(offset, unit))
            perp_sq = sum(o * o for o in offset) - projection * projection
            radius_sq = radius * radius
            if perp_sq > radius_sq:
                continue
            half_chord = math.sqrt(max(0.0, radius_sq - perp_sq))
            near = projection - half_chord
            far = projection + half_chord
            if far <= 0:
                continue
            stop = max(near, 0.0) - padding
            if stop < min_distance:
                stop = min_distance
            if stop < nearest:
                nearest = stop

        return tuple(p + d * nearest for p, d in zip(target, unit))

    def _record(self, rig_id, t, position):
        track = self.tracks.setdefault(rig_id, [])
        entry = {"t": t, "position": list(position)}
        if track and track[-1]["t"] == t:
            track[-1] = entry
        else:
            track.append(entry)
        self.rigs[rig_id] = tuple(position)

    def snap(self, rig_id, target, direction, t):
        position = self.solve(target, direction)
        self._record(rig_id, t, position)
        return tuple(position)

    def step(self, rig_id, target, direction, t):
        desired = self.solve(target, direction)
        if rig_id not in self.rigs:
            position = tuple(desired)
        else:
            smooth = float(self._cfg("smooth", 1.0))
            current = self.rigs[rig_id]
            position = tuple(
                cur + (dst - cur) * smooth
                for cur, dst in zip(current, desired)
            )
        self._record(rig_id, t, position)
        return tuple(position)

    def timeline(self, rig_id, lo=0.0, hi=None):
        track = self.tracks.get(rig_id, [])
        entries = [entry for entry in track if entry["t"] >= lo
                   and (hi is None or entry["t"] <= hi)]
        return [
            {"t": entry["t"], "position": list(entry["position"])}
            for entry in entries
        ]

    def replay_seek(self, rig_id, t):
        track = self.tracks.get(rig_id, [])
        if not track or t < track[0]["t"]:
            raise ValueError("seek time is earlier than the first record")
        chosen = track[0]
        for entry in track:
            if entry["t"] <= t:
                chosen = entry
            else:
                break
        position = tuple(chosen["position"])
        self.rigs[rig_id] = position
        return list(position)

    def state(self):
        return {
            "rigs": {
                rig_id: {"position": list(position)}
                for rig_id, position in self.rigs.items()
            },
            "tracks": {
                rig_id: [
                    {"t": entry["t"], "position": list(entry["position"])}
                    for entry in track
                ]
                for rig_id, track in self.tracks.items()
            },
        }
