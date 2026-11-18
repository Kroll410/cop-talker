"""Five greetings in a row from the same NPC must all differ."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker  # noqa: E402

brain = talker.Brain()
state = {"level": "zaton", "hours": 19, "minutes": 30, "weather": "clear", "emission": False,
         "actor": {"health": 0.8, "weapon": "wpn_ak74", "outfit": "stalker_outfit", "money": 3400}, "npcs": []}
npc = {"id": 32, "name": "Петро Каштан", "story_name": "zat_sim_stalker_4410", "community": "stalker",
       "relation": "friend", "rank": 400, "health": 1.0, "dist": 3, "weapon": "wpn_toz34", "place": "«Скадовськ»",
       "voice": "characters_voice\\human_01\\stalker\\"}
spoken = []
with open(Path(__file__).resolve().parent.parent / "test_result.txt", "w", encoding="utf-8") as out:
    for mode in ["greet"] * 5 + ["hostile"] * 3:
        if mode == "hostile":
            npc = dict(npc, community="bandit", relation="enemy", in_combat=True, fighting="player",
                       voice="characters_voice\\human_03\\bandit\\")
        line = brain.reply(npc, state, "nothing notable", [], "", mode, recent=spoken[-8:])
        dup = talker.too_similar(line, spoken[-8:])
        out.write(f"[{mode}{' DUP' if dup else ''}] {line}\n")
        spoken.append(line)
