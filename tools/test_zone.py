"""The Twitch Zone reward (companion/zone.py, twitch.py, talker.py, the game script v14), offline:
the 25/50/25 roll, packs of weak mutants and lone strong ones, the queue (first at once, the rest 5-7 min apart,
gap 0 = all at once; kept across restarts, test
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
    check(all(1 <= r["count"] <= zone.most(r["monster"]) for r in children),
          f"Дитя: 1 to {zone.PACK_MAX} mutants (default), тушкан up to 10")
    check(zone.most("тушкан", 3) == 10 and zone.most("сліпий пес", 3) == 3 and zone.most("бюрер") == zone.PACK_MAX,
          "тушкан has his own most (10), whatever TWITCH_ZONE_PACK_MAX says")
    tush = Counter(r["count"] for r in (zone.roll("v", "child", random.Random(s)) for s in range(30000))
                   if r["monster"] == "тушкан")
    check(max(tush) > 6 and max(tush) <= 10 and abs(sum(zone.count_chance("тушкан", n) for n in range(1, 11)) - 1) < 1e-9
          and zone.count_chance("тушкан", 11) == 0 and zone.count_chance("сліпий пес", 7) == 0,
          f"тушкан: packs up to 10 really come ({sorted(tush.items())})")

    # pack sizes: mostly one or two, big packs rare, dangerous kinds rarer and smaller (over many rolls)
    def packs(pack_max, n=60000, seed=8):
        g = random.Random(seed)
        return [zone.roll("v", "child", g, pack_max) for _ in range(n)]

    for pm in (6, 10):
        got = packs(pm)
        size = Counter(r["count"] for r in got)
        share = {k: v / len(got) for k, v in size.items()}
        small, mid, big = (sum(share.get(c, 0) for c in rng_) for rng_ in (range(1, 3), range(3, 5), range(5, 11)))
        check(all(r["count"] <= (10 if r["monster"] == "тушкан" else pm) for r in got),
              f"max {pm}: never more (тушкан: 10) ({max(size)})")
        check(small > .75 and mid < .2 and big < .06,
              f"max {pm}: 1-2: {small:.0%}, 3-4: {mid:.0%}, 5+: {big:.1%} (mostly small, big rare)")
        check(all(share.get(c, 0) >= share.get(c + 1, 0) for c in range(1, pm)),
              "each extra mutant is less likely than one fewer")
    got = packs(10)
    kinds = Counter(r["monster"] for r in got)
    check(kinds["тушкан"] > 5 * kinds["псевдогігант"] and kinds["сліпий пес"] > 3 * kinds["химера"],
          f"weak kinds come far more often than dangerous ones {kinds.most_common(3)} ... гігант {kinds['псевдогігант']}")
    big_giants = sum(1 for r in got if r["monster"] == "псевдогігант" and r["count"] >= 3) / len(got)
    big_dogs = sum(1 for r in got if r["monster"] == "сліпий пес" and r["count"] >= 3) / len(got)
    check(big_giants < 0.001 and big_dogs > 10 * big_giants, f"3+ pseudogiants: {big_giants:.4%}, 3+ dogs: {big_dogs:.2%}")
    one = next(r for r in got if r["monster"] == "тушкан" and r["count"] == 1)
    seen = sum(1 for r in got if r["monster"] == "тушкан" and r["count"] == 1) / len(got)
    check(abs(one["chance"] / zone.chance({"kind": "child"}) - seen) < 0.01,
          f"the chance it carries is the real one (1 tushkan: {one['chance'] / .25:.3f} vs seen {seen:.3f})")
    check("1-2:" in zone.odds_report(6) and "псевдогігант" in zone.odds_report(6), "odds_report lists the odds")

    # the PDA chance of an exact event (kind x pack size x 25% Дитя) is what the real roll gives (tools/zone_sim.py)
    sys.path.insert(0, str(ROOT / "tools"))
    import zone_sim  # noqa: E402
    sim_n = 400000
    seen, _, shown = zone_sim.simulate(sim_n, 6, seed=5)
    worst = max(abs(seen[k] / sim_n - zone.chance({"kind": "child", "monster": k[0], "count": k[1]}, 6))
                / max(zone.chance({"kind": "child", "monster": k[0], "count": k[1]}, 6), 0.002)
                for k in seen if seen[k] >= 400)
    check(worst < 0.1 and all(abs(shown[k] - zone.chance({"kind": "child", "monster": k[0], "count": k[1]}, 6)) < 1e-12
                              for k in shown), f"shown chance = how often the roll gives it (worst off by {worst:.1%})")
    c = lambda m, n: zone.chance({"kind": "child", "monster": m, "count": n}, 6)  # noqa: E731
    for rare in ("бюрер", "контролер", "химера", "псевдогігант"):
        check(c(rare, 1) < c("сліпий пес", 3) and c(rare, 1) * 8 < c("сліпий пес", 1),
              f"a lone {rare} ({zone.pct(c(rare, 1))}) is rarer than 3 dogs ({zone.pct(c('сліпий пес', 3))}), "
              f"far rarer than 1 dog ({zone.pct(c('сліпий пес', 1))})")
    check(all(c(m[0], n + 1) <= c(m[0], n) / 2 for m in zone.MONSTERS for n in range(1, 6)),
          "every kind: one more mutant halves the chance at least")
    check(c("сліпий пес", 5) * 20 < c("сліпий пес", 1) and c("сліпий пес", 3) * 4 < c("сліпий пес", 1),
          f"dogs: 1 {zone.pct(c('сліпий пес', 1))}, 3 {zone.pct(c('сліпий пес', 3))}, 5 {zone.pct(c('сліпий пес', 5))}")
    check(abs(sum(c(m[0], n) for m in zone.MONSTERS for n in range(1, 11)) - 0.25) < 1e-9,
          "all mutant outcomes add up to the 25% of Дитя Зони")

    # the chance in the PDA line
    check(zone.pct(0.25) == "25%" and zone.pct(0.0412) == "4.1%" and zone.pct(0.0004) == "0.04%"
          and zone.pct(0.0996) == "10%", "percent text: 25%, 4.1%, 0.04%")
    check([zone.pct(p) for p in (0.0025, 0.00083, 0.00996, 0.0095, 0.009449, 0.0001)] ==
          ["0.25%", "0.083%", "1.0%", "0.95%", "0.94%", "0.01%"], "under 1%: two significant digits (0.25%, 0.083%)")
    tiny = {p: zone.pct(p) for p in (0.0000059, 0.00000059, 0.000001, 0.0000999, 0.0000940, 0.0000949)}
    check(tiny == {0.0000059: "0.00059%", 0.00000059: "0.000059%", 0.000001: "0.0001%", 0.0000999: "0.01%",
                   0.0000940: "0.0094%", 0.0000949: "0.0095%"} and zone.pct(0) == "0.00%",
          f"tiny chances keep two significant digits, never 0.00%: {tiny}")
    three_burers = zone.chance({"kind": "child", "monster": "бюрер", "count": 3})
    check(zone.pct(three_burers) != "0.00%" and float(zone.pct(three_burers)[:-1]) > 0,
          f"3 burers: {zone.pct(three_burers)}")
    life = zone.roll("V", "life", random.Random(1))
    check(abs(life["chance"] - 0.25) < 1e-9 and "(шанс 25%)" in zone.command(life)[2], f"life: {zone.command(life)[2]}")
    # mutants: two rolls (who, then how many), two chances in the PDA line; together they make the exact chance
    kid = next(k for k in (zone.roll("V", "child", random.Random(s)) for s in range(500))
               if k["monster"] == "сліпий пес" and k["count"] == 3)
    text = zone.command(kid)[2]
    check(abs(zone.who_chance("сліпий пес") - 22 / 100) < 1e-12
          and abs(kid["count_chance"] - zone.count_chance("сліпий пес", 3)) < 1e-12
          and abs(.25 * zone.who_chance("сліпий пес") * kid["count_chance"] - kid["chance"]) < 1e-12,
          f"3 dogs: 25% Дитя x who x how many = the exact chance {kid}")
    check(text == "Зона народжує... сліпий пес (шанс 22%), кількість 3 (шанс 9.6%) — шанс саме «сліпий пес (3)»: 2.1%",
          f"child: {text}")
    check(all(abs(sum(zone.count_chance(m[0], n) for n in range(1, 11)) - 1) < 1e-9 for m in zone.MONSTERS)
          and abs(sum(zone.who_chance(m[0]) for m in zone.MONSTERS) - 1) < 1e-9,
          "who: all kinds add up to 100%; how many: its own 100% for each kind")
    burer = zone.command({"kind": "child", "user": "V", "monster": "бюрер", "sections": ["burer_normal"], "count": 1})[2]
    check(burer.count("шанс") == 3 and "бюрер (шанс 1.0%)" in burer and "кількість 1 (шанс 95%) — шанс саме «бюрер (1)»: 0.95%" in burer,
          f"an old queued event (no chances saved) gets them worked out: {burer}")
    q = zone.ZoneQueue(tmp / "q_label.json", (0, 0), random.Random(1))
    q.items = [dict(kid, due=0)]
    check(q.summary(0)[0]["label"] == f"Дитя Зони: сліпий пес ×3 (22%, {zone.pct(kid['count_chance'])})",
          f"window: both chances {q.summary(0)[0]['label']}")
    check("{chance:25}" in zone.command({"kind": "gift", "user": "V"})[2], "gift: the game divides 25% by its items")
    for line in zone.command(kid):
        line.encode("cp1251")

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
    check(zone.parse_gap("5-7") == (300, 420) and zone.parse_gap("3") == (180, 180) and zone.parse_gap("0") == (0, 0),
          "TWITCH_ZONE_GAP parsed")

    # ------------------------------------------------------------ the queue
    q = zone.ZoneQueue(tmp / "q.json", (300, 420), random.Random(4))
    a = q.add("one", 1000)
    b = q.add("two", 1010)
    check(a["due"] == 1000, "gap 5-7, empty queue: the first redemption goes off at once")
    check(300 <= b["due"] - a["due"] <= 420, f"a second one behind it waits 5-7 min ({b['due'] - a['due']:.0f} s)")
    check(q.pop_due(999) is None, "nothing goes off before its redemption")
    late = a["due"] + 600  # the game was paused: the first goes off late...
    check(q.pop_due(late) is a, "the first goes off when its time comes")
    check(q.items[0]["due"] >= late + 300, "...and the second still waits 5-7 min after it")
    t1 = q.add_test("me", late + 1, "child")
    check(q.pop_due(late + 1) is t1 and q.items[0] is b, "a test goes off at once and leaves the real one waiting")
    check(q.pop_due(late + 1 + 299) is None, "the second doesn't go off early")
    q2 = zone.ZoneQueue(tmp / "q.json")
    check([i["user"] for i in q2.items] == ["two"], "the queue survives a restart of the app")
    q0 = zone.ZoneQueue(tmp / "q0.json", zone.parse_gap("0"), random.Random(6))
    z = [q0.add(u, 50) for u in ("a", "b", "c")]
    check([i["due"] for i in z] == [50, 50, 50], "gap 0: every redemption is due at once")
    check([q0.pop_due(50)["user"] for _ in range(3)] == ["a", "b", "c"] and q0.pop_due(50) is None,
          "gap 0: they all go off right away, in order, no spacing")
    q1 = zone.ZoneQueue(tmp / "q1.json", (300, 420), random.Random(7))
    first = q1.add("x", 10)
    q1.pop_due(10)
    later = q1.add("y", 70)  # a minute after the first went off, the queue is empty again
    check(later["due"] == 70, "gap 5-7: first in an empty queue again -> at once")
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
    t.zone_react = lambda *a, **k: None  # the men's reactions: tools/test_zone_react.py
    t.zone = zone.ZoneQueue(tmp / "zq.json", (300, 420), random.Random(5))
    t.twitch_links, t.twitch_names, t.zone_links, t.left_npc = {}, {}, set(), {}
    t.LINKS_FILE = tmp / "links.json"
    t.on_zone("Viewer")
    t.on_zone("Second")
    check(len(t.zone.items) == 2 and sent and sent[0][0] == "twitch" and "Зона почула тебе" in sent[0][2],
          f"redemption: queued, PDA notice {sent}")
    check("просто зараз" in sent[0][2] and "за ~" in sent[1][2], f"first: 'right now', second: 'in ~N min' {sent}")
    sent.clear()
    state = {"mod_version": 14, "actor": {"health": 1}}
    t.zone_tick(state)
    check(len(sent) == 1 and sent[0][0] == "zone" and [i["user"] for i in t.zone.items] == ["Second"],
          f"the first goes off at the next check, the second waits {sent}")
    sent.clear()
    t.zone_tick(state)
    check(not sent, "the second waits its 5-7 minutes")
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
