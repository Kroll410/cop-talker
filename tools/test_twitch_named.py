"""Twitch message naming a nearby stalker: someone else says it, the named one answers (real Gemini, voice mocked)."""
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker  # noqa: E402

out = open(Path(__file__).resolve().parent.parent / "test_result.txt", "w", encoding="utf-8")
said = []
t = talker.Talker.__new__(talker.Talker)
t.busy, t.recording, t.twitch, t.twitch_queue, t.next_twitch_note, t.spoken = threading.Lock(), False, None, [], 0, []
t.brain = talker.Brain()
t.game = type("G", (), {"send": lambda self, *a: said.append(("GAME",) + a), "distance_to": lambda self, i: 3})()
t.voice = type("V", (), {"say": lambda self, npc, line, current_dist=None, on_start=None: (
    on_start and on_start(), said.append((npc["name"], line)))})()
v = "characters_voice\human_01\stalker\\"
lots = {"id": 1, "name": "Лоцман", "community": "stalker", "rank": 400, "relation": "friend", "dist": 4, "voice": v}
kost = {"id": 2, "name": "Кастет", "community": "stalker", "rank": 300, "relation": "neutral", "dist": 6, "voice": v}
state = {"level": "zaton", "hours": 14, "weather": "clear", "actor": {}, "npcs": [lots, kost]}

for msg, npcs in [("$Лоцмане, ти чого такий смурний сьогодні?", [lots, kost]),
                  ("%Скажи Лоцману, що він винен 500 купонів", [lots, kost]),
                  ("$Лоцман, ти найкращий сталкер Зони!", [lots]),
                  ("$Всім привіт від чату!", [lots, kost])]:
    said.clear()
    t.on_twitch("test_viewer", msg, None)
    t.twitch_speak(dict(state, npcs=npcs))
    time.sleep(0.2)
    while t.busy.locked():
        time.sleep(0.2)
    out.write(f"\n{msg}  (near: {', '.join(n['name'] for n in npcs)})\n")
    for s in said:
        if s[0] != "GAME" or s[1] in ("twitch", "say"):
            out.write(f"   {s}\n")
out.close()
