"""Paid hits, haggling, money and emotes decided by the AI (no game needed)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker  # noqa: E402

brain = talker.Brain()
bandit = {"id": 3, "name": "Сивий", "community": "bandit", "rank": 400, "relation": "neutral", "dist": 2,
          "voice": "characters_voice\human_03\bandit\\"}
merc = {"id": 5, "name": "Кремінь", "community": "killer", "rank": 600, "relation": "neutral", "dist": 3,
        "voice": "characters_voice\human_02\stalker\\"}
lots = {"id": 1, "name": "Лоцман", "community": "stalker", "rank": 400, "relation": "friend", "dist": 4,
        "voice": "characters_voice\human_01\stalker\\"}
kostet = {"id": 2, "name": "Кастет", "community": "stalker", "rank": 300, "relation": "neutral", "dist": 12,
          "voice": "characters_voice\human_02\stalker\\"}
boroda = {"id": 9, "name": "Борода", "community": "stalker", "rank": 900, "relation": "friend", "dist": 15,
          "story": True, "voice": "characters_voice\human_01\stalker\\"}
rich = {"level": "zaton", "hours": 22, "weather": "clear", "actor": {"weapon": "wpn_ak74", "money": 15000},
        "npcs": [bandit, merc, lots, kostet, boroda]}
poor = dict(rich, actor={"weapon": "wpn_ak74", "money": 300})
out = open(Path(__file__).resolve().parent.parent / "test_result.txt", "w", encoding="utf-8")
cases = [(bandit, rich, "Дам тобі 10 тисяч гривень, якщо завалиш Кастета."),
         (bandit, rich, "Даю 200 купонів, пристрели Кастета."),
         (merc, rich, "Скільки хочеш, щоб прибрати Кастета?"),
         (lots, rich, "Лоцмане, вбий Кастета, заплачу 10000."),
         (bandit, rich, "10 тисяч, якщо вб'єш Бороду."),
         (bandit, poor, "Дам 10 тисяч, завали Кастета."),
         (bandit, rich, "Тримай 500 гривень за інформацію, де схрон."),
         (lots, rich, "Здоров, Лоцмане! Давно не бачились!")]
for npc, st, said in cases:
    line = brain.reply(npc, st, "", [], said, "reply")
    out.write(f"[{npc['name']}, has {st['actor']['money']}] {said}\n  -> {line}\n  actions: {brain.last_action} "
              f"{brain.last_extras}\n")
out.close()

# two steps: ask the price, then agree to what he named
out = open(Path(__file__).resolve().parent.parent / "test_result.txt", "a", encoding="utf-8")
first = brain.reply(merc, rich, "", [], "Скільки хочеш, щоб прибрати Кастета?", "reply")
second = brain.reply(merc, rich, "", [{"player": "Скільки хочеш, щоб прибрати Кастета?", "npc": first}],
                     "Добре, домовились.", "reply")
out.write(f"\nTWO STEPS\n  price -> {first}\n  agree -> {second}\n  actions: {brain.last_extras} "
          f"(limit {talker.offered_amount('Добре, домовились.', [{'npc': first}])})\n")
out.close()
