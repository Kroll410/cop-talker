"""Text-only check of quirks, unprompted greetings and hostile shouting."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker  # noqa: E402

brain = talker.Brain()
state = {"level": "zaton", "hours": 19, "minutes": 30, "weather": "clear", "emission": False,
         "actor": {"health": 0.8, "weapon": "wpn_ak74", "outfit": "stalker_outfit", "money": 3400}, "npcs": []}
base = {"rank": 400, "health": 1.0, "dist": 4, "weapon": "wpn_toz34", "place": "«Скадовськ»"}
npcs = [
    dict(base, id=31, name="Гриша Сухий", story_name="zat_sim_stalker_7781", community="stalker", relation="neutral",
         voice="characters_voice\\human_02\\stalker\\"),
    dict(base, id=32, name="Петро Каштан", story_name="zat_sim_stalker_4410", community="stalker", relation="friend",
         voice="characters_voice\\human_01\\stalker\\"),
    dict(base, id=33, name="Лютий", story_name="zat_sim_bandit_1203", community="bandit", relation="enemy",
         in_combat=True, fighting="player", dist=18, place="Лісопилка", voice="characters_voice\\human_03\\bandit\\"),
]
with open(Path(__file__).resolve().parent.parent / "test_result.txt", "w", encoding="utf-8") as out:
    for npc in npcs:
        out.write(f"{npc['name']} ({npc['community']}) quirks: {talker.npc_quirks(npc)}\n")
        mode = "hostile" if npc["relation"] == "enemy" else "greet"
        for _ in range(2):
            out.write(f"  [{mode}] {brain.reply(npc, state, 'nothing notable', [], '', mode)}\n")
