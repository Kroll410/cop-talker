"""Offline check of the new features: NPC chats, companion remarks, quick reactions, trade/quest talk,
Twitch lines, and streaming voice (one short line, costs ~40 ElevenLabs characters)."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker  # noqa: E402

out = open(Path(__file__).resolve().parent.parent / "test_result.txt", "w", encoding="utf-8")
brain = talker.Brain()
v1 = "characters_voice\\human_01\\stalker\\"
v2 = "characters_voice\\human_02\\stalker\\"
a = {"id": 1, "name": "Лоцман", "story_name": "zat_sim_1", "community": "stalker", "rank": 400, "relation": "friend",
     "health": 1.0, "dist": 6, "voice": v1, "place": "zat_stalker_base_smart"}
b = {"id": 2, "name": "Ленька Ствол", "story_name": "zat_sim_2", "community": "stalker", "rank": 200,
     "relation": "neutral", "health": 1.0, "dist": 7, "voice": v2, "place": "zat_stalker_base_smart"}
trader = {"id": 3, "name": "Борода", "story_name": "zat_a2_stalker_barmen", "community": "stalker", "rank": 900,
          "relation": "friend", "health": 1.0, "dist": 2, "voice": v1, "story": True,
          "stock": ["Аптечка x12 ~300", "Бинт x20 ~150", "Патрони 5.45x39 x40 ~200", "Горілка «Козаки» x8 ~120",
                    "Ковбаса «Дієтична» x10 ~100", "Детектор «Відгук» x1 ~2500"]}
state = {"level": "zaton", "hours": 20, "weather": "clear", "emission": False,
         "actor": {"weapon": "wpn_ak74", "outfit": "stalker_outfit", "health": 1.0},
         "npcs": [a, b, trader], "tasks": ["* %c[255,238,155,23]Знайти зниклих сталкерів", "Аномальне поле «Сосна»"]}

t0 = time.time()
lines = brain.chat(a, b, state, "nothing notable")
out.write(f"CHAT ({time.time() - t0:.1f}s, 1 request):\n" + "\n".join(f"  {n['name']}: {l}" for n, l in lines) + "\n")
for what in talker.Talker.REACTIONS.values():
    out.write(f"REACT {what[:40]}... -> {brain.reply(a, state, '', [], '', 'react', extra={'what': what.format(name='Медуза')})}\n")
comp = dict(a, following=True)
out.write(f"COMPANION -> {brain.reply(comp, state, '', [], '', 'companion', extra={'what': 'Tell a short rumour or story you heard at the campfire.'})}\n")
out.write(f"TRADE -> {brain.reply(trader, state, '', [], 'Що в тебе є з аптечок і скільки коштує?', 'reply')}\n")
out.write(f"TASK -> {brain.reply(a, state, '', [], 'Чув щось про зниклих сталкерів? Я їх шукаю.', 'reply')}\n")
out.write(f"TWITCH character -> {brain.reply(b, state, '', [], '', 'twitch', extra={'text': 'Привіт стрімеру, ти найкращий сталкер!'})}\n")
situation = brain.situation(trader, state, "", [], "Що продаєш?", "reply")
out.write(f"trade context included: {'Аптечка' in situation}; tasks for unrelated question: "
          f"{'PDA' in brain.situation(a, state, '', [], 'Як справи?', 'reply')}\n")

# streaming voice: time to first sound
voice = talker.Voice() if "--voice" in sys.argv else talker.Voice.__new__(talker.Voice); voice.client = getattr(voice, "client", None)
if voice.client:
    started = {}
    t0 = time.time()
    voice.say(a, "Ну що, бродяго, перевіряємо звук.", on_start=lambda: started.setdefault("t", time.time() - t0))
    out.write(f"VOICE stream: first sound after {started.get('t', -1):.2f}s, finished after {time.time() - t0:.1f}s\n")
out.write(talker.USAGE.summary() + "\n")
out.close()
