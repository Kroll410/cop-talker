"""The Twitch Zone reward (companion/zone.py, twitch.py, talker.py, the game script v14), offline:
the 25/50/25 roll, packs of weak mutants and lone strong ones, the 5-7 min queue (kept across restarts, test
buttons at once), Twitch routing of the reward, the app's side (PDA notice, the game line, the viewer linked to
his man until he dies, retries) and the game script itself in LuaJIT (tools/zone_lua.py)."""
import os
import random
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "companion"))
import talker  # noqa: E402
import zone  # noqa: E402
from twitch import Twitch  # noqa: E402

ok = True


def check(cond, what):
    global ok
    ok &= bool(cond)
    print(("ok   " if cond else "FAIL ") + what)


tmp = Path(tempfile.mkdtemp())
try:
    # ------------------------------------------------------------ the roll
    rng = random.Random(1)
    rolls = [zone.roll("v", rng=rng) for _ in range(40000)]
    kinds = Counter(r["kind"] for r in rolls)
    share = {k: kinds[k] / len(rolls) for k in kinds}
    check(abs(share["gift"] - .25) < .015 and abs(share["life"] - .5) < .015 and abs(share["child"] - .25) < .015,
          f"Дар 25%, Життя 50%, Дитя 25%: {share}")
    sides = Counter(r["side"] for r in rolls if r["kind"] == "life")
    check(abs(sides["ally"] / sum(sides.values()) - .5) < .02, f"Життя: half friends, half enemies {dict(sides)}")
    children = [r for r in rolls if r["kind"] == "child"]
    check(all(1 <= r["count"] <= 10 for r in children), "Дитя: 1 to 10 mutants")

    def p10(name):
        r = next(m[2] for m in zone.MONSTERS if m[0] == name)
        w = zone.count_weights(r)
        return w[9] / sum(w)

    check(0.008 < p10("псевдогігант") < 0.012, f"10 pseudogiants: about 1% ({p10('псевдогігант'):.4f})")
    r = random.Random(2)
    tush = Counter(r.choices(range(1, 11), zone.count_weights(zone.MONSTERS[0][2]))[0] for _ in range(20000))
    check(tush.most_common(1)[0][0] == 10, f"tushkans: ten is the likeliest pack {tush.most_common(3)}")
    giant = Counter(r.choices(range(1, 11), zone.count_weights(zone.MONSTERS[-1][2]))[0] for _ in range(20000))
    check(giant.most_common(1)[0][0] == 1, f"pseudogiants: mostly one {giant.most_common(3)}")

    # ------------------------------------------------------------ the game line
    what, cap, text = zone.command({"kind": "gift", "user": "Vasya"})
    check((what, cap) == ("gift", "Дар Зони (Vasya)") and "{item}" in text and text.startswith("Зона бажає милосердя"),
          f"gift line: {what}|{cap}|{text}")
    what, cap, text = zone.command({"kind": "life", "side": "enemy", "user": "Vasya"})
    check(what == "life:enemy:Vasya" and text.startswith("Зона грає з життям як заманеться"), f"life line: {what} {text}")
    item = {"kind": "child", "user": "V", "monster": "тушкан", "sections": ["tushkano_normal", "tushkano_weak"],
            "count": 7}
    what, cap, text = zone.command(item)
    check(what == "child:7:tushkano_normal,tushkano_weak" and text.startswith("Зона народжує..."), f"child line: {what}")
    for kind in ("gift", "life", "child"):
        for line in zone.command(zone.roll("Ю|зер\n", kind, random.Random(3))):
            line.encode("cp1251")  # the game reads cp1251: every sign must exist there
    check(zone.clean_nick("Ю|зер\n") == "Юзер", "a nickname can't break the line ('|', new lines)")
    check(zone.parse_gap("5-7") == (300, 420) and zone.parse_gap("3") == (180, 180), "TWITCH_ZONE_GAP parsed")

    # ------------------------------------------------------------ the queue
    q = zone.ZoneQueue(tmp / "q.json", (300, 420), random.Random(4))
    a = q.add("one", 1000)
    b = q.add("two", 1010)
    check(1300 <= a["due"] <= 1420, f"first: 5-7 min after the redemption ({a['due'] - 1000:.0f} s)")
    check(b["due"] - a["due"] >= 300, f"second: 5-7 min after the first ({b['due'] - a['due']:.0f} s)")
    check(q.pop_due(1299) is None, "nothing goes off early")
    late = a["due"] + 600  # the game was paused: the first goes off late...
    check(q.pop_due(late) is a, "the first goes off when its time comes")
    check(q.items[0]["due"] >= late + 300, "...and the second still waits 5-7 min after it")
    t1 = q.add_test("me", late + 1, "child")
    check(q.pop_due(late + 1) is t1 and q.items[0] is b, "a test goes off at once and leaves the real one waiting")
    q2 = zone.ZoneQueue(tmp / "q.json")
    check([i["user"] for i in q2.items] == ["two"], "the queue survives a restart of the app")
    c = q.add("three", late + 2, "life")
    side = c["side"]
    q.items = [c]
    tries = [q.retry(q.pop_due(10 ** 9), 0) for _ in range(3)]
    check(tries == [True, True, False], f"a failed event is tried 3 times in all {tries}")
    q.items = []
    q.retry(dict(c, tries=0), 0)
    check(q.items[0]["side"] == side and q.items[0]["due"] == 30, "a retry keeps friend/enemy, 30 s later")

    # ------------------------------------------------------------ Twitch: which redemption goes where
    zoned, spoken = [], []
    tw = Twitch("id", "Скажи через сталкера", tmp / "tok.json", lambda u, t, r: spoken.append(t), lambda m: None,
                source="chat", zone_title="Зона", on_zone=lambda u, r: zoned.append(u))
    check("channel:read:redemptions" in tw.scopes.split() and "user:read:chat" in tw.scopes.split(),
          f"chat mode with a Zone reward asks to read redemptions too: {tw.scopes}")
    ev = {"id": "r1", "user_name": "Viewer", "reward": {"id": "x", "title": " зона "}, "user_input": ""}
    tw.on_redemption(ev)
    tw.on_redemption(ev)  # the same redemption from a second subscription
    tw.on_redemption({"id": "r2", "user_name": "Other", "reward": {"id": "y", "title": "Hydrate"}, "user_input": "hi"})
    check(zoned == ["Viewer"] and not spoken, f"chat mode: the Zone reward once, other rewards ignored {zoned} {spoken}")
    zoned.clear()
    tw2 = Twitch("id", "Скажи", tmp / "tok.json", lambda u, t, r: spoken.append(t), lambda m: None,
                 source="reward", zone_title="Зона", on_zone=lambda u, r: zoned.append(u))
    tw2.reward_id, tw2.zone_reward_id = "say", "zz"
    tw2.on_redemption({"id": "a", "user_name": "A", "reward": {"id": "zz", "title": "renamed"}, "user_input": ""})
    tw2.on_redemption({"id": "b", "user_name": "B", "reward": {"id": "say", "title": "Скажи"}, "user_input": "$hello"})
    tw2.on_redemption({"id": "c", "user_name": "C", "reward": {"id": "other", "title": "x"}, "user_input": "no"})
    check(zoned == ["A"] and spoken == ["$hello"], f"reward mode: Zone by id, the speech reward as before {zoned} {spoken}")
    tw3 = Twitch("id", "Скажи", tmp / "tok.json", lambda *a: None, lambda m: None, source="chat")
    check(tw3.scopes == "user:read:chat", "no Zone reward set: the sign-in asks for nothing new")

    # ------------------------------------------------------------ the app's side
    sent = []
    t = talker.Talker.__new__(talker.Talker)
    t.game = type("G", (), {"send": lambda self, *x: sent.append(x)})()
    t.twitch, t.zone_reported = None, None
    t.zone = zone.ZoneQueue(tmp / "zq.json", (300, 420), random.Random(5))
    t.twitch_links, t.twitch_names, t.zone_links, t.left_npc = {}, {}, set(), {}
    t.LINKS_FILE = tmp / "links.json"
    t.on_zone("Viewer")
    check(len(t.zone.items) == 1 and sent and sent[0][0] == "twitch" and "Зона почула тебе" in sent[0][2],
          f"redemption: queued, PDA notice {sent}")
    sent.clear()
    state = {"mod_version": 14, "actor": {"health": 1}}
    t.zone_tick(state)
    check(not sent, "not yet: it waits its 5-7 minutes")
    t.zone.items[0]["due"] = 0
    t.zone_tick(dict(state, mod_version=13))
    check(not sent and t.zone.items, "an old game script (v13) gets nothing: it would ignore the line")
    t.zone_tick({"mod_version": 14, "actor": {"health": 0}})
    check(not sent, "the player is dead: it waits")
    t.zone_tick(state)
    check(len(sent) == 1 and sent[0][0] == "zone" and sent[0][2].count("|") == 2 and not t.zone.items,
          f"its time: one zone line for the game {sent}")
    sent.clear()
    t.zone_fired = {"kind": "life", "side": "ally", "user": "Viewer"}
    t.on_zone_results([{"type": "zone_done", "ok": False, "reason": "no place"}])
    check(len(t.zone.items) == 1 and t.zone.items[0]["kind"] == "life", "the game couldn't: tried again soon")
    t.zone.items = []
    t.on_zone_results([{"type": "zone_spawned", "id": 501, "nick": "Viewer", "npc": {"name": "Новенький"}}])
    check(t.twitch_links.get("viewer") == 501 and "viewer" in t.zone_links and ("link", 501, "Viewer") in sent,
          f"his man wears his nickname {t.twitch_links} {sent}")
    check('"zone": true' in t.LINKS_FILE.read_text(encoding="utf-8"), "kept across restarts as a Zone link")
    t.unlink_viewer("Viewer")
    check(t.twitch_links.get("viewer") == 501, "'%%' doesn't take away a man the Zone gave him")
    t.load_links()
    check("viewer" in t.zone_links, "Zone link read back after a restart")
    sent.clear()
    talker.TWITCH_LINKS = False
    t.next_link_sync = 0
    t.sync_links({"twitch_links": [501, 77], "npcs": [{"id": 501}]})
    talker.TWITCH_LINKS = True
    check(("link", 77, "") in sent and ("link", 501, "") not in sent,
          f"links off: other labels go, the Zone man keeps his {sent}")
    t.save_links = lambda: None
    t.unlink_dead([{"type": "death", "victim": {"id": 501}}])
    check("viewer" not in t.twitch_links and "viewer" not in t.zone_links, "he dies: the link goes")
    t.zone_test("gift")
    check(t.zone.items and t.zone.items[0].get("test") and t.zone.items[0]["kind"] == "gift",
          "the window's test button: a gift at once")

    # ------------------------------------------------------------ the game script, in LuaJIT
    game = tmp / "game"
    (game / "talker").mkdir(parents=True)
    out = subprocess.run([sys.executable, str(ROOT / "tools" / "zone_lua.py"),
                          str(ROOT / "mod/gamedata/scripts/talker_bridge.script"), str(game)],
                         capture_output=True, text=True, encoding="utf-8", timeout=60,
                         env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    print("  " + (out.stdout + out.stderr).strip().replace("\n", "\n  "))
    check(out.stdout.strip().endswith("OK"), "game script: gift, friend, enemy, mutants, missing sections")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("OK" if ok else "FAIL")
