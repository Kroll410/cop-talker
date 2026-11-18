"""Play a tone while the 'NPC' walks from 2 m to 30 m away: the volume must fade during playback."""
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker  # noqa: E402

v = talker.Voice.__new__(talker.Voice)
t = np.arange(int(22050 * 4)) / 22050
tone = (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
start = time.time()


def dist():
    return 2 + (time.time() - start) * 7  # walking away 7 m/s


for d in (2, 5, 10, 20, 30):
    print(f"{d:>2} m -> {talker.distance_volume(d) / talker.NPC_VOLUME * 100:.0f}%")
src = talker.PcmSource()
src.feed((tone * 32767).astype(np.int16).tobytes())
src.close()
v.play_spatial(src, {"dist": 2}, dist)
print(f"played 4 s, distance went 2 -> {dist():.0f} m, ok")
