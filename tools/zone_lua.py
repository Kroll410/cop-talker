"""Runs talker_bridge.script in LuaJIT with engine stubs and checks the "zone" inbox line (used by test_zone.py).
Prints one line per check ("ok   ..." / "FAIL ...") and OK or FAIL at the end."""
import json
import sys
from pathlib import Path

import lupa.luajit21 as lj

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import zone  # noqa: E402  (its pct must read the same as the game's zone_pct)

script, root = sys.argv[1], sys.argv[2].replace("\\", "/") + "/"
L = lj.LuaRuntime()
L.execute(r'''
ROOT = ...
now_ms = 1000
news, created, follows, hits = {}, {}, {}, {}
function time_global() return now_ms end
function getFS() return { update_path = function() return ROOT .. "talker/" end } end
function vector()
  local v = { x = 0, y = 0, z = 0 }
  function v:set(x, y, z) if type(x) == "table" then self.x, self.y, self.z = x.x, x.y, x.z else self.x, self.y, self.z = x, y, z end; return self end
  function v:sub(o) self.x, self.y, self.z = self.x - o.x, self.y - o.y, self.z - o.z; return self end
  function v:distance_to(o) return math.sqrt((self.x - o.x)^2 + (self.z - o.z)^2) end
  return v
end
objs = {}
function make(id, name, x)
  local o = { _id = id, _alive = true, _x = x or 0, _rel = 1, health = 1 }
  function o:id() return self._id end; function o:alive() return self._alive end
  function o:position() return vector():set(self._x, 0, 0) end; function o:character_name() return name end
  function o:character_community() return self._comm or "stalker" end; function o:character_rank() return 300 end
  function o:set_character_community(c) self._comm = c end
  function o:name() return "st_" .. id end; function o:relation() return self._rel end
  function o:set_relation(r) self._rel = r end; function o:force_set_goodwill(g) self._gw = g end
  function o:best_enemy() return nil end; function o:sound_prefix() return "" end; function o:clsid() return 1 end
  function o:active_item() return nil end; function o:get_current_outfit() return nil end
  function o:make_object_visible_somewhen() end
  function o:hit(h) table.insert(hits, self._id .. ":" .. tostring(h.draftsman and h.draftsman:id())) end
  function o:level_vertex_id() return 1 end; function o:game_vertex_id() return 7 end
  function o:give_game_news(caption, text) table.insert(news, caption .. "|" .. text) end
  objs[id] = o; return o end
game_object = { enemy = 3, friend = 0, neutral = 1 }
db = { storage = {} }
db.actor = make(0, "Player", 0); db.actor.health = 1
-- sections the "game" has: a few items, two stalkers, two mutant kinds
HAVE = { medkit = true, af_medusa = true, wpn_ak74 = true, sim_default_bandit_2 = true, sim_default_duty_1 = true,
  sim_default_stalker_3 = true,
  tushkano_normal = true, gigant_strong = true }
function system_ini() return {
  section_exist = function(_, s) return HAVE[s] == true end,
  r_string = function(_, s, k) return "name_" .. s end,
  r_float = function(_, s, k) return COST[s] or 1000 end } end
COST = { medkit = 250, af_medusa = 4000, wpn_ak74 = 4000, vodka = 40, wpn_addon_silencer = 200 }
game = { translate_string = function(s) return "T(" .. s .. ")" end }
next_id = 100
function alife() return {
  object = function(_, id) return objs[id] and { force_set_goodwill = function() end } or nil end,
  create = function(_, sec, pos, lv, gv, parent)
    next_id = next_id + 1
    table.insert(created, { id = next_id, sec = sec, lv = lv, gv = gv, parent = parent, d = pos:distance_to(db.actor:position()),
      x = pos.x, y = pos.y, z = pos.z })
    return { id = next_id }
  end } end
-- walkable vertices: vertex N stands N metres east of the player
-- saves: what the console was told; TUTORIAL = a scripted scene (no saving), on until the autosave checks below
saves, TUTORIAL, TALKING = {}, true, false
function get_console() return { execute = function(_, cmd) table.insert(saves, cmd) end } end
db.actor.is_talking = function() return TALKING end
level = { object_by_id = function(id) return objs[id] end, name = function() return "zaton" end,
  has_active_tutorial = function() return TUTORIAL end, is_wfx_playing = function() return false end,
  vertex_in_direction = function(from, dir, dist) return 1000 + math.floor(dist) end,
  vertex_position = function(lv) return vector():set(lv - 1000, 0, 0) end }
function hit() return {} end
hit = setmetatable({ wound = 5 }, { __call = function() return {} end })
news_manager = { relocate_item = function(_, dir, sec) table.insert(news, "relocate|" .. dir .. "|" .. sec) end }
xr_sound = { set_sound_play = function() end }
xr_logic = { configure_schemes = function(npc) table.insert(follows, npc:id()) end, activate_by_section = function() end }
modules = { stype_stalker = 1 }
function IsStalker(o) return o and o._id ~= 0 end
function IsMonster() return false end
DIK_keys = setmetatable({}, { __index = function() return 1 end })
function ini_file() return nil end
xr_wounded = { is_wounded = function() return false end }
callback = { key_press = 1, hit = 2, key_release = 3 }
db.actor.set_callback = function() end
function get_hud() return nil end
''', root)
L.execute(open(script, encoding="utf-8").read())

ok = True


def check(cond, what):
    global ok
    ok &= bool(cond)
    print(("ok   " if cond else "FAIL ") + what)


def inbox(text):
    with open(root + "talker/inbox.txt", "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text + "\n")


def step(ms):
    L.execute(f"now_ms = now_ms + {ms}; pcall(update, 0)")


def events():
    try:
        with open(root + "talker/events.jsonl", encoding="utf-8") as fh:
            out = [json.loads(line) for line in fh if line.strip()]
    except OSError:
        return []
    open(root + "talker/events.jsonl", "w").close()
    return out


def take(name):
    out = list(L.eval(name).values())
    L.execute(f"{name} = {{}}")
    return out


step(300)
events()

# gift: one existing item into the player's backpack, PDA line with its name first
inbox("zone||gift|Дар Зони (viewer)|Зона бажає милосердя — отримано {item} в рюкзак (шанс {chance:25})")
step(300)
c, n, ev = take("created"), take("news"), events()
check(len(c) == 1 and c[0]["parent"] == 0 and c[0]["sec"] in ("medkit", "af_medusa", "wpn_ak74"),
      f"gift: one real item made in the backpack {[dict(x) for x in c]}")
sec = c[0]["sec"] if c else "?"
def gift_pct(sec, have=("medkit", "af_medusa", "wpn_ak74"), base=25):
    costs = {"medkit": 250, "af_medusa": 4000, "wpn_ak74": 4000, "vodka": 40, "wpn_addon_silencer": 200}
    w = {s: (100 / max(costs[s], 10)) ** 0.6 * (0.15 if s.startswith("wpn_addon_") else 1) for s in have}
    return zone.pct(base * w[sec] / sum(w.values()) / 100)


check(n and n[0] == f"Дар Зони (viewer)|Зона бажає милосердя — отримано T(name_{sec}) в рюкзак (шанс {gift_pct(sec)})",
      f"gift: PDA line with the item's name comes first {n}")
check(any(x.startswith("relocate|in|") for x in n), "gift: the game's 'item received' notice")
check(ev and ev[0]["type"] == "zone_done" and ev[0]["ok"] and ev[0]["section"] == sec, f"gift: zone_done ok {ev}")
# a very rare chance still reads as a number, not "0.00%" (two significant digits, same as zone.py)
inbox("zone||gift|Dar|{item} {chance:0.003}")
step(300)
c, n = take("created"), take("news")
events()
tiny = gift_pct(c[0]["sec"], base=0.003) if c else "?"
check(n and n[0].endswith(" " + tiny) and "0.00%" not in n[0] and 0 < float(tiny[:-1]) < 0.01,
      f"gift: a tiny chance shows its digits ({n[0] if n else n})")

# life: ally, 15-30 m away, follows, wears the nickname, the app hears zone_spawned
inbox("zone||life:ally:Viewer_1|Життя для Зони (Viewer_1)|Зона грає з життям як заманеться — Viewer_1 тепер іде з тобою")
step(300)
c, n, ev = take("created"), take("news"), events()
check(len(c) == 1 and c[0]["sec"] == "sim_default_stalker_3" and c[0]["parent"] is None,
      f"life: the friend is always a Loner (free stalker section) {[dict(x) for x in c]}")
check(c and 15 <= c[0]["d"] <= 30, f"life: 15-30 m away ({c[0]['d'] if c else '?'} m)")
check(n and n[0].startswith("Життя для Зони (Viewer_1)|Зона грає"), f"life: PDA line {n}")
check(ev and ev[0]["ok"] and ev[0]["side"] == "ally" and ev[0]["nick"] == "Viewer_1", f"life: zone_done {ev}")
ally = c[0]["id"] if c else 0
step(300)  # not in the game yet: nothing happens, nothing breaks
L.execute(f"o = make({ally}, 'Новенький', 20); o._comm = 'bandit'; db.storage[{ally}] = {{ object = o }}")
step(300)  # seen
check(not take("follows"), "life: waits a moment after he comes into the game")
step(1200)
check(take("follows") == [ally], "life: the ally follows the player")
check(L.eval(f"objs[{ally}]._rel") == 0, "life: the ally is a friend")
check(L.eval(f"objs[{ally}]:character_community()") == "stalker", "life: forced to the Loners if anything changed it")
L.execute(f"objs[{ally}]._rel = 3; objs[{ally}]._comm = 'bandit'")  # a stray shot, or the game's logic, turns him
step(2100)
check(L.eval(f"objs[{ally}]._rel") == 0 and L.eval(f"objs[{ally}]:character_community()") == "stalker",
      "life: he turns back into a friendly Loner within 2 s")
check(L.eval(f"twitch_links[{ally}]") == "Viewer_1", "life: he wears the viewer's nickname")
ev = events()
check(ev and ev[0]["type"] == "zone_spawned" and ev[0]["id"] == ally and ev[0]["nick"] == "Viewer_1"
      and ev[0]["npc"]["name"] == "Новенький", f"life: the app hears zone_spawned {ev}")

# life: enemy
# enemies: any faction (over many rolls the bandit and Duty sections both come up)
seen = set()
for _ in range(30):
    inbox("zone||life:enemy:Rnd|c|t")
    step(300)
    seen |= {x["sec"] for x in take("created")}
    events()
    take("news")
check({"sim_default_bandit_2", "sim_default_duty_1"} <= seen, f"life: an enemy may be of any faction {seen}")
inbox("zone||life:enemy:Bad_Guy|c|t")
step(300)
c = take("created")
events()
foe = c[0]["id"]
L.execute(f"o = make({foe}, 'Злий', 25); db.storage[{foe}] = {{ object = o }}")
step(300)
step(1200)
check(L.eval(f"objs[{foe}]._rel") == 3 and not take("follows"), "life: the enemy hates the player and doesn't follow")
check(L.eval(f"twitch_links[{foe}]") == "Bad_Guy", "life: the enemy wears the nickname too")
events()
take("news")

# child: n mutants of the first section the game has, 25-50 m away, each provoked once in the game
inbox("zone||child:4:tushkano_weak,tushkano_normal|Дитя Зони (v)|Зона народжує... тушкан (4)")
step(300)
c, n, ev = take("created"), take("news"), events()
check(len(c) == 4 and all(x["sec"] == "tushkano_normal" for x in c), f"child: 4 tushkans {[x['sec'] for x in c]}")
check(all(25 <= x["d"] <= 50 for x in c), f"child: 25-50 m away {[x['d'] for x in c]}")
check(n and n[0] == "Дитя Зони (v)|Зона народжує... тушкан (4)", f"child: PDA line {n}")
check(ev and ev[0]["ok"] and ev[0]["count"] == 4, f"child: zone_done {ev}")
for x in c:
    L.execute(f"o = make({x['id']}, 'тушкан', 30); db.storage[{x['id']}] = {{ object = o }}")
step(300)
step(1200)
h = take("hits")
check(sorted(h) == sorted(f"{x['id']}:0" for x in c), f"child: each one goes for the player {h}")

# a mutant the game doesn't have: nothing made, the app is told why
inbox("zone||child:3:chimera_normal,chimera_strong|c|t")
step(300)
c, n, ev = take("created"), take("news"), events()
check(not c and not n and ev and not ev[0]["ok"] and ev[0]["reason"] == "no mutant", f"child: missing section {ev}")

# count is clamped to 1..10
inbox("zone||child:99:gigant_strong|c|t")
step(300)
c = take("created")
events()
take("news")
check(len(c) == 10, f"child: at most 10 ({len(c)})")

# nonsense: reported, nothing made
inbox("zone||boom|c|t")
step(300)
ev = events()
check(not take("created") and ev and not ev[0]["ok"] and ev[0]["reason"] == "unknown", f"unknown event {ev}")

# a man who never comes into the game is forgotten after 30 s (no endless checking)
inbox("zone||life:ally:Ghost|c|t")
step(300)
take("created")
events()
step(31000)
try:
    errors = open(root + "talker/bridge_errors.log", encoding="utf-8").read()
except OSError:
    errors = ""
check("never came into the game" in errors, "a spawn that never comes into the game is forgotten after 30 s")

# autosave before a Zone event: one rotating save, the event a moment after it, once for events close together
L.execute("TUTORIAL = false")
take("saves")
step(11000)
events()
take("created")
take("news")
inbox("zone||gift|c|Зона бажає милосердя — отримано {item} в рюкзак")
step(300)
s = take("saves")
check(s == ["save talker_autosave"], f"autosave: the game is saved first, under one name {s}")
check(not take("created"), "autosave: the event waits for the save")
inbox("zone||child:2:tushkano_normal|c|t")  # a second event 0.5 s later
step(300)
check(not take("saves") and not take("created"), "a second event close behind: no second save, and it waits its turn")
step(1200)
c = take("created")
ev = events()
check([x["sec"] for x in c][:1] != ["tushkano_normal"] and len(c) == 3, f"then both, the gift first {[x['sec'] for x in c]}")
check([e.get("autosave") for e in ev if e["type"] == "zone_done"] == ["saved", "recent"], f"the app hears it {ev}")
take("news")
step(11000)
L.execute("TALKING = true")
inbox("zone||gift|c|t")
step(300)
ev = events()
check(not take("saves") and take("created") and ev[0].get("autosave") == "talking",
      "talking to someone: no save, the event goes off at once")
L.execute("TALKING = false; TUTORIAL = true")
take("news")
step(11000)
inbox("zone||gift|c|t")
step(300)
ev = events()
check(not take("saves") and ev[0].get("autosave") == "scene", "a scripted scene: no save")
L.execute("TUTORIAL = false; db.actor._alive = false")
take("news")
take("created")
step(11000)
inbox("zone||gift|c|t")
step(300)
ev = [e for e in events() if e["type"] == "zone_done"]  # (the game also reports the player's death)
check(not take("saves") and ev and ev[0].get("autosave") == "dead", f"dead: no save {ev}")

# gift odds follow the price, add-ons rarer than their price: over many gifts
L.execute("db.actor._alive = true; HAVE.vodka = true; HAVE.wpn_addon_silencer = true; TUTORIAL = true")
from collections import Counter
got = Counter()
for _ in range(400):
    inbox("zone||gift|c|t")
    step(300)
    got.update(x["sec"] for x in take("created"))
    events()
    take("news")
print("  gifts:", dict(got))
check(got["vodka"] > got["medkit"] > got["wpn_addon_silencer"] and got["vodka"] > 5 * got["wpn_addon_silencer"],
      "cheap things come most; a cheap silencer still much rarer than vodka or a medkit")
check(got["medkit"] > 2 * got["wpn_ak74"], "a medkit (250) comes far more often than an AK (4000)")

# «Шари Суслова»: at once (no queue in the game either), two fireballs side by side ahead of the player, the sausage
# right between them and further ahead, all just above the ground
L.execute("""HAVE.af_fireball = true; HAVE.kolbasa = true; TUTORIAL = true
level.vertex_id = function(p) return 5000 end
function db.actor:direction() return vector():set(0, 0, 1) end""")
take("created"); events(); take("news")
inbox("zone||suslov|Шари Суслова|viewer шле привіт від Суслова")
step(300)
c, n, ev = take("created"), take("news"), events()
balls = sorted((x for x in c if x["sec"] == "af_fireball"), key=lambda x: x["x"])
sausage = [x for x in c if x["sec"] == "kolbasa"]
check(len(balls) == 2 and len(sausage) == 1 and len(c) == 3, f"suslov: 2 fireballs and 1 sausage {[x['sec'] for x in c]}")
if len(balls) == 2 and sausage:
    s0 = sausage[0]
    check(abs(balls[0]["x"] + balls[1]["x"]) < 1e-6 and balls[1]["x"] - balls[0]["x"] > 0.15,
          f"the balls lie side by side, mirrored about the sausage's line ({balls[0]['x']:.2f}, {balls[1]['x']:.2f})")
    check(abs(s0["x"]) < 1e-6 and s0["z"] > balls[0]["z"] == balls[1]["z"] > 1.0,
          f"the sausage is between them, pointing away from the player (balls z={balls[0]['z']:.2f}, sausage z={s0['z']:.2f})")
    check(all(abs(x["y"] - 0.1) < 1e-6 and x["parent"] is None for x in c), "all on the ground (just above it), none in the backpack")
check(ev and ev[0]["ok"] and ev[0]["what"] == "suslov" and any("Суслова" in x for x in n), f"done, with a PDA line {ev} {n}")

# they stay props: settle, then pinned; the fireballs never hide; picked up -> put back; kept over a reload
L.execute("""
pstor, shown, drops = {}, {}, {}
xr_logic.pstor_store = function(_, k, v) pstor[k] = v end
xr_logic.pstor_retrieve = function(_, k, d) return pstor[k] or d end
function prop(id, x, af)
  local o = make(id, "prop", x)
  o._fixed = {}
  function o:parent() return self._parent end
  function o:get_physics_shell() return { get_elements_number = function() return 2 end,
    get_element_by_order = function(_, i) return { is_fixed = function() return o._fixed[i] end,
      fix = function() o._fixed[i] = true end } end } end
  if af then function o:get_artefact() return { SwitchVisibility = function(_, b) table.insert(shown, id) end } end
  else function o:get_artefact() error("not an artifact") end end
  return o
end""")
ids = {x["sec"]: [] for x in c}
for x in c:
    ids[x["sec"]].append(x["id"])
    L.execute(f"prop({x['id']}, {x['x']}, {'true' if x['sec'] == 'af_fireball' else 'false'})")
pinned = lambda i: L.eval(f"objs[{i}]._fixed[0] == true and objs[{i}]._fixed[1] == true")
step(1100)
check(not any(pinned(x["id"]) for x in c), "just landed: not pinned yet (let them settle)")
step(1100); step(1100)
check(all(pinned(x["id"]) for x in c), "settled: every piece pinned in place, they don't roll")
shown = take("shown")
check(set(shown) == set(ids["af_fireball"]), f"the fireballs are kept shown, the sausage isn't asked {shown}")
ball = ids["af_fireball"][0]
L.execute(f"""objs[{ball}]._x = 0.5
db.actor.drop_item_and_teleport = function(self, o, p) table.insert(drops, o:id() .. '@' .. p.z); o._parent = nil end
objs[{ball}]._parent = db.actor; on_item_take(objs[{ball}])""")
check(not [e for e in events() if e.get("type") == "artifact"], "picking one up isn't reported as a found artifact")
step(100)
drops = take("drops")
check(len(drops) == 1 and drops[0].startswith(f"{ball}@"), f"picked up: put straight back on the ground {drops}")
saved = L.eval("pstor.talker_props") or ""
check(saved.count(";") == 2 and saved.count(":1:1") == 2, f"kept in the save, pinned: {saved}")
L.execute(f"on_actor_spawn(); for _, i in ipairs({{{','.join(str(x['id']) for x in c)}}}) do objs[i]._fixed = {{}} end")
step(1100)
check(all(pinned(x["id"]) for x in c), "after a reload: pinned again at once (already settled before)")
L.execute(f"objs[{ids['kolbasa'][0]}] = nil")
step(1100)
check(ids["kolbasa"][0] not in [int(p.split(":")[0]) for p in (L.eval("pstor.talker_props") or "").split(";") if p],
      "a prop gone from the game is forgotten")
events()
L.execute("HAVE.kolbasa = false")
inbox("zone||suslov|c|t")
step(300)
ev = events()
check(not take("created") and ev and not ev[0]["ok"] and ev[0]["reason"] == "no item", f"no sausage in the game: nothing spawned {ev}")
print("OK" if ok else "FAIL")
