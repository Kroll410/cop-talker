"""The Skadovsk case: "$гайз ви чули...?" from Twitch, voiced by one stalker; the others (no squads) answer."""
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker  # noqa: E402

men = [{"id": i, "name": n, "community": "stalker", "rank": r, "dist": d}
       for i, (n, r, d) in enumerate([("Гармата", 300, 3), ("Саня Макарон", 500, 5), ("Лоцман", 200, 7),
                                      ("Жорка", 400, 9)], 1)]
state = {"level": "zaton", "npcs": men}
spoken, asked = [], {}

t = talker.Talker.__new__(talker.Talker)
t.busy, t.recording, t.twitch, t.twitch_queue = threading.Lock(), False, None, []
t.game = type("G", (), {"send": lambda self, *a: None})()
t.memory = type("M", (), {"remembers": lambda self, k: "", "add": lambda self, *a: None})()
t.npc_key = lambda n, s: f"k{n['id']}"
t.gesture = lambda *a: None
t.speak = lambda npc, line, *a, **k: spoken.append((npc["name"], line, k.get("aside", False)))
brain = type("B", (), {})()
brain.last_extras = []


def group(men_, state_, said, speaker, **k):
    asked.update(men=[m["name"] for m in men_], said=said, speaker=speaker)
    return [(men_[0], "Та чув, брехня то все.", [], False), (men_[1], "Мічений вічний.", [], True)]


brain.group = group
t.brain = brain
talker.random.uniform = lambda a, b: 0
talker.time.sleep = lambda s: None

t._twitch_line(men[0], state, ("viewer", "гайз ви чули шо на болотах мічений після викиду вижив?", None, "verbatim"))
print("voiced by:", spoken[0][0])
print("group asked:", asked.get("men"), "| speaker:", asked.get("speaker"))
print("answers:", [(n, l, "aside" if a else "answer") for n, l, a in spoken[1:]])
ok = asked and "Гармата" not in asked["men"] and len(spoken) == 3
print("OK" if ok else "FAIL")
