"""Text-only check: emission in/out of shelter and after it, follow/stay actions, enemy answering, listener choice."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker  # noqa: E402

brain = talker.Brain()
base = {"level": "zaton", "hours": 14, "minutes": 0, "weather": "clear", "emission": False,
        "actor": {"health": 1.0, "weapon": "wpn_ak74", "outfit": "stalker_outfit", "money": 3400}, "npcs": []}
npc = {"id": 71, "name": "Льоха Ворон", "story_name": "zat_sim_71", "community": "stalker", "rank": 400,
       "relation": "friend", "health": 1.0, "dist": 3, "place": "zat_stalker_base_smart",
       "voice": "characters_voice\\human_02\\stalker\\"}
enemy = dict(npc, id=72, name="Кабан", community="bandit", relation="enemy", in_combat=True, fighting="player",
             dist=25, voice="characters_voice\\human_03\\bandit\\")
out = open(Path(__file__).resolve().parent.parent / "test_result.txt", "w", encoding="utf-8")


def ask(label, who, state, said, mode="reply"):
    line = brain.reply(who, state, "", [], said, mode)
    out.write(f"[{label}] {said}\n  -> {line}   (action {brain.last_action})\n")


ask("emission, in shelter", dict(npc, sheltered=True), dict(base, emission=True), "Як ти?")
ask("emission, outside", dict(npc, place="zat_b55"), dict(base, emission=True), "Як ти?")
ask("emission ended 2 min ago", npc, dict(base, emission_ended_min=2), "Як ти?")
ask("no emission", npc, base, "Як ти?")
ask("follow request", npc, base, "Ходімо зі мною до Шевченка, прикриєш мене?")
ask("stay", dict(npc, following=True), base, "Все, дякую, чекай тут.")
ask("talking to enemy", enemy, base, "Гей, кабане, давай поговоримо!")

g = talker.Game.__new__(talker.Game)
g.last_used_npc = (None, 0)
state = dict(base, target_id=81, npcs=[
    {"id": 80, "name": "Гонта", "dist": 2.5, "relation": "neutral"},
    {"id": 81, "name": "Кіт", "dist": 4.0, "relation": "neutral"},
    {"id": 82, "name": "Вовк", "dist": 30.0, "relation": "enemy"}])
for said in ["Гонто, що скажеш?", "Привіт", "Вовче, здавайся!"]:
    out.write(f"[listener] '{said}' -> {g.pick_listener(state, said)['name']}\n")
out.write(f"[place] zat_stalker_base_smart -> {talker.place_name('zat_stalker_base_smart')}, "
          f"zat_b55 -> {talker.place_name('zat_b55')}, some_unknown_smart -> {talker.place_name('some_unknown_smart')}\n")
out.close()
