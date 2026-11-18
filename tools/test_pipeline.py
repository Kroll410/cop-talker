"""Follow-up lines are prepared while the line before them plays: the AI writes the answer and its voice is
fetched during the first line, so the answer starts the moment the first one ends, and always after it."""
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker  # noqa: E402

AI, FETCH, PLAY = 2.0, 0.8, 3.0  # seconds: writing a reply, getting the voice, playing a line
log = []
voice_lock = threading.Lock()   # the voice player: one line at a time
t0 = time.time()


def fake_speak(npc, line, state=None, pda_text=None, note=None, aside=False, on_start=None):
    time.sleep(FETCH)                       # the voice is fetched (can overlap another line playing)
    with voice_lock:                        # ...then waits its turn to play
        log.append((round(time.time() - t0, 1), "starts", npc["name"]))
        if on_start:
            on_start()
        time.sleep(PLAY)
        log.append((round(time.time() - t0, 1), "ends", npc["name"]))


t = talker.Talker.__new__(talker.Talker)
t.recording = False
t.speak = fake_speak
t.gesture = lambda *a: None
t.recent_lines = lambda: []
t.npc_key = lambda n, s: "k"
t.memory = type("M", (), {"remembers": lambda self, k: ""})()
t.game = type("G", (), {"describe_events": lambda self, *a: ""})()
t.brain = type("B", (), {"last_extras": [], "reply": lambda self, *a, **k: time.sleep(AI) or "Відповідь."})()

# A says a line; B's answer is written and fetched meanwhile
a, b = {"id": 1, "name": "A"}, {"id": 2, "name": "B"}
started = threading.Event()
follow = t.answer_after(started, b, {}, "addressed", extra={"name": "A", "line": "Привіт"})
fake_speak(a, "Привіт", on_start=started.set)
follow.join(10)
ends_a = next(x for x, w, n in log if w == "ends" and n == "A")
starts_b = next(x for x, w, n in log if w == "starts" and n == "B")
print(f"answer after a line: A ends {ends_a}s, B starts {starts_b}s -> pause {starts_b - ends_a:.1f}s "
      f"(before: about {AI + FETCH:.1f}s)")
ok1 = 0 <= starts_b - ends_a < 0.3

# a 4-line chat: every next voice fetched while the line before plays
log.clear()
t0 = time.time()
lines = [(a, "1"), (b, "2"), (a, "3"), (b, "4")]
t.speak_lines(lines, {})
order = [n for _, w, n in log if w == "starts"]
gaps = [round(log[i + 1][0] - log[i][0], 1) for i in range(1, len(log) - 1, 2)]
print(f"chat: order {order}, pauses between lines {gaps} (before: {FETCH}s each)")
ok2 = order == ["A", "B", "A", "B"] and all(g < 0.3 for g in gaps)
print("OK" if ok1 and ok2 else "FAIL")
