"""Text-only check of AI-decided actions: insults should turn NPCs hostile, kindness should not."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker  # noqa: E402

brain = talker.Brain()
state = {"level": "zaton", "hours": 15, "minutes": 0, "weather": "clear", "emission": False,
         "actor": {"health": 1.0, "weapon": "wpn_ak74", "outfit": "stalker_outfit", "money": 3400}, "npcs": []}
stalker = {"id": 41, "name": "Федір Сич", "story_name": "zat_sim_1", "community": "stalker", "rank": 500,
           "relation": "neutral", "health": 1.0, "dist": 3, "voice": "characters_voice\\human_01\\stalker\\"}
bandit = dict(stalker, id=42, name="Штиль", community="bandit", voice="characters_voice\\human_03\\bandit\\")
hostile_bandit = dict(bandit, relation="enemy")
barman = dict(stalker, id=43, name="Борода", story=True)
cases = [
    (stalker, "Привіт, як справи?"),
    (stalker, "Що чути про викид?"),
    (stalker, "Ти жалюгідний покидьок, я твою матір у болоті втопив."),
    (bandit, "Слухай, пропусти, будь ласка."),
    (bandit, "Пішов нахуй, урод, зараз тобі голову відстрелю."),
    (hostile_bandit, "Стій, не стріляй! Я тобі тисячу дам і розійдемось, лади?"),
    (stalker, "Тримай аптечку і тушонку, брате, ти мені вчора життя врятував."),
    (barman, "Ти старий жирний злодій, Бородо, я тебе вб'ю."),
]
with open(Path(__file__).resolve().parent.parent / "test_result.txt", "w", encoding="utf-8") as out:
    for npc, said in cases:
        reply = brain.reply(npc, state, "nothing notable", [], said, "reply")
        out.write(f"[{npc['name']}, {npc['community']}, {npc['relation']}{', story' if npc.get('story') else ''}] "
                  f"-> ACTION {brain.last_action}\n  P: {said}\n  NPC: {reply}\n")
