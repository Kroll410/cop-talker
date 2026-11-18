"""settings.ini is yours and stays out of git; settings.example.ini (in git) holds every option with its notes.

ensure_settings() makes settings.ini from the example when it's missing, and adds options that an update brought
into the example but your settings.ini doesn't have yet: each goes into its own [section], with its notes and its
default value. Nothing you set is ever changed or removed.
"""
import re
import shutil
from pathlib import Path

KEY = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=")


def _blocks(lines):
    """[(section, key, [notes..., "KEY=value"])] for every option in the example, in order."""
    out, section, notes = [], "", []
    for line in lines:
        s = line.strip()
        if s.startswith("["):
            section, notes = s, []
        elif s.startswith("#") or s.startswith(";"):
            notes.append(line)
        elif KEY.match(line):
            out.append((section, KEY.match(line).group(1), notes + [line]))
            notes = []
        elif not s:
            notes = []
    return out


def ensure_settings(root):
    """Returns a short note of what was done ("" if nothing)."""
    root = Path(root)
    mine, example = root / "settings.ini", root / "settings.example.ini"
    if not example.exists():
        return ""
    if not mine.exists():
        shutil.copyfile(example, mine)
        return "settings.ini created from settings.example.ini"
    lines = mine.read_text(encoding="utf-8-sig").splitlines()
    have = {KEY.match(line).group(1) for line in lines if KEY.match(line)}
    missing = [b for b in _blocks(example.read_text(encoding="utf-8-sig").splitlines()) if b[1] not in have]
    if not missing:
        return ""
    for section, key, block in missing:
        start = next((i for i, line in enumerate(lines) if line.strip() == section), None) if section else None
        if start is None:  # the section isn't there yet: add it at the end
            if section:
                lines += ["", section]
            lines += block
            continue
        end = next((i for i in range(start + 1, len(lines)) if lines[i].strip().startswith("[")), len(lines))
        while end > start + 1 and not lines[end - 1].strip():  # before the blank lines that close the section
            end -= 1
        lines[end:end] = block
    mine.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return "new settings added to settings.ini: " + ", ".join(key for _, key, _ in missing)
