"""Polite or business questions to a neutral stalker shouldn't get insults; rude ones may."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker  # noqa: E402

brain = talker.Brain()
zhorka = {"id": 7, "name": "Жорка Адвокат", "community": "stalker", "rank": 300, "relation": "neutral", "dist": 2,
          "voice": "characters_voice\\human_02\\stalker\\"}
bandit = dict(zhorka, id=8, name="Сивий", community="bandit", voice="characters_voice\\human_03\\bandit\\")
state = {"level": "zaton", "hours": 15, "weather": "clear", "actor": {"weapon": "wpn_ak74", "money": 5000,
         "outfit": "stalker_outfit"}, "npcs": [zhorka, bandit]}
out = open(Path(__file__).resolve().parent.parent / "test_result.txt", "w", encoding="utf-8")
for npc, said in [(zhorka, "Жорка, підзаробити хочеш?"), (zhorka, "Привіт, як справи?"),
                  (zhorka, "Можеш допомогти мені знайти схрон?"), (zhorka, "Ти тупий лох, Жорко."),
                  (bandit, "Підзаробити хочеш?")]:
    for _ in range(2):
        out.write(f"[{npc['name']}] {said} -> {brain.reply(npc, state, '', [], said, 'reply')}\n")
out.close()
