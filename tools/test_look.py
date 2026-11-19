"""When one NPC talks to another, they face each other while he speaks: the app sends "look:<id>:<s>" for both,
and the game script (v13) turns them, keeps them turned while their own logic tries to look elsewhere, lets go
after the time is up, never turns a man who is fighting, and makes a gesture toward the man he talks to."""
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "companion"))
import talker  # noqa: E402

ok = True


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    return cond


sent = []
t = talker.Talker.__new__(talker.Talker)
t.recording, t.spoken = False, []
t.game = type("G", (), {"send": lambda self, *x: sent.append(x), "distance_to": lambda self, i: 3})()
t.voice = type("V", (), {"say": lambda self, npc, line, current_dist=None, on_start=None, **k: on_start()})()
t.brain = type("B", (), {"news": type("N", (), {"mark_mentioned": lambda self, x: []})()})()
t.show_line = lambda *a: None
t.gesture = lambda *a: None
talker.report = lambda *a: None
looks = lambda: [(x[1], x[2].rsplit(":", 1)[0]) for x in sent if x[0] == "act" and x[2].startswith("look:")]

a, b, c = {"id": 5, "name": "Гонта"}, {"id": 6, "name": "Лоцман"}, {"id": 7, "name": "Вовк"}

# a chat: each line is said to the other one, and both turn to each other
t.speak_lines([(a, "Привіт"), (b, "Здоров"), (a, "Як воно?")], {})
ok &= check(looks() == [(5, "look:6"), (6, "look:5"), (6, "look:5"), (5, "look:6"), (5, "look:6"), (6, "look:5")],
            f"chat: {looks()}")

# an overheard scene: the named man first faces the one who said his name, then whoever answers him
sent.clear()
t.speak_lines([(c, "Що ти сказав?"), (b, "Та нічого"), (c, "То й мовчи")], {}, look_first=b)
ok &= check([x for x in looks() if x[0] == 7] == [(7, "look:6")] * 3, f"overheard: {looks()}")

# one line to a man: he and the man face each other; to the player (or nobody): no look sent
sent.clear()
t.speak(a, "Тримай", {}, look_at=b)
t.speak(a, "Тримай", {}, look_at=talker.PLAYER_TALKER)
t.speak(a, "Тримай", {})
ok &= check(looks() == [(5, "look:6"), (6, "look:5")], f"one line: {looks()}")
hold = [x[2] for x in sent if x[0] == "act" and x[2].startswith("look:")][0]
ok &= check(int(hold.rsplit(":", 1)[1]) >= 3, f"held at least as long as he talks ({hold})")

ok &= check(talker.Talker.MOD_VERSION == 13, "app expects game script v13")

# gestures: never for a man who is fighting or wounded right now (the game refuses them: log noise)
real_gesture = talker.Talker.gesture
fighter, calm = {"id": 21, "name": "Різак"}, {"id": 22, "name": "Вобла"}
t.game.state = lambda: {"npcs": [dict(fighter, in_combat=True), calm]}
sent.clear()
real_gesture(t, fighter, "threat")
real_gesture(t, calm, "threat")
real_gesture(t, dict(calm, wounded=True), "hello")
ok &= check([x for x in sent if x[2].startswith("emote:")] == [("act", 22, "emote:threat")],
            f"gesture only for the man not fighting: {sent}")

# the game script itself, run in LuaJIT (lupa) with stubs for the engine
lua_test = ROOT / "tools" / "look_lua.py"
if lua_test.exists():
    tmp = Path(tempfile.mkdtemp())
    (tmp / "talker").mkdir()
    try:
        out = subprocess.run([sys.executable, str(lua_test), str(ROOT / "mod/gamedata/scripts/talker_bridge.script"),
                              str(tmp)], capture_output=True, text=True, encoding="utf-8", timeout=60).stdout
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("  " + out.strip().replace("\n", "\n  "))
    ok &= check(out.strip().endswith("OK"), "game script: look, keep, let go, not in a fight, gesture toward him")

print("OK" if ok else "FAIL")
