"""An NPC never talks about himself by his own name ("Борода каже, що..."), and Russian letters never reach the
voice ("крыша" -> "криша"). Saying who he is stays ("Вовк мене звати"). With --live, Claude writes replies."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker  # noqa: E402

boroda = {"id": 1, "name": "Борода", "community": "stalker", "rank": 900, "story": True, "place": "zat_b55"}
vovk = {"id": 2, "name": "Вовк", "community": "stalker", "rank": 500}
cases = [
    (boroda, "Та він, Глухарю, мабуть, платить своїм обаянням, бо грошей я в нього не бачив, їбать! Борода каже, що "
             "в нього тут крыша з тушонки, хай сидить, не кусається.",
     "Та він, Глухарю, мабуть, платить своїм обаянням, бо грошей я в нього не бачив, їбать! В нього тут крыша з "
     "тушонки, хай сидить, не кусається."),
    (boroda, "У Бороди все чесно. Наливаю всім.", "Наливаю всім."),
    (vovk, "Вовк мене звати. А ти хто?", "Вовк мене звати. А ти хто?"),
    (vovk, "Я Вовк, і що?", "Я Вовк, і що?"),
    (vovk, "Гонта сказав, що ти брешеш.", "Гонта сказав, що ти брешеш."),
    # one long sentence with "я" in it: the "Борода каже, що" bit goes, the rest stays (from the log)
    (boroda, "Глухарю, та я сам не розумію, блядь, Борода каже, що його люди тут терпимі, а вигнати їх у дощ "
             "як-то не по-людськи, їбать!",
     "Глухарю, та я сам не розумію, блядь, його люди тут терпимі, а вигнати їх у дощ як-то не по-людськи, їбать!"),
    (boroda, "Борода каже: наливаю всім. Сідай.", "Наливаю всім. Сідай."),
    (boroda, "Наливаю всім, бо Борода знає, що вам важко.", "Наливаю всім, бо вам важко."),
    (vovk, "Я тут стою, а Вовк думає, що ти брешеш.", "Я тут стою, а ти брешеш."),
    # asked his name, he answers with it: a short sentence with the name is an introduction, it stays
    ({"name": "Шульга"}, "Шульга. Запам'ятай, бо двічі не повторюватиму.",
     "Шульга. Запам'ятай, бо двічі не повторюватиму."),
    (vovk, "Вовк я. А ти хто?", "Вовк я. А ти хто?"),
    (vovk, "[sighs] Вовк. А ти, як чую, Кроль, так?", "[sighs] Вовк. А ти, як чую, Кроль, так?"),
]
ok = True
for npc, line, want in cases:
    got = talker.drop_own_name(line, npc)
    good = got == want
    ok &= good
    print(("ok   " if good else "FAIL ") + f"{npc['name']}: {got}")

# asked his name, "Вовк я, вільний сталкер." is his answer, not narration about himself; "Вовк зітхає" still is
for raw_line, want in [("Вовк я, вільний сталкер. А ти хто?", "Вовк я, вільний сталкер. А ти хто?"),
                       ("Вовк мене звати. А ти?", "Вовк мене звати. А ти?"),
                       ("Вовк зітхає важко. Горілки нема.", "Горілки нема.")]:
    got = talker.drop_narration(raw_line, vovk)
    ok &= got == want
    print(("ok   " if got == want else "FAIL ") + f"narration: {raw_line} -> {got}")

for text, want in [("тут крыша з тушонки", "тут криша з тушонки"), ("Ёлки, это что", "Йолки, ето что"),
                   ("підъїзд", "під'їзд")]:
    got = talker.ukrainian_letters(text)
    ok &= got == want
    print(("ok   " if got == want else "FAIL ") + f"{text} -> {got}")

# a healthy man doesn't trail off with "..." (the wounded still do)
voiced = []
tk = talker.Talker.__new__(talker.Talker)
tk.recording, tk.spoken = False, []
tk.game = type("G", (), {"send": lambda self, *x: None, "distance_to": lambda self, i: 3})()
tk.voice = type("V", (), {"say": lambda self, npc, line, **k: voiced.append(line)})()
tk.brain = type("B", (), {"news": type("N", (), {"mark_mentioned": lambda self, x: []})()})()
tk.show_line = lambda *a: None
talker.report = lambda *a: None
tk.speak(vovk, "Ну привіт, привіт...")
tk.speak(vovk, "Та шо нового… [sighs]")
tk.speak(vovk, "Іду... зараз буду.")
tk.speak(dict(vovk, wounded=True), "Аптечку...")
ok &= voiced == ["Ну привіт, привіт.", "Та шо нового. [sighs]", "Іду... зараз буду.", "Аптечку..."]
print(("ok   " if voiced[:4] == ["Ну привіт, привіт.", "Та шо нового. [sighs]", "Іду... зараз буду.", "Аптечку..."]
       else "FAIL ") + f"trailing '...': {voiced}")

# the player's name in most lines got tiring (16 of 20 live replies): an address set off by commas, anywhere in
# the line, is kept only in about a third of lines; a name inside the words stays
real_name, talker.PLAYER_NAME = talker.PLAYER_NAME, "Кроль"
for line, want in [("Та нормально, Кролю, живий поки, хулі.", "Та нормально, живий поки, хулі."),
                   ("чё ти питаєш, Кроль?", "чё ти питаєш?"), ("Кролю, бар у Скадовську.", "Бар у Скадовську."),
                   ("Ти часом не той самий Кроль, про якого всі базікають?",
                    "Ти часом не той самий Кроль, про якого всі базікають?")]:
    got = talker.thin_player_name(line, keep=0)
    ok &= got == want
    print(("ok   " if got == want else "FAIL ") + f"player name thinned: {got}")
kept = sum("Крол" in talker.thin_player_name("Та нормально, Кролю, живий поки.") for _ in range(600))
ok &= 120 < kept < 300
print(("ok   " if 120 < kept < 300 else "FAIL ") + f"name kept in {kept} of 600 lines")
talker.PLAYER_NAME = real_name

if "--live" in sys.argv:
    talker.LLM_PROVIDER = "claude"
    brain = talker.Brain()
    gluhar = {"id": 3, "name": "Глухар", "community": "stalker", "rank": 300}
    state = {"level": "zaton", "hours": 21, "weather": "clear", "npcs": [boroda, gluhar]}
    line = ("Борода, а скажи мені, якого хріна Султан у тебе тут робить, він же бандюган, ну? Йому тут місце як "
            "їжаку в пральній машині, а він сидить і п'є, паскуда!")
    print("\nLive:")
    for _ in range(3):
        raw = brain.reply(boroda, state, "", [], "", "addressed", extra={"name": "Глухар", "line": line})
        spoken = talker.ukrainian_letters(raw)
        print("  " + spoken)
        ok &= not any(c in spoken for c in "ыэъё") and not re.search(r"Бород\w*\s+(каже|говорить|вважає|думає)", spoken)

print("OK" if ok else "FAIL")
