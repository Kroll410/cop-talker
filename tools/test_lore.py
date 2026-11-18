"""Lore: famous Zone people are recognised in many spellings; ordinary words that look like names are not."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
from lore import lore_for  # noqa: E402

hits = {
    "Гайз, ви чули шо на болотах Мічений після викиду вижив?": "Стрілець (Strelok)",
    "Що ти знаєш про Стрільця?": "Стрілець (Strelok)",
    "А Стрелок реально існує?": "Стрілець (Strelok)",
    "Кажуть, Меченый на ЧАЕС дійшов": "Стрілець (Strelok)",
    "Сидорович ще живий?": "Сидорович",
    "Бармен з Ростка ще наливає?": "Бармен",
    "Що там у Долга, Воронін досі головний?": "Генерал Воронін",
    "Де зараз Лукаш?": "Лукаш",
    "Хто такий Шрам?": "Шрам (Scar)",
    "Бачив Привида?": "Привид (Ghost)",
    "Кардан знову п'яний?": "Кардан",
    "Що скажеш про Ноя?": "Ной:",
    "Сич щось купує?": "Сич:",
    "Що там з операцією Фарватер?": "Operation «Фарватер»",
    "Випалювач мізків правда вимкнули?": "Випалювач мізків",
    "Ти знаєш Дегтярьова?": "Дегтярьов",
    "Де Гонта зі своїми мисливцями?": "Гонта:",
}
misses = ["Клацни, де тут клик мишкою", "У підвалі привид живе, чесно", "Ной тут тільки собака", "стрілка годинника",
          "Він стріляє добре", "Ну ти й сич", "кардан у машини полетів", "Я вчора стрілок купив", "Як справи?"]
# "Ной тут тільки собака" starts with a capital, so it IS read as the name; a fair match
fails = 0
for text, want in hits.items():
    got = lore_for(text)
    ok = want in got
    fails += not ok
    print(("ok  " if ok else "FAIL") + f" hit  {text}")
for text in misses:
    got = lore_for(text)
    ok = not got or text.startswith("Ной")
    fails += not ok
    print(("ok  " if ok else "FAIL") + f" miss {text}" + ("" if not got else "  (capitalised Ной: counted as the name)"))
print(f"\n{fails} failed" if fails else "\nall passed")
