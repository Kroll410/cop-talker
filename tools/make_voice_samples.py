"""Build voice-cloning samples from the game's Ukrainian voiceover.

For each generic stalker voice (human_01/02/03) it takes calm dialogue lines
(talk/ states folders, stalker faction first), decodes them, and writes one
~2.5 minute WAV per voice into samples/, ready to upload to ElevenLabs.

Usage: python make_voice_samples.py <xukrainian.db> <out_dir>
"""
import io
import os
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(__file__))
import xdb_unpack as x  # noqa: E402

# (output name, voice actor folder, faction folder). Faction sets that are identical
# recordings in the game (freedom/military of human_01 and human_02) are cloned once.
SETS = [
    ("human_01", "human_01", "stalker"), ("human_02", "human_02", "stalker"), ("human_03", "human_03", "stalker"),
    ("human_01_bandit", "human_01", "bandit"), ("human_02_bandit", "human_02", "bandit"),
    ("human_03_bandit", "human_03", "bandit"),
    ("freedom_a", "human_01", "freedom"), ("freedom_b", "human_03", "freedom"),
    ("military_a", "human_01", "military"), ("military_b", "human_03", "military"),
    # Monolith exists only in the Russian voiceover (Localization\base_sounds.db) and is one actor for all
    ("monolith", "human_01", "monolith"),
]
SHARED_OK = {"monolith"}  # sets allowed to use recordings shared between actors
# Calm speech first; fight/threat lines are shouting and make a worse clone.
KINDS = ["talk", "states", "help", "reactions", "alife", "threat", "fight"]
TARGET_SECONDS = 150
RATE = 44100


def main():
    archive, out_dir = sys.argv[1:3]
    os.makedirs(out_dir, exist_ok=True)
    data = open(archive, "rb").read()
    entries = list(x.list_files(x.read_chunks(data)[1]))

    import hashlib
    # Some lines are the very same recording for every actor (e.g. Monolith prayers): count who has each
    # recording so a sample only uses lines unique to its actor.
    owners = {}
    for name, size_real, size_compr, offset in entries:
        p = name.lower().split("\\")
        if len(p) > 4 and p[1] == "characters_voice" and p[2].startswith("human") and name.lower().endswith(".ogg"):
            h = hashlib.md5(data[offset:offset + size_compr]).hexdigest()
            owners.setdefault((p[3], h), set()).add(p[2])

    only = sys.argv[3:]  # optional: build just these sets
    for out_name, voice, faction in SETS:
        if only and out_name not in only:
            continue
        chosen = []
        for kind in KINDS:
            prefix = f"sounds\\characters_voice\\{voice}\\{faction}\\{kind}\\"
            files = [e for e in entries if e[0].lower().startswith(prefix) and e[0].lower().endswith(".ogg")
                     and (out_name in SHARED_OK or
                          owners.get((faction, hashlib.md5(data[e[3]:e[3] + e[2]]).hexdigest()), {voice}) == {voice})]
            files.sort(key=lambda e: -e[1])  # longest lines first
            chosen.extend(files)

        parts, total = [], 0.0
        gap = np.zeros(int(RATE * 0.4), dtype=np.float32)
        for name, size_real, size_compr, offset in chosen:
            raw = data[offset:offset + size_compr]
            body = raw if size_real == size_compr else x.lzo1x_decompress(raw, size_real)
            try:
                audio, rate = sf.read(io.BytesIO(body), dtype="float32", always_2d=True)
            except Exception:
                continue
            audio = audio.mean(axis=1)
            if rate != RATE:
                idx = np.linspace(0, len(audio) - 1, int(len(audio) * RATE / rate))
                audio = np.interp(idx, np.arange(len(audio)), audio).astype(np.float32)
            dur = len(audio) / RATE
            if dur < 1.5:
                continue
            parts += [audio, gap]
            total += dur
            if total >= TARGET_SECONDS:
                break

        mix = np.concatenate(parts)
        peak = float(np.max(np.abs(mix))) or 1.0
        mix = mix / peak * 0.9
        dest = os.path.join(out_dir, f"{out_name}_{'rus' if faction == 'monolith' else 'ukr'}.mp3")
        sf.write(dest, mix, RATE, format="MP3", bitrate_mode="CONSTANT", compression_level=0.0)
        print(f"{dest}: {total:.0f}s from {len(parts)//2} lines")


if __name__ == "__main__":
    main()
