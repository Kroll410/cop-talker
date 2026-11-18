"""Humour style: funny/stupid things about their own life, not insults at the player."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker  # noqa: E402

brain = talker.Brain()
v = "characters_voice\human_0%d\stalker\\"
men = [{"id": i, "name": n, "community": "stalker", "rank": 300, "relation": "neutral", "dist": 3, "voice": v % (i % 3 + 1),
        "story_name": f"t{i}"} for i, n in enumerate(["Жорка Адвокат", "Лоцман", "Кастет"], 1)]
state = {"level": "zaton", "hours": 21, "weather": "clear", "actor": {"weapon": "wpn_ak74", "outfit": "stalker_outfit"},
         "npcs": men}
out = open(Path(__file__).resolve().parent.parent / "test_result.txt", "w", encoding="utf-8")
out.write(f"FUN_LEVEL={talker.FUN_LEVEL}\n")
for npc, said in [(men[0], "Як справи?"), (men[1], "Що нового?"), (men[2], "Чим займаєшся?"), (men[0], "Нудно тут, га?")]:
    out.write(f"{said} -> {brain.reply(npc, state, '', [], said, 'reply')}\n")
for _ in range(3):
    out.write(f"greet -> {brain.reply(men[1], state, '', [], '', 'greet', recent=[l for l in []])}\n")
for n, l in brain.chat(men[0], men[2], state, ""):
    out.write(f"  chat {n['name']}: {l}\n")
out.close()
