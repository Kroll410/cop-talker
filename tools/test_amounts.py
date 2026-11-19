"""Money amounts in what the player says (deals, hits, debts): digits, number words, slang, fractions, hundreds.
Counts and dates are not prices."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker  # noqa: E402

CASES = {
    "дам п'ятсот": 500, "за тисячу двісті": 1200, "дві тисячі п'ятсот": 2500, "300 гривень": 300, "за 1500": 1500,
    "тисячу": 1000, "сто п'ятдесят": 150, "дев'ятсот": 900, "п'ять тисяч": 5000, "дам 2000 купонів": 2000,
    "сорок": 40, "чотириста п'ятдесят": 450, "5 тисяч": 5000, "2к дам": 2000, "10 000": 10000,
    # slang and fractions
    "1,5к": 1500, "2.5к": 2500, "1.5 тисячі": 1500, "півтори тисячі": 1500, "пів тисячі": 500,
    "три сотні": 300, "пару сотень": 200, "п'ять тисяч три сотні": 5300, "за сотку": 100,
    # not prices
    "пару днів тому": None, "пів дня ходив": None, "три кабани": None, "о 5.30 прийду": None, "версія 1.6": None,
    "сотні сталкерів загинули": None,
}
ok = True
for text, want in CASES.items():
    got = talker.amounts(text)
    value = max(got) if got else None
    good = value == want
    ok &= good
    if not good:
        print(f"FAIL {text!r}: {got} (want {want})")
# asking a price or what he sells puts his stock in the prompt (a trader asked "Скільки за хліб?" said
# "я шо тобі, пекарня?" with bread in his bag)
TRADE = ["Скільки за хліб?", "За скільки віддаси хліб?", "По чому ковбаса?", "Почому патрони?", "Що в тебе є?",
         "Шо продаєш?", "Продаси хліб?"]
NOT_TRADE = ["Скільки тобі років?", "Скільки за мною йде мутантів?", "Як справи?"]
for q in TRADE:
    if not talker.TRADE_WORDS.search(q):
        ok = False
        print(f"FAIL trade not seen: {q!r}")
for q in NOT_TRADE:
    if talker.TRADE_WORDS.search(q):
        ok = False
        print(f"FAIL taken as trade: {q!r}")
print(f"{len(CASES)} phrases")
print("OK" if ok else "FAIL")
