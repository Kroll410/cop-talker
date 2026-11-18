"""Debts: a medkit or a hand in a fight is remembered; asked to pay, he pays and the debt is settled."""
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker  # noqa: E402

fails = []


def check(name, ok):
    print(("ok  " if ok else "FAIL") + " " + name)
    if not ok:
        fails.append(name)


mem = talker.Memory.__new__(talker.Memory)
mem.data, mem.lock, mem.busy_keys, mem.summarize = {}, threading.Lock(), set(), None
mem.save = lambda: None
mem.owe("k", "he gave you his medkit when you lay dying", 400)
mem.owe("k", "he gave you his medkit when you lay dying", 400)
check("same help counted once", len(mem.owed("k")) == 1)
mem.owe("k", "he helped you in a fight: killed Бандит who was attacking", 700)
check("memory text tells what he owes", "You owe him for:" in mem.remembers("k") and "medkit" in mem.remembers("k"))
check("asking for pay is recognised", all(talker.PAY_ASK.search(s) for s in
      ["Ти мені винен за аптечку", "Заплати за допомогу", "А де моя винагорода?", "Я ж тебе врятував, з тебе магарич"]))
check("ordinary talk isn't", not any(talker.PAY_ASK.search(s) for s in ["Як справи?", "Що продаєш?"]))

# the helper: he pays 400 -> the oldest debt (the medkit) is settled, the fight one stays
sent = []
t = talker.Talker.__new__(talker.Talker)
t.game = type("G", (), {"send": lambda self, *a: sent.append(a)})()
t.memory = mem
t.confront = lambda *a: None
t.do_deals({"id": 5, "name": "Лоцман"}, {"actor": {"money": 100}}, [("give", 400)], "k", "Ти мені винен")
check("he pays you", ("act", 5, "give:400") in sent)
check("medkit debt settled, fight debt left", [d["worth"] for d in mem.owed("k")] == [700])

# the prompt: with a debt he's told to pay; without one, to refuse
b = talker.Brain.__new__(talker.Brain)
b.news = talker.News("", 3600, lambda m: None)
npc = {"id": 5, "name": "Лоцман", "community": "stalker", "rank": 400, "dist": 3, "money": 1500}
st = {"level": "zaton", "hours": 12, "actor": {}, "npcs": []}
p_owed = b.situation(npc, st, "", [], "Ти мені винен за аптечку", "reply", remembers=mem.remembers("k"))
p_none = b.situation(npc, st, "", [], "Ти мені винен за аптечку", "reply", remembers="")
check("owes: told to pay with the give tag", "[ACTION: give N]" in p_owed and "1500" in p_owed)
check("owes nothing: told to refuse", "you owe him nothing" in p_none)
print(f"\n{len(fails)} failed" if fails else "\nall passed")
