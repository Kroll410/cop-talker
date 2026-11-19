"""Zone prices for voice trading, the way the game's own trade works (configs/misc/trade/trade_generic.ltx):
price = the item's base cost x a factor. Each factor pair is (for a friend, for an enemy); a neutral man is in
the middle. A man SELLS to you above the base cost and BUYS from you well below it.

Ordinary stalkers in the game don't trade outfits, helmets or detectors at all; for those the factors of the
Затон trader (trade_zat_b30_stalker_trader.ltx) are used.
"""
import re

# (pattern on the game section, (sell friend, sell enemy), (buy friend, buy enemy))
FACTORS = [
    (r"^af_", (1.1, 2.0), (0.8, 0.5)),                                             # artifacts
    (r"^(bread|kolbasa|conserva|vodka|energy_drink)", (1.5, 2.5), (0.6, 0.3)),    # food and drink
    (r"^(ammo_|grenade_|medkit|bandage|antirad|drug_|novice_outfit)", (1.5, 2.5), (0.8, 0.4)),
    (r"^wpn_", (1.0, 2.0), (0.25, 0.2)),                                          # guns and add-ons
    (r"(_outfit|^helm_)", (1.0, 2.2), (0.5, 0.3)),                                 # outfits, helmets
    (r"^(detector_|device_)", (1.0, 2.2), (0.3, 0.1)),
]
DEFAULT = ((1.5, 2.5), (0.6, 0.3))
WHERE = {"friend": 0.0, "neutral": 0.5, "enemy": 1.0}  # how far from the friend's price to the enemy's


def factors(section):
    for pattern, sell, buy in FACTORS:
        if re.search(pattern, section or ""):
            return sell, buy
    return DEFAULT


def _between(pair, relation):
    t = WHERE.get(relation, 0.5)
    return pair[0] + (pair[1] - pair[0]) * t


def _round(price):
    """Prices people say: 47 -> 50, 1234 -> 1250, never 0."""
    step = 5 if price < 100 else 10 if price < 500 else 50 if price < 5000 else 100
    return max(step, int(round(price / step)) * step)


def sell_price(section, cost, relation="neutral"):
    """What he asks for one of his items."""
    return _round(cost * _between(factors(section)[0], relation))


def buy_price(section, cost, relation="neutral"):
    """What he'd pay for one of the player's items."""
    return _round(cost * _between(factors(section)[1], relation))
