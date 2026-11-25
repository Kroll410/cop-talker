"""A wounded bandit lying on the ground: he should groan and beg, not threaten."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker  # noqa: E402

brain = talker.Brain()
bandit = {"id": 3, "name": "Сивий", "community": "bandit", "rank": 300, "relation": "neutral", "dist": 2,
          "health": 0.08, "wounded": True, "voice": "characters_voice\\human_03\\bandit\\"}
stalker = dict(bandit, id=4, name="Лоцман", community="stalker", voice="characters_voice\\human_01\\stalker\\")
state = {"level": "zaton", "hours": 14, "weather": "clear", "actor": {"weapon": "wpn_ak74"}, "npcs": [bandit, stalker]}
out = open(Path(__file__).resolve().parent.parent / "test_result.txt", "w", encoding="utf-8")
for npc, said in [(bandit, "Шо, лежиш, падло?"), (bandit, "Дай сюди свої гроші."), (bandit, "Тримай аптечку, бро."),
                  (stalker, "Як ти?"), (stalker, "Розкажи анекдот.")]:
    line = brain.reply(npc, state, "", [], said, "reply")
    out.write(f"[{npc['name']}, wounded] {said} -> {line}   (action {brain.last_action})\n")
out.close()
