"""Short or garbled player input should get short, natural replies."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker  # noqa: E402

brain = talker.Brain()
zh = {"id": 7, "name": "Жорка Адвокат", "community": "stalker", "rank": 300, "relation": "neutral", "dist": 2,
      "voice": "characters_voice\\human_02\\stalker\\"}
state = {"level": "zaton", "hours": 15, "weather": "clear", "emission": True, "actor": {"weapon": "wpn_ak74",
         "outfit": "stalker_outfit"}, "npcs": [zh]}
out = open(Path(__file__).resolve().parent.parent / "test_result.txt", "w", encoding="utf-8")
for said in ["журнака", "Привіт", "Як справи?", "Дякую", "Що думаєш про викид?",
             "Де тут можна сховатися від викиду і що мені робити, якщо не встигну?"]:
    line = brain.reply(zh, state, "", [], said, "reply")
    out.write(f"{said} -> {line}   ({len(line.split())} words)\n")
out.close()
