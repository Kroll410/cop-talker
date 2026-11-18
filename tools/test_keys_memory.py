"""Offline check: in-game push-to-talk keys, follow/stay hotkey answers, and long-term NPC memory."""
import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker  # noqa: E402

out = open(Path(__file__).resolve().parent.parent / "test_result.txt", "w", encoding="utf-8")
tmp = Path(tempfile.mkdtemp())
talker.BRIDGE = tmp
talker.MEMORY_FILE = tmp / "memory.json"

# 1) keys bridge
game = talker.Game()
(tmp / "keys.txt").write_text("game_keys\nptt_down\n", encoding="ascii")
out.write(f"keys read: {game.new_keys()}  then: {game.new_keys()}\n")

t = talker.Talker.__new__(talker.Talker)
t.game, t.game_ptt, t.recording = game, False, False
t.ptt_up = talker.threading.Event()
t.busy = talker.threading.Lock()
started = []
t.on_push_to_talk = lambda: started.append(1)
(tmp / "keys.txt").write_text("game_keys\nptt_down\n", encoding="ascii")
t.handle_keys()
time.sleep(0.1)
out.write(f"game_ptt={t.game_ptt} recording thread started={bool(started)} held={t.ptt_held()}\n")
(tmp / "keys.txt").write_text("ptt_up\n", encoding="ascii")
t.handle_keys()
out.write(f"after ptt_up held={t.ptt_held()}\n")

# 2) memory: witness + compression with the real model
mem = talker.Memory()
brain = talker.Brain()
mem.summarize = brain.summarize
key = "zaton:zat_sim_91"
mem.witness(key, "he killed Сирота (бандит)")
talks = [("Привіт, Лоцмане.", "Здоров, бродяго."), ("Позич 500, завтра віддам.", "Добре, але завтра щоб віддав."),
         ("Де Борода?", "У Скадовську, де ж іще."), ("Ти лох.", "Ще раз так скажеш - пожалкуєш."),
         ("Вибач, погарячкував.", "Гаразд, проїхали."), ("Мене звати Дегтярьов.", "Запам'ятаю."),
         ("Що чути про Юпітер?", "Кажуть, там аномалій повно."), ("Дякую за пораду.", "Нема за що."),
         ("Підеш зі мною на Залізний ліс?", "Не сьогодні."), ("А за 1000?", "За 1000 подумаю."),
         ("Бувай.", "Бувай."), ("Я знову тут.", "Бачу."), ("Борг пам'ятаю.", "Ну-ну."),
         ("Холодно сьогодні.", "Зона ж."), ("Тримай 500.", "О, віддав! Поважаю.")]
for p, n in talks:
    mem.add(key, p, n)
time.sleep(12)
data = json.loads(talker.MEMORY_FILE.read_text(encoding="utf-8"))
out.write(f"turns kept: {len(data[key])}\nremembers: {mem.remembers(key)}\n")

# 3) a reply that uses the memory
npc = {"id": 91, "name": "Лоцман", "story_name": "zat_sim_91", "community": "stalker", "rank": 400,
       "relation": "friend", "health": 1.0, "dist": 3, "voice": "characters_voice\\human_01\\stalker\\"}
state = {"level": "zaton", "hours": 14, "weather": "clear", "actor": {"weapon": "wpn_ak74"}, "npcs": [npc]}
line = brain.reply(npc, state, "", mem.history(key), "Пам'ятаєш, що я тобі винен був?", "reply",
                   remembers=mem.remembers(key))
out.write(f"reply with memory: {line}\n")
for what in ("The player signals you to follow him and you are coming along now. Say a few words as you go.",
             "The player signals you to come with him, but you have your own business here and refuse."):
    out.write(f"order -> {brain.reply(npc, state, '', [], '', 'react', extra={'what': what})}\n")
out.close()
