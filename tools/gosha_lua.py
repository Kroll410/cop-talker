"""Runs talker_bridge.script in LuaJIT with the engine stubs of tools/zone_lua.py and checks the named-man Zone line
("npc:<tag>:<community>:<weapon>:<side>:<nick>|<name>|<PDA text>", used by «Гоша»). Called by test_gosha.py.
Prints one line per check ("ok   ..." / "FAIL ...") and OK or FAIL at the end."""
import json
import re
import sys
from pathlib import Path

import lupa.luajit21 as lj

script, root = sys.argv[1], sys.argv[2].replace("\\", "/") + "/"
stubs = re.search(r"L\.execute\(r'''(.*?)''', root\)", (Path(__file__).parent / "zone_lua.py").read_text(encoding="utf-8"),
                  re.S).group(1)
L = lj.LuaRuntime()
L.execute(stubs, root)
L.execute(r'''
pstor = {}
xr_logic.pstor_store = function(_, k, v) pstor[k] = v end
xr_logic.pstor_retrieve = function(_, k, d) return pstor[k] or d end
HAVE.sim_default_killer_2 = true; HAVE.wpn_spas12 = true; HAVE.ammo_12x70_buck = true
function system_ini() return {
  section_exist = function(_, s) return HAVE[s] == true end,
  r_string = function(_, s, k)
    if k == "ammo_class" and s == "wpn_spas12" then return "ammo_12x70_buck, ammo_12x76_zhekan" end
    return "name_" .. s end,
  r_float = function(_, s, k) return COST[s] or 1000 end } end
SE, names, calls, released = {}, {}, {}, {}
NAMEABLE = true
local base_alife = alife
function alife()
  local a = base_alife()
  local create = a.create
  a.create = function(self, sec, pos, lv, gv, parent)
    local se = create(self, sec, pos, lv, gv, parent)
    function se:rank() table.insert(calls, "rank"); return 30 end
    if NAMEABLE then function se:set_character_name(n) table.insert(calls, "name"); names[self.id] = n end end
    SE[se.id] = se
    return se
  end
  a.object = function(_, id)
    if SE[id] or objs[id] then return SE[id] or { id = id, force_set_goodwill = function() end } end
    return nil
  end
  a.release = function(_, se) table.insert(released, se.id); SE[se.id] = nil end
  return a
end
function merc(id, name, x, inv)
  local o = make(id, name, x)
  o._rels, o._inv = {}, inv
  function o:set_relation(r, who) self._rels[who:id()] = r end
  function o:relation(who) return self._rels[who:id()] or game_object.neutral end
  function o:character_community() return "killer" end
  function o:iterate_inventory(fn, owner) for _, it in ipairs(self._inv) do if SE[it:id()] then fn(owner, it) end end end
  db.storage[id] = { object = o }
  return o
end
function item(id, sec)
  SE[id] = SE[id] or { id = id }
  return { id = function() return id end, section = function() return sec end }
end
''')
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


L.execute("TUTORIAL = false")  # no scripted scene: the autosave goes first, the event 1.5 s later
step(300)
events()

LINE = "zone||npc:gosha:killer:wpn_spas12:enemy:Vasyl_77|Гоша|Vasyl_77 кличе Гошу"
inbox(LINE)
step(300)
step(1600)
c, n, ev = take("created"), take("news"), [e for e in events() if e.get("type") == "zone_done"]
man = [x for x in c if x["sec"].startswith("sim_default_killer_")]
gun = [x for x in c if x["sec"] == "wpn_spas12"]
ammo = [x for x in c if x["sec"] == "ammo_12x70_buck"]
check(len(man) == 1 and len(gun) == 1 and len(ammo) == 2 and len(c) == 4,
      f"one найманець, a SPAS-12 and two packs of its buckshot {[x['sec'] for x in c]}")
mid = man[0]["id"] if man else -1
check(man and 15 <= man[0]["d"] <= 30 and man[0]["parent"] is None, f"he turns up 15-30 m away {man}")
check(all(x["parent"] == mid for x in gun + ammo), "the shotgun and the shells are made in his inventory")
check(L.eval(f"names[{mid}]") == "Гоша", "his name in the game is the caption (set on the server object)")
check(take("calls") == ["rank", "name"], "his profile is picked (rank) before the name, so it isn't overwritten")
check(ev and ev[0]["ok"] and ev[0]["what"].startswith("npc:gosha:") and ev[0]["tag"] == "gosha"
      and ev[0]["name"] == "Гоша" and ev[0]["id"] == mid and ev[0]["weapon"] == "wpn_spas12"
      and ev[0]["section"] == "sim_default_killer_2", f"done {ev}")
check(any(x == "Гоша|Vasyl_77 кличе Гошу" for x in n), f"a PDA line under his name {n}")
check(L.eval(f"twitch_links[{mid}]") is None, "no label yet: he isn't in the game")

# he comes into the game with his own gear: a rifle, a pistol, a grenade, a knife, binoculars, bread
gid = gun[0]["id"] if gun else -1
L.execute(f"""G = merc({mid}, "Гоша", 20, {{ item(900, 'wpn_ak74'), item(901, 'wpn_knife'), item(902, 'grenade_f1'),
  item({gid}, 'wpn_spas12'), item(903, 'bread'), item(904, 'wpn_binoc'), item(905, 'wpn_pm') }})""")
step(300)
check(not take("released"), "his own logic goes first: nothing taken in the first second")
step(1100)
check(sorted(take("released")) == [900, 902, 905], "his rifle, pistol and grenade go; the knife, binoculars, bread and SPAS-12 stay")
check(L.eval("G:relation(db.actor)") == L.eval("game_object.enemy"), "hostile to the player")
check(L.eval(f"is_contract(objs[{mid}], db.actor)"), "he really comes for the player (a grudge, even near a base)")
check(L.eval(f"twitch_links[{mid}]") == "Vasyl_77", "the viewer's nickname is on the label over his head")
ev = events()
sp = [e for e in ev if e.get("type") == "zone_spawned"]
check(sp and sp[0]["id"] == mid and sp[0]["nick"] == "Vasyl_77" and sp[0]["tag"] == "gosha" and sp[0]["side"] == "enemy"
      and sp[0]["named"] is True and sp[0]["npc"]["name"] == "Гоша", f"zone_spawned for the app {sp}")
L.execute("table.insert(G._inv, item(906, 'wpn_toz34'))")  # his gear came a moment late
step(1000)
check(take("released") == [906], "a gun that turns up a moment later is taken too")
step(5000)
L.execute("table.insert(G._inv, item(907, 'wpn_bm16'))")
step(1000)
check(not take("released"), "after a few seconds his inventory is his own again (a gun he picks up stays)")

# a stalker or gun the game doesn't have: nothing spawned, a clear reason
L.execute("HAVE.wpn_spas12 = false")
take("created"); take("news")
inbox(LINE)
step(300); step(1600)
ev = [e for e in events() if e.get("type") == "zone_done"]
check(not take("created") and ev and not ev[0]["ok"] and ev[0]["reason"] == "no wpn_spas12", f"no SPAS-12: {ev}")
L.execute("HAVE.wpn_spas12 = true; HAVE.sim_default_killer_2 = false")
inbox(LINE)
step(300); step(1600)
ev = [e for e in events() if e.get("type") == "zone_done"]
check(not take("created") and ev and not ev[0]["ok"] and ev[0]["reason"] == "no killer", f"no найманець: {ev}")

# an engine without set_character_name: he still comes (named or not is in zone_spawned), no crash
L.execute("HAVE.sim_default_killer_2 = true; NAMEABLE = false")
inbox(LINE)
step(300); step(1600)
c = take("created")
ev = [e for e in events() if e.get("type") == "zone_done"]
check(ev and ev[0]["ok"] and len(c) == 4, f"no set_character_name: he still turns up {ev}")

# a neutral one with his own gun (empty weapon): nothing taken from him
L.execute("NAMEABLE = true")
inbox("zone||npc:test:killer::neutral:|Хтось|t")
step(300); step(1600)
c = take("created")
man = [x for x in c if x["sec"].startswith("sim_default_killer_")]
check(len(c) == 1 and man, f"empty weapon: only the man {[x['sec'] for x in c]}")
nid = man[0]["id"] if man else -1
L.execute(f"N = merc({nid}, 'Хтось', 20, {{ item(910, 'wpn_ak74') }}); N._rels[0] = game_object.enemy")
step(300); step(1100)
check(not take("released"), "his own rifle stays")
check(L.eval("N:relation(db.actor)") != L.eval("game_object.enemy"), "neutral: not the player's enemy")
check(L.eval(f"twitch_links[{nid}]") is None, "no viewer: no label")
print("OK" if ok else "FAIL")
