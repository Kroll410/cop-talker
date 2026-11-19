"""Voice-trade prices follow the game's own trade (trade_generic.ltx): a man sells above the base cost and buys
well below it, cheaper to sell and dearer to buy for a friend, guns bought for next to nothing. The prompt shows
these prices, never the raw base cost."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import prices  # noqa: E402
import talker  # noqa: E402

ok = True


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    return cond


ok &= check(prices.sell_price("medkit", 300) == 600 and prices.buy_price("medkit", 300) == 180,
            "medkit (base 300): sells 600, buys 180 (neutral)")
ok &= check(prices.sell_price("medkit", 300, "friend") == 450 and prices.sell_price("medkit", 300, "enemy") == 750,
            "a friend pays less, an enemy more")
ok &= check(prices.buy_price("medkit", 300, "friend") > prices.buy_price("medkit", 300, "enemy"),
            "a friend is paid more for his things")
ok &= check(prices.buy_price("wpn_ak74", 4500) == 1000, "an AK-74 is bought for about a fifth of its cost")
ok &= check(prices.buy_price("bread", 50) == 20 and prices.sell_price("bread", 50) == 100, "bread: 100 / 20")
ok &= check(prices.sell_price("af_medusa", 3000) == 4650, "artifact sell factor 1.1..2")
ok &= check(prices.sell_price("stalker_outfit", 5000) == 8000, "outfits use the Затон trader's factors")
ok &= check(all(p % 5 == 0 for p in (prices.sell_price("x", c) for c in (7, 33, 141, 777, 2345))),
            "prices are round numbers people say")

line = talker.stock_name("Аптечка x3 ~300 #medkit", "sell")
ok &= check(line == "Аптечка (3 pcs, 600 coupons each)", f"his stock in the prompt: {line}")
line = talker.stock_name("Аптечка x3 ~300 #medkit", "buy", "friend")
ok &= check(line == "Аптечка (3 pcs, 240 coupons each)", f"the player's stock, what a friend pays: {line}")
ok &= check(talker.stock_name("Щось x2 #thing") == "Щось (2 pcs)", "no cost known: no price shown")
print("OK" if ok else "FAIL")
