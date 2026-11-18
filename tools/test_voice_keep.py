"""An NPC keeps the voice he first spoke with, also when his details come in incomplete or after a restart."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker as t  # noqa: E402

os.environ.update({"VOICE_HUMAN_01": "v1", "VOICE_HUMAN_02": "v2", "VOICE_HUMAN_03": "v3",
                   "VOICE_HUMAN_01_BANDIT": "vb1", "VOICE_HUMAN_03_BANDIT": "vb3"})
t.VOICE_IDS.update({"human_01": "v1", "human_02": "v2", "human_03": "v3"})
t.Voice.VOICES_FILE = Path(tempfile.mkdtemp()) / "npc_voices.json"
BANDIT = r"characters_voice\human_01\bandit" + "\\"
v = t.Voice.__new__(t.Voice)
v.dead = set()
first = v.voice_for({"id": 4, "story_name": "zat_bandit_4", "voice": BANDIT})
later = v.voice_for({"id": 4, "story_name": "zat_bandit_4"})  # an event without his voice details
v2 = t.Voice.__new__(t.Voice)
v2.dead = set()
restart = v2.voice_for({"id": 4, "story_name": "zat_bandit_4"})
v2.dead.add("vb1")  # his clone deleted in ElevenLabs: a new one is picked (and kept from then on)
gone = v2.voice_for({"id": 4, "story_name": "zat_bandit_4", "voice": BANDIT})
print(f"first {first}, later {later}, after restart {restart}, clone deleted -> {gone}")
print("OK" if first == later == restart == "vb1" and gone not in ("vb1", "") else "FAIL")
