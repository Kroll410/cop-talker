"""Recent headlines from Ukrainian news sites, so stalkers can talk about what is really going on outside the Zone.

Feeds are read in the background every NEWS_REFRESH seconds; only titles are kept. Nothing about the user is sent.

Stalkers shouldn't keep chewing the same story: once a headline has been talked about (seen in what an NPC actually
said), it is not offered again. Only very popular news, the kind several sites carry at once, can come back,
a few times and not too often, like real people keep bringing up the big story of the week.
"""
import html
import json
import random
import re
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx

DEFAULT_FEEDS = ",".join([
    "https://suspilne.media/rss/all.rss",          # Суспільне: Ukraine
    "https://feeds.bbci.co.uk/ukrainian/rss.xml",  # BBC News Україна: Ukraine and the world
    "https://tsn.ua/rss/full.rss",                 # ТСН: also showbiz, sports, tech, lifestyle
])

# Headlines about deaths and attacks are kept for when someone asks about the news, but never handed out as
# idle-chatter topics (the chatter is often joking).
GRIM = re.compile(r"загин|загибл|вбит|вбив|убив|убит|смерт|помер|жертв|поранен|ракет|обстріл|удар|атак|шахед|"
                  r"дрон|вибух|полон|окупант|фронт|бої|бій|штурм|тривог|евакуац|зґвалт|катув|трагед|ДТП|пожеж",
                  re.I)
JUNK = re.compile(r"^(новини|news|bbc|tsn|тсн|суспільне|nv)\b|гороскоп|прогноз погоди|курс валют на|"
                  r"що відбувається у світі: головне|онлайн", re.I)

POPULAR_SOURCES = 2      # a story on at least this many sites is "very popular"
POPULAR_REPEATS = 3      # how many times a popular story may be talked about in all
POPULAR_GAP = 30 * 60    # seconds before a popular story may come up again
FORGET_AFTER = 3 * 24 * 3600  # talked-about stories are remembered this long (seconds)

# Small words that say nothing about which story it is.
STOP = {"після", "через", "також", "проти", "щодо", "буде", "будуть", "може", "можуть", "який", "яка", "яке", "які",
        "того", "цього", "році", "року", "днів", "може", "своїх", "свою", "своє", "заявив", "заявила", "заявили",
        "каже", "кажуть", "розповів", "розповіла", "повідомили", "стало", "відомо", "україні", "україна", "україни",
        "україну", "українців", "українці", "новини", "сьогодні", "вчора", "листопада", "грудня", "жовтня"}


def stems(text):
    """The words that identify a story, cut to 5 letters so word forms match ("Трампа" = "Трамп")."""
    words = re.findall(r"[a-zа-яіїєґ0-9']{4,}", (text or "").lower().replace("’", "'"))
    return {w[:5] for w in words if w not in STOP}


def same_story(a, b):
    """Two headlines (or a headline and a spoken line) are about the same story."""
    common = len(a & b)
    return common >= 3 or (common >= 2 and common >= 0.4 * min(len(a), len(b)))


class News:
    def __init__(self, feeds=DEFAULT_FEEDS, refresh=3600, log=print, seen_file=None):
        self.feeds = [f.strip() for f in (feeds or "").split(",") if f.strip()]
        self.refresh = refresh
        self.log = log
        self.items = []  # [{"title", "stems", "sources"}], one per story
        self.lock = threading.Lock()
        self.seen_file = Path(seen_file) if seen_file else None
        self.seen = self._load_seen()  # [{"title", "stems", "count", "last"}]: stories already talked about
        if self.feeds:
            threading.Thread(target=self._loop, daemon=True).start()

    # ---------------------------------------------------------------- fetching
    def _loop(self):
        while True:
            try:
                self.update()
            except Exception as exc:  # never let the news take the helper down
                self.log(f"news: {exc!r}")
            time.sleep(self.refresh if self.items else 300)

    def update(self):
        found = []  # (title, feed index)
        with httpx.Client(timeout=10, follow_redirects=True,
                          headers={"User-Agent": "Mozilla/5.0 (StalkerTalker news reader)"}) as client:
            for index, url in enumerate(self.feeds):
                try:
                    data = client.get(url).content[:3_000_000]
                    if b"<!ENTITY" in data or b"<!DOCTYPE" in data[:2000].upper():
                        raise ValueError("feed declares entities")  # no entity tricks from a feed
                    root = ET.fromstring(data)
                except Exception as exc:
                    self.log(f"news: {url} failed ({exc.__class__.__name__})")
                    continue
                for item in list(root.iter("item"))[:40]:
                    title = html.unescape((item.findtext("title") or "")).replace("\xa0", " ").strip()
                    title = re.sub(r"\s+", " ", title)
                    if 20 <= len(title) <= 160 and not JUNK.search(title):
                        found.append((title, index))
        if not found:
            return
        stories = self.group(found)
        with self.lock:
            self.items = stories
        popular = sum(len(s["sources"]) >= POPULAR_SOURCES for s in stories)
        self.log(f"News: {len(stories)} fresh stories, {popular} of them on several sites")

    @staticmethod
    def group(found):
        """One entry per story; a story several sites carry keeps all their sources."""
        stories = []
        for title, source in found:
            s = stems(title)
            if not s:
                continue
            same = next((st for st in stories if same_story(st["stems"], s)), None)
            if same:
                same["sources"].add(source)
            else:
                stories.append({"title": title, "stems": s, "sources": {source}})
        return stories

    # ---------------------------------------------------------------- what was already said
    def _load_seen(self):
        if not self.seen_file:
            return []
        try:
            data = json.loads(self.seen_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        cutoff = time.time() - FORGET_AFTER
        return [dict(e, stems=set(e["stems"])) for e in data if e.get("last", 0) > cutoff]

    def _save_seen(self):
        if not self.seen_file:
            return
        try:
            data = [dict(e, stems=sorted(e["stems"])) for e in self.seen]
            self.seen_file.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError as exc:
            self.log(f"news: can't save what was said ({exc})")

    def _seen_entry(self, story):
        return next((e for e in self.seen if same_story(e["stems"], story["stems"])), None)

    def available(self, story, now=None):
        """Fresh, or very popular and not talked to death (and not just a minute ago)."""
        entry = self._seen_entry(story)
        if entry is None:
            return True
        now = now or time.time()
        return (len(story["sources"]) >= POPULAR_SOURCES and entry["count"] < POPULAR_REPEATS
                and now - entry["last"] > POPULAR_GAP)

    def mark_mentioned(self, text):
        """An NPC just said this: any story it talks about counts as told. Returns the titles it matched."""
        said = stems(text)
        if len(said) < 2:
            return []
        hits = []
        with self.lock:
            for story in self.items:
                if same_story(story["stems"], said):
                    entry = self._seen_entry(story)
                    if entry:
                        entry["count"] += 1
                        entry["last"] = time.time()
                    else:
                        self.seen.append({"title": story["title"], "stems": set(story["stems"]),
                                          "count": 1, "last": time.time()})
                    hits.append(story["title"])
            if hits:
                cutoff = time.time() - FORGET_AFTER
                self.seen = [e for e in self.seen if e["last"] > cutoff]
                self._save_seen()
        return hits

    # ---------------------------------------------------------------- what to offer
    def headlines(self, n=8):
        """Headlines for when someone asks what's new: fresh ones, the big stories first and marked as such."""
        with self.lock:
            now = time.time()
            stories = [s for s in self.items if self.available(s, now)]
        popular = [s for s in stories if len(s["sources"]) >= POPULAR_SOURCES]
        others = [s for s in stories if len(s["sources"]) < POPULAR_SOURCES]
        random.shuffle(popular)
        random.shuffle(others)
        picked = (popular[:max(2, n // 3)] + others)[:n]
        return [s["title"] + (" (everyone's talking about it)" if len(s["sources"]) >= POPULAR_SOURCES else "")
                for s in picked]

    def topic(self):
        """One light, fresh headline to chat about (big stories more likely), or None when there's nothing new."""
        with self.lock:
            now = time.time()
            light = [s for s in self.items if not GRIM.search(s["title"]) and self.available(s, now)]
        if not light:
            return None
        weights = [3 if len(s["sources"]) >= POPULAR_SOURCES else 1 for s in light]
        return random.choices(light, weights=weights)[0]["title"]
