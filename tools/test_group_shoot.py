"""Twitch: "$хлопці, хто в мене вистрілить даю 300 рублів" said by one stalker; do the others shoot him?"""
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker  # noqa: E402

talker.MEMORY_FILE = Path(tempfile.mkdtemp()) / "memory.json"
out = open(Path(__file__).resolve().parent.parent / "test_result.txt", "w", encoding="utf-8")
sent, said = [], []
t = talker.Talker.__new__(talker.Talker)
t.busy, t.recording, t.twitch, t.twitch_queue, t.next_twitch_note, t.spoken = threading.Lock(), False, None, [], 0, []
t.brain, t.memory = talker.Brain(), talker.Memory()
t.game = type("G", (), {"send": lambda self, *a: sent.append(a), "distance_to": lambda self, i: 3,
                        "last_used_npc": (None, 0)})()
t.voice = type("V", (), {"say": lambda self, npc, line, current_dist=None, on_start=None: said.append((npc["name"], line))})()
v = "characters_voice\human_0%d\%s\\"
men = [{"id": 1, "name": "Лоцман", "community": "stalker", "rank": 400, "relation": "friend", "dist": 4, "voice": v % (1, "stalker")},
       {"id": 2, "name": "Кастет", "community": "stalker", "rank": 300, "relation": "neutral", "dist": 6, "voice": v % (2, "stalker")},
       {"id": 3, "name": "Сивий", "community": "bandit", "rank": 300, "relation": "neutral", "dist": 8, "voice": v % (3, "bandit")},
       {"id": 4, "name": "Гнилий", "community": "bandit", "rank": 200, "relation": "neutral", "dist": 7, "voice": v % (1, "bandit")}]
state = {"level": "zaton", "hours": 20, "weather": "clear", "actor": {}, "npcs": men}
for run in range(3):
    said.clear(); sent.clear()
    t.on_twitch("PhillHess", "$хлопці, хто в мене вистрілить даю 300 рублів", None)
    t.twitch_speak(state)
    time.sleep(0.3)
    while t.busy.locked():
        time.sleep(0.2)
    out.write(f"\nrun {run + 1}\n" + "\n".join(f"   {n}: {l}" for n, l in said) + "\n")
    out.write("   game: " + "; ".join(f"{a[0]} {a[1]} {a[2]}" for a in sent if a[0] in ("act", "info")) + "\n")
out.close()
