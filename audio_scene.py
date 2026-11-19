import copy
import math


def _is_number(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _is_point(value):
    return (
        isinstance(value, (tuple, list))
        and len(value) == 2
        and all(_is_number(v) for v in value)
    )


def _orientation(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(a, b, p):
    return (
        min(a[0], b[0]) <= p[0] <= max(a[0], b[0])
        and min(a[1], b[1]) <= p[1] <= max(a[1], b[1])
    )


def _segments_intersect(p1, p2, p3, p4):
    d1 = _orientation(p3, p4, p1)
    d2 = _orientation(p3, p4, p2)
    d3 = _orientation(p1, p2, p3)
    d4 = _orientation(p1, p2, p4)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
        return True
    if d1 == 0 and _on_segment(p3, p4, p1):
        return True
    if d2 == 0 and _on_segment(p3, p4, p2):
        return True
    if d3 == 0 and _on_segment(p1, p2, p3):
        return True
    if d4 == 0 and _on_segment(p1, p2, p4):
        return True
    return False


class AudioScene:
    def __init__(self, buses, config=None):
        self.buses = {
            name: {
                "parent": spec.get("parent"),
                "volume": float(spec.get("volume", 1.0)),
                "mute": bool(spec.get("mute", False)),
            }
            for name, spec in buses.items()
        }
        self.config = dict(config or {})
        self.sounds = {}
        self.listener = (0.0, 0.0)
        self.walls = []

    def play(self, sound_id, bus, position=None, loudness=1.0, priority=0):
        if bus not in self.buses:
            raise ValueError("unknown bus: %r" % (bus,))
        if sound_id in self.sounds:
            raise ValueError("duplicate sound id: %r" % (sound_id,))
        if position is not None and not _is_point(position):
            raise ValueError("invalid position: %r" % (position,))

        limit = self.config.get("max_channels")
        if limit is not None:
            on_bus = [
                sid for sid, s in self.sounds.items() if s["bus"] == bus
            ]
            if len(on_bus) >= limit:
                lowest = min(self.sounds[sid]["priority"] for sid in on_bus)
                if priority <= lowest:
                    raise ValueError(
                        "bus %r is full and priority %r is not higher than %r"
                        % (bus, priority, lowest)
                    )
                victim = next(
                    sid
                    for sid in on_bus
                    if self.sounds[sid]["priority"] == lowest
                )
                del self.sounds[victim]

        self.sounds[sound_id] = {
            "bus": bus,
            "position": tuple(float(v) for v in position)
            if position is not None
            else None,
            "loudness": float(loudness),
            "priority": priority,
        }
        return None

    def stop(self, sound_id):
        self.sounds.pop(sound_id, None)
        return None

    def set_bus(self, bus, volume=None, mute=None):
        if bus not in self.buses:
            raise ValueError("unknown bus: %r" % (bus,))
        if volume is not None:
            if not _is_number(volume) or volume < 0:
                raise ValueError("invalid volume: %r" % (volume,))
            self.buses[bus]["volume"] = float(volume)
        if mute is not None:
            self.buses[bus]["mute"] = bool(mute)
        return None

    def update(self, listener, walls=None):
        if not _is_point(listener):
            raise ValueError("invalid listener position: %r" % (listener,))
        self.listener = (float(listener[0]), float(listener[1]))
        if walls is not None:
            parsed = []
            for wall in walls:
                if (
                    not isinstance(wall, (tuple, list))
                    or len(wall) != 2
                    or not _is_point(wall[0])
                    or not _is_point(wall[1])
                ):
                    raise ValueError("invalid wall segment: %r" % (wall,))
                parsed.append(
                    (
                        (float(wall[0][0]), float(wall[0][1])),
                        (float(wall[1][0]), float(wall[1][1])),
                    )
                )
            self.walls = parsed
        return None

    def _bus_chain(self, name):
        chain = []
        node = name
        while node is not None and node in self.buses:
            chain.append(node)
            node = self.buses[node]["parent"]
        return chain

    def _duck_active(self):
        source = self.config.get("duck_source")
        if not source:
            return False
        return any(s["bus"] == source for s in self.sounds.values())

    def _bus_gain(self, name):
        chain = self._bus_chain(name)
        gain = 1.0
        for node in chain:
            spec = self.buses[node]
            if spec["mute"]:
                return 0.0
            gain *= spec["volume"]
        target = self.config.get("duck_target")
        if target and target in chain and self._duck_active():
            gain *= 10.0 ** (self.config.get("duck_db", 0.0) / 20.0)
        return gain

    def _occluded(self, position):
        a = self.listener
        b = position
        for w1, w2 in self.walls:
            if _segments_intersect(a, b, w1, w2):
                return True
        return False

    def _sound_gain(self, sound):
        gain = self._bus_gain(sound["bus"]) * sound["loudness"]
        position = sound["position"]
        if position is not None:
            distance = math.dist(self.listener, position)
            gain *= 1.0 / (1.0 + distance)
            if self._occluded(position):
                gain *= self.config.get("occlusion_floor", 1.0)
        return gain

    def mix(self):
        buses = {name: round(self._bus_gain(name), 4) for name in self.buses}
        active = {
            sid: {
                "gain": round(self._sound_gain(sound), 4),
                "bus": sound["bus"],
                "priority": sound["priority"],
            }
            for sid, sound in self.sounds.items()
        }
        return {"buses": buses, "active": active}

    def state(self):
        return {
            "buses": copy.deepcopy(self.buses),
            "active": copy.deepcopy(self.sounds),
            "listener": tuple(self.listener),
        }
