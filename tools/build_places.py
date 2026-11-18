"""Build companion/places.json: real Ukrainian location names per level, from the game files.

Reads misc/smart_names.ltx (level -> smart terrain -> string id) from configs.db/patch and
resolves the string ids in the Ukrainian string tables from xukrainian.db.
Usage: python build_places.py <game_dir> <xukrainian.db>
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import xdb_unpack as x  # noqa: E402


def read_files(archive, wanted):
    data = open(archive, "rb").read()
    out = {}
    for name, size_real, size_compr, offset in x.list_files(x.read_chunks(data)[1]):
        low = name.lower()
        if any(low.startswith(w) for w in wanted) and size_compr:
            raw = data[offset:offset + size_compr]
            out[low] = raw if size_real == size_compr else x.lzo1x_decompress(raw, size_real)
    return out


def main():
    game, ukr_db = Path(sys.argv[1]), sys.argv[2]
    ltx = {}
    for db in (game / "resources" / "configs.db", game / "patches" / "xpatch_02.db"):
        ltx.update(read_files(str(db), ["configs\\misc\\smart_names.ltx"]))
    names_ltx = ltx["configs\\misc\\smart_names.ltx"].decode("cp1251")

    strings = {}
    for body in read_files(ukr_db, ["configs\\text\\ukr\\"]).values():
        text = body.decode("cp1251", "replace")
        for sid, value in re.findall(r'<string id="([^"]+)">\s*<text>(.*?)</text>', text, re.S):
            strings[sid] = value.strip()

    places, smart_names, section = {}, {}, None
    for line in names_ltx.splitlines():
        line = line.split(";")[0].strip()
        if m := re.match(r"\[(\w+)\]", line):
            section = m.group(1)
        elif section and section != "levels" and "=" in line:
            smart, sid = (s.strip() for s in line.split("=", 1))
            name = strings.get(sid)
            if name:
                smart_names[smart] = name
                if name not in places.setdefault(section, []):
                    places[section].append(name)
    (Path(__file__).resolve().parent.parent / "companion" / "smart_names.json").write_text(
        json.dumps(smart_names, ensure_ascii=False, indent=1), encoding="utf-8")

    dest = Path(__file__).resolve().parent.parent / "companion" / "places.json"
    dest.write_text(json.dumps(places, ensure_ascii=False, indent=1), encoding="utf-8")
    for level, names in places.items():
        print(level, len(names), names[:6])


if __name__ == "__main__":
    main()
