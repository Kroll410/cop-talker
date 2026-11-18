"""A paid hit on a man far away: the deal goes through, money is taken, and the killer is sent to find him."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker  # noqa: E402


class FakeGame:
    sent = []

    def send(self, kind, npc_id, text):
        self.sent.append((kind, npc_id, text))


class FakeMemory:
    def add(self, *a):
        pass


t = talker.Talker.__new__(talker.Talker)
t.game, t.memory = FakeGame(), FakeMemory()
t.confront = lambda *a: FakeGame.sent.append(("confront",))
killer = {"id": 1, "name": "Сивий", "community": "bandit", "dist": 2}
state = {"mod_version": 10, "actor": {"money": 50000},
         "npcs": [killer, {"id": 3, "name": "Кастет", "community": "stalker", "dist": 12}],
         "far": [{"id": 7, "name": "Лоцман", "community": "stalker", "dist": 340}]}
t.do_deals(killer, state, [("take", 5000), ("kill", "Лоцмана")], "k", "Даю 5000, завали його")
print(*FakeGame.sent, sep="\n")
assert ("act", 1, "take:5000") in FakeGame.sent and ("act", 1, "kill:7:paid") in FakeGame.sent
assert ("confront",) not in FakeGame.sent, "no face-to-face talk with a man 340 m away"
FakeGame.sent.clear()
t.do_deals(killer, state, [("take", 5000), ("kill", "Кастета")], "k", "Даю 5000, завали його")
assert ("confront",) in FakeGame.sent and ("act", 1, "kill:3:paid") in FakeGame.sent
FakeGame.sent.clear()
t.do_deals(killer, state, [("take", 5000), ("kill", "Бороду")], "k", "Даю 5000, завали його")
assert not any(s[0] == "act" for s in FakeGame.sent), "unknown target: no money taken"
print("far hit ok")
