"""News memory: a told story isn't offered again; only stories several sites carry can come back, a few times."""
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import news  # noqa: E402

fails = []


def check(name, ok):
    print(("ok  " if ok else "FAIL") + " " + name)
    if not ok:
        fails.append(name)


found = [
    ("Зустріч Трампа, Сі Цзіньпіна та Путіна в Китаї: чи долучаться Віткофф", 0),
    ("Трамп і Сі Цзіньпін зустрілися в Китаї, Путін теж приїхав", 1),
    ("Сі Цзіньпін прийняв Трампа та Путіна у Пекіні", 2),
    ("На Миколаївщині вночі відчули підземні поштовхи землетрусу", 0),
    ("Збірна України з футболу зіграла внічию з Італією", 2),
    ("Де у Полтаві через ремонтні роботи не буде води: адреси", 0),
]
stories = news.News.group(found)
seen_file = Path(tempfile.mkdtemp()) / "news_seen.json"
n = news.News("", log=lambda m: None, seen_file=seen_file)
n.items = stories
big = next(s for s in stories if "Трамп" in s["title"])
quake = next(s for s in stories if "поштовхи" in s["title"])
check("three sites' versions grouped into one story", len(stories) == 4 and len(big["sources"]) == 3)
check("big story counts as popular", len(big["sources"]) >= news.POPULAR_SOURCES)
check("local story is not popular", len(quake["sources"]) == 1)
check("popular story marked when asked", any("talking about it" in h for h in n.headlines(8)))

# an NPC tells the quake story in his own words -> it's never offered again
told = n.mark_mentioned("Чув, на Миколаївщині вночі земля трусилась, підземні поштовхи, уявляєш?")
check("retold quake recognised", told == [quake["title"]])
check("told local story gone from topics", all(n.topic() != quake["title"] for _ in range(50)))
check("told local story gone from headlines", not any("поштовхи" in h for h in n.headlines(8)))
check("unrelated chatter marks nothing", n.mark_mentioned("Та я вчора ковбасу їв і спав як убитий.") == [])

# the big story may come back, but not right away, and only POPULAR_REPEATS times
n.mark_mentioned("Трамп з Сі Цзіньпіном у Китаї зустрілися, і Путін туди приперся")
check("popular story not repeated right away", not n.available(big))
entry = n._seen_entry(big)
entry["last"] -= news.POPULAR_GAP + 1
check("popular story back after the gap", n.available(big))
entry["count"] = news.POPULAR_REPEATS
check(f"popular story retired after {news.POPULAR_REPEATS} times", not n.available(big))

# remembered across restarts, forgotten after FORGET_AFTER
n2 = news.News("", log=lambda m: None, seen_file=seen_file)
n2.items = stories
check("memory survives a restart", not n2.available(quake))
data = seen_file.read_text(encoding="utf-8").replace('"last": ', '"last": -1e9 + ')
seen_file.write_text(seen_file.read_text(encoding="utf-8"), encoding="utf-8")
import json  # noqa: E402
old = json.loads(seen_file.read_text(encoding="utf-8"))
for e in old:
    e["last"] = time.time() - news.FORGET_AFTER - 10
seen_file.write_text(json.dumps(old), encoding="utf-8")
n3 = news.News("", log=lambda m: None, seen_file=seen_file)
n3.items = stories
check("old memory forgotten after 3 days", n3.available(quake))

# nothing fresh left -> topic() gives None, so the NPC talks about his own life instead
for s in stories:
    n.mark_mentioned(s["title"])
n._seen_entry(big)["count"] = news.POPULAR_REPEATS
check("all told -> no news topic", n.topic() is None)

print(f"\n{len(fails)} failed" if fails else "\nall passed")
