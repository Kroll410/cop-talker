"""Accusations: stalkers own up, brag, dodge or lie instead of always denying."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker  # noqa: E402

brain = talker.Brain()
v = "characters_voice\human_0%d\stalker\\"
men = [{"id": i, "name": n, "community": c, "rank": 300, "relation": "neutral", "dist": 3, "voice": v % (i % 3 + 1),
        "story_name": f"t{i}"} for i, (n, c) in enumerate([("Жорка Адвокат", "stalker"), ("Сивий", "bandit"),
                                                          ("Кастет", "freedom"), ("Лоцман", "stalker")], 1)]
state = {"level": "zaton", "hours": 21, "weather": "clear", "actor": {"weapon": "wpn_ak74", "outfit": "stalker_outfit"},
         "npcs": men}
out = open(Path(__file__).resolve().parent.parent / "test_result.txt", "w", encoding="utf-8")
for npc, said in [(men[0], "Я бачив, як ти вкрав аптечку в Бороди."), (men[1], "Це ти вчора обібрав новачка біля мосту?"),
                  (men[2], "Кажуть, ти напився і спав у аномалії."), (men[3], "Це ти здав нашу схованку військовим?"),
                  (men[0], "Ти вчора з'їв мою ковбасу?"), (men[1], "Зізнавайся, твоя робота з тим трупом?"),
                  (men[3], "Що нового в Україні?"), (men[2], "Чув щось у світі цікаве?"), (men[0], "Як там вдома?")]:
    try:
        out.write(f"[{npc['community']}] {said} -> {brain.reply(npc, state, '', [], said, 'reply')}\n")
    except Exception as exc:
        out.write(f"{said} -> ERROR {exc!r}\n")
talker.OUTSIDE_TALK = 1.0
recent = []
for i in range(4):
    line = brain.reply(men[i % 4], state, '', [], '', 'greet', recent=recent)
    recent.append(line)
    out.write(f"greet -> {line}\n")
out.close()
