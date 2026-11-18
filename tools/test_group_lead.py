"""Group address in lead mode: one man answers (the leader), others mutter quieter over the answer.
Offline: the AI reply and the voice are faked; checks parsing, who leads, order, overlap and volume."""
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker  # noqa: E402

fails = []


def check(name, ok):
    print(("ok  " if ok else "FAIL") + " " + name)
    if not ok:
        fails.append(name)


men = [{"id": 1, "name": "Лоцман", "community": "stalker", "rank": 300, "dist": 4},
       {"id": 2, "name": "Кастет", "community": "stalker", "rank": 700, "dist": 6, "leader": True},
       {"id": 3, "name": "Жорка", "community": "stalker", "rank": 900, "dist": 3}]
check("leader picked over higher rank", talker.Brain.group_lead(men) == 1)
check("no leader: highest rank", talker.Brain.group_lead([dict(m, leader=False) for m in men]) == 2)

brain = talker.Brain.__new__(talker.Brain)
brain.vary_tags = lambda line: line
talker.LLM_PROVIDER = "claude"
seen_prompt = {}
reply = "2: Бар Бороди на Скадовську, третій трюм.\n1~: Знову він про Бороду...\n3: Та там і наливають гидоту.\n1~: Ще одне."
brain.ask_claude = lambda s, system=None: seen_prompt.setdefault("p", s) and reply
talker.GROUP_STYLE = "lead"
out = brain.group(men, {"hours": 12}, "Пацани, де тут бар?", "The player")
check("prompt names the lead", "Man 2 speaks for the group" in seen_prompt["p"])
check("question noticed", "answers the question" in seen_prompt["p"])
check("one answer, by the leader", [(n["name"], a) for n, _, _, a in out if not a] == [("Кастет", False)])
check("unmarked line from another man becomes an aside", any(n["name"] == "Жорка" and a for n, _, _, a in out))
check(f"asides capped at {talker.GROUP_ASIDES}", sum(a for *_, a in out) == talker.GROUP_ASIDES)
check("asides carry no actions", all(not acts for _, _, acts, a in out if a))

talker.GROUP_STYLE = "all"
seen_prompt.clear()
out_all = brain.group(men, {"hours": 12}, "Пацани, де тут бар?", "The player")
check("all mode: old prompt", "Who answers, and what?" in seen_prompt["p"])
check("all mode: no asides", not any(a for *_, a in out_all))

# playback order and overlap: mutters start after the answer starts, before it ends, quieter
talker.GROUP_STYLE = "lead"
events = []
t = talker.Talker.__new__(talker.Talker)
t.recording, t.brain = False, brain
t.npc_key = lambda n, s: f"k{n['id']}"
t.memory = type("M", (), {"remembers": lambda self, k: "", "add": lambda self, *a: None})()
t.game = type("G", (), {"send": lambda self, *a: None})()
brain.group = lambda *a, **k: [(men[1], "Відповідь.", [], False), (men[0], "Бурмоче.", [], True)]


def fake_speak(npc, line, state=None, pda_text=None, note=None, aside=False, on_start=None):
    events.append(("start", npc["name"], aside, round(time.time(), 2)))
    if on_start:
        on_start()
    time.sleep(2.5 if not aside else 0.5)  # the answer takes 2.5 s
    events.append(("end", npc["name"], aside, round(time.time(), 2)))


t.speak = fake_speak
talker.random.uniform = lambda a, b: 1.0
start = time.time()
t.group_answer({"npcs": men}, "Пацани, де тут бар?", "The player", from_player=True)
took = time.time() - start
starts = {(e[1]): e[3] for e in events if e[0] == "start"}
ends = {(e[1]): e[3] for e in events if e[0] == "end"}
check("answer starts first", starts["Кастет"] < starts["Лоцман"])
check("mutter overlaps the answer", starts["Лоцман"] < ends["Кастет"])
check("group waits for the mutter to finish", took >= (ends["Лоцман"] - start) - 0.05)

# volume and overlap reach the voice
calls = {}
t2 = talker.Talker.__new__(talker.Talker)
t2.spoken, t2.game = [], type("G", (), {"send": lambda self, *a: None, "distance_to": lambda self, i: 3})()
t2.voice = type("V", (), {"say": lambda self, npc, line, **k: calls.update(k)})()
talker.Talker.speak(t2, men[0], "Бурмоче.", aside=True)
check("aside quieter", calls.get("volume") == talker.GROUP_ASIDE_VOLUME and calls.get("overlap") is True)
talker.Talker.speak(t2, men[0], "Каже.")
check("normal line full volume, waits its turn", calls.get("volume") == 1.0 and calls.get("overlap") is False)

print(f"\n{len(fails)} failed" if fails else "\nall passed")
