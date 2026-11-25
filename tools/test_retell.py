"""%-messages: the NPC says the viewer's idea as his own line, never answers it."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker  # noqa: E402

brain = talker.Brain()
v = "characters_voice\\human_0%d\\%s\\"
kostet = {"id": 2, "name": "Кастет", "community": "stalker", "rank": 300, "relation": "neutral", "dist": 3,
          "voice": v % (2, "stalker"), "place": "zat_stalker_base_smart"}
others = [{"id": 1, "name": "Лоцман", "community": "stalker", "rank": 400, "relation": "friend", "dist": 5,
           "voice": v % (1, "stalker")},
          {"id": 3, "name": "Сивий", "community": "bandit", "rank": 300, "relation": "neutral", "dist": 6,
           "voice": v % (3, "bandit")}]
state = {"level": "zaton", "hours": 20, "weather": "clear", "actor": {"weapon": "wpn_ak74"}, "npcs": [kostet] + others}
out = open(Path(__file__).resolve().parent.parent / "test_result.txt", "w", encoding="utf-8")
for text in ["скажи їм, що ти їх переїбашеш зараз", "розпитай їх про корупційні скандали, якщо не дадуть відповідь, "
             "то пригрози вбивством", "стрімер найкращий сталкер", "передай Лоцману, що він винен 500 купонів",
             "я хочу пива"]:
    out.write(f"%{text}\n  Кастет -> {brain.reply(kostet, state, '', [], '', 'twitch', extra={'text': text})}\n")
out.close()
