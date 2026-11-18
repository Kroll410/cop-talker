"""Count prompt tokens per request type with Gemini's free token counter (no generation)."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "companion"))
import talker  # noqa: E402
from google import genai  # noqa: E402

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
brain = talker.Brain()
state = {"level": "zaton", "hours": 22, "minutes": 40, "weather": "rain_default", "emission": False,
         "actor": {"health": 0.62, "weapon": "wpn_ak74", "outfit": "stalker_outfit", "money": 3400},
         "npcs": [{"id": i, "name": f"Сталкер {i}", "community": "stalker", "dist": 5 + i} for i in range(1, 8)]}
npc = {"id": 21, "name": "Вася Хрипатий", "story_name": "zat_sim_1", "community": "stalker", "rank": 650,
       "relation": "friend", "health": 0.9, "dist": 3, "weapon": "wpn_toz34", "place": "«Скадовськ»",
       "voice": "characters_voice\\human_01\\stalker\\", "goodwill": 300}
events = "\n".join(f"{i * 20}s ago: Бандит {i} was killed by гравець" for i in range(1, 9))
history = [{"player": "Привіт, як справи?", "npc": "Та нормально, бродяга, живий поки."}] * 12
recent = ["Здоров, бродяга. Не заблукав ще тут?"] * 8
system = client.models.count_tokens(model=talker.GEMINI_MODEL, contents=talker.SYSTEM_PROMPT).total_tokens
print(f"system prompt: {system} tokens")
for mode, text in [("reply", "Де тут можна знайти артефакти?"), ("greet", ""), ("hostile", ""), ("event", "")]:
    body = brain.situation(npc, state, events, history, text, mode)
    body += "\n" + "\n".join(recent)
    n = client.models.count_tokens(model=talker.GEMINI_MODEL, contents=body).total_tokens
    print(f"{mode:8} request: {n} + system {system} = {n + system} tokens")
