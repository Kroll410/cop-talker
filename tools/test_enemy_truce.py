"""Enemies don't trade; they can be talked down or bought off. The prompt shows an enemy no goods and no trade
rules, only how a fight may end; any trade tag he writes is dropped, money only as the price of a truce; a
truce paid with money the player doesn't have doesn't happen; and in the game "calm" makes the whole squad
neutral (goodwill raised until the game no longer counts the player as their enemy)."""
import shutil
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


stock = ["Аптечка x2 ~300 #medkit"]
enemy = {"id": 7, "name": "Фелько", "community": "bandit", "rank": 400, "relation": "enemy", "dist": 15, "stock": stock}
state = {"level": "zaton", "npcs": [enemy], "actor": {"money": 2500, "stock": ["Медуза x1 ~3000 #af_medusa"]}}
b = talker.Brain.__new__(talker.Brain)
prompt = b.situation(enemy, state, "", [], "Скільки за аптечку? Куплю за тисячу", "reply")
ok &= check("Аптечка" not in prompt and "[ACTION: item" not in prompt and "He wants to sell you" not in prompt,
            "an enemy sees no goods and no trade rules")
ok &= check("[ACTION: calm]" in prompt and "bribe" in prompt and "2500" not in prompt,
            "he is told how a fight can end (truce, bribe), not how much money the player has")
neutral = dict(enemy, relation="neutral")
ok &= check("Аптечка" in b.situation(neutral, state, "", [], "Скільки за аптечку?", "reply"),
            "a neutral man still trades")

# the reply's tags: no trade with an enemy, money only together with a truce
b.ask_claude = lambda *a, **k: "Давай три штуки і вали.\n[ACTION: calm] [ACTION: take 3000] [ACTION: item Аптечка]"
talker.LLM_PROVIDER = "claude"
b.news = type("N", (), {"mark_mentioned": lambda self, x: [], "available": lambda self, *a: []})()
b.reply(enemy, state, "", [], "Три тисячі, і розійдемось", "reply")
ok &= check(b.last_action == "calm" and b.last_extras == [("take", 3000)], f"truce for money kept, item dropped: "
                                                                          f"{b.last_action} {b.last_extras}")
b.ask_claude = lambda *a, **k: "Тисяча за аптечку.\n[ACTION: item Аптечка] [ACTION: take 1000]"
b.reply(enemy, state, "", [], "Куплю аптечку за тисячу", "reply")
ok &= check(b.last_extras == [], f"an enemy's sale is dropped: {b.last_extras}")

# no money, no truce
sent = []
t = talker.Talker.__new__(talker.Talker)
t.recording, t.spoken = False, []
t.game = type("G", (), {"send": lambda self, *x: sent.append(x), "describe_events": lambda self, *a: "",
                        "last_spoke_to_player": (None, 0, ""), "distance_to": lambda self, i: 5})()
t.memory = type("M", (), {"history": lambda self, k: [], "add": lambda self, *a: None, "remembers": lambda self, k: "",
                          "owed": lambda self, k: 0})()
t.brain = type("B", (), {"reply": lambda self, *a, **k: "Давай дві штуки і вали.", "last_action": "calm",
                         "last_extras": [("take", 2000)]})()
t.speak = lambda *a, **k: None
t.gesture = lambda *a, **k: None
t.squad_backup = lambda *a: None
t.recent_lines = lambda: []
t.npc_key = lambda n, s: n["name"]
talker.CHIME_CHANCE = 0
t.converse(enemy, dict(state, actor={"money": 300}), "Дві тисячі, тільки не стріляйте", "reply")
ok &= check(not any(x[0] == "act" and x[2] in ("calm", "take:2000") for x in sent),
            f"a truce for money he doesn't have: no truce, nothing taken ({[x for x in sent if x[0] == 'act']})")
sent.clear()
t.converse(enemy, dict(state, actor={"money": 5000}), "Дві тисячі, тільки не стріляйте", "reply")
ok &= check(("act", 7, "take:2000") in sent and ("act", 7, "calm") in sent, "with the money: paid, then the truce")

# the game script: "calm" makes him and his squad neutral, even when his faction hates the player
tmp = Path(tempfile.mkdtemp())
(tmp / "talker").mkdir()
try:
    sys.argv = ["x", str(ROOT / "mod/gamedata/scripts/talker_bridge.script"), str(tmp)]
    src = (ROOT / "tools/look_lua.py").read_text(encoding="utf-8")
    env = {}
    exec(src[:src.index("ok = True")], env)
    L, step, inbox = env["L"], env["step"], env["inbox"]
    L.execute("""
    -- relation from goodwill as the engine does: faction attitude (bandits hate the player: -1200) + personal
    function rel_of(o) local a = -1200 + (o._gw or 0)
      if a <= -1000 then return game_object.enemy elseif a >= 1000 then return game_object.friend end return 1 end
    game_object.neutral, game_object.friend = 1, 2
    for _, id in ipairs({5, 6}) do
      local o = objs[id]
      o.relation = function(self) return rel_of(self) end
      o.set_relation = function(self, r) self._gw = 0 end
      o.force_set_goodwill = function(self, g) self._gw = g end
    end
    offline = { force_set_goodwill = function(self, g) self._gw = g end }
    function alife() return { object = function(_, id) return id == 9 and offline or objs[id] end } end
    squad = { squad_members = function() local ids, i = {5, 6, 9}, 0
      return function() i = i + 1; if ids[i] then return { id = ids[i] } end end end }
    function get_object_squad() return squad end
    """)
    inbox("act|5|calm")
    step(300)
    rels = L.eval("{rel_of(objs[5]), rel_of(objs[6]), offline._gw}")
    rels = [rels[1], rels[2], rels[3]]
    ok &= check(rels[0] != 3 and rels[1] != 3, f"the man and his squad mate are no longer enemies ({rels[:2]})")
    ok &= check(rels[2] == 1000, "the squad member off-screen gets the goodwill too")
finally:
    shutil.rmtree(tmp, ignore_errors=True)
print("OK" if ok else "FAIL")
