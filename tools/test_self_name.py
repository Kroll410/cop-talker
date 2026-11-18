"""An NPC never talks about himself by his own name ("Борода каже, що..."), and Russian letters never reach the
voice ("крыша" -> "криша"). Saying who he is stays ("Вовк мене звати"). With --live, Claude writes replies."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker  # noqa: E402

boroda = {"id": 1, "name": "Борода", "community": "stalker", "rank": 900, "story": True, "place": "zat_b55"}
vovk = {"id": 2, "name": "Вовк", "community": "stalker", "rank": 500}
cases = [
    (boroda, "Та він, Глухарю, мабуть, платить своїм обаянням, бо грошей я в нього не бачив, їбать! Борода каже, що "
             "в нього тут крыша з тушонки, хай сидить, не кусається.",
     "Та він, Глухарю, мабуть, платить своїм обаянням, бо грошей я в нього не бачив, їбать!"),
    (boroda, "У Бороди все чесно. Наливаю всім.", "Наливаю всім."),
    (vovk, "Вовк мене звати. А ти хто?", "Вовк мене звати. А ти хто?"),
    (vovk, "Я Вовк, і що?", "Я Вовк, і що?"),
    (vovk, "Гонта сказав, що ти брешеш.", "Гонта сказав, що ти брешеш."),
]
ok = True
for npc, line, want in cases:
    got = talker.drop_own_name(line, npc)
    good = got == want
    ok &= good
    print(("ok   " if good else "FAIL ") + f"{npc['name']}: {got}")

for text, want in [("тут крыша з тушонки", "тут криша з тушонки"), ("Ёлки, это что", "Йолки, ето что"),
                   ("підъїзд", "під'їзд")]:
    got = talker.ukrainian_letters(text)
    ok &= got == want
    print(("ok   " if got == want else "FAIL ") + f"{text} -> {got}")

if "--live" in sys.argv:
    talker.LLM_PROVIDER = "claude"
    brain = talker.Brain()
    gluhar = {"id": 3, "name": "Глухар", "community": "stalker", "rank": 300}
    state = {"level": "zaton", "hours": 21, "weather": "clear", "npcs": [boroda, gluhar]}
    line = ("Борода, слухай, а чого цей Юрась Батон тут узагалі сидить, га? Бандюкам же в бар вхід як кроту "
            "в філармонію, чи він вам у борг наливає?")
    print("\nLive:")
    for _ in range(3):
        raw = brain.reply(boroda, state, "", [], "", "addressed", extra={"name": "Глухар", "line": line})
        spoken = talker.ukrainian_letters(raw)
        print("  " + spoken)
        ok &= not any(c in spoken for c in "ыэъё") and "Борода каже" not in spoken

print("OK" if ok else "FAIL")
