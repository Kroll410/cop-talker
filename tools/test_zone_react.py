"""Men nearby react out loud to a Zone event (companion/talker.py zone_react), offline with a fake AI and voice:
who may react (near, not wounded, not an enemy, not Monolith, not fighting unless it's a fight), the friend the
Zone sent greets first, the second man hears the first, one reaction per cooldown, also in chat-only mode."""
import random
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "companion"))
import talker  # noqa: E402

ok = True


def check(cond, what):
    global ok
    ok &= bool(cond)
    print(("ok   " if cond else "FAIL ") + what)


def npc(i, name, dist=5, **kw):
    return dict(dict(id=i, name=name, dist=dist, relation="neutral", community="stalker"), **kw)


NPCS = [npc(1, "Борода", 6), npc(2, "Ворог", 5, relation="enemy"), npc(3, "Моноліт", 4, community="monolith"),
        npc(4, "Поранений", 3, wounded=True), npc(5, "Далекий", 45), npc(6, "Боєць", 8, in_combat=True)]
asked, spoken = [], []
t = talker.Talker.__new__(talker.Talker)
t.busy = threading.Lock()
t.ZONE_REACT_DELAY = 0
state = {"npcs": NPCS}
t.game = type("G", (), {"state": lambda self: state})()
t.brain = type("B", (), {"reply": lambda self, n, s, e, h, p, mode=None, extra=None, **k: (
    asked.append((n.get("name"), mode, extra["what"])) or f"Ого, {n.get('name')} бачив!")})()
t.speak = lambda n, line, s=None, **k: spoken.append((n.get("name"), line))


def react(kind, ev, spawned=None):
    asked.clear()
    spoken.clear()
    t.next_zone_react = 0
    t.zone_react(kind, ev, spawned, background=False)


random.seed(1)
react("gift", {"name": "Аптечка", "section": "medkit"})
check([s[0] for s in spoken] == ["Борода"], f"gift: only the man who may react does {spoken}")
check(asked and asked[0][1] == "react" and "Аптечка" in asked[0][2] and "gift of the Zone" in asked[0][2],
      f"he is told what happened {asked[:1]}")

t.zone_react("gift", {"name": "x"}, background=False)
check(len(spoken) == 1, "a second event right after: no second reaction (cooldown)")

state["npcs"] = NPCS + [npc(7, "Сусід", 10)]
for seed in range(20):  # over a few tries a second man joins, hearing the first
    random.seed(seed)
    react("child", {"monster": "тушкан", "count": 7})
    if len(spoken) == 2:
        break
names = [s[0] for s in spoken]
check(len(spoken) == 2 and set(names) <= {"Борода", "Боєць", "Сусід"}, f"mutants: up to two, a fighter may shout too {spoken}")
check('just said: "Ого' in asked[1][2], "the second hears what the first said")
check("тушкан" in asked[0][2] and "7" in asked[0][2], "mutants: what and how many")
react("gift", {"name": "x"})
check("Боєць" not in [s[0] for s in spoken], "a gift: a man in a fight has no time for it")

friend = {"id": 501, "name": "Новенький", "community": "stalker"}
state["npcs"] = NPCS + [dict(friend, dist=18, relation="friend")]
random.seed(2)
react("life", {"side": "ally", "nick": "Viewer", "id": 501}, friend)
check(spoken and spoken[0][0] == "Новенький", f"the Zone's friend greets the player first {spoken}")
check("Viewer" in asked[0][2] and "companion" in asked[0][2], "he knows he came for the player")
check(len(spoken) <= 2 and "Новенький" not in [s[0] for s in spoken[1:]], "then at most one man around reacts")
react("life", {"side": "enemy", "nick": "Bad", "id": 777}, {"id": 777, "name": "Злий"})
check(spoken and "Злий" not in [s[0] for s in spoken] and "hostile" in asked[0][2],
      f"an enemy: no greeting, the men around warn {spoken}")

talker.CHAT_ONLY = True
react("gift", {"name": "x"})
check(spoken, "chat-only mode: they still react (it's a viewer's redeem)")

state["npcs"] = []
react("gift", {"name": "x"})
check(not spoken and not t.busy.locked(), "nobody around: silence, nothing stuck")

t.busy.acquire()
react("gift", {"name": "x"})  # someone is talking all the time: it waits up to 10 s, then gives up
t.busy.release()
check(not spoken, "someone keeps talking: the reaction gives up instead of piling up")

# which game answers start a reaction
calls = []
t2 = talker.Talker.__new__(talker.Talker)
t2.zone_react = lambda kind, ev, spawned=None: calls.append((kind, (spawned or {}).get("name")))
t2.link_viewer = lambda *a, **k: None
t2.report_zone = lambda **k: None
t2.zone = type("Q", (), {"retry": lambda self, *a: False})()
for item, evs in [({"kind": "gift"}, [{"type": "zone_done", "ok": True, "name": "Хліб"}]),
                  ({"kind": "child", "monster": "снорк"}, [{"type": "zone_done", "ok": True, "count": 2}]),
                  ({"kind": "life", "side": "ally"}, [{"type": "zone_done", "ok": True}]),
                  (None, [{"type": "zone_spawned", "id": 9, "nick": "V", "side": "ally", "npc": {"name": "Н"}}]),
                  ({"kind": "gift"}, [{"type": "zone_done", "ok": False, "reason": "no item"}])]:
    t2.zone_fired = item
    t2.on_zone_results(evs)
check(calls == [("gift", None), ("child", None), ("life", "Н")],
      f"gift and mutants react when done, a man when he is in the game, a failure never {calls}")
print("OK" if ok else "FAIL")
