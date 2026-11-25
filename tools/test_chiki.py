"""«Чики-брики»: works like «62» (tools/clip_checks.py), with another clip: «а ну чики-брики» shouted 7-17 times from
all round the player (sounds\\talker\\chiki_briki*.ogg)."""
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


check_clip(check, "chiki", "Чики-брики", "chiki_briki", "TWITCH_CHIKI_REWARD", "on_chiki", "а ну чики-брики",
           ("бандити",))
print("OK" if ok else "FAIL")
