"""Daily usage counter: Gemini requests/tokens and ElevenLabs characters, plus the real ElevenLabs quota."""
import json
import threading
import time
from pathlib import Path


class Usage:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Lock()
        try:
            self.data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.data = {}
        self.quota = None  # (used, limit) of ElevenLabs credits this month, from their API
        self.next_quota_check = 0.0

    def today(self):
        day = time.strftime("%Y-%m-%d")
        if self.data.get("day") != day:
            self.data = {"day": day, "gemini_requests": 0, "gemini_tokens": 0, "tts_chars": 0, "tts_lines": 0}
        return self.data

    def add_gemini(self, response):
        meta = getattr(response, "usage_metadata", None)
        tokens = (getattr(meta, "total_token_count", 0) or 0) if meta else 0
        with self.lock:
            d = self.today()
            d["gemini_requests"] += 1
            d["gemini_tokens"] += tokens
            self.save()

    def add_tts(self, text):
        with self.lock:
            d = self.today()
            d["tts_chars"] += len(text)
            d["tts_lines"] += 1
            self.save()

    def refresh_quota(self, client):
        """Ask ElevenLabs how much of the monthly quota is used (at most every 10 minutes).
        Runs in the background: their API sometimes takes minutes to answer, and nothing else may wait for it."""
        if not client or time.time() < self.next_quota_check:
            return
        self.next_quota_check = time.time() + 600

        def ask():
            try:
                sub = client.user.subscription.get(request_options={"timeout_in_seconds": 20})
                self.quota = (sub.character_count, sub.character_limit)
            except Exception:
                pass

        threading.Thread(target=ask, daemon=True).start()

    def summary(self):
        with self.lock:
            d = dict(self.today())
        text = (f"Today: Gemini {d['gemini_requests']} requests / {d['gemini_tokens'] / 1000:.1f}k tokens, "
                f"voice {d['tts_lines']} lines / {d['tts_chars']} chars")
        if self.quota:
            used, limit = self.quota
            text += f" | ElevenLabs month: {used:,} of {limit:,} ({used * 100 // max(limit, 1)}%)"
        return text

    def save(self):
        try:
            self.path.write_text(json.dumps(self.data), encoding="utf-8")
        except OSError:
            pass
