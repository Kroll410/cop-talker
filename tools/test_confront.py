"""The talk between a hired killer and his target before the shooting (real AI, no voice)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker  # noqa: E402

brain = talker.Brain()
bandit = {"id": 3, "name": "Сивий", "community": "bandit", "rank": 400, "relation": "neutral", "dist": 2,
          "voice": "characters_voice\human_03\bandit\\", "place": "zat_stalker_base_smart"}
kostet = {"id": 2, "name": "Кастет", "community": "stalker", "rank": 300, "relation": "neutral", "dist": 9,
          "voice": "characters_voice\human_02\stalker\\", "place": "zat_stalker_base_smart"}
state = {"level": "zaton", "hours": 19, "weather": "clear", "actor": {}, "npcs": [bandit, kostet]}
out = open(Path(__file__).resolve().parent.parent / "test_result.txt", "w", encoding="utf-8")
for _ in range(2):
    scene = ("A has just been paid by the player to kill B. A turns to B and calls him out right now (a cold "
             "threat, a cruel joke or 'nothing personal, it's business'); B realises what's happening and "
             "answers (begs, swears, threatens back or grabs his gun). 2-3 lines in total, starting with A, "
             "ending right before the first shot.")
    for n, line in brain.chat(bandit, kostet, state, "", scene=scene):
        out.write(f"{n['name']}: {line}\n")
    out.write("\n")
out.close()
