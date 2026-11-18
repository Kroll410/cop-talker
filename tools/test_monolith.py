"""Text-only check of the Monolith speaking style in every situation."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker  # noqa: E402

brain = talker.Brain()
state = {"level": "pripyat", "hours": 23, "minutes": 0, "weather": "foggy", "emission": False,
         "actor": {"health": 0.7, "weapon": "wpn_ak74", "outfit": "stalker_outfit", "money": 3400}, "npcs": []}
mono = {"id": 61, "name": "Брат Ілля", "story_name": "pri_sim_61", "community": "monolith", "rank": 800,
        "relation": "enemy", "health": 1.0, "dist": 12, "in_combat": True, "fighting": "player",
        "voice": "characters_voice\\human_01\\monolith\\"}
cases = [
    ("hostile", "", None),
    ("hostile", "", None),
    ("reply", "Стій! Не стріляй, я просто хочу поговорити.", None),
    ("reply", "Що таке Моноліт?", None),
    ("reply", "Ви всі просто зомбовані фанатики.", None),
    ("react", "", {"what": "The sky turns red: an EMISSION is starting right now."}),
    ("react", "", {"what": "You were just badly wounded and fell. Call for help."}),
]
spoken = []
with open(Path(__file__).resolve().parent.parent / "test_result.txt", "w", encoding="utf-8") as out:
    for mode, said, extra in cases:
        line = brain.reply(mono, state, "", [], said, mode, recent=spoken, extra=extra)
        spoken.append(line)
        out.write(f"[{mode}] {said or (extra or {}).get('what', '')}\n  -> {line}   (action {brain.last_action})\n")
