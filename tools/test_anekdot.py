"""«Анекдот»: a reward the streamer makes on Twitch (the app never creates it) and picks in Settings. A redemption
goes to the game at once, no Zone queue, no waiting; the game drops a «Хліб», a «Ковбаса» and a handful of bolts on the
ground in front of the player. They roll and can be kicked, but nobody can keep them (layout and props checked in
tools/zone_lua.py), and the men around laugh and tell a joke."""
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


# Twitch: a redemption of the «Анекдот» reward calls its trigger once; the other rewards keep their own
got = []
tw = Twitch("id", "", ROOT / "nope.json", lambda *a: None, lambda *a: None, source="chat",
            zone_title="Дар Зони", on_zone=lambda u, ev: got.append(("zone", u)),
            triggers={"Шари Суслова": lambda u, ev: got.append(("suslov", u)),
                      "Анекдот": lambda u, ev: got.append(("anekdot", u))})
red = {"id": "r1", "user_name": "Vasyl", "reward": {"id": "x", "title": "Анекдот"}}
tw.on_redemption(red)
tw.on_redemption(red)  # delivered twice by two subscriptions
tw.on_redemption({"id": "r2", "user_name": "Olia", "reward": {"id": "y", "title": "Шари Суслова"}})
tw.on_redemption({"id": "r3", "user_name": "Ivan", "reward": {"id": "z", "title": "Щось інше"}})
check(got == [("anekdot", "Vasyl"), ("suslov", "Olia")], f"routed by title, once each: {got}")

# one entry in companion/redeems.py: Twitch routing, the Redeems tab's picker and Test, the helper's test command
check_redeem(check, "anekdot", "TWITCH_ANEKDOT_REWARD", "on_anekdot")
ini = (ROOT / "settings.example.ini").read_text(encoding="utf-8")
check("\nTWITCH_ANEKDOT_REWARD=" in ini.replace("\r\n", "\n"), "settings.example.ini has it (empty = off)")
check(all("TWITCH_ANEKDOT_REWARD" in (ROOT / r).read_text(encoding="utf-8") for r in ("README.md", "README.en.md")),
      "both READMEs explain it")

# the helper: at once, straight to the game, not through the Zone queue
sent = []
t = talker.Talker.__new__(talker.Talker)
state = {"mod_version": 15, "actor": {"health": 1}}
t.game = type("G", (), {"send": lambda self, *x: sent.append(x), "state": lambda self: state})()
t.zone = type("Q", (), {"add": lambda *a: (_ for _ in ()).throw(AssertionError("queued")),
                        "retry": lambda *a: (_ for _ in ()).throw(AssertionError("retried"))})()
t.on_anekdot("Vasyl_77")
check(len(sent) == 1 and sent[0][0] == "zone" and sent[0][2].startswith("anekdot|Анекдот|Vasyl_77"),
      f"sent to the game at once: {sent}")
check(t.zone_fired.get("kind") == "anekdot", "the game's answer is matched to it (for the reaction)")
sent.clear()
state["mod_version"] = 14
t.on_anekdot("Vasyl_77")
check(not sent, "an old game script (before v15): nothing sent")
state["mod_version"], state["actor"]["health"] = 15, 0
t.on_anekdot("Vasyl_77")
check(not sent, "player dead: nothing sent")

# the game's answer: on success the men react; a failure isn't retried (it's not a queued Zone event)
reacted = []
t.zone_react = lambda kind, ev, *a, **k: reacted.append(kind)
t.report_zone = lambda *a, **k: None
t.zone_fired = {"kind": "anekdot", "user": "Vasyl_77"}
t.on_zone_results([{"type": "zone_done", "what": "anekdot", "ok": True, "section": "bread, kolbasa, bolt x12"}])
check(reacted == ["anekdot"], f"done: the men around react {reacted}")
t.zone_fired = {"kind": "anekdot", "user": "Vasyl_77"}
t.on_zone_results([{"type": "zone_done", "what": "anekdot", "ok": False, "reason": "no item"}])
check(reacted == ["anekdot"] and t.zone_fired is None, "failed: given up, no reaction, no retry")

what = talker.Talker.zone_what(t, "anekdot", {})
check("bread" in what and "bolts" in what and "laugh" in what and "joke" in what,
      "the men around are told what fell, to laugh and tell a short joke")
print("OK" if ok else "FAIL")
