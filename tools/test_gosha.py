"""«Гоша»: a reward the streamer makes on Twitch (the app never creates it) and picks in Settings. A redemption goes to
the game at once, no Zone queue: a Mercenary (найманець) named «Гоша» turns up 15-30 m away with a stock SPAS-12 and
comes for the player; the viewer's nickname is on his label and the men around react once he's in the game. The game
script's side (name, gun, his own guns taken, hostility) is checked in LuaJIT by tools/gosha_lua.py."""
import os
import re
import subprocess
import sys
import tempfile
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


# Twitch: a redemption of the «Гоша» reward calls its trigger once, next to the other rewards
got = []
tw = Twitch("id", "", ROOT / "nope.json", lambda *a: None, lambda *a: None, source="chat",
            zone_title="Дар Зони", on_zone=lambda u, ev: got.append(("zone", u)),
            triggers={"Шари Суслова": lambda u, ev: got.append(("suslov", u)),
                      "Гоша": lambda u, ev: got.append(("gosha", u))})
red = {"id": "r1", "user_name": "Vasyl", "reward": {"id": "x", "title": "Гоша"}}
tw.on_redemption(red)
tw.on_redemption(red)  # delivered twice by two subscriptions
tw.on_redemption({"id": "r2", "user_name": "Olia", "reward": {"id": "y", "title": "Шари Суслова"}})
check(got == [("gosha", "Vasyl"), ("suslov", "Olia")], f"routed by title, once each: {got}")
src = (ROOT / "companion" / "twitch.py").read_text(encoding="utf-8")
check('"POST", "/channel_points/custom_rewards"' not in src and '"DELETE"' not in src,
      "the app never creates or deletes a reward")
tsrc = (ROOT / "companion" / "talker.py").read_text(encoding="utf-8")
check("(TWITCH_GOSHA_REWARD, self.on_gosha)" in tsrc, "the setting's reward is routed to on_gosha")

# the handler: at once, straight to the game, not through the Zone queue
sent = []
t = talker.Talker.__new__(talker.Talker)
state = {"mod_version": 15, "actor": {"health": 1}}
t.game = type("G", (), {"send": lambda self, *x: sent.append(x), "state": lambda self: state})()
t.zone = type("Q", (), {"add": lambda *a: (_ for _ in ()).throw(AssertionError("queued")),
                        "retry": lambda *a: (_ for _ in ()).throw(AssertionError("retried"))})()
t.on_gosha("Vasyl|77\n")
check(len(sent) == 1 and sent[0][0] == "zone", f"sent to the game at once: {sent}")
what, caption, text = sent[0][2].split("|") if sent else ("", "", "")
check(what == "npc:gosha:killer:wpn_spas12:enemy:Vasyl77", f"a найманець (killer) with a stock SPAS-12, hostile: {what}")
check(caption == "Гоша" and text.startswith("Vasyl77 кличе Гошу"), f"named «Гоша», PDA line from the viewer: {caption}|{text}")
check(t.zone_fired == {"kind": "gosha", "user": "Vasyl|77\n"}, "the game's answer is matched to it")
for st, why in (({"mod_version": 14, "actor": {"health": 1}}, "old script"),
                ({"mod_version": 15, "actor": {"health": 0}}, "player dead")):
    sent.clear()
    state.clear()
    state.update(st)
    t.on_gosha("Vasyl")
    check(not sent, f"{why}: nothing sent")

# the game's answers: no reaction until he's in the game, then the men around react and the viewer speaks through him
reacts, links, logs = [], [], []
t.zone_react = lambda kind, ev, spawned=None: reacts.append((kind, (spawned or {}).get("name")))
t.link_viewer = lambda user, npc, from_zone=False: links.append((user, npc["id"], from_zone))
t.report_zone = lambda force=False: None
talker.log = lambda s: logs.append(s)
t.zone_fired = {"kind": "gosha", "user": "Vasyl"}
t.on_zone_results([{"type": "zone_done", "what": "npc:gosha:killer:wpn_spas12:enemy:Vasyl", "ok": True, "id": 101,
                    "tag": "gosha", "name": "Гоша", "section": "sim_default_killer_2"}])
check(not reacts, "done, but he isn't in the game yet: nobody reacts")
t.on_zone_results([{"type": "zone_spawned", "id": 101, "nick": "Vasyl", "side": "enemy", "tag": "gosha",
                    "named": True, "npc": {"name": "Гоша", "community": "killer"}}])
check(reacts == [("gosha", "Гоша")], f"in the game: the men around react to Гоша {reacts}")
check(links == [("Vasyl", 101, True)], f"the viewer speaks through him until he dies {links}")
logs.clear()
t.on_zone_results([{"type": "zone_spawned", "id": 102, "nick": "Vasyl", "side": "enemy", "tag": "gosha",
                    "named": False, "npc": {"name": "Петро Шуляк"}}])
check(any("Петро Шуляк" in s for s in logs), f"the game kept its own name: said in the log {logs}")
t.zone_fired = {"kind": "gosha", "user": "Vasyl"}
logs.clear()
t.on_zone_results([{"type": "zone_done", "what": "npc:gosha:killer:wpn_spas12:enemy:Vasyl", "ok": False,
                    "reason": "no place"}])
check(any("given up" in s for s in logs), f"the game couldn't: given up, not queued again {logs}")

what = talker.Talker.zone_what(t, "gosha", {}, {"name": "Гоша"})
check("Гоша" in what and "найманці" in what and "shotgun" in what, f"the men around are told who came: {what}")

# the window and the settings
app = (ROOT / "companion" / "app.py").read_text(encoding="utf-8")
check(re.search(r'REWARD_PICK = \{[^}]*"TWITCH_GOSHA_REWARD"', app), "Settings: picked from the channel's rewards")
check('"TWITCH_GOSHA_REWARD": "«Гоша» reward"' in app and '("Гоша", "gosha",' in app, "a label and a test button")
check(re.search(r"^TWITCH_GOSHA_REWARD=$", (ROOT / "settings.example.ini").read_text(encoding="utf-8"), re.M),
      "in settings.example.ini, off by default")
for readme in ("README.md", "README.en.md"):
    check("TWITCH_GOSHA_REWARD" in (ROOT / readme).read_text(encoding="utf-8"), f"described in {readme}")

# the game script itself
tmp = Path(tempfile.mkdtemp())
(tmp / "talker").mkdir()
out = subprocess.run([sys.executable, str(ROOT / "tools" / "gosha_lua.py"),
                      str(ROOT / "mod" / "gamedata" / "scripts" / "talker_bridge.script"), str(tmp)],
                     capture_output=True, text=True, encoding="utf-8", env=dict(os.environ, PYTHONIOENCODING="utf-8"))
print(out.stdout.rstrip())
check(out.returncode == 0 and out.stdout.rstrip().endswith("OK"), f"game script (gosha_lua.py) {out.stderr[-400:]}")
print("OK" if ok else "FAIL")
