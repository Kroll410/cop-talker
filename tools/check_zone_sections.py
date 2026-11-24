"""Checks the Zone reward's sections against your installed game: every item in ZONE_ITEMS (talker_bridge.script),
every stalker section and every mutant in companion/zone.py must exist in the game's configs (configs.db + patches),
and no item may be a quest item. Unpacks the configs into a temp folder (deleted after).

Usage: python tools/check_zone_sections.py ["C:\\Games\\S.T.A.L.K.E.R. Call of Pripyat"]
(default: STALKER_DIR from settings.ini)"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "companion"))
import zone  # noqa: E402


def game_dir():
    if len(sys.argv) > 1:
        return Path(sys.argv[1])
    for name in ("settings.ini", "settings.example.ini"):
        p = ROOT / name
        if p.exists():
            m = re.search(r"^\s*STALKER_DIR\s*=\s*(.+)$", p.read_text(encoding="utf-8"), re.M)
            if m:
                return Path(m.group(1).strip())
    sys.exit("Give the game folder as the first argument")


def load_sections(roots):
    secs, parents = {}, {}
    for root in roots:
        for p in sorted(Path(root).rglob("*.ltx")):
            cur = None
            for line in p.read_text(encoding="cp1251", errors="replace").splitlines():
                line = line.split(";")[0].rstrip()
                m = re.match(r"\s*\[([^\]]+)\]\s*(?::\s*(.*))?", line)
                if m:
                    cur = m.group(1).strip().lower()
                    secs[cur] = {}
                    parents[cur] = [x.strip().lower() for x in (m.group(2) or "").split(",") if x.strip()]
                elif cur and "=" in line:
                    k, v = line.split("=", 1)
                    secs[cur][k.strip()] = v.strip()

    def get(sec, key, seen=()):
        if sec not in secs or sec in seen:
            return None
        if key in secs[sec]:
            return secs[sec][key]
        for par in parents.get(sec, []):
            v = get(par, key, seen + (sec,))
            if v is not None:
                return v
        return None
    return secs, get


game = game_dir()
archives = [game / "resources" / "configs.db"] + sorted((game / "patches").glob("*.db"))
tmp = Path(tempfile.mkdtemp())
try:
    roots = []
    for i, db in enumerate(a for a in archives if a.exists()):
        out = tmp / str(i)
        subprocess.run([sys.executable, str(ROOT / "tools" / "xdb_unpack.py"), str(db), str(out)],
                       check=True, capture_output=True)
        roots.append(out)
    if (game / "gamedata").exists():
        roots.append(game / "gamedata")
    secs, get = load_sections(roots)
finally:
    shutil.rmtree(tmp, ignore_errors=True)
if not secs:
    sys.exit(f"No configs found in {game}")

lua = (ROOT / "mod/gamedata/scripts/talker_bridge.script").read_text(encoding="utf-8")
items = re.findall(r'"([a-z0-9_.\-]+)"', lua[lua.index("local ZONE_ITEMS"):lua.index("local ZONE_PEOPLE")])
factions = re.findall(r'"([a-z]+)"', lua[lua.index("local ZONE_PEOPLE"):].split("\n", 1)[0])
people = [f"sim_default_{f}_{r}" for f in factions for r in range(5)]
bad = [i for i in items if i not in secs]
quest = [i for i in items if i in secs and (get(i, "quest_item") not in (None, "false") or get(i, "cost") in (None, "0"))]
mutants = [s for m in zone.MONSTERS for s in m[1]]
kinds_without = [m[0] for m in zone.MONSTERS if not any(s in secs for s in m[1])]
print(f"items: {len(items) - len(bad)}/{len(items)} exist; missing {bad}; quest or free {quest}")
print(f"stalkers: {sum(p in secs for p in people)}/{len(people)} exist (missing ones are skipped)")
print(f"mutants: {sum(s in secs for s in mutants)}/{len(mutants)} sections exist; kinds with none: {kinds_without}")
ok = not bad and not quest and not kinds_without and any(p in secs for p in people)
print("OK" if ok else "FAIL")
