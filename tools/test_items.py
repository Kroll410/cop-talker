"""Buying items by talking: price first, item + payment only once a price is agreed."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker  # noqa: E402

brain = talker.Brain()
stock = ["Аптечка x12 ~300 #medkit", "Бинт x20 ~150 #bandage", "Горілка «Козаки» x8 ~120 #vodka",
         "Ковбаса «Дієтична» x10 ~100 #sausage", "Детектор «Відгук» x1 ~2500 #detector_advanced"]
boroda = {"id": 9, "name": "Борода", "community": "stalker", "rank": 900, "relation": "friend", "dist": 2,
          "story": True, "stock": stock, "voice": "characters_voice\\human_01\\stalker\\"}
state = {"level": "zaton", "hours": 20, "weather": "clear", "actor": {"weapon": "wpn_ak74", "money": 5000,
         "outfit": "stalker_outfit"}, "npcs": [boroda]}
out = open(Path(__file__).resolve().parent.parent / "test_result.txt", "w", encoding="utf-8")
history = []
for said in ["Продай аптечку.", "Добре, беру.", "Дам 200 за пляшку горілки.", "Подаруй мені бинт, я ж свій."]:
    line = brain.reply(boroda, state, "", history, said, "reply")
    extras = brain.last_extras
    items = [(a, talker.find_stock_item(stock, a)) for k, a in extras if k == "item"]
    out.write(f"{said}\n  -> {line}\n  actions: {extras}  items resolved: {items}\n")
    history.append({"player": said, "npc": talker.strip_tags(line)})
out.close()
