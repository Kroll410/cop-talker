"""«62»: a reward the streamer makes on Twitch (the app never creates it) and picks on the Redeems tab. A redemption
goes to the game at once, no Zone queue and no autosave; the game shouts the streamer's clip «шиісят два» 10 times
from all round the player, each copy at its own spot, volume, pitch and delay (checked in tools/zone_lua.py), and the
men around are confused and freaked out. The checks are shared with «Чики-брики» (tools/clip_checks.py)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "companion"))
import talker  # noqa: E402,F401
from clip_checks import check_clip  # noqa: E402  (tools/clip_checks.py)

ok = True


def check(cond, what):
    global ok
    ok &= bool(cond)
    print(("ok   " if cond else "FAIL ") + what)


check_clip(check, "62", "62", "sixty_two", "TWITCH_62_REWARD", "on_sixty_two", "шиісят два", ("sixty-two",))
print("OK" if ok else "FAIL")
