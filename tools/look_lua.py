"""Runs talker_bridge.script in LuaJIT with engine stubs and checks the look:<id>:<s> action (used by test_look.py)."""
import sys
import lupa.luajit21 as lj

script, root = sys.argv[1], sys.argv[2].replace("\\", "/") + "/"
L = lj.LuaRuntime()
L.execute(r'''
ROOT = ...
now_ms = 1000
calls = {}
function time_global() return now_ms end
function getFS() return { update_path = function() return ROOT .. "talker/" end } end
function vec(x) local v = { x = x, y = 0, z = 0 }; function v:distance_to(o) return math.abs(self.x - o.x) end; return v end
objs = {}
function make(id, name, x)
  local o = { _id = id, _alive = true, _x = x, _enemy = nil }
  function o:id() return self._id end; function o:alive() return self._alive end
  function o:position() return vec(self._x) end; function o:character_name() return name end
  function o:character_community() return "stalker" end; function o:character_rank() return 300 end
  function o:name() return "st_" .. id end; function o:relation() return 1 end
  function o:best_enemy() return self._enemy end; function o:sound_prefix() return "" end; function o:clsid() return 1 end
  function o:active_item() return nil end; function o:get_current_outfit() return nil end
  objs[id] = o; return o end
game_object = { enemy = 3 }
db = { storage = {} }
db.actor = make(0, "Player", 0); db.actor.health = 1
level = { object_by_id = function(id) return objs[id] end, name = function() return "zaton" end }
function IsStalker(o) return o and o._id ~= 0 end
function IsMonster() return false end
DIK_keys = setmetatable({}, { __index = function() return 1 end })
function ini_file() return nil end
function emission_active() return false end
function alife() return { object = function() return nil end } end
xr_wounded = { is_wounded = function() return false end }
-- the state manager: records what he is told to look at, like the game's own one
state_mgr = {
  get_state = function(npc) return "guard" end,
  set_state = function(npc, state, cb, timeout, target, extra)
    local id = npc:id()
    local look = target and target.look_object and target.look_object:id() or nil
    db.storage[id].state_mgr = { look_object = look }
    table.insert(calls, id .. ":" .. state .. ":" .. tostring(look))
  end }
callback = { key_press = 1, hit = 2, key_release = 3 }
db.actor.set_callback = function() end
''', root)
L.execute(open(script, encoding="utf-8").read())
L.execute('''
a = make(5, "Глухар", 10); db.storage[5] = {}
b = make(6, "Юрась", 12); db.storage[6] = {}
''')


def inbox(text):
    open(root + "talker/inbox.txt", "w", encoding="utf-8").write(text + "\n")


def step(ms):
    L.execute(f"now_ms = now_ms + {ms}; pcall(update, 0)")


def calls():
    out = list(L.eval("calls").values())
    L.execute("calls = {}")
    return out


ok = True
step(300)
calls()
inbox("act|5|look:6:4\nact|6|look:5:4")
step(300)
c = calls()
print("look sent:", c)
ok &= "5:guard:6" in c and "6:guard:5" in c

# his logic turns him away: he faces the man again on the next update
L.execute("db.storage[5].state_mgr.look_object = nil")
step(300)
c = calls()
print("logic turned him away ->", c)
ok &= "5:guard:6" in c

# time is up: his own logic gets the look back
step(4500)
c = calls()
print("after 4 s ->", c)
ok &= "5:guard:nil" in c and "6:guard:nil" in c

# a fight: no turning to chat partners
L.execute("a._enemy = b")
inbox("act|5|look:6:4")
step(300)
c = calls()
print("while fighting ->", c)
ok &= not any(x.startswith("5:") for x in c)
L.execute("a._enemy = nil")

# an emote while looking at someone: the gesture is made toward him, not the player
inbox("act|5|look:6:6\nact|5|emote:threat")
step(300)
c = calls()
print("emote while looking ->", c)
ok &= "5:threat:6" in c
print("OK" if ok else "FAIL")
