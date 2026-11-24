"""«Шари Суслова»: a reward the streamer makes on Twitch (the app never creates it) and picks in Settings. A
redemption goes to the game at once, no Zone queue, no waiting; the game lays two «Вогняна куля» and a «Ковбаса»
on the ground in a rude shape (layout checked in tools/zone_lua.py), and the men around laugh about it."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "companion"))
import talker  # noqa: E402
from twitch import Twitch  # noqa: E402
from redeem_checks import check_redeem  # noqa: E402  (tools/redeem_checks.py)

ok = True


def check(cond, what):
    global ok
    ok &= bool(cond)
    print(("ok   " if cond else "FAIL ") + what)


# Twitch: a redemption of the «Шари Суслова» reward calls its trigger once; other rewards don't
got = []
tw = Twitch("id", "", ROOT / "nope.json", lambda *a: None, lambda *a: None, source="chat",
            zone_title="Дар Зони", on_zone=lambda u, ev: got.append(("zone", u)),
            triggers={"Шари Суслова": lambda u, ev: got.append(("suslov", u))})
check("channel:read:redemptions" in tw.scopes.split(), "chat mode asks to read redemptions for it")
red = {"id": "r1", "user_name": "Vasyl", "reward": {"id": "x", "title": "Шари Суслова"}}
tw.on_redemption(red)
tw.on_redemption(red)  # delivered twice by two subscriptions
tw.on_redemption({"id": "r2", "user_name": "Olia", "reward": {"id": "y", "title": "Дар Зони"}})
tw.on_redemption({"id": "r3", "user_name": "Ivan", "reward": {"id": "z", "title": "Щось інше"}})
check(got == [("suslov", "Vasyl"), ("zone", "Olia")], f"routed by title, once each: {got}")
tw.trigger_ids = {"abc": "шари суслова"}
got.clear()
tw.on_redemption({"id": "r4", "user_name": "Petro", "reward": {"id": "abc", "title": "renamed on Twitch"}})
check(got == [("suslov", "Petro")], "found by its id after connecting, even if renamed")
src = (ROOT / "companion" / "twitch.py").read_text(encoding="utf-8")
check('"POST", "/channel_points/custom_rewards"' not in src, "the app never creates a reward")
check_redeem(check, "suslov", "TWITCH_SUSLOV_REWARD", "on_suslov")  # routing, Redeems tab, test command

# the helper: at once, straight to the game, not through the Zone queue
sent = []
t = talker.Talker.__new__(talker.Talker)
state = {"mod_version": 14, "actor": {"health": 1}}
t.game = type("G", (), {"send": lambda self, *x: sent.append(x), "state": lambda self: state})()
t.zone = type("Q", (), {"add": lambda *a: (_ for _ in ()).throw(AssertionError("queued"))})()
t.on_suslov("Vasyl_77")
check(len(sent) == 1 and sent[0][0] == "zone" and sent[0][2].startswith("suslov|Шари Суслова|Vasyl_77"),
      f"sent to the game at once: {sent}")
check(t.zone_fired.get("kind") == "suslov", "the game's answer is matched to it (for the reaction)")
sent.clear()
state["actor"]["health"] = 0
t.on_suslov("Vasyl_77")
check(not sent, "player dead: nothing sent")

what = talker.Talker.zone_what(t, "suslov", {})
check("dick" in what and "laugh" in what, "the men around are told what lies there and to laugh")
print("OK" if ok else "FAIL")
