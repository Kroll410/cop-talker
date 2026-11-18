"""Push-to-talk while an NPC is talking: the player's words are recorded and understood at once, and the answer
comes right after the NPC finishes (nothing is lost, he doesn't have to repeat himself)."""
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker  # noqa: E402

events = []
t = talker.Talker.__new__(talker.Talker)
t.busy, t.recording, t.game_on, t.game_ptt = threading.Lock(), False, True, True
t.game = type("G", (), {"send": lambda self, *a: None, "state": lambda self: {"npcs": [{"id": 1, "name": "Лоцман"}]},
                         "pick_listener": lambda self, s, text: {"id": 1, "name": "Лоцман"}})()
t.ears = type("E", (), {"record_while_held": lambda self, held: events.append(("recorded", time.time())) or b"audio",
                         "transcribe": lambda self, a: events.append(("understood", time.time())) or "Лоцман, ти де був?"})()
t.ptt_held = lambda: False
t.converse = lambda npc, state, text: events.append(("answer to: " + text, time.time()))

npc_talking = threading.Event()


def npc_line():  # an NPC says a 2-second line
    with t.busy:
        npc_talking.set()
        events.append(("NPC starts", time.time()))
        time.sleep(2)
        events.append(("NPC ends", time.time()))


threading.Thread(target=npc_line).start()
npc_talking.wait()
time.sleep(0.3)
t.on_push_to_talk()  # T pressed while he talks
start = events[0][1]
for what, at in events:
    print(f"  {at - start:4.1f}s  {what}")
names = [e[0] for e in events]
ok = names.index("recorded") < names.index("NPC ends") and names.index("answer to: Лоцман, ти де був?") > names.index("NPC ends")
print("OK: recorded during his line, answered after it" if ok else "FAIL")
