"""Several NPCs nearby, each with his own linked Twitch viewer. Runs the real queue, linking and answer code
(the AI and the voice are faked) and checks that:
- every viewer always speaks through his own NPC, message after message, in order, one at a time;
- a viewer whose message names another viewer's NPC still speaks through his own; the named NPC answers as
  himself and stays linked to his own viewer;
- a line said to another linked NPC's face gets his answer; a third linked NPC named in a talk reacts;
- a viewer's NPC that dies passes the viewer to a free NPC, never to a man who already has a viewer;
- a new viewer when every NPC nearby is taken does not steal another viewer's NPC;
- the in-game labels follow the links;
- when one NPC speaks to another, they turn to each other."""
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker  # noqa: E402

talker.TWITCH_SHOW_NAME = 1
talker.report = lambda *a: None
ok = True


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    return cond


def npc(i, name, x):
    return {"id": i, "name": name, "community": "stalker", "rank": 300, "x": x, "z": 0, "dist": 4 + x / 2,
            "place": "zat_b55"}


hrin, lotsman, vovk, gonta, shulyak = (npc(11, "Хрін", 0), npc(12, "Лоцман", 2), npc(13, "Вовк", 4),
                                       npc(14, "Гонта", 6), npc(15, "Шуляк", 8))
state = {"npcs": [hrin, lotsman, vovk, gonta], "level": "zaton", "hours": 20, "weather": "clear"}

spoken, sent = [], []


class FakeBrain:
    last_extras, last_action, chat_emotes = [], None, []
    news = type("N", (), {"mark_mentioned": lambda self, x: []})()

    def reply(self, n, state, ev, hist, player_text, mode, extra=None, **k):
        time.sleep(0.05)
        if mode == "addressed":
            return f"{n['name']} відповідає {extra['name']}."
        return "Ага."

    def group(self, men, *a, **k):
        return []

    def overheard(self, c, a, b, lines, state, remembers=""):
        return [(c, f"{c['name']} чув, що про нього кажуть.", None, [])]


t = talker.Talker.__new__(talker.Talker)
t.busy, t.recording, t.twitch = threading.Lock(), False, None
t.twitch_queue, t.twitch_links, t.twitch_names, t.next_twitch_note, t.left_npc = [], {}, {}, 0, {}
t.spoken = []
t.save_links = lambda: None
t.recent_lines = lambda: []
t.npc_key = lambda n, s: n["name"]
t.memory = type("M", (), {"remembers": lambda self, k: "", "said": lambda self, *a: None})()
t.game = type("G", (), {"send": lambda self, *x: sent.append(x), "describe_events": lambda self, *x: "",
                        "distance_to": lambda self, i: 4})()
t.voice = type("V", (), {"say": lambda self, n, line, current_dist=None, on_start=None, **k: (
    on_start(), spoken.append((n["name"], line)), time.sleep(0.05))})()
t.show_line = lambda *a: None
t.gesture = lambda *a: None
t.brain_gesture = lambda *a: None
t.brain = FakeBrain()


def say(user, text):
    """A viewer writes; the queue runs until it is empty (one message at a time, like the helper's loop)."""
    t.on_twitch(user, text, None)


def run_queue():
    deadline = time.time() + 20
    while (t.twitch_queue or t.busy.locked()) and time.time() < deadline:
        t.twitch_speak(state)
        time.sleep(0.02)
    time.sleep(0.1)


def via(user):
    return next(n["name"] for n in state["npcs"] if n["id"] == t.twitch_links.get(user.lower()))


# four viewers write their first messages: each gets his own NPC
for user in ("anna", "bob", "carl", "dan"):
    say(user, f"$Привіт, я {user}")
run_queue()
links = {u: via(u) for u in ("anna", "bob", "carl", "dan")}
print("  links:", links)
ok &= check(len(set(links.values())) == 4, "four viewers, four different NPCs")
first = [n for n, l in spoken if l.startswith("Привіт, я")]
ok &= check(first == [links[u] for u in ("anna", "bob", "carl", "dan")], f"said in order, by their own men: {first}")

# many messages at once: still their own NPC each time, in order, never two lines over each other
spoken.clear()
for i in range(3):
    for user in ("anna", "bob", "carl", "dan"):
        say(user, f"${user} пише {i}")
run_queue()
said_by = {u: {n for n, l in spoken if l.startswith(f"{u} пише")} for u in links}
ok &= check(all(said_by[u] == {links[u]} for u in links), f"12 messages, each by his viewer's NPC: {said_by}")
order = [l for n, l in spoken if " пише " in l]
ok &= check(order == [f"{u} пише {i}" for i in range(3) for u in ("anna", "bob", "carl", "dan")], "in order")

# anna names bob's NPC: she still speaks through hers, bob's NPC answers her, and stays bob's
spoken.clear()
sent.clear()
bobs = next(n for n in state["npcs"] if n["name"] == links["bob"])
say("anna", f"${bobs['name']}, ти де був?")
run_queue()
ok &= check([n for n, _ in spoken] == [links["anna"], links["bob"]], f"anna -> bob's man answers: {spoken}")
ok &= check(via("anna") == links["anna"] and via("bob") == links["bob"], "nobody's link changed")
looks = [(x[1], x[2].rsplit(":", 1)[0]) for x in sent if x[0] == "act" and x[2].startswith("look:")]
annas = next(n for n in state["npcs"] if n["name"] == links["anna"])
ok &= check((annas["id"], f"look:{bobs['id']}") in looks and (bobs["id"], f"look:{annas['id']}") in looks,
            "they turn to each other")

# carl's message names bob's NPC and dan's NPC: bob's man answers, dan's man (named, nearby) reacts too
spoken.clear()
dans = next(n for n in state["npcs"] if n["name"] == links["dan"])
say("carl", f"${bobs['name']}, а {dans['name']} правду каже, що ти боягуз?")
run_queue()
names = [n for n, _ in spoken]
ok &= check(names[0] == links["carl"] and sorted(names[1:]) == sorted([links["bob"], links["dan"]]),
            f"carl names two linked men: one answers, the other reacts: {names}")

# a message said to another linked NPC's face (viewer named nobody, "%" retold): that man answers
spoken.clear()
t.brain.reply = lambda n, s, e, h, p, mode, extra=None, **k: (
    f"{dans['name']}, ти мені винен." if mode == "twitch" else FakeBrain.reply(t.brain, n, s, e, h, p, mode, extra))
say("anna", "%argue with someone")
run_queue()
t.brain.reply = FakeBrain().reply
names = [n for n, _ in spoken]
ok &= check(names == [links["anna"], links["dan"]], f"said to dan's man's face: he answers: {names}")
ok &= check(via("dan") == links["dan"], "and stays dan's")

# bob's NPC dies: bob's next message goes through a free NPC (Шуляк came close), never through someone's man
state["npcs"] = [n for n in state["npcs"] if n is not bobs] + [shulyak]
sent.clear()
say("bob", "$Я тут")
run_queue()
ok &= check(via("bob") == "Шуляк", f"bob moved to the free man: {via('bob')}")
ok &= check(all(via(u) == links[u] for u in ("anna", "carl", "dan")), "the others keep theirs")
ok &= check(("link", shulyak["id"], "bob") in sent, "the label shows bob on Шуляк")

# a fifth viewer while all four men nearby have viewers: he must not take anyone's NPC
before = dict(t.twitch_links)
spoken.clear()
say("eve", "$А я хто?")
run_queue()
ok &= check(all(t.twitch_links.get(u) == before[u] for u in before),
            f"eve took nobody's man (links: {[(u, via(u)) for u in t.twitch_links]})")
ok &= check(len(spoken) == 1, f"eve's message is still said by someone: {spoken}")
ok &= check("eve" not in t.twitch_links, "eve is not linked while nobody is free")

# a man comes free (carl's NPC walks away and carl stops writing): eve gets him on her next message
gone = next(n for n in state["npcs"] if n["name"] == links["carl"])
state["npcs"] = [n for n in state["npcs"] if n is not gone] + [npc(16, "Ной", 10)]
say("eve", "$Тепер я тут")
run_queue()
ok &= check(via("eve") == "Ной", f"eve linked to the free man: {via('eve') if 'eve' in t.twitch_links else None}")


# dan's NPC dies: dan is just unlinked (label cleared), nobody else is given to him until he writes again
sent.clear()
dans_now = next(n for n in state["npcs"] if n["id"] == t.twitch_links["dan"])
state["npcs"] = [n for n in state["npcs"] if n is not dans_now] + [npc(17, "Кардан", 12)]
t.unlink_dead([{"type": "death", "victim": {"id": dans_now["id"], "name": dans_now["name"]}}])
ok &= check("dan" not in t.twitch_links and ("link", dans_now["id"], "") in sent
            and not any(x[0] == "link" and x[2] for x in sent), "dan's man died: unlinked, no new man given")
say("dan", "$Я знову тут")
run_queue()
ok &= check(via("dan") == "Кардан", "dan writes again: he gets a free man like a new viewer")

# "%%": bob lets go of his NPC; his next message goes through another man, the label moves
sent.clear()
spoken.clear()
bobs_before = t.twitch_links["bob"]
state["npcs"].append(npc(19, "Ной", 16))
say("bob", "%%")
run_queue()
ok &= check("bob" not in t.twitch_links and ("link", bobs_before, "") in sent and not spoken,
            "%% unlinks bob, clears his label, says nothing")
say("bob", "$А тепер хто я?")
run_queue()
ok &= check(t.twitch_links.get("bob") not in (None, bobs_before), f"bob's next message: a new man ({via('bob')})")
say("eve", "%%")  # nothing to unlink: nothing happens
run_queue()

print("OK" if ok else "FAIL")
