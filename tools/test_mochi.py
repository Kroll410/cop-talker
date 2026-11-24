"""«Мочии»: a clip reward like «62» and «Чики-брики» (one code path, play_clip, checked in tools/zone_lua.py), but the
clip is the game's own zombified stalker groaning «Мочи...» (sounds\\characters_voice\\human_01\\zombied\\fight\\attack\\
script_attack_5.ogg in base_sounds.db, which every copy of the game has), so the mod ships no file for it: one
version, the copies told apart by pitch alone (sound_object.frequency, settable from script in OpenXRay)."""
import io
import re
import sys
from pathlib import Path

import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "companion"))
sys.path.insert(0, str(ROOT / "tools"))
import talker  # noqa: E402
from twitch import Twitch  # noqa: E402
from redeem_checks import check_redeem  # noqa: E402

ok = True


def check(cond, what):
    global ok
    ok &= bool(cond)
    print(("ok   " if cond else "FAIL ") + what)


RID, NAME, KEY, HANDLER = "mochi", "Мочии", "TWITCH_MOCHI_REWARD", "on_mochi"
GAME_SOUND = "characters_voice\\human_01\\zombied\\fight\\attack\\script_attack_5"

# the game script: one line in CLIPS, the game's own sound path, its length as the game has it
lua = (ROOT / "mod" / "gamedata" / "scripts" / "talker_bridge.script").read_text(encoding="utf-8")
line = re.search(r'^\s*mochi = \{[^\n]*', lua, re.M)
versions = re.findall(r'\{ "([^"]+)", ([\d.]+) \}', line.group(0) if line else "")
check([v[0] for v in versions] == [GAME_SOUND.replace("\\", "\\\\")], f"CLIPS.mochi: the game's own sound, one version {versions}")
length = float(versions[0][1]) if versions else 0
check(abs(length - 2.11) < 0.05, f"the script knows its length ({length} s)")
check(not list((ROOT / "mod" / "gamedata" / "sounds").rglob("*script_attack*")), "the mod ships no copy of the game's sound")
# the copy the streamer pulled from base_sounds.db (only on their machine): mono for 3D, and the length matches
copy = Path.home() / "Downloads" / "zombie_voices" / "human_01_attack_script_attack_5.ogg"
if copy.exists():
    info = sf.info(io.BytesIO(copy.read_bytes()))
    check(info.channels == 1 and info.samplerate == 44100 and abs(info.duration - length) < 0.05,
          f"the game's file: mono 44.1 kHz, {info.duration:.2f} s")
else:
    print("skip the game's file isn't extracted on this machine (Downloads\\zombie_voices)")

# Twitch: a redemption of the reward calls its trigger once; other rewards don't
got = []
tw = Twitch("id", "", ROOT / "nope.json", lambda *a: None, lambda *a: None, source="chat",
            zone_title="Дар Зони", on_zone=lambda u, ev: got.append(("zone", u)),
            triggers={NAME: lambda u, ev: got.append((RID, u))})
red = {"id": "r1", "user_name": "Vasyl", "reward": {"id": "x", "title": NAME}}
tw.on_redemption(red)
tw.on_redemption(red)  # delivered twice by two subscriptions
tw.on_redemption({"id": "r2", "user_name": "Olia", "reward": {"id": "y", "title": "Дар Зони"}})
tw.on_redemption({"id": "r3", "user_name": "Ivan", "reward": {"id": "z", "title": "Мочи"}})
check(got == [(RID, "Vasyl"), ("zone", "Olia")], f"routed by title, once each: {got}")

# the handler: at once, straight to the game, not through the Zone queue
sent = []
t = talker.Talker.__new__(talker.Talker)
state = {"mod_version": 15, "actor": {"health": 1}}
t.game = type("G", (), {"send": lambda self, *x: sent.append(x), "state": lambda self: state})()
t.zone = type("Q", (), {"add": lambda *a: (_ for _ in ()).throw(AssertionError("queued"))})()
getattr(t, HANDLER)("Vasyl_77")
check(len(sent) == 1 and sent[0][0] == "zone" and sent[0][2].startswith(f"{RID}|{NAME}|Vasyl_77")
      and "мочи" in sent[0][2], f"sent to the game at once: {sent}")
check(t.zone_fired.get("kind") == RID, "the game's answer is matched to it (for the reaction)")
for bad, why in (({"mod_version": 14, "actor": {"health": 1}}, "an old game script"),
                 ({"mod_version": 15, "actor": {"health": 0}}, "player dead")):
    sent.clear()
    state.clear()
    state.update(bad)
    getattr(t, HANDLER)("Vasyl_77")
    check(not sent, f"{why}: nothing sent")

what = talker.Talker.zone_what(t, RID, {})
check(what and "Мочи" in what and "zombie" in what and "nobody" in what and "confused" in what and "gun" in what,
      "the men around hear a zombie's «Мочи» from all round, are spooked and grab their guns")

# one entry in companion/redeems.py: Twitch routing, the Redeems tab, the helper's test command, never retried
check_redeem(check, RID, KEY, HANDLER)

ini = (ROOT / "settings.example.ini").read_text(encoding="utf-8")
check(re.search(rf"^{KEY}=$", ini, re.M), f"settings.example.ini has {KEY} (empty = off)")
for readme in ("README.md", "README.en.md"):
    text = (ROOT / readme).read_text(encoding="utf-8")
    check(KEY in text and "script_attack_5" in text, f"{readme} explains it")
print("OK" if ok else "FAIL")
