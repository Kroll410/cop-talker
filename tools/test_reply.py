"""Offline test: three NPCs with rich context reply to the player and speak in their cloned voices."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
out = open(ROOT / "test_result.txt", "w", encoding="utf-8")
clips = ROOT / "clips"
clips.mkdir(exist_ok=True)
brain, voice = talker.Brain(), talker.Voice()
state = {
    "level": "zaton", "hours": 22, "minutes": 40, "weather": "rain_default", "emission": False,
    "actor": {"health": 0.62, "weapon": "wpn_ak74", "outfit": "stalker_outfit", "money": 3400},
    "npcs": [
        {"id": 11, "name": "Кузьма Бородатий", "community": "stalker", "dist": 6, "wounded": True},
        {"id": 12, "name": "Сивий", "community": "stalker", "dist": 9},
    ],
}
events = "40s ago: Ковбой (бандит) was killed by гравець\n25s ago: the player shot Сивий"
npcs = [
    ({"id": 21, "name": "Вася Хрипатий", "community": "stalker", "rank": 650, "relation": "friend", "health": 0.9,
      "dist": 3, "weapon": "wpn_toz34", "place": "Скадовськ", "voice": "characters_voice\\human_01\\stalker\\"},
     "Що тут сталося? Чого всі такі нервові?"),
    ({"id": 22, "name": "Толік Шпана", "community": "bandit", "rank": 250, "relation": "neutral", "health": 1.0,
      "dist": 4, "weapon": "wpn_pm", "place": "Залізничний міст", "voice": "characters_voice\\human_03\\bandit\\"},
     "Слухай, пропусти мене, мені треба на той бік."),
    ({"id": 23, "name": "Серьога Бро", "community": "freedom", "rank": 420, "relation": "friend", "health": 0.8,
      "dist": 2, "weapon": "wpn_lr300", "place": "Затон", "voice": "characters_voice\\human_02\\freedom\\"},
     "Привіт, є якісь новини?"),
]
for npc, question in npcs:
    t = time.time()
    try:
        reply = brain.reply(npc, state, events, [], question)
        out.write(f"[{talker.voice_key(npc)}, {npc['community']}] {time.time() - t:.1f}s\n  Player: {question}\n  {npc['name']}: {reply}\n")
        out.flush()
        voice.say(npc, reply, save_to=clips / f"{talker.voice_key(npc)}_{npc['community']}.wav")
    except Exception as exc:
        out.write(f"FAIL {npc['name']}: {exc!r}\n")
        out.flush()
out.close()
