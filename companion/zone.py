"""Zone events: a Twitch channel-points reward (made by the channel owner, no message) makes something random
happen in the game. Each redemption is rolled at once (so the window can show what's coming), waits in a queue,
and goes off 5-7 minutes after the one before it (and after its own redemption):

  Дар Зони    (25%)  a random item of the game lands in your backpack
  Життя для Зони (50%) a random stalker appears 15-30 m away, half the time a friend who follows you, half an
                     enemy; he wears the viewer's nickname until he dies
  Дитя Зони   (25%)  1-10 mutants of one kind 25-50 m away come for you; weak ones come in packs, strong ones
                     mostly alone (10 pseudogiants: about 1 in 100)

The game script (talker_bridge.script, v14) does the spawning: "zone||<what>|<PDA caption>|<PDA text>".
"""
import json
import random
import re
import threading
from pathlib import Path

KINDS = [("gift", 25), ("life", 50), ("child", 25)]
TITLES = {"gift": "Дар Зони", "life": "Життя для Зони", "child": "Дитя Зони"}

# (name in Ukrainian, game sections (whichever the game has), r): the chance of n of them is r**(n-1), n = 1..10.
# r > 1: packs are likely (tushkans); r = 0.68: ten pseudogiants come about once in 100 pseudogiant events.
# Section names checked against the game's configs (configs.db + patches): only these exist there.
MONSTERS = [
    ("тушкан", ["tushkano_normal"], 1.3),
    ("сліпий пес", ["dog_weak", "dog_normal", "dog_strong"], 1.2),
    ("плоть", ["flesh_normal", "flesh_strong"], 1.1),
    ("кабан", ["boar_normal", "boar_strong"], 0.95),
    ("псевдособака", ["pseudodog_normal"], 0.9),
    ("снорк", ["snork_weak", "snork_normal", "snork_strong"], 0.85),
    ("пси-собака", ["psy_dog_normal", "psy_dog"], 0.75),
    ("кровосос", ["bloodsucker_weak", "bloodsucker_normal", "bloodsucker_strong"], 0.75),
    ("полтергейст", ["m_poltergeist_normal_flame", "m_poltergeist_normal_tele"], 0.75),
    ("бюрер", ["burer_normal"], 0.72),
    ("контролер", ["m_controller_normal"], 0.7),
    ("химера", ["chimera_normal"], 0.7),
    ("псевдогігант", ["gigant_normal"], 0.68),
]
MAX_TRIES = 3


def count_weights(r):
    return [r ** (n - 1) for n in range(1, 11)]


def parse_gap(text):
    """"5-7" (minutes) -> (300, 420) seconds; one number = exactly that."""
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", text or "")] or [5, 7]
    lo, hi = min(nums[0], nums[-1]), max(nums[0], nums[-1])
    return lo * 60, hi * 60


def clean_nick(user):
    return re.sub(r"[|\r\n]", "", str(user or "")).strip() or "Twitch"


def roll(user, kind=None, rng=random):
    """What this redemption will do, decided now."""
    item = {"user": clean_nick(user), "kind": kind or rng.choices([k for k, _ in KINDS], [w for _, w in KINDS])[0]}
    if item["kind"] == "life":
        item["side"] = rng.choice(["ally", "enemy"])
    elif item["kind"] == "child":
        name, sections, r = rng.choice(MONSTERS)
        item.update(monster=name, sections=sections, count=rng.choices(range(1, 11), count_weights(r))[0])
    return item


def label(item):
    """For the window: what's coming."""
    if item["kind"] == "gift":
        return f"{TITLES['gift']}: випадковий предмет"
    if item["kind"] == "life":
        return f"{TITLES['life']}: {'друг' if item['side'] == 'ally' else 'ворог'} «{item['user']}»"
    return f"{TITLES['child']}: {item['monster']} ×{item['count']}"


def command(item):
    """(what, PDA caption, PDA text) for the game's "zone" inbox line."""
    user = item["user"]
    caption = f"{TITLES[item['kind']]} ({user})"
    if item["kind"] == "gift":
        return "gift", caption, "Зона бажає милосердя — отримано {item} в рюкзак"
    if item["kind"] == "life":
        who = f"{user} тепер іде з тобою" if item["side"] == "ally" else f"{user} прийшов по твою душу"
        return f"life:{item['side']}:{user}", caption, f"Зона грає з життям як заманеться — {who}"
    return (f"child:{item['count']}:{','.join(item['sections'])}", caption,
            f"Зона народжує... {item['monster']} ({item['count']})")  # cp1251: no ×


class ZoneQueue:
    """Redemptions waiting their turn. Kept in a file, so a restart of the app doesn't lose paid events."""

    def __init__(self, path: Path, gap=(300, 420), rng=random):
        self.path, self.gap, self.rng = path, gap, rng
        self.items = []
        self.lock = threading.RLock()  # Twitch adds from its own thread
        try:
            self.items = [i for i in json.loads(path.read_text(encoding="utf-8")) if isinstance(i, dict) and "kind" in i]
        except (OSError, ValueError):
            pass

    def save(self):
        try:
            self.path.write_text(json.dumps(self.items, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass

    def wait(self):
        return self.rng.uniform(*self.gap)

    def add(self, user, now, kind=None):
        """A redemption: rolled now, due 5-7 min after the last one waiting (or after now)."""
        with self.lock:
            item = roll(user, kind, self.rng)
            last = max([i["due"] for i in self.items if not i.get("test")] + [now])
            item["due"] = last + self.wait()
            self.items.append(item)
            self.save()
            return item

    def add_test(self, user, now, kind=None):
        """The window's test button: goes off at once, doesn't move the real ones."""
        with self.lock:
            item = roll(user, kind, self.rng)
            item.update(due=now, test=True)
            self.items.insert(0, item)
            return item

    def pop_due(self, now):
        """The event whose time has come (a test first), or None. The next one then waits at least the gap."""
        with self.lock:
            tests = [i for i in self.items if i.get("test")]
            real = [i for i in self.items if not i.get("test")]
            head = next((i for i in tests + real[:1] if i["due"] <= now), None)
            if not head:
                return None
            self.items.remove(head)
            if not head.get("test") and len(real) > 1:
                real[1]["due"] = max(real[1]["due"], now + self.wait())
            self.save()
            return head

    def retry(self, item, now):
        """The game couldn't do it (no room, a section missing): try again soon, a few times, rolled anew."""
        with self.lock:
            item["tries"] = item.get("tries", 0) + 1
            if item["tries"] >= MAX_TRIES:
                return False
            fresh = roll(item["user"], item["kind"], self.rng)
            fresh.update(due=now + 30, tries=item["tries"], test=item.get("test", False))
            if item["kind"] == "life":
                fresh["side"] = item["side"]
            self.items.insert(0, fresh)
            self.save()
            return True

    def summary(self, now):
        with self.lock:
            return [{"label": label(i), "user": i["user"], "in": max(0, int(i["due"] - now)), "test": bool(i.get("test"))}
                    for i in self.items]
