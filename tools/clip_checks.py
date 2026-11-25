"""Shared checks for a clip reward («62», «Чики-брики»): a reward the streamer makes on Twitch (the app never creates
it) and picks on the Redeems tab. A redemption goes to the game at once, no Zone queue and no autosave; the game
shouts the clip 7-17 times from all round the player, each copy at its own spot, volume, pitch and delay (one code path,
play_clip, checked in tools/zone_lua.py), and the men around are confused and freaked out. Used by test_sixty_two.py
and test_chiki.py; import it after talker (it needs companion/ on sys.path)."""
import io
import re
from pathlib import Path

import soundfile as sf

import talker
from twitch import Twitch
from redeem_checks import check_redeem

ROOT = Path(__file__).resolve().parent.parent


def check_clip(check, rid, name, base, key, handler, words, react):
    """rid: the redeem id and the Zone event's what; name: the reward's PDA caption; base: the clip's file name
    (sounds\\talker\\<base>[_slow|_fast].ogg); key: its settings.ini key; handler: the Talker method; words: what the
    voice shouts (in the PDA line and the NPCs' prompt); react: words the NPCs' prompt must have."""
    # the clip ships with the mod: Ogg Vorbis (the only kind X-Ray plays), mono (needed for a 3D position), 44.1 kHz
    # in three versions: as recorded, slowed down and sped up (same pitch), each length as the game script has it
    lua = (ROOT / "mod" / "gamedata" / "scripts" / "talker_bridge.script").read_text(encoding="utf-8")
    line = re.search(r'^\s*(?:\["%s"\]|%s) = \{ \{ "talker[^\n]*' % (re.escape(rid), re.escape(rid)), lua, re.M)
    versions = re.findall(r'\{ "talker\\\\(\w+)", ([\d.]+) \}', line.group(0) if line else "")
    check([v[0] for v in versions] == [base, f"{base}_slow", f"{base}_fast"], f"{rid}: three versions in CLIPS: {versions}")
    lengths = {}
    for clip_name, length in versions:
        clip = ROOT / "mod" / "gamedata" / "sounds" / "talker" / f"{clip_name}.ogg"
        info = sf.info(io.BytesIO(clip.read_bytes())) if clip.exists() else None
        check(info and info.format == "OGG" and info.subtype == "VORBIS" and info.channels == 1 and info.samplerate == 44100,
              f"{clip_name}.ogg: mono Ogg Vorbis, 44.1 kHz ({info and (info.format, info.subtype, info.channels, info.samplerate)})")
        check(info and abs(info.duration - float(length)) < 0.05, f"{clip_name}: the script knows its length ({length} s)")
        lengths[clip_name] = info.duration if info else 0
    check(lengths.get(f"{base}_slow", 0) > lengths.get(base, 0) * 1.4 > lengths.get(f"{base}_fast", 0) * 2 > 0,
          f"{rid}: slowed down and sped up for real {lengths}")
    inst = (ROOT / "install_mod.ps1").read_text(encoding="utf-8")
    check('sounds\\talker\\*.ogg' in inst, "install_mod.ps1 copies it with the other talker sounds")

    # Twitch: a redemption of the reward calls its trigger once; other rewards don't
    got = []
    tw = Twitch("id", "", ROOT / "nope.json", lambda *a: None, lambda *a: None, source="chat",
                zone_title="Дар Зони", on_zone=lambda u, ev: got.append(("zone", u)),
                triggers={name: lambda u, ev: got.append((rid, u))})
    red = {"id": "r1", "user_name": "Vasyl", "reward": {"id": "x", "title": name}}
    tw.on_redemption(red)
    tw.on_redemption(red)  # delivered twice by two subscriptions
    tw.on_redemption({"id": "r2", "user_name": "Olia", "reward": {"id": "y", "title": "Дар Зони"}})
    tw.on_redemption({"id": "r3", "user_name": "Ivan", "reward": {"id": "z", "title": name + "0"}})
    check(got == [(rid, "Vasyl"), ("zone", "Olia")], f"{rid}: routed by title, once each: {got}")

    # the helper: at once, straight to the game, not through the Zone queue
    sent = []
    t = talker.Talker.__new__(talker.Talker)
    state = {"mod_version": 15, "actor": {"health": 1}}
    t.game = type("G", (), {"send": lambda self, *x: sent.append(x), "state": lambda self: state})()
    t.zone = type("Q", (), {"add": lambda *a: (_ for _ in ()).throw(AssertionError("queued"))})()
    getattr(t, handler)("Vasyl_77")
    check(len(sent) == 1 and sent[0][0] == "zone" and sent[0][2].startswith(f"{rid}|{name}|Vasyl_77")
          and words in sent[0][2], f"{rid}: sent to the game at once: {sent}")
    check(t.zone_fired.get("kind") == rid, f"{rid}: the game's answer is matched to it (for the reaction)")
    for bad, why in (({"mod_version": 14, "actor": {"health": 1}}, "an old game script"),
                     ({"mod_version": 15, "actor": {"health": 0}}, "player dead")):
        sent.clear()
        state.clear()
        state.update(bad)
        getattr(t, handler)("Vasyl_77")
        check(not sent, f"{rid}: {why}: nothing sent")

    what = talker.Talker.zone_what(t, rid, {})
    check(what and words in what and "confused" in what and "nobody" in what and all(w in what for w in react),
          f"{rid}: the men around are told a voice shouts «{words}» from all round, and to be confused and freaked out")

    # one entry in companion/redeems.py: Twitch routing, the Redeems tab's picker and Test, the helper's test
    # command, and a failed one is given up, not retried like a Zone event
    check_redeem(check, rid, key, handler)

    # the example file has it
    ini = (ROOT / "settings.example.ini").read_text(encoding="utf-8")
    check(re.search(rf"^{key}=$", ini, re.M), f"settings.example.ini has {key} (empty = off)")
    for readme in ("README.md", "README.en.md"):
        text = (ROOT / readme).read_text(encoding="utf-8")
        check(key in text and f"{base}*.ogg" in text, f"{readme} explains it")
