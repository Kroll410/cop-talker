"""NPCs only know about deaths and shootings near them or in their own area (A-Life smart terrain)."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker  # noqa: E402

fails = []


def check(name, ok):
    print(("ok  " if ok else "FAIL") + " " + name)
    if not ok:
        fails.append(name)


bar = {"id": 1, "name": "Борода", "x": 0, "z": 0, "place": "zat_stalker_base_smart", "dist": 3}
camp = {"id": 2, "name": "Лоцман", "x": 30, "z": 10, "place": "zat_stalker_base_smart", "dist": 25}
far = {"id": 3, "name": "Кастет", "x": 400, "z": -200, "place": "zat_b18", "dist": 420}
victim_near = {"id": 9, "name": "Бандит", "x": 20, "z": 5, "place": None, "dist": 18}
victim_far = {"id": 8, "name": "Сталкер", "x": 900, "z": 900, "place": "zat_b100", "dist": 1200}

check("near death: man at the bar knows", talker.knows(bar, victim_near))
check("near death: man 400 m away doesn't", not talker.knows(far, victim_near))
check("far death: nobody at the bar knows", not talker.knows(bar, victim_far))
same_area = dict(victim_far, x=None, z=None, place="zat_stalker_base_smart")
check("no positions, same area: knows", talker.knows(camp, same_area))
old = {"id": 5, "dist": 10}
check("old game script: both near the player -> knows", talker.knows(old, {"id": 6, "dist": 20}))
check("old game script: victim far from the player -> doesn't", not talker.knows(old, {"id": 6, "dist": 80}))

g = talker.Game.__new__(talker.Game)
g.recent_events = [(time.time() - 5, {"type": "death", "victim": victim_near, "by_actor": True}),
                   (time.time() - 3, {"type": "death", "victim": victim_far, "killer": {"name": "кровосос"}})]
check("events list for the bar man: only the near death", "Бандит" in g.describe_events(bar)
      and "Сталкер" not in g.describe_events(bar))
check("events list for the far man: nothing", g.describe_events(far) == "nothing notable")
check("no listener: everything (for logs)", "Сталкер" in g.describe_events())
print(f"\n{len(fails)} failed" if fails else "\nall passed")
