"""Zone events: a Twitch channel-points reward (made by the channel owner, no message) makes something random
happen in the game. Each redemption is rolled at once (so the window can show what's coming) and goes into a queue. The first one in the queue
goes off at once; the ones behind it each wait 5-7 minutes (TWITCH_ZONE_GAP) after the one before. Gap 0: all at
once, no waiting:

  Дар Зони    (25%)  a random item of the game lands in your backpack
  Життя для Зони (50%) a stalker appears 15-30 m away: half the time a friend who follows you (always a Loner),
                     half an enemy of any faction; he wears the viewer's nickname until he dies
  Дитя Зони   (25%)  mutants of one kind 25-50 m away come for you: mostly one or two; weak kinds come more
                     often and in bigger packs than strong ones (table MONSTERS, at most TWITCH_ZONE_PACK_MAX)

Each PDA line shows the chance of what happened ("шанс 25%"), from the same weights that rolled it. Mutants are
rolled in two steps, who comes and then how many, and the line shows both, each out of its own 100%: which kind of all mutants ("бюрер (шанс 1%)"),
then how many of that kind ("кількість 1 (шанс 95%)"), and last the two multiplied, the chance of exactly that
pack among mutant events: "шанс саме «бюрер (1)»: 0.95%". Тушкан comes up to 10 (OWN_MAX), the rest up to
TWITCH_ZONE_PACK_MAX.
"python tools/zone_sim.py" checks every chance against a million real rolls.
Run "python companion/zone.py [pack max]" to see the odds in plain numbers.

The game script (talker_bridge.script, v14) does the spawning: "zone||<what>|<PDA caption>|<PDA text>".
"""
import json
import math
import random
import re
import threading
from pathlib import Path

KINDS = [("gift", 25), ("life", 50), ("child", 25)]
TITLES = {"gift": "Дар Зони", "life": "Життя для Зони", "child": "Дитя Зони"}

# Дитя Зони, all its odds in one table:
#   name in Ukrainian, game sections (whichever the game has; checked against its configs),
#   weight: how often this kind comes (share = weight / sum of weights),
#   r: pack size: each extra mutant is r times as likely as one fewer (r 0.5: half as likely; smaller = smaller packs).
# Weak kinds come often and sometimes in packs; dangerous ones seldom, almost always alone.
# "python companion/zone.py" prints the resulting odds.
# Weights add up to 100, so each is the kind's % of Дитя Зони. Balanced (tools/zone_sim.py shows it) so that a lone
# burer, controller, chimera or pseudogiant is rarer than even three blind dogs, and each extra mutant cuts the odds
# by at least half (weak kinds) up to twentyfold (the most dangerous ones).
MONSTERS = [
    # name            sections                                                      weight  r
    ("тушкан",        ["tushkano_normal"],                                             22, 0.4),
    ("сліпий пес",    ["dog_weak", "dog_normal", "dog_strong"],                        22, 0.4),
    ("плоть",         ["flesh_normal", "flesh_strong"],                                18, 0.35),
    ("кабан",         ["boar_normal", "boar_strong"],                                  10, 0.25),
    ("снорк",         ["snork_weak", "snork_normal", "snork_strong"],                   9, 0.25),
    ("псевдособака",  ["pseudodog_normal"],                                             7, 0.25),
    ("пси-собака",    ["psy_dog_normal", "psy_dog"],                                  3.5, 0.12),
    ("полтергейст",   ["m_poltergeist_normal_flame", "m_poltergeist_normal_tele"],    3.5, 0.12),
    ("кровосос",      ["bloodsucker_weak", "bloodsucker_normal", "bloodsucker_strong"], 2.5, 0.1),
    ("бюрер",         ["burer_normal"],                                                 1, 0.05),
    ("контролер",     ["m_controller_normal"],                                        0.6, 0.05),
    ("химера",        ["chimera_normal"],                                             0.6, 0.05),
    ("псевдогігант",  ["gigant_normal"],                                              0.3, 0.05),
]
MAX_TRIES = 3


PACK_MAX = 6  # default for TWITCH_ZONE_PACK_MAX: the most mutants one event may bring (the game allows 10)
OWN_MAX = {"тушкан": 10}  # kinds with their own most per event, whatever TWITCH_ZONE_PACK_MAX says


def most(monster, pack_max=PACK_MAX):
    """The most of this kind one event may bring: its own (OWN_MAX) or TWITCH_ZONE_PACK_MAX, never over 10."""
    return max(1, min(10, OWN_MAX.get(monster, pack_max)))


def count_weights(r, pack_max=PACK_MAX):
    """Pack size n = 1..pack_max; each extra mutant is r times as likely as one fewer (r < 1: drops steeply)."""
    return [r ** (n - 1) for n in range(1, max(1, min(10, pack_max)) + 1)]


def pct(p):
    """0.0412 -> "4.1%": whole numbers from 10% up, one decimal from 1%; under 1% two significant digits, so a
    rare event reads true and never "0.00%" (0.0025 -> "0.25%", 0.0000059 -> "0.00059%"). Same as zone_pct in the game."""
    x = p * 100
    if x >= 9.95:
        return f"{x:.0f}%"
    if x >= 0.995:
        return f"{x:.1f}%"
    if x <= 0:
        return "0.00%"
    return f"{x:.{1 - math.floor(math.log10(x))}f}".rstrip("0").rstrip(".") + "%"


def who_chance(monster):
    """Дитя Зони, step 1: once it's a mutant event, how likely this kind is (0..1): its weight share; all kinds
    together make 100%."""
    m = next((m for m in MONSTERS if m[0] == monster), None)
    return m[2] / sum(x[2] for x in MONSTERS) if m else 1.0


def count_chance(monster, count, pack_max=PACK_MAX):
    """Дитя Зони, step 2: once the kind is rolled, how likely exactly this many of them are (0..1)."""
    m = next((m for m in MONSTERS if m[0] == monster), None)
    if not m:
        return 1.0
    w = count_weights(m[3], most(monster, pack_max))
    return w[count - 1] / sum(w) if 1 <= count <= len(w) else 0.0


def chance(item, pack_max=PACK_MAX):
    """How likely this exact outcome was when it was rolled (0..1). Gift: the chance of a gift at all (the game
    picks the item and divides it by the number of items it has). Mutants: 25% x who x how many."""
    kinds = dict(KINDS)
    p = kinds[item["kind"]] / sum(kinds.values())
    if item["kind"] == "life":
        return p / 2
    if item["kind"] == "child":
        if not any(m[0] == item.get("monster") for m in MONSTERS):
            return p
        return p * who_chance(item["monster"]) * count_chance(item["monster"], item.get("count", 1), pack_max)
    return p


def odds_report(pack_max=PACK_MAX):
    """The odds in plain numbers, for tuning MONSTERS / TWITCH_ZONE_PACK_MAX."""
    total = sum(m[2] for m in MONSTERS)
    sizes = [0.0] * max(most(m[0], pack_max) for m in MONSTERS)
    lines = [f"Дитя Зони, at most {most('', pack_max)} mutants ({', '.join(f'{k}: {v}' for k, v in OWN_MAX.items())}):",
             "  kind            this kind   1-2    3-4    5+"]
    for name, _, weight, r in MONSTERS:
        w = count_weights(r, most(name, pack_max))
        share = [x / sum(w) for x in w]
        for i, s in enumerate(share):
            sizes[i] += weight / total * s
        lines.append(f"  {name:<15} {weight / total * 100:5.1f}%   {sum(share[:2]) * 100:4.0f}%  "
                     f"{sum(share[2:4]) * 100:4.0f}%  {sum(share[4:]) * 100:4.1f}%")
    lines.append("  all kinds together: 1-2: {}, 3-4: {}, 5+: {}".format(
        pct(sum(sizes[:2])), pct(sum(sizes[2:4])), pct(sum(sizes[4:]))))
    lines.append("  by count: " + ", ".join(f"{n}: {pct(s)}" for n, s in enumerate(sizes, 1)))
    return "\n".join(lines)


def parse_gap(text):
    """"5-7" (minutes) -> (300, 420) seconds; one number = exactly that; "0" = no waiting at all."""
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", text or "")] or [5, 7]
    lo, hi = min(nums[0], nums[-1]), max(nums[0], nums[-1])
    return lo * 60, hi * 60


def clean_nick(user):
    return re.sub(r"[|\r\n]", "", str(user or "")).strip() or "Twitch"


def roll(user, kind=None, rng=random, pack_max=PACK_MAX):
    """What this redemption will do, decided now (with its chance, for the PDA line)."""
    item = {"user": clean_nick(user), "kind": kind or rng.choices([k for k, _ in KINDS], [w for _, w in KINDS])[0]}
    if item["kind"] == "life":
        item["side"] = rng.choice(["ally", "enemy"])
    elif item["kind"] == "child":
        # first who comes, then how many of them: two rolls, each with its own chance (each out of 100%) in the PDA
        name, sections, _, r = rng.choices(MONSTERS, [m[2] for m in MONSTERS])[0]
        item.update(monster=name, sections=sections)
        w = count_weights(r, most(name, pack_max))
        item["count"] = rng.choices(range(1, len(w) + 1), w)[0]
        item["count_chance"] = count_chance(name, item["count"], pack_max)
    item["chance"] = chance(item, pack_max)
    return item


def child_chances(item):
    """(who, how many) chances of a mutant event, each out of its own 100%: which kind of all mutant kinds, and
    how many of that kind. The pack's chance is kept from its roll (it depends on TWITCH_ZONE_PACK_MAX)."""
    who = who_chance(item.get("monster"))
    many = item.get("count_chance") or count_chance(item.get("monster"), item.get("count", 1))
    return who, many


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
        # the game fills in the item and its chance: this one in 25% / (items it has)
        return "gift", caption, "Зона бажає милосердя — отримано {item} в рюкзак (шанс {chance:%g})" % (
            dict(KINDS)["gift"] / sum(dict(KINDS).values()) * 100)
    if item["kind"] == "life":
        who = f"{user} тепер іде з тобою" if item["side"] == "ally" else f"{user} прийшов по твою душу"
        return (f"life:{item['side']}:{user}", caption,
                f"Зона грає з життям як заманеться — {who} (шанс {pct(item.get('chance') or chance(item))})")
    who, many = child_chances(item)
    return (f"child:{item['count']}:{','.join(item['sections'])}", caption,  # cp1251: no ×
            f"Зона народжує... {item['monster']} (шанс {pct(who)}), кількість {item['count']} (шанс {pct(many)}) — "
            f"шанс саме «{item['monster']} ({item['count']})»: {pct(who * many)}")  # who x how many, of mutant events


class ZoneQueue:
    """Redemptions waiting their turn. Kept in a file, so a restart of the app doesn't lose paid events."""

    def __init__(self, path: Path, gap=(300, 420), rng=random, pack_max=PACK_MAX):
        self.path, self.gap, self.rng, self.pack_max = path, gap, rng, pack_max
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
        """A redemption: rolled now. First in the queue: due at once; behind others: 5-7 min after the last."""
        with self.lock:
            item = roll(user, kind, self.rng, self.pack_max)
            waiting = [i["due"] for i in self.items if not i.get("test")]
            item["due"] = max(max(waiting) + self.wait(), now) if waiting else now
            self.items.append(item)
            self.save()
            return item

    def add_test(self, user, now, kind=None):
        """The window's test button: goes off at once, doesn't move the real ones."""
        with self.lock:
            item = roll(user, kind, self.rng, self.pack_max)
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
            fresh = roll(item["user"], item["kind"], self.rng, self.pack_max)
            fresh.update(due=now + 30, tries=item["tries"], test=item.get("test", False))
            if item["kind"] == "life":
                fresh["side"] = item["side"]
            self.items.insert(0, fresh)
            self.save()
            return True

    def summary(self, now):
        with self.lock:
            return [{"label": label(i) + ("" if i.get("kind") == "gift" else
                                          " ({}, {})".format(*map(pct, child_chances(i))) if i.get("kind") == "child"
                                          else f" ({pct(i['chance'])})" if i.get("chance") else ""),
                     "user": i["user"], "in": max(0, int(i["due"] - now)), "test": bool(i.get("test"))}
                    for i in self.items]


if __name__ == "__main__":
    import sys
    print(odds_report(int(sys.argv[1]) if len(sys.argv) > 1 else PACK_MAX))
