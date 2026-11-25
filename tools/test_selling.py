"""Offline: which player lines count as selling his own goods (then the NPC sees them and can buy them)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker  # noqa: E402

fails = 0
SELLS = ["Візьми мою ковбасу за 100", "Хочу продати ковбасу.", "Купиш ковбасу за 80?", "Продам горілку",
         "Купи мої патрони", "Забери мою аптечку за 300", "Візьмеш хліб?", "Можу продати тобі бинти",
         "Візьми цю мою ковбасу", "Давай продати тобі детектор"]
NOT = ["Продай ковбасу.", "Скільки за ковбасу?", "Беру.", "Візьми мене з собою", "Продай мені свою ковбасу",
       "Що в тебе є?", "Можеш продати ковбасу?"]
for s in SELLS:
    if not talker.selling_context(s, []):
        fails += 1
        print("FAIL not seen as selling:", s)
for s in NOT:
    if talker.selling_context(s, []):
        fails += 1
        print("FAIL seen as selling:", s)
# the next line of the same talk still counts ("За 150 згода?" after "Хочу продати ковбасу")
if not talker.selling_context("За 150 згода?", [{"player": "Хочу продати ковбасу.", "npc": "Що просиш?"}]):
    fails += 1
    print("FAIL the price line after a sell offer")
talk = [{"player": "Хочу продати ковбасу.", "npc": "Давай подивимось."},
        {"player": "Скільки даси?", "npc": "Сорок за штуку."}]
if not talker.selling_context("Добре, по руках.", talk):
    fails += 1
    print("FAIL two lines after the sell offer it's still a sale")
if talker.selling_context("Беру.", talk + [{"player": "А продай мені хліб.", "npc": "Сорок."}]):
    fails += 1
    print("FAIL he turned to buying: no longer a sale")


def check(ok, what):
    global fails
    if not ok:
        fails += 1
        print("FAIL", what)


# which of the player's things the talk is about
stock = ["Ковбаса «Дієтична» x2 ~100 #kolbasa", "Горілка «Козаки» x1 ~200 #vodka", "Хліб x1 ~50 #bread"]
check(talker.mentioned_stock(stock, "Візьми мою ковбасу") == "Ковбаса «Дієтична»", "ковбасу -> the sausage")
check(talker.mentioned_stock(stock, "Ковбасу і горілку бери") is None, "two things named: not one")
check(talker.mentioned_stock(stock, "По руках") is None, "nothing named")

# a price per item: "сорок за штуку" then "Згода" for two sausages is 40 each, not 40 for both
settle = talker.Brain.settle_buys
two = [("buy", ("Ковбаса Дієтична", 40)), ("buy", ("Ковбаса Дієтична", 40))]
hist = [{"player": "Купиш ковбасу?", "npc": "Ковбасу беру, сорок за штуку дам."}]
check(settle(two, "Згода.", hist) == two, f"40 each kept {settle(two, 'Згода.', hist)}")
low = [("buy", ("Ковбаса Дієтична", 40)), ("buy", ("Ковбаса Дієтична", 30))]
check(settle(low, "Згода.", hist) == [], "one below the agreed each price: not a deal yet")
# a price for all of them stays a total: "дві за 80" pays 80 in all
hist2 = [{"player": "Купиш дві ковбаси?", "npc": "Дві візьму за вісімдесят."}]
got = settle([("buy", ("Ковбаса", 60)), ("buy", ("Ковбаса", 60))], "Згода.", hist2)
check(sum(a[1] for _, a in got) == 80, f"a total price stays the total {got}")
print("OK" if not fails else f"{fails} failed")
sys.exit(1 if fails else 0)
