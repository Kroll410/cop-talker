"""Group address: player or Twitch talks to everybody; several men answer in one request (voice mocked)."""
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker  # noqa: E402

talker.MEMORY_FILE = Path(tempfile.mkdtemp()) / "memory.json"
out = open(Path(__file__).resolve().parent.parent / "test_result.txt", "w", encoding="utf-8")
said = []
t = talker.Talker.__new__(talker.Talker)
t.busy, t.recording, t.twitch, t.twitch_queue, t.next_twitch_note, t.spoken = threading.Lock(), False, None, [], 0, []
import tempfile  # noqa: E402
talker.MEMORY_FILE = Path(tempfile.mkdtemp()) / "memory.json"  # never the player's real NPC memory
talker.CLEAR_MEMORY = False
t.brain, t.memory = talker.Brain(), talker.Memory()
t.twitch_links, t.twitch_names, t.left_npc, t.zone_links, t.next_link_sync = {}, {}, {}, set(), 0  # Talker.__init__
t.save_links = lambda: None
t.game = type("G", (), {"send": lambda self, *a: None, "distance_to": lambda self, i: 3,
                        "last_used_npc": (None, 0)})()
t.voice = type("V", (), {"say": lambda self, npc, line, current_dist=None, on_start=None, **k: said.append((npc["name"], line))})()
v1, v2, v3 = ("characters_voice\\human_0%d\\stalker\\" % i for i in (1, 2, 3))
men = [{"id": 1, "name": "Лоцман", "community": "stalker", "rank": 400, "relation": "friend", "dist": 4, "voice": v1},
       {"id": 2, "name": "Кастет", "community": "stalker", "rank": 300, "relation": "neutral", "dist": 6, "voice": v2},
       {"id": 3, "name": "Сивий", "community": "bandit", "rank": 300, "relation": "neutral", "dist": 8,
        "voice": "characters_voice\\human_03\\bandit\\"},
       {"id": 4, "name": "Нік Хохмач", "community": "stalker", "rank": 200, "relation": "friend", "dist": 5, "voice": v3}]
state = {"level": "zaton", "hours": 20, "weather": "clear", "actor": {}, "npcs": men}

print("group words:", [w for w in ["Пацани, привіт", "Всім здоров", "Сталкери, хто йде?", "Лоцмане, як ти?",
                                   "Привіт, сталкере"] if talker.GROUP_WORDS.search(w)], file=out)
for who, text in [("player", "Пацани, хто знає, де тут нормальний хабар знайти?"),
                  ("player", "Всім добраніч, я спати."), ("twitch", "$Сталкери, хто з вас найбільший лох?")]:
    said.clear()
    if who == "player":
        t.group_answer(state, text, "The player (a stalker)", from_player=True)
    else:
        t.on_twitch("test_viewer", text, None)
        t.twitch_speak(state)
        time.sleep(0.3)
        while t.busy.locked():
            time.sleep(0.2)
    out.write(f"\n[{who}] {text}\n" + "\n".join(f"   {n}: {l}" for n, l in said) + "\n")

# healing: wounded -> healed right after you used him
t.game.last_used_npc = (4, time.time())
t.wounded_before = {4: True}
healed = dict(men[3], wounded=False, dist=1.5)
t._ambient_line = lambda npc, st, mode, extra: said.append((npc["name"], "(thanks line: " + extra["what"][:40] + ")"))
said.clear()
t.check_healed(dict(state, npcs=[healed]))
out.write(f"\nHEAL -> {said}\nmemory: {t.memory.remembers('zaton:' + str(4))}\n")
out.close()
