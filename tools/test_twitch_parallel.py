"""Offline: TWITCH_PARALLEL lets several waiting viewer messages play at the same time (voice, AI and game faked).
Checks that:
- N messages go to N different NPCs, their voices overlap, and each starts after a pause inside
  TWITCH_PARALLEL_DELAY;
- the batch holds `busy` (other speech and the player's answer wait) and lets it go once every line is done;
- a viewer with two messages waiting gets only one in a batch (his own man says both, one after the other);
- a line still in its pause when the player starts talking goes back to the queue, not said over him;
- each said message is finished (spoken=True) and the window's waiting count follows the queue;
- TWITCH_PARALLEL=1 is the old behaviour: one message, one NPC, nothing overlapping."""
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker  # noqa: E402

reports = []
talker.report = lambda kind, text: reports.append((kind, text))
talker.log = lambda *a: None
LINE = 0.6  # each fake voice line lasts this long
fails = []


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        fails.append(what)


def npc(i, name, dist):
    return {"id": i, "name": name, "community": "stalker", "dist": dist}


state = {"npcs": [npc(11, "Хрін", 4), npc(12, "Лоцман", 6), npc(13, "Вовк", 8), npc(14, "Гонта", 10)],
         "level": "zaton"}
played, finished, lock = [], [], threading.Lock()


def say(self, n, line, current_dist=None, on_start=None, volume=1.0, overlap=False, **k):
    start = time.time()
    if on_start:
        on_start()
    time.sleep(LINE)
    with lock:
        played.append({"npc": n["id"], "line": line, "start": start, "end": time.time(), "overlap": overlap})


def make():
    t = talker.Talker.__new__(talker.Talker)
    t.busy, t.recording, t.next_twitch_note, t.spoken = threading.Lock(), False, 0, []
    t.twitch_queue, t.twitch_links, t.twitch_names, t.left_npc, t.zone_links = [], {}, {}, {}, set()
    t.twitch = type("T", (), {"finish": lambda self, r, spoken=True: finished.append((r, spoken))})()
    t.save_links = lambda: None
    t.npc_key = lambda n, s: n["name"]
    t.start_overheard = lambda *a, **k: None
    t.memory = type("M", (), {"remembers": lambda self, k: "", "said": lambda self, *a: None})()
    t.brain = type("B", (), {"last_extras": [], "news": type("N", (), {"mark_mentioned": lambda s, x: []})()})()
    t.game = type("G", (), {"send": lambda self, *a: None, "distance_to": lambda self, i: 4,
                            "state": lambda self: state})()
    t.voice = type("V", (), {"say": say})()
    return t


def reset():
    played.clear(), finished.clear(), reports.clear()


def wait_free(t, limit=10):
    end = time.time() + limit
    time.sleep(0.05)
    while t.busy.locked() and time.time() < end:
        time.sleep(0.02)


# ------------------------------------------------------------ three at once
talker.TWITCH_PARALLEL, talker.TWITCH_PARALLEL_DELAY = 3, (0.2, 0.5)
t = make()
reset()
for user, text in (("ann", "Добрий день"), ("bob", "Тримайтеся разом"), ("cid", "Холодно сьогодні"),
                   ("dan", "Ще одне слово")):
    t.twitch_queue.append((user, text, {"id": user}, "verbatim"))
t0 = time.time()
check(t.twitch_speak(state) is True, "a batch starts")
check(t.busy.locked(), "the batch holds busy (other speech waits)")
check(len(t.twitch_queue) == 1 and t.twitch_queue[0][0] == "dan", "three taken, the fourth still waits")
check(("TWITCH_QUEUE", "1") in reports, "the window's waiting count drops to 1 at once")
check(t.twitch_speak(state) is False, "no second batch while the first one plays")
wait_free(t)
check(not t.busy.locked(), "busy is let go once every line is done")
ids = [p["npc"] for p in played]
check(len(played) == 3 and len(set(ids)) == 3, f"three lines by three different NPCs: {ids}")
starts = sorted(p["start"] - t0 for p in played)
check(all(0.19 <= s <= 0.5 + 0.15 for s in starts), f"each started after a pause inside 0.2-0.5 s: "
      f"{[round(s, 2) for s in starts]}")
first, last = min(p["end"] for p in played), max(p["start"] for p in played)
check(last < first, "the voices overlap (the last one started before the first one ended)")
check(all(p["overlap"] for p in played), "parallel lines are played with overlap=True")
check(sorted(r["id"] for r, s in finished) == ["ann", "bob", "cid"] and all(s for r, s in finished),
      "each said message is finished as spoken")
check(len({t.twitch_links[u] for u in ("ann", "bob", "cid")}) == 3, "each new viewer got his own NPC")

# ------------------------------------------------------------ one viewer, two messages
reset()
t.twitch_queue[:] = [("ann", "Перше слово", None, "verbatim"), ("ann", "Друге слово", None, "verbatim"),
                     ("bob", "Моє слово", None, "verbatim")]
ann, bob = t.twitch_links["ann"], t.twitch_links["bob"]
t.twitch_speak(state)
check([q[1] for q in t.twitch_queue] == ["Друге слово"], "the same viewer's second message waits for the next batch")
wait_free(t)
check(sorted(p["npc"] for p in played) == sorted([ann, bob]), "each viewer through his own linked NPC")
t.twitch_speak(state)
wait_free(t)
check([p["npc"] for p in played[2:]] == [ann] and not t.twitch_queue, "then his own man says the second one")

# ------------------------------------------------------------ the player starts talking during the pauses
reset()
talker.TWITCH_PARALLEL_DELAY = (0.4, 0.6)
t.twitch_queue[:] = [("cid", "Раз", None, "verbatim"), ("dan", "Два", None, "verbatim")]
t.twitch_speak(state)
time.sleep(0.1)
t.recording = True
wait_free(t)
check(not played and sorted(q[1] for q in t.twitch_queue) == ["Два", "Раз"],
      "lines still in their pause go back to the queue when the player talks")
check(not t.busy.locked(), "and busy is free for the player's answer")
check(t.twitch_speak(state) is False and len(t.twitch_queue) == 2, "nothing new starts while he is recording")
t.recording = False

# ------------------------------------------------------------ only men already talking are around
reset()
talker.TWITCH_PARALLEL_DELAY = (0.0, 0.0)
one = {"npcs": [npc(11, "Хрін", 4)], "level": "zaton"}
t2 = make()
t2.twitch_queue[:] = [("eve", "Раз", None, "verbatim"), ("fay", "Два", None, "verbatim")]
t2.twitch_speak(one)
check(len(t2.twitch_queue) == 1, "one NPC around: one line now, the other waits")
wait_free(t2)

# ------------------------------------------------------------ TWITCH_PARALLEL=1: the old way
reset()
talker.TWITCH_PARALLEL = 1
t3 = make()
for user, text in (("ann", "Перше"), ("bob", "Друге")):
    t3.twitch_queue.append((user, text, None, "verbatim"))
t0 = time.time()
check(t3.twitch_speak(state) is True and len(t3.twitch_queue) == 1, "PARALLEL=1: one message taken")
time.sleep(0.05)
check(t3.busy.locked() and t3.twitch_speak(state) is False, "PARALLEL=1: the next waits while it plays")
wait_free(t3)
check(t3.twitch_speak(state) is True, "PARALLEL=1: then the next one")
wait_free(t3)
check(len(played) == 2 and played[1]["start"] >= played[0]["end"], "PARALLEL=1: one after another, no overlap")
check(not any(p["overlap"] for p in played), "PARALLEL=1: lines use the shared voice lock (overlap=False)")
check(played[0]["start"] - t0 < 0.15, "PARALLEL=1: no pause before the line")

# ------------------------------------------------------------ the setting is read
check(talker.seconds_range("0.5-3") == (0.5, 3.0) and talker.seconds_range("2") == (2.0, 2.0)
      and talker.seconds_range("3 - 1,5") == (1.5, 3.0) and talker.seconds_range("") == (0.5, 3.0),
      "TWITCH_PARALLEL_DELAY ranges are read")
print("FAILED: " + "; ".join(fails) if fails else "OK")
sys.exit(1 if fails else 0)
