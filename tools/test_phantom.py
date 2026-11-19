"""An NPC offering goods he doesn't carry is asked again (one more LLM call, seconds of silence). Pointing the
player at someone else's goods ("В Бороди є тушонка, бери там") is not such an offer."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker  # noqa: E402

CASES = [("В Бороди є тушонка і хліб, бери там.", False), ("У Сича є патрони, тільки дорого.", False),
         ("У нього є горілка, 200 купонів.", False), ("В Скадовську є хліб, ціна нормальна.", False),
         ("Є пляшка горілки, 600 купонів.", True), ("У мене є тушонка, бери за сотню.", True),
         ("Тримай хліб, сто купонів.", True), ("Там у мене є аптечка, віддам за триста.", True),
         ("Маю горілку, тільки сто купонів.", True)]
ok = True
for line, want in CASES:
    got = bool(talker.phantom_items(line, []))
    ok &= got == want
    print(("ok   " if got == want else "FAIL ") + f"{line}  (his own offer: {got})")
print("OK" if ok else "FAIL")
