"""Broken or odd state files never crash the helper and never silently wipe NPC memory:
a broken memory.json is kept as memory.broken-<time>.json; a JSON list where a dictionary belongs, or an old
news_seen.json without "stems", just starts afresh."""
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import news  # noqa: E402
import talker  # noqa: E402
import usage  # noqa: E402

ok = True


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    return cond


tmp = Path(tempfile.mkdtemp())
real_memory, talker.CLEAR_MEMORY = talker.MEMORY_FILE, False
try:
    talker.MEMORY_FILE = tmp / "memory.json"
    # cut off mid-write: kept aside, not overwritten by the first save
    talker.MEMORY_FILE.write_text('{"zaton:Вовк": {"summary": "пам\'ятає', encoding="utf-8")
    m = talker.Memory()
    backups = list(tmp.glob("memory.broken-*.json"))
    ok &= check(m.data == {} and len(backups) == 1 and "Вовк" in backups[0].read_text(encoding="utf-8"),
                "broken memory.json kept as memory.broken-*.json")
    m.save()
    ok &= check(backups[0].exists(), "the first save leaves the broken copy alone")
    for b in backups:
        b.unlink()
    # valid JSON, wrong shape
    talker.MEMORY_FILE.write_text("[1, 2, 3]", encoding="utf-8")
    m = talker.Memory()
    ok &= check(m.data == {} and len(list(tmp.glob("memory.broken-*.json"))) == 1, "a list in memory.json: kept aside")

    v = talker.Voice.__new__(talker.Voice)
    v.dead = set()
    talker.Voice.VOICES_FILE = tmp / "npc_voices.json"
    talker.Voice.VOICES_FILE.write_text('["not", "a", "dict"]', encoding="utf-8")
    v.pick_voice = lambda npc: "voice_x"
    try:
        got = v.voice_for({"id": 5, "name": "Вовк"})
        ok &= check(got == "voice_x", "a list in npc_voices.json: no crash, a voice is picked")
    except Exception as exc:
        ok &= check(False, f"npc_voices.json list crashed: {exc!r}")

    seen = tmp / "news_seen.json"
    seen.write_text(json.dumps([{"last": 9e12, "title": "old format without stems"}]), encoding="utf-8")
    try:
        n = news.News(feeds=[], seen_file=seen)
        ok &= check(n.seen == [], "an old news_seen.json without stems: starts afresh")
    except Exception as exc:
        ok &= check(False, f"news_seen.json crashed: {exc!r}")

    use = tmp / "usage.json"
    use.write_text("[]", encoding="utf-8")
    try:
        u = usage.Usage(use)
        ok &= check(u.data == {}, "a list in usage.json: starts afresh")
    except Exception as exc:
        ok &= check(False, f"usage.json crashed: {exc!r}")
finally:
    talker.MEMORY_FILE = real_memory
    shutil.rmtree(tmp, ignore_errors=True)
print("OK" if ok else "FAIL")
