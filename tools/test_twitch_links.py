"""Twitch viewer <-> NPC links: same NPC while he's near, relink when he leaves or dies, one viewer per NPC."""
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker  # noqa: E402
import tempfile  # noqa: E402

talker.Talker.LINKS_FILE = Path(tempfile.mkdtemp()) / "twitch_links.json"  # never the real one


class FakeGame:
    def __init__(self):
        self.sent = []

    def send(self, kind, npc_id, text):
        self.sent.append((kind, npc_id, text))


t = talker.Talker.__new__(talker.Talker)
t.twitch_queue, t.busy, t.recording = [], threading.Lock(), False
t.twitch_links, t.twitch_names, t.next_link_sync, t.next_twitch_note = {}, {}, 0.0, 0.0
t.left_npc = {}
t.game = FakeGame()
spoke = []
t._twitch_line = lambda npc, state, item, named=None: spoke.append((item[0], npc and npc["name"], named and named["name"]))
threading.Thread = lambda target, args, daemon: type("T", (), {"start": lambda self: target(*args)})()

men = {i: {"id": i, "name": n, "dist": 5} for i, n in [(1, "Лоцман"), (2, "Кастет"), (3, "Жорка")]}
state = lambda *ids: {"npcs": [men[i] for i in ids]}


def say(user, text, st):
    t.twitch_queue.append((user, text, None, "verbatim"))
    t.twitch_speak(st)
    return spoke[-1]


first = say("Viewer1", "привіт", state(1, 2, 3))[1]
assert all(say("Viewer1", "ще раз", state(1, 2, 3))[1] == first for _ in range(5)), "should stay on his NPC"
other = say("viewer2", "я тут", state(1, 2, 3))[1]
assert other != first, "a second viewer gets another NPC while one is free"
rest = [i for i in (1, 2, 3) if men[i]["name"] == first][0]
gone = [i for i in (1, 2, 3) if i != rest]
new = say("Viewer1", "де ти", state(*gone))[1]
assert new != first and t.twitch_links["viewer1"] != rest, "relinked when his NPC left"
assert ("link", rest, "") in t.game.sent, "old label removed"
# the words name his own man: he still says it himself, and the link stays
mine = t.twitch_links["viewer1"]
r = say("Viewer1", f"{men[mine]['name']}, ти де був?", state(1, 2, 3))
assert r[1] == men[mine]["name"] and r[2] is None and t.twitch_links["viewer1"] == mine
# sync: game forgot labels after a save load
t.game.sent.clear()
t.sync_links({"npcs": [men[1], men[2], men[3]], "twitch_links": []})
assert {s[1] for s in t.game.sent} == set(t.twitch_links.values()), t.game.sent
print("links ok:", t.twitch_links)

# --- his own NPC speaks even if the words seem to name him ("бороду" vs Борода), and links survive a restart
beard = {"id": 9, "name": "Борода", "dist": 4}
t.twitch_links, t.twitch_names = {}, {}
spoke.clear()
say("Viewer3", "привіт", {"npcs": [beard]})
r = say("Viewer3", "ох от би хто мені на бороду щось", {"npcs": [beard, men[1], men[2]]})
assert r[1] == "Борода" and r[2] is None, r
t2 = talker.Talker.__new__(talker.Talker)
t2.load_links()
assert t2.twitch_links.get("viewer3") == 9 and t2.twitch_names.get("viewer3") == "Viewer3", t2.twitch_links
print("own NPC kept despite 'бороду'; links survive a restart")
