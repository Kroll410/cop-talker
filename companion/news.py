"""Recent headlines from Ukrainian news sites, so stalkers can talk about what is really going on outside the Zone.

Feeds are read in the background every NEWS_REFRESH seconds; only titles are kept. Nothing about the user is sent.
"""
import html
import random
import re
import threading
import time
import xml.etree.ElementTree as ET

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


class News:
    def __init__(self, feeds=DEFAULT_FEEDS, refresh=3600, log=print):
        self.feeds = [f.strip() for f in (feeds or "").split(",") if f.strip()]
        self.refresh = refresh
        self.log = log
        self.items = []  # [(title, fetched_at)]
        self.lock = threading.Lock()
        if self.feeds:
            threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while True:
            try:
                self.update()
            except Exception as exc:  # never let the news take the helper down
                self.log(f"news: {exc!r}")
            time.sleep(self.refresh if self.items else 300)

    def update(self):
        titles = []
        with httpx.Client(timeout=10, follow_redirects=True,
                          headers={"User-Agent": "Mozilla/5.0 (StalkerTalker news reader)"}) as client:
            for url in self.feeds:
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
                        titles.append(title)
        if not titles:
            return
        seen, unique = set(), []
        for t in titles:
            key = t.lower()[:50]
            if key not in seen:
                seen.add(key)
                unique.append(t)
        with self.lock:
            self.items = unique
        self.log(f"News: {len(unique)} fresh headlines")

    def headlines(self, n=8):
        """A mix of current headlines, for when someone asks what's new."""
        with self.lock:
            items = list(self.items)
        return random.sample(items, min(n, len(items)))

    def topic(self):
        """One light headline to chat about, or None."""
        with self.lock:
            light = [t for t in self.items if not GRIM.search(t)]
        return random.choice(light) if light else None
