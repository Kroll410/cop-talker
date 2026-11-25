"""Sample lines at the current FUN_LEVEL (set it in the environment to compare)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker  # noqa: E402

brain = talker.Brain()
v1, v2 = "characters_voice\\human_01\\stalker\\", "characters_voice\\human_02\\bandit\\"
a = {"id": 1, "name": "Лоцман", "story_name": "zat_sim_1", "community": "stalker", "rank": 400,
     "relation": "friend", "health": 1.0, "dist": 3, "voice": v1, "place": "zat_stalker_base_smart"}
b = {"id": 2, "name": "Сивий", "story_name": "zat_sim_2", "community": "bandit", "rank": 300,
     "relation": "neutral", "health": 1.0, "dist": 4, "voice": v2, "place": "zat_stalker_base_smart"}
state = {"level": "zaton", "hours": 21, "weather": "clear", "actor": {"weapon": "wpn_pm", "outfit": "novice_outfit"},
         "npcs": [a, b]}
out = open(Path(__file__).resolve().parent.parent / f"test_fun_{talker.FUN_LEVEL}.txt", "w", encoding="utf-8")
out.write(f"FUN_LEVEL={talker.FUN_LEVEL}\n")
for npc, said in [(a, "Розкажи щось смішне."), (a, "Як справи?"), (b, "Чого вилупився?"),
                  (a, "Що думаєш про Бороду?"), (b, "Дай закурити.")]:
    out.write(f"[{npc['name']}] {said} -> {brain.reply(npc, state, '', [], said, 'reply')}\n")
out.write(f"[greet {a['name']}] -> {brain.reply(a, state, '', [], '', 'greet')}\n")
for n, line in brain.chat(a, b, state, ""):
    out.write(f"  chat {n['name']}: {line}\n")
out.close()
