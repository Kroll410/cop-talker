"""Zone event odds by simulation: rolls the real zone.roll() many times (every redemption, all three kinds) and
prints, for each mutant kind and pack size, how often it really came next to the chance the PDA line shows.

    .venv/Scripts/python.exe tools/zone_sim.py [rolls] [pack max]      (default 1000000 rolls, pack max 6)

Each cell is "seen / shown" in % of ALL Zone events. "!" marks a cell where the two differ by more than chance noise
(more than 4 standard errors and 0.02 points)."""
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import zone  # noqa: E402


def simulate(n=1_000_000, pack_max=zone.PACK_MAX, seed=1):
    """{(monster, count): times seen}, {kind: times seen}, and the chance each outcome carried."""
    rng = random.Random(seed)
    seen, kinds, shown = Counter(), Counter(), {}
    for _ in range(n):
        item = zone.roll("v", rng=rng, pack_max=pack_max)
        kinds[item["kind"]] += 1
        if item["kind"] == "child":
            key = (item["monster"], item["count"])
            seen[key] += 1
            shown[key] = item["chance"]
    return seen, kinds, shown


def report(n=1_000_000, pack_max=zone.PACK_MAX):
    seen, kinds, shown = simulate(n, pack_max)
    sizes = range(1, max(zone.most(m[0], pack_max) for m in zone.MONSTERS) + 1)  # тушкан: up to 10
    out = [f"{n} Zone events rolled, pack max {pack_max}: "
           + ", ".join(f"{zone.TITLES[k]} {kinds[k] / n:.1%}" for k, _ in zone.KINDS),
           "Дитя Зони, % of all events, seen / shown in the PDA:",
           f"  {'kind':<14}{'any':>13}" + "".join(f"{'x' + str(c):>15}" for c in sizes)]
    bad = 0
    for name, *_ in zone.MONSTERS:
        cells = []
        for c in sizes:
            p = zone.chance({"kind": "child", "monster": name, "count": c}, pack_max)
            s = seen[(name, c)] / n
            off = abs(s - p) > max(4 * (p * (1 - p) / n) ** 0.5, 0.0002)
            bad += off
            cells.append(f"{zone.pct(s):>7}/{zone.pct(p):<6}{'!' if off else ' '}")
        anyp = sum(zone.chance({"kind": "child", "monster": name, "count": c}, pack_max) for c in sizes)
        anys = sum(seen[(name, c)] for c in sizes) / n
        out.append(f"  {name:<14}{zone.pct(anys):>6}/{zone.pct(anyp):<6}" + "".join(cells))
    total = sum(seen.values())
    out.append("  pack size, share of Дитя Зони: "
               + ", ".join(f"{c}: {sum(v for (m, k), v in seen.items() if k == c) / total:.1%}" for c in sizes))
    out.append("All shown chances match the roll." if not bad else f"{bad} cells differ from the roll!")
    return "\n".join(out), bad


if __name__ == "__main__":
    text, bad = report(int(sys.argv[1]) if len(sys.argv) > 1 else 1_000_000,
                       int(sys.argv[2]) if len(sys.argv) > 2 else zone.PACK_MAX)
    print(text)
    sys.exit(1 if bad else 0)
