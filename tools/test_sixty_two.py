"""«62»: a reward the streamer makes on Twitch (the app never creates it) and picks in Settings. A redemption goes to
the game at once, no Zone queue and no autosave; the game shouts the streamer's clip «шиісят два» 10 times from all
round the player, each copy at its own spot, volume, pitch and delay (checked in tools/zone_lua.py), and the men
around are confused and freaked out."""
import io
import re
import sys
from pathlib import Path

import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "companion"))
import talker  # noqa: E402
from twitch import Twitch  # noqa: E402

ok = True


def check(cond, what):
    global ok
    ok &= bool(cond)
    print(("ok   " if cond else "FAIL ") + what)


# the clip ships with the mod: Ogg Vorbis (the only kind X-Ray plays), mono (needed for a 3D position), 44.1 kHz
# in three versions: as recorded, slowed down and sped up (same pitch), each length as the game script has it
lua = (ROOT / "mod" / "gamedata" / "scripts" / "talker_bridge.script").read_text(encoding="utf-8")
versions = re.findall(r'\{ "talker\\\\(sixty_two\w*)", ([\d.]+) \}', re.search(r"SIXTY_TWO_SOUNDS = [^\n]*", lua).group(0))
check([v[0] for v in versions] == ["sixty_two", "sixty_two_slow", "sixty_two_fast"], f"three versions: {versions}")
lengths = {}
for name, length in versions:
    clip = ROOT / "mod" / "gamedata" / "sounds" / "talker" / f"{name}.ogg"
    info = sf.info(io.BytesIO(clip.read_bytes())) if clip.exists() else None
    check(info and info.format == "OGG" and info.subtype == "VORBIS" and info.channels == 1 and info.samplerate == 44100,
          f"{name}.ogg: mono Ogg Vorbis, 44.1 kHz ({info and (info.format, info.subtype, info.channels, info.samplerate)})")
    check(info and abs(info.duration - float(length)) < 0.05, f"{name}: the script knows its length ({length} s)")
    lengths[name] = info.duration if info else 0
check(lengths["sixty_two_slow"] > lengths["sixty_two"] * 1.4 > lengths["sixty_two_fast"] * 2,
      f"slowed down and sped up for real {lengths}")
inst = (ROOT / "install_mod.ps1").read_text(encoding="utf-8")
check('sounds\\talker\\*.ogg' in inst, "install_mod.ps1 copies it with the other talker sounds")

# Twitch: a redemption of the «62» reward calls its trigger once; other rewards don't
got = []
tw = Twitch("id", "", ROOT / "nope.json", lambda *a: None, lambda *a: None, source="chat",
            zone_title="Дар Зони", on_zone=lambda u, ev: got.append(("zone", u)),
            triggers={"62": lambda u, ev: got.append(("62", u))})
red = {"id": "r1", "user_name": "Vasyl", "reward": {"id": "x", "title": "62"}}
tw.on_redemption(red)
tw.on_redemption(red)  # delivered twice by two subscriptions
tw.on_redemption({"id": "r2", "user_name": "Olia", "reward": {"id": "y", "title": "Дар Зони"}})
tw.on_redemption({"id": "r3", "user_name": "Ivan", "reward": {"id": "z", "title": "620"}})
check(got == [("62", "Vasyl"), ("zone", "Olia")], f"routed by title, once each: {got}")

# the helper: at once, straight to the game, not through the Zone queue
sent = []
t = talker.Talker.__new__(talker.Talker)
state = {"mod_version": 15, "actor": {"health": 1}}
t.game = type("G", (), {"send": lambda self, *x: sent.append(x), "state": lambda self: state})()
t.zone = type("Q", (), {"add": lambda *a: (_ for _ in ()).throw(AssertionError("queued"))})()
t.on_sixty_two("Vasyl_77")
check(len(sent) == 1 and sent[0][0] == "zone" and sent[0][2].startswith("62|62|Vasyl_77"), f"sent to the game at once: {sent}")
check(t.zone_fired.get("kind") == "62", "the game's answer is matched to it (for the reaction)")
for bad, why in (({"mod_version": 14, "actor": {"health": 1}}, "an old game script"),
                 ({"mod_version": 15, "actor": {"health": 0}}, "player dead")):
    sent.clear()
    state.clear()
    state.update(bad)
    t.on_sixty_two("Vasyl_77")
    check(not sent, f"{why}: nothing sent")

what = talker.Talker.zone_what(t, "62", {})
check("шиісят два" in what and "confused" in what and "nobody" in what,
      "the men around are told a voice shouts «шиісят два» from all round, and to be confused and freaked out")

# a failed one is given up, not retried like a Zone event
src = (ROOT / "companion" / "talker.py").read_text(encoding="utf-8")
check(re.search(r'not in \([^)]*"62"\) and self\.zone\.retry', src), "a failed «62» isn't retried")
check('TWITCH_62_REWARD, self.on_sixty_two' in src and 'arg == "62"' in src, "wired to Twitch and the test button")

# settings: the window names it and offers the channel's rewards for it; the example file has it
app = (ROOT / "companion" / "app.py").read_text(encoding="utf-8")
pick = re.search(r"REWARD_PICK = \{([^}]*)\}", app).group(1)
check('"TWITCH_62_REWARD": "«62» reward"' in app and '"TWITCH_62_REWARD"' in pick, "Settings: a label and a reward picker")
check('("62", "62",' in app, "Twitch tab: a «62» test button")
ini = (ROOT / "settings.example.ini").read_text(encoding="utf-8")
check(re.search(r"^TWITCH_62_REWARD=$", ini, re.M), "settings.example.ini has TWITCH_62_REWARD (empty = off)")
for readme in ("README.md", "README.en.md"):
    check("TWITCH_62_REWARD" in (ROOT / readme).read_text(encoding="utf-8"), f"{readme} explains it")
print("OK" if ok else "FAIL")
