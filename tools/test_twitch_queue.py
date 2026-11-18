"""Offline: a viewer message waits while nobody is near, then goes to a random nearby NPC (voice mocked)."""
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker  # noqa: E402

said, sent = [], []
t = talker.Talker.__new__(talker.Talker)
t.busy, t.recording, t.twitch, t.twitch_queue, t.next_twitch_note, t.spoken = threading.Lock(), False, None, [], 0, []
t.game = type("G", (), {"send": lambda self, *a: sent.append(a), "distance_to": lambda self, i: 3})()
t.voice = type("V", (), {"say": lambda self, npc, line, current_dist=None, on_start=None: (on_start and on_start(),
                                                                                          said.append((npc["name"], line)))})()
t.on_twitch("viewer42", "Слава Україні! Глянь https://spam.example", {"id": "r1", "reward": {"id": "x"}})
far = {"npcs": [{"id": 1, "name": "Далекий", "dist": 60}]}
print("nobody near -> spoke:", t.twitch_speak(far), "queue:", len(t.twitch_queue))
near = {"npcs": [{"id": 2, "name": "Лоцман", "dist": 5, "voice": ""}, {"id": 3, "name": "Ленька", "dist": 8}]}
print("NPC near -> spoke:", t.twitch_speak(near))
time.sleep(0.5)
print("said:", said, "| queue:", len(t.twitch_queue))
print("sent to game:", sent)
