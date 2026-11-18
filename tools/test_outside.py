"""Talk about life and news outside the Zone: replies to news questions, greetings and NPC chats."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker  # noqa: E402

talker.OUTSIDE_TALK = 1.0  # every idle line about the outside, to see them
brain = talker.Brain()
brain.news.update()
v = "characters_voice\human_0%d\stalker\\"
men = [{"id": i, "name": n, "community": "stalker", "rank": 300, "relation": "neutral", "dist": 3, "voice": v % (i % 3 + 1),
        "story_name": f"t{i}"} for i, n in enumerate(["Жорка Адвокат", "Лоцман", "Кастет"], 1)]
state = {"level": "zaton", "hours": 21, "weather": "clear", "actor": {"weapon": "wpn_ak74", "outfit": "stalker_outfit"},
         "npcs": men}
out = open(Path(__file__).resolve().parent.parent / "test_result.txt", "w", encoding="utf-8")
for npc, said in [(men[0], "Що нового в Україні?"), (men[1], "Чув щось у світі?"), (men[2], "Як там вдома в тебе?"),
                  (men[0], "За кого вболіваєш у футболі?")]:
    out.write(f"{said} -> {brain.reply(npc, state, '', [], said, 'reply')}\n")
recent = []
for i in range(4):
    line = brain.reply(men[i % 3], state, '', [], '', 'greet', recent=recent)
    recent.append(line)
    out.write(f"greet -> {line}\n")
for _ in range(2):
    for n, l in brain.chat(men[0], men[2], state, ""):
        out.write(f"  chat {n['name']}: {l}\n")
    out.write("\n")
out.close()
