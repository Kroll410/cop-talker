"""Telling an NPC what someone else said must not make him hostile; real insults still do."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker  # noqa: E402

brain = talker.Brain()
pasha = {"id": 5, "name": "Паша Самогон", "community": "stalker", "rank": 300, "relation": "neutral", "dist": 2,
         "voice": "characters_voice\\human_01\\stalker\\"}
grishka = {"id": 6, "name": "Грішка", "community": "stalker", "rank": 200, "relation": "neutral", "dist": 15,
           "voice": "characters_voice\\human_02\\stalker\\"}
state = {"level": "zaton", "hours": 16, "weather": "clear", "actor": {"weapon": "wpn_ak74", "money": 5000,
         "outfit": "stalker_outfit"}, "npcs": [pasha, grishka]}
out = open(Path(__file__).resolve().parent.parent / "test_result.txt", "w", encoding="utf-8")
for said in ["А-а, грішка болить, мене образив. Він сказав, що моя мама шлюха. Я цього йому не пробачу. "
             "Зможеш вирішити питання?",
             "Паша, ти конченний мудак і твоя мама шлюха.",
             "Грішка сказав, що ти лох і боягуз."]:
    line = brain.reply(pasha, state, "", [], said, "reply")
    out.write(f"{said}\n  -> {line}\n  action: {brain.last_action} {brain.last_extras}\n")
out.close()
