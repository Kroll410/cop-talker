"""Text-only check: who agrees to follow, and that story NPCs refuse instead of fake-agreeing."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker  # noqa: E402

brain = talker.Brain()
state = {"level": "zaton", "hours": 14, "minutes": 0, "weather": "clear", "emission": False,
         "actor": {"health": 1.0, "weapon": "wpn_ak74", "outfit": "stalker_outfit", "money": 3400}, "npcs": []}
friend = {"id": 91, "name": "Лоцман", "story_name": "zat_sim_91", "community": "stalker", "rank": 400,
          "relation": "friend", "health": 1.0, "dist": 3, "place": "zat_stalker_base_smart",
          "voice": "characters_voice\\human_01\\stalker\\"}
neutral = dict(friend, id=92, name="Ленька Ствол", relation="neutral")
story = dict(friend, id=93, name="Гонта", story=True)
out = open(Path(__file__).resolve().parent.parent / "test_result.txt", "w", encoding="utf-8")
for who in (friend, neutral, story):
    for said in ["Давай, ідем за мною.", "Ходімо зі мною до Шевченка, я заплачу тобі 2000."]:
        line = brain.reply(who, state, "", [], said, "reply")
        out.write(f"[{who['name']}, {who['relation']}{', story' if who.get('story') else ''}] {said}\n"
                  f"  -> {line}   (action {brain.last_action})\n")
out.close()
