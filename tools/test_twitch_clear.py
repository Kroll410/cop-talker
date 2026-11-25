"""Offline: the window's Clear queue drops every waiting viewer message and refunds speech-reward redemptions."""
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker  # noqa: E402

reports, refunds = [], []
talker.report = lambda kind, text: reports.append((kind, text))
t = talker.Talker.__new__(talker.Talker)
t.busy, t.recording, t.twitch_queue, t.next_twitch_note, t.spoken = threading.Lock(), False, [], 0, []
t.twitch = type("T", (), {"finish": lambda self, r, spoken=True: refunds.append((r and r["id"], spoken))})()

t.twitch_queue += [("a", "$раз", None, "say"), ("b", "$два", {"id": "r2", "reward": {"id": "x"}}, "say"),
                   ("c", "%три", {"id": "r3", "reward": {"id": "x"}}, "retell")]
n = t.clear_twitch_queue()
assert n == 3 and t.twitch_queue == [], (n, t.twitch_queue)
assert refunds == [(None, False), ("r2", False), ("r3", False)], refunds  # finish() skips the None itself
assert reports[-1] == ("TWITCH_QUEUE", "0"), reports

# nothing waiting: harmless
reports.clear()
assert t.clear_twitch_queue() == 0 and reports[-1] == ("TWITCH_QUEUE", "0")

# without Twitch connected (test messages only): still clears
t.twitch = None
t.twitch_queue.append(("d", "$чотири", None, "say"))
assert t.clear_twitch_queue() == 1 and not t.twitch_queue

# the window wires it: a button sends "twitchclear", the helper listens for it
app = (Path(__file__).resolve().parent.parent / "companion" / "app.py").read_text(encoding="utf-8")
src = (Path(__file__).resolve().parent.parent / "companion" / "talker.py").read_text(encoding="utf-8")
assert 'b"twitchclear\\n"' in app and '"Clear queue"' in app
assert '== "twitchclear"' in src
print("OK")
