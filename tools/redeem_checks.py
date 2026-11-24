"""Shared check for a trigger redeem's wiring: it's one entry in companion/redeems.py, and that entry drives the
Twitch routing, the window's Redeems row (picker + Test) and the helper's test command. Used by the test_<redeem>.py
scripts; import it after talker (it needs companion/ on sys.path)."""
import types

import redeems
import talker


def check_redeem(check, rid, key, handler):
    r = redeems.by_id(rid)
    check(r is not None and r.key == key and r.handler == handler and r.kind == "trigger",
          f"redeems.py: «{rid}» is one entry ({key} -> {handler})")
    if r is None:
        return
    check(callable(getattr(talker.Talker, handler, None)), f"Talker.{handler} exists")
    fake = types.SimpleNamespace(**{x.handler: x.handler for x in redeems.TRIGGERS})
    routed = redeems.triggers({key: "Мій редім", "TWITCH_UNRELATED": "x"}, fake)
    check(routed == {"Мій редім": handler}, f"a title in {key} routes redemptions to {handler}")
    check(redeems.triggers({key: "  "}, fake) == {}, f"{key} empty: off, nothing routed")
    check(key in redeems.KEYS, "the window shows it on the Redeems tab (picker from the channel's rewards, Test)")
    check(rid in talker.NO_RETRY, "fired at once: a failed one is given up, never retried")
