"""Bandits talk surzhyk (about 3 words in 10 Russian, kept in Russian letters); everyone else speaks
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

# every variant is caught (a scientist never says one; a bandit may), and ordinary words are not
VARIANTS = ["негр", "негрятко", "негрик", "негрило", "негер", "нігер", "ніга", "Негростан", "негроїд", "підарок",
            "підріла", "підарасік", "підорлик", "підор", "підар", "підарас", "підорас", "Нігери", "Ніга"]
missed = [w for w in VARIANTS if not talker.has_slur(f"Слухай, {w}, вали звідси", scientist)]
ok &= check(not missed, f"every slur variant is caught {missed}")
ok &= check(all(not talker.has_slur(f"Слухай, {w}, вали звідси", bandit) for w in VARIANTS), "a bandit may say each")
CLEAN = ["негайно", "негерметичний костюм", "нігті", "підрозділ", "підрив", "Нігерія", "в Нігерії", "наша нога",
         "ні гадки"]
caught = [w for w in CLEAN if talker.SLUR_STEMS.search(w)]
ok &= check(not caught, f"ordinary words aren't slurs {caught}")
note = talker.slur_note(bandit)
ok &= check(all(w in note for w in ("підорлик", "негрило", "Негростан", "підріла")) and "Vary" in note,
            "a bandit gets the whole list and is told to vary it")
ok &= check("негр" in talker.slur_note(stalker) and "Vary" not in talker.slur_note(stalker),
            "a stalker: rare, not told to vary like a bandit")
# a stalker: about one line in ten is rolled to have a slur (from the whole list); the filter follows that roll
rolled, agree = 0, True
for _ in range(4000):
    n = talker.slur_note(stalker)
    yes = "work one street slur in" in n
    rolled += yes
    if yes and not all(w in n for w in ("підорлик", "негрило", "Негростан", "жид")):
        agree = False
    if talker.has_slur("Слухай, підарас, вали звідси", stalker) == yes:  # allowed exactly when rolled
        agree = False
ok &= check(0.08 < rolled / 4000 < 0.12, f"a stalker: a slur line about 10% of the time ({rolled / 40:.1f}%)")
ok &= check(agree, "a stalker: a rolled line gets the whole list, and only a rolled line may keep its slur")
talker.SLUR_TURN.clear()
ok &= check(talker.has_slur("Слухай, підарас, вали звідси", stalker), "no roll yet for him: no slur")

# SLURS=0: nobody may say one, nobody is given slur words, everybody still answers one
talker.SLURS = False
ok &= check(all(talker.has_slur(f"Слухай, {w}, вали звідси", n) for w in VARIANTS + ["жид"] for n in (bandit, stalker)),
            "SLURS=0: a bandit's or a stalker's line with any slur is written again")
notes = [talker.slur_note(n) for n in (bandit, stalker, scientist)]
ok &= check(all("react" in x and not talker.SLUR_STEMS.search(x) for x in notes),
            "SLURS=0: no slur words in anyone's prompt, but they still react to one")
ok &= check("surzhyk" in talker.npc_brief(bandit) and not talker.SLUR_STEMS.search(talker.npc_brief(bandit)),
            "SLURS=0: a bandit still talks surzhyk, without slurs")
tw = talker.Talker.__new__(talker.Talker)
tw.twitch_queue, tw.twitch = [], None
tw.on_twitch("viewer", "$Лоцман, ти підорлик", None)
tw.on_twitch("viewer", "$Лоцман, ти молодець", None)
ok &= check([x[1] for x in tw.twitch_queue] == ["Лоцман, ти молодець"],
            f"SLURS=0: a chat message with a slur is skipped, not said word for word {tw.twitch_queue}")
talker.SLURS = True
ok &= check(not talker.has_slur("Ти жид, братан", bandit), "SLURS=1 again: a bandit may")

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

# each request suggests its own few fillers, so the model doesn't lean on one ("йопта" everywhere)
hints = {talker.filler_hint() for _ in range(20)}
ok &= check(len(hints) > 10 and all(h.split(": ", 1)[1].count(", ") == 2 for h in hints),
            f"filler hints vary: {len(hints)} different of 20")
prompt = talker.Brain.__new__(talker.Brain).situation(stalker, {"level": "zaton", "npcs": [stalker]}, "", [], "Привіт")
ok &= check("Fillers that suit this moment" in prompt, "a reply prompt carries its own filler hint")

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
