"""settings.ini saved by Notepad as ANSI (cp1251) or with a BOM: the app still starts, reads «PLAYER_NAME=Бродяга»
right, and merging new options turns the file into UTF-8 without losing anything."""
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "companion"))
import settings_file  # noqa: E402
import talker  # noqa: E402

ok = True


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    return cond


for label, data in [("ANSI (cp1251)", "[Personality]\r\nPLAYER_NAME=Бродяга\r\nZZ_ENC_TEST=Привіт\r\n".encode("cp1251")),
                    ("UTF-8 with BOM", "﻿[Personality]\nPLAYER_NAME=Бродяга\nZZ_ENC_TEST=Привіт\n".encode("utf-8"))]:
    tmp = Path(tempfile.mkdtemp())
    try:
        shutil.copy(ROOT / "settings.example.ini", tmp)
        (tmp / "settings.ini").write_bytes(data)
        ok &= check("PLAYER_NAME=Бродяга" in settings_file.read_text(tmp / "settings.ini"), f"{label}: read right")
        note = settings_file.ensure_settings(tmp)
        merged = (tmp / "settings.ini").read_bytes().decode("utf-8")  # now UTF-8
        ok &= check(bool(note) and "PLAYER_NAME=Бродяга" in merged and "TWITCH_LINKS=" in merged,
                    f"{label}: new options merged, name kept, file now UTF-8")
        (tmp / "settings.ini").write_bytes(data)  # back to the odd encoding: the helper must still start
        os.environ.pop("ZZ_ENC_TEST", None)
        real_root, talker.ROOT = talker.ROOT, tmp
        try:
            talker.load_env()
        finally:
            talker.ROOT = real_root
        ok &= check(os.environ.get("ZZ_ENC_TEST") == "Привіт", f"{label}: the helper reads it at start")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
print("OK" if ok else "FAIL")
