"""Duty is always "Долг" and its men "долгівці": the AI is told so, and anything that slips through is fixed
before it is spoken. The ordinary word "обов'язок" (a duty) is left alone. With --live, Claude writes lines."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker  # noqa: E402

cases = [
    ("Обов'язок знову патрулює міст.", "Долг знову патрулює міст."),
    ("Він з Обов’язку, видно по броні.", "Він з Долгу, видно по броні."),
    ("Ми з «Обов'язком» не дружимо.", "Ми з «Долгом» не дружимо."),
    ("З «обов'язку» прийшли.", "З «Долгу» прийшли."),
    ("Ці обов'язківці задовбали.", "Ці долгівці задовбали."),
    ("Обов'язківець стоїть біля входу.", "Долгівець стоїть біля входу."),
    ("Дай обов'язківцю патронів.", "Дай долгівцю патронів."),
    ("Хуєплют ти обов'язківський.", "Хуєплют ти долгівський."),
    ("Мій обов'язок прикрити тебе.", "Мій обов'язок прикрити тебе."),
    ("У мене купа обов'язків.", "У мене купа обов'язків."),
    ("Це твій обов'язок, брате.", "Це твій обов'язок, брате."),
]
ok = True
for text, want in cases:
    got = talker.fix_factions(text)
    good = got == want
    ok &= good
    print(("ok   " if good else "FAIL ") + f"{text} -> {got}")

ok &= "Обов" not in talker.COMMUNITIES["dolg"] and "Долг" in talker.COMMUNITIES["dolg"]
ok &= "Долг" in talker.CHAT_SYSTEM and "Долг" in talker.SYSTEM_PROMPT and "Долг" in talker.GROUP_SYSTEM \
    and "Долг" in talker.OVERHEARD_SYSTEM
print("prompts and faction name:", "ok" if ok else "FAIL")

if "--live" in sys.argv:
    talker.LLM_PROVIDER = "claude"
    brain = talker.Brain()
    duty = {"id": 1, "name": "Вовк", "community": "dolg", "rank": 700, "place": "p"}
    free = {"id": 2, "name": "Лоцман", "community": "freedom", "rank": 300, "place": "p"}
    stalker = {"id": 3, "name": "Гонта", "community": "stalker", "rank": 500, "place": "p"}
    state = {"level": "zaton", "hours": 20, "weather": "clear", "npcs": [duty, free, stalker]}
    raw = []
    for _ in range(2):
        raw += [l for _, l in brain.chat(free, stalker, state, "",
                                         scene="They argue about the Duty faction and its men: what they think of "
                                               "them, a story about one of them.")]
    for q in ("Ти з якого угруповання?", "Що думаєш про своїх товаришів по фракції?"):
        raw.append(brain.reply(duty, state, "", [], q, "reply"))
    raw.append(brain.reply(stalker, state, "", [], "Що скажеш про угруповання Долг і його бійців?", "reply"))
    print("\nLive lines (as written, then as spoken):")
    for line in raw:
        fixed = talker.fix_factions(line)
        print("  " + line + ("" if fixed == line else f"\n    -> {fixed}"))
        ok &= "Обов'язок" not in fixed and "обов'язків" not in fixed.lower().replace("обов'язків ", "")
    mentioned = sum("долг" in l.lower() for l in raw)
    print(f"Долг/долгівці mentioned in {mentioned} of {len(raw)} lines")

print("OK" if ok else "FAIL")
