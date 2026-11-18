"""Text-only check: environment reactions, a warning with squad backup, and squad mates joining a fight."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker  # noqa: E402

brain = talker.Brain()
state = {"level": "zaton", "hours": 21, "minutes": 0, "weather": "rain", "emission": False,
         "actor": {"health": 1.0, "weapon": "wpn_ak74", "outfit": "stalker_outfit", "money": 3400}, "npcs": []}
leader = {"id": 51, "name": "Сокира", "story_name": "zat_sim_51", "community": "dolg", "rank": 700,
          "relation": "neutral", "health": 1.0, "dist": 3, "squad": 900, "leader": True,
          "voice": "characters_voice\\human_01\\stalker\\"}
mate1 = dict(leader, id=52, name="Рядовий Глушко", story_name="zat_sim_52", leader=False, dist=6,
             voice="characters_voice\\human_02\\stalker\\")
mate2 = dict(leader, id=53, name="Кіт", story_name="zat_sim_53", leader=False, dist=8,
             voice="characters_voice\\human_03\\stalker\\")
stalker = {"id": 54, "name": "Льоха", "story_name": "zat_sim_54", "community": "stalker", "rank": 300,
           "relation": "friend", "health": 1.0, "dist": 5, "voice": "characters_voice\\human_02\\stalker\\"}
spoken = []
with open(Path(__file__).resolve().parent.parent / "test_result.txt", "w", encoding="utf-8") as out:
    for what in ["The sky turns red: an EMISSION is starting right now.",
                 "You spot a кровосос about 22 m away.",
                 "You were just badly wounded and fell. Call for help.",
                 "It is getting dark, night is falling in the Zone."]:
        line = brain.reply(stalker, state, "", [], "", "react", recent=spoken, extra={"what": what})
        spoken.append(line)
        out.write(f"[react] {what}\n  Льоха: {line}\n")

    for said in ["Слухай, Обов'язок — це просто клоуни в зелених костюмчиках.",
                 "Та пішли ви всі нахуй разом зі своїм генералом, собаки військові."]:
        reply = brain.reply(leader, state, "", [], said, "reply", recent=spoken)
        action = brain.last_action
        spoken.append(reply)
        out.write(f"\n[reply] P: {said}\n  Сокира: {reply}   -> ACTION {action}\n")
        if action in ("warn", "hostile"):
            for mate in (mate1, mate2):
                line = brain.reply(mate, state, "", [], "", "backup", recent=spoken,
                                   extra={"leader": leader["name"], "line": reply})
                spoken.append(line)
                out.write(f"  {mate['name']} (backs up{', turns hostile' if action == 'hostile' else ''}): {line}\n")
