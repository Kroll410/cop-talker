"""«Вова Віст»: a reward the streamer makes on Twitch (the app never creates it) and picks in Settings. A redemption goes
to the game at once, no Zone queue; the game spawns a soldier named «Вова Віст» with «Свистілка Вови Віста», a PKM that
fires 100x as fast and does 1000x less damage (game side checked in tools/zone_lua.py, run by test_zone.py).

Here: the app side, the gun's section and name against the installed game's own configs (skipped without the game),
and install_mod.ps1 / uninstall_mod.ps1 on a throwaway game folder (they add and take out one #include line).

Usage: python tools/test_vova.py ["C:\\Games\\S.T.A.L.K.E.R. Call of Pripyat"]  (default: STALKER_DIR from settings.ini)"""
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
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


# Twitch: each reward title calls its own trigger
got = []
tw = Twitch("id", "", ROOT / "nope.json", lambda *a: None, lambda *a: None, source="chat",
            zone_title="Дар Зони", on_zone=lambda u, ev: got.append(("zone", u)),
            triggers={"Шари Суслова": lambda u, ev: got.append(("suslov", u)),
                      "Вова Віст": lambda u, ev: got.append(("vova", u))})
tw.on_redemption({"id": "r1", "user_name": "Vasyl", "reward": {"id": "x", "title": "Вова Віст"}})
tw.on_redemption({"id": "r1", "user_name": "Vasyl", "reward": {"id": "x", "title": "Вова Віст"}})  # twice
tw.on_redemption({"id": "r2", "user_name": "Olia", "reward": {"id": "y", "title": "Шари Суслова"}})
check(got == [("vova", "Vasyl"), ("suslov", "Olia")], f"routed by title, once each: {got}")
src = (ROOT / "companion" / "twitch.py").read_text(encoding="utf-8")
check('"POST", "/channel_points/custom_rewards"' not in src and '"DELETE"' not in src,
      "the app never creates or deletes a reward")

# one entry in companion/redeems.py: Twitch routing, the Redeems tab's picker and Test, the helper's test command
check_redeem(check, "vova", "TWITCH_VOVA_REWARD", "on_vova")

# at once, straight to the game, not through the Zone queue
sent = []
t = talker.Talker.__new__(talker.Talker)
state = {"mod_version": 15, "actor": {"health": 1}}
t.game = type("G", (), {"send": lambda self, *x: sent.append(x), "state": lambda self: state})()
t.zone = type("Q", (), {"add": lambda *a: (_ for _ in ()).throw(AssertionError("queued")),
                        "retry": lambda *a: (_ for _ in ()).throw(AssertionError("retried"))})()
t.on_vova("Vasyl_77")
check(len(sent) == 1 and sent[0][0] == "zone" and sent[0][2].startswith("vova|Вова Віст|Vasyl_77"),
      f"sent to the game at once, «Вова Віст» as the caption (his name): {sent}")
check(t.zone_fired.get("kind") == "vova", "the game's answer is matched to it (for the reaction)")
sent.clear()
state["mod_version"] = 14
t.on_vova("Vasyl_77")
check(not sent, "an old game script (no «Вова Віст» in it): nothing sent")
state.update(mod_version=15, actor={"health": 0})
t.on_vova("Vasyl_77")
check(not sent, "player dead: nothing sent")
check(talker.Talker.MOD_VERSION == 15, "the helper wants script version 15")
lua = (ROOT / "mod/gamedata/scripts/talker_bridge.script").read_text(encoding="utf-8")
check(re.search(r"^MOD_VERSION = 15\b", lua, re.M), "the game script is version 15")

# the game couldn't (no gun section, no place): given up, never retried like a Zone event
reacted, logged = [], []
t.zone_fired = {"kind": "vova", "user": "Vasyl"}
t.report_zone = lambda force=False: None
t.zone_react = lambda *a, **k: reacted.append(a)
talker_log = talker.log
talker.log = lambda m: logged.append(m)
try:
    t.on_zone_results([{"type": "zone_done", "what": "vova", "ok": False, "reason": "no wpn_vova_vist"}])
    check(not reacted and any("given up" in m for m in logged), f"failed: given up, no reaction {logged}")
    t.zone_fired = {"kind": "vova", "user": "Vasyl"}
    t.on_zone_results([{"type": "zone_done", "what": "vova", "ok": True, "section": "sim_default_military_2"}])
    check(reacted and reacted[0][0] == "vova", "done: the men around react")
finally:
    talker.log = talker_log
what = talker.Talker.zone_what(t, "vova", {})
check("Вова Віст" in what and "військові" in what and "except the player" in what,
      "the men around are told who he is and what he does")

ini = (ROOT / "settings.example.ini").read_text(encoding="utf-8")
check(re.search(r"^TWITCH_VOVA_REWARD=$", ini, re.M), "in settings.example.ini, empty (off)")
for readme in ("README.md", "README.en.md"):
    check("TWITCH_VOVA_REWARD" in (ROOT / readme).read_text(encoding="utf-8"), f"{readme} tells about it")

# the gun's own files
MOD = ROOT / "mod" / "gamedata" / "configs"
ltx_raw = (MOD / "talker_items.ltx").read_bytes()
check(ltx_raw.isascii() and b"\r\n" in ltx_raw and b"\n" not in ltx_raw.replace(b"\r\n", b""),
      "talker_items.ltx: plain ASCII, CRLF like the game's own")
for lang in ("ukr", "rus", "eng"):
    raw = (MOD / "text" / lang / "talker_items.xml").read_bytes()
    text = raw.decode("cp1251")
    names = dict(re.findall(r'<string id="([^"]+)">\s*<text>([^<]*)</text>', text))
    check(raw.startswith(b'<?xml version="1.0" encoding="windows-1251" ?>') and
          set(names) == {"st_wpn_vova_vist", "st_wpn_vova_vist_descr"}, f"text\\{lang}\\talker_items.xml: both strings")
    if lang == "ukr":
        check(names.get("st_wpn_vova_vist") == "Свистілка Вови Віста", "its name in Ukrainian: «Свистілка Вови Віста»")


def game_dir():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args:
        return Path(args[0])
    p = ROOT / "settings.ini"
    if p.exists():
        m = re.search(r"^\s*STALKER_DIR\s*=\s*(.+)$", p.read_text(encoding="utf-8"), re.M)
        if m:
            return Path(m.group(1).strip())
    return None


def unpack(db, out, *prefixes):
    subprocess.run([sys.executable, "-I", str(ROOT / "tools" / "xdb_unpack.py"), str(db), str(out), *prefixes],
                   check=True, capture_output=True)


def ini_sections(paths):
    """[section]:parents and key = value, the way the game reads them (later files win, ';' starts a comment)."""
    secs, parents = {}, {}
    for p in paths:
        cur = None
        for line in Path(p).read_text(encoding="cp1251", errors="replace").splitlines():
            line = line.split(";")[0].rstrip()
            m = re.match(r"\s*\[([^\]]+)\]\s*(?::\s*(.*))?", line)
            if m:
                cur = m.group(1).strip().lower()
                secs[cur] = {}
                parents[cur] = [x.strip().lower() for x in (m.group(2) or "").split(",") if x.strip()]
            elif cur and "=" in line:
                k, v = line.split("=", 1)
                secs[cur][k.strip()] = v.strip()

    def get(sec, key):
        if key in secs.get(sec, {}):
            return secs[sec][key]
        for par in parents.get(sec, []):
            v = get(par, key)
            if v is not None:
                return v
        return None
    return secs, parents, get


game = game_dir()
patches = game / "patches" if game else None
if not game or not (game / "resources" / "configs.db").exists():
    print("skip the game's own configs and the installer: no game found (give its folder)")
else:
    tmp = Path(tempfile.mkdtemp(prefix="talker_vova_"))
    junctions = []
    try:
        # the PKM it's made from, in the game's own weapons file (configs.db, a patch may change it)
        cfg = tmp / "cfg"
        archives = [game / "resources" / "configs.db"] + sorted(patches.glob("*.db"))
        for i, db in enumerate(archives):
            unpack(db, cfg / str(i), "configs\\weapons\\", "configs\\external.ltx")
        weapons = sorted(p for i in range(len(archives)) for p in (cfg / str(i) / "configs" / "weapons").glob("w_pkm.ltx"))
        secs, parents, get = ini_sections(weapons + [MOD / "talker_items.ltx"])
        check(parents.get("wpn_vova_vist") == ["wpn_pkm"] and "wpn_pkm" in secs, "[wpn_vova_vist] is a wpn_pkm")
        rpm = float(get("wpn_pkm", "rpm"))
        check(float(get("wpn_vova_vist", "rpm")) == rpm * 100, f"fires 100x as fast ({rpm:g} -> {get('wpn_vova_vist', 'rpm')})")
        pkm_hit = [float(x) for x in get("wpn_pkm", "hit_power").split(",")]
        vova_hit = [float(x) for x in get("wpn_vova_vist", "hit_power").split(",")]
        check(len(vova_hit) == 4 and all(abs(v - p / 1000) < 1e-12 for v, p in zip(vova_hit, pkm_hit)),
              f"does 1000x less damage ({pkm_hit} -> {vova_hit})")
        check(get("wpn_vova_vist", "inv_name") == "st_wpn_vova_vist" and get("wpn_vova_vist", "ammo_mag_size") == "5000",
              "its own name and a 5000-round belt")
        check(get("wpn_vova_vist", "$npc") == "on" and get("wpn_vova_vist", "ammo_class") == "ammo_pkm_100",
              "NPCs can use it, PKM ammo")

        # install_mod.ps1 on a throwaway game folder: its patches are the real ones (a junction, only read)
        def junction(link, target):
            subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True, capture_output=True)
            junctions.append(link)

        inst = tmp / "inst"
        (inst / "tools").mkdir(parents=True)
        for f in ("install_mod.ps1", "uninstall_mod.ps1", "settings.example.ini"):
            shutil.copy(ROOT / f, inst / f)
        shutil.copy(ROOT / "tools" / "xdb_unpack.py", inst / "tools")
        shutil.copytree(ROOT / "mod", inst / "mod")
        junction(inst / ".venv", ROOT / ".venv")
        fake = tmp / "game"
        (fake / "bin").mkdir(parents=True)
        junction(fake / "patches", patches)
        (inst / "settings.ini").write_text(f"STALKER_DIR={fake}\n", encoding="utf-8")

        def ps(script):
            r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(inst / script)],
                               capture_output=True, text=True)
            return r.returncode, r.stdout + r.stderr

        # the patch that has external.ltx, newest first, as the game picks it
        original = None
        for i in reversed(range(1, len(archives))):
            p = cfg / str(i) / "configs" / "external.ltx"
            if p.exists():
                original = p.read_bytes()
                break
        ext = fake / "gamedata" / "configs" / "external.ltx"
        inc = b'#include "talker_items.ltx"\r\n'
        code, out = ps("install_mod.ps1")
        check(code == 0, f"install runs {out[-300:] if code else ''}")
        check(original and ext.exists() and ext.read_bytes() == inc + original,
              "no external.ltx in gamedata: the game's patched one copied out byte for byte, one #include line on top")
        check((fake / "gamedata/configs/talker_items.ltx").read_bytes() == ltx_raw and
              (fake / "gamedata/configs/text/ukr/talker_items.xml").exists(), "the sections and their names are copied")
        ps("install_mod.ps1")
        check(ext.read_bytes() == inc + original, "run again: nothing added twice")
        code, out = ps("uninstall_mod.ps1")
        check(code == 0 and not ext.exists() and not (fake / "talker/external_ltx_ours.txt").exists(),
              f"uninstall: the copy it made is deleted {out[-300:] if code else ''}")
        check(not (fake / "gamedata/configs/talker_items.ltx").exists() and
              not list((fake / "gamedata/configs/text").glob("*/talker_items.xml")), "and our files are gone")

        # another mod's external.ltx already there: only our line goes in and comes out again
        theirs = b"; someone else's\r\n#include \"their_mod.ltx\"\r\n[reduce_lod_texture_list]\r\nact\\act_x\r\n"
        ext.parent.mkdir(parents=True, exist_ok=True)
        ext.write_bytes(theirs)
        ps("install_mod.ps1")
        check(ext.read_bytes() == inc + theirs, "another external.ltx: kept, our line added on top")
        ps("uninstall_mod.ps1")
        check(ext.read_bytes() == theirs, "uninstall: exactly their file again")
        print(f"  {hashlib.sha256(original or b'').hexdigest()[:12]}: the patched external.ltx used")
    finally:
        for j in junctions:  # the link only, never what it points to
            os.rmdir(j)
        shutil.rmtree(tmp, ignore_errors=True)
print("OK" if ok else "FAIL")
