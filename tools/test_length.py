"""Text-only check that reply length adapts to the question."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker  # noqa: E402

brain = talker.Brain()
state = {"level": "zaton", "hours": 14, "minutes": 10, "weather": "cloudy", "emission": False,
         "actor": {"health": 1.0, "weapon": "wpn_ak74", "outfit": "stalker_outfit", "money": 3400}, "npcs": []}
npc = {"id": 21, "name": "Вася Хрипатий", "community": "stalker", "rank": 650, "relation": "friend", "health": 1.0,
       "dist": 3, "weapon": "wpn_toz34", "place": "Скадовськ", "voice": "characters_voice\\human_01\\stalker\\"}
cases = [
    ("nothing notable", "Привіт."),
    ("nothing notable", "Ти бачив тут бандитів?"),
    ("nothing notable", "Дякую."),
    ("nothing notable", "Розкажи, де на Затоні шукати артефакти і що там небезпечно?"),
    ("nothing notable", "Скільки коштує хороший детектор у Бороди?"),
    ("10s ago: Сивий (вільний сталкер) was killed by гравець", ""),
]
with open(Path(__file__).resolve().parent.parent / "test_result.txt", "w", encoding="utf-8") as out:
    for events, q in cases:
        r = brain.reply(npc, state, events, [], q)
        out.write(f"[{len(r.split())} words] {q or '(event: player killed Сивий)'}\n  -> {r}\n")
