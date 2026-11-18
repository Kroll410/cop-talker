"""Bandits talk surzhyk (about half Russian, Russian words kept in Russian letters); everyone else speaks
Ukrainian (stray Russian letters fixed). «жид» is in the bandits' street vocabulary like the other slurs; others
use it only rarely, and a man it's thrown at reacts. With --live, Claude writes lines."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker  # noqa: E402

ok = True


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    return cond


bandit = {"id": 1, "name": "Сивий", "community": "bandit", "rank": 400}
stalker = {"id": 2, "name": "Лоцман", "community": "stalker", "rank": 300}
scientist = {"id": 3, "name": "Озьорський", "community": "ecolog", "rank": 300}

ok &= check("surzhyk" in talker.npc_brief(bandit) and "surzhyk" not in talker.npc_brief(stalker),
            "bandit described as a surzhyk speaker, stalker not")
ok &= check("«жид»" in talker.slur_note(bandit) and "жид" in talker.slur_note(stalker), "«жид» in the slur notes")
ok &= check("react" in talker.slur_note(scientist) and "жид" not in talker.slur_note(bandit).split("If someone")[0][:0],
            "a scientist never says it but reacts to it")
ok &= check(not talker.has_slur("Ти жид, братан", bandit), "a bandit may say it")

# the voice: a bandit's Russian stays, a stalker's stray Russian letters are fixed
sent, voiced = [], []
t = talker.Talker.__new__(talker.Talker)
t.recording, t.spoken = False, []
t.game = type("G", (), {"send": lambda self, *x: sent.append(x), "distance_to": lambda self, i: 3})()
t.voice = type("V", (), {"say": lambda self, npc, line, **k: voiced.append(line)})()
t.brain = type("B", (), {"news": type("N", (), {"mark_mentioned": lambda self, x: []})()})()
t.show_line = lambda *a: None
talker.report = lambda *a: None
t.speak(bandit, "Слышь, братан, чё ты тут забыл?")
t.speak(stalker, "Та в нього тут крыша з тушонки.")
ok &= check(voiced == ["Слышь, братан, чё ты тут забыл?", "Та в нього тут криша з тушонки."], f"voiced: {voiced}")

if "--live" in sys.argv:
    talker.LLM_PROVIDER = "claude"
    brain = talker.Brain()
    state = {"level": "zaton", "hours": 21, "weather": "clear", "npcs": [bandit, stalker]}
    russian = re.compile(r"[ыэъё]|\b(чё|что|слышь|короче|братан|базар|тебя|меня|сейчас|нормально|ну всё)\b", re.I)
    print("\nBandit replies to the player:")
    for q in ("Привіт, що тут робиш?", "Скільки за аптечку?", "Чого ти на мене так дивишся?"):
        line = brain.reply(bandit, state, "", [], q, "reply")
        print(f"  {q} -> {line}")
        ok &= check(bool(russian.search(line or "")), "  has Russian words")
    print("\nStalker replies (Ukrainian):")
    for q in ("Привіт, що тут робиш?", "Що думаєш про бандитів?"):
        line = talker.ukrainian_letters(brain.reply(stalker, state, "", [], q, "reply"))
        print(f"  {q} -> {line}")
        ok &= check(not re.search(r"[ыэъё]", line or ""), "  no Russian letters")
    print("\nBandit and stalker chat, money talk:")
    for _ in range(2):
        for n, l in brain.chat(bandit, stalker, state, "", scene="A wants B to pay back 500 he owes; B haggles and "
                                                                  "stalls. Short, crude."):
            print(f"  {n['name']}: {l}")
        print("  --")
    print("\nA stalker is called «жид» by the bandit and answers:")
    for _ in range(2):
        line = brain.reply(stalker, state, "", [], "", "addressed",
                           extra={"name": "Сивий", "line": "Слышь, жид, ты мне пятьсот должен, чё зажал?"})
        print(f"  Лоцман: {line}")

print("OK" if ok else "FAIL")
