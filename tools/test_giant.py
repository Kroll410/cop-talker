"""«Хуй будеш?»: a reward the streamer makes on Twitch (the app never creates it) and picks in Settings. A redemption
goes to the game at once, no Zone queue, no waiting; the game puts one pseudogiant near the player, hostile and
provoked like the Zone's mutants (checked in tools/zone_lua.py), and the men around panic about it."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "companion"))
import talker  # noqa: E402
from twitch import Twitch  # noqa: E402

ok = True


def check(cond, what):
    global ok
    ok &= bool(cond)
    print(("ok   " if cond else "FAIL ") + what)


# Twitch: a redemption of the «Хуй будеш?» reward calls its trigger once, next to the other trigger rewards
got = []
tw = Twitch("id", "", ROOT / "nope.json", lambda *a: None, lambda *a: None, source="chat",
            zone_title="Дар Зони", on_zone=lambda u, ev: got.append(("zone", u)),
            triggers={"Шари Суслова": lambda u, ev: got.append(("suslov", u)),
                      "Хуй будеш?": lambda u, ev: got.append(("giant", u))})
red = {"id": "r1", "user_name": "Vasyl", "reward": {"id": "x", "title": "Хуй будеш?"}}
tw.on_redemption(red)
tw.on_redemption(red)  # delivered twice by two subscriptions
tw.on_redemption({"id": "r2", "user_name": "Olia", "reward": {"id": "y", "title": "Шари Суслова"}})
check(got == [("giant", "Vasyl"), ("suslov", "Olia")], f"routed by title, once each: {got}")
tw.trigger_ids = {"abc": "хуй будеш?"}
got.clear()
tw.on_redemption({"id": "r3", "user_name": "Petro", "reward": {"id": "abc", "title": "renamed on Twitch"}})
check(got == [("giant", "Petro")], "found by its id after connecting, even if renamed")

# the app wires the setting to the handler
src = (ROOT / "companion" / "talker.py").read_text(encoding="utf-8")
check("(TWITCH_GIANT_REWARD, self.on_giant)" in src, "TWITCH_GIANT_REWARD routes to on_giant")
app = (ROOT / "companion" / "app.py").read_text(encoding="utf-8")
check('"TWITCH_GIANT_REWARD"' in app and '"giant"' in app, "Settings picker and a test button in the window")
ini = (ROOT / "settings.example.ini").read_text(encoding="utf-8")
check("TWITCH_GIANT_REWARD=" in ini.splitlines(), "in settings.example.ini, off by default")

# the helper: at once, straight to the game, not through the Zone queue
sent = []
t = talker.Talker.__new__(talker.Talker)
state = {"mod_version": 15, "actor": {"health": 1}}
t.game = type("G", (), {"send": lambda self, *x: sent.append(x), "state": lambda self: state})()
t.zone = type("Q", (), {"add": lambda *a: (_ for _ in ()).throw(AssertionError("queued"))})()
t.on_giant("Vasyl_77")
check(len(sent) == 1 and sent[0][0] == "zone" and sent[0][2].startswith("giant|Хуй будеш?|Vasyl_77"),
      f"sent to the game at once: {sent}")
check(sent and sent[0][2].count("|") == 2, "the PDA text has no extra | in it")
check(t.zone_fired.get("kind") == "giant", "the game's answer is matched to it (for the reaction)")
sent.clear()
state["mod_version"] = 14
t.on_giant("Vasyl_77")
check(not sent, "old game script (no giant branch): nothing sent")
state["mod_version"] = 15
state["actor"]["health"] = 0
t.on_giant("Vasyl_77")
check(not sent, "player dead: nothing sent")

what = talker.Talker.zone_what(t, "giant", {})
check("pseudogiant" in what and "panic" in what and "Хуй будеш?" in what,
      "the men around are told what came, why, and to panic")

# the game's answer: a reaction, and a failure is not retried through the Zone queue
reacted, retried = [], []
t.zone_fired = {"kind": "giant", "user": "Vasyl_77", "monster": "псевдогігант"}
t.zone_react = lambda kind, ev, *a, **k: reacted.append((kind, ev.get("monster")))
t.zone = type("Q", (), {"retry": lambda self, *a: retried.append(a) or True})()
t.report_zone = lambda force=False: None
t.on_zone_results([{"type": "zone_done", "what": "giant", "ok": True, "section": "gigant_normal", "count": 1}])
check(reacted == [("giant", "псевдогігант")], f"done: the men around react {reacted}")
t.zone_fired = {"kind": "giant", "user": "Vasyl_77"}
t.on_zone_results([{"type": "zone_done", "what": "giant", "ok": False, "reason": "no place"}])
check(not retried, "failed: given up, not queued again")
print("OK" if ok else "FAIL")
