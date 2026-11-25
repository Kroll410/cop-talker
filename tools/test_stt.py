"""Compare speech recognition on short Ukrainian game voice lines: local Whisper vs Gemini."""
import io
import os
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "companion"))
sys.path.insert(0, str(ROOT / "tools"))
import talker  # noqa: E402
import xdb_unpack as x  # noqa: E402

if len(sys.argv) < 2:  # a manual tool: needs the voice archive
    print("usage: python tools/test_stt.py <xukrainian.db>  (skipped: no archive given)")
    sys.exit(0)
archive = sys.argv[1]
data = open(archive, "rb").read()
lines = []
for name, size_real, size_compr, offset in x.list_files(x.read_chunks(data)[1]):
    low = name.lower()
    if "\\stalker\\talk\\" in low or "\\stalker\\help\\" in low or "\\bandit\\talk\\" in low:
        if 40_000 < size_real < 120_000 and low.endswith(".ogg"):
            lines.append((name, size_real, size_compr, offset))
lines = lines[::max(1, len(lines) // 6)][:6]

os.environ["STT_PROVIDER"] = "gemini"
ears = talker.Ears.__new__(talker.Ears)
ears.model = None
talker.Ears.__init__(ears)
out = open(ROOT / "test_result.txt", "w", encoding="utf-8")
for name, size_real, size_compr, offset in lines:
    raw = data[offset:offset + size_compr]
    body = raw if size_real == size_compr else x.lzo1x_decompress(raw, size_real)
    audio, rate = sf.read(io.BytesIO(body), dtype="float32", always_2d=True)
    audio = audio.mean(axis=1)
    idx = np.linspace(0, len(audio) - 1, int(len(audio) * 16000 / rate))
    audio = np.interp(idx, np.arange(len(audio)), audio).astype(np.float32)
    out.write(f"{name.split(chr(92))[-1]} ({len(audio) / 16000:.1f}s)\n")
    t = time.time()
    segs, _ = ears.load_local().transcribe(audio, language="uk", beam_size=5, vad_filter=True)
    text = " ".join(s.text.strip() for s in segs)  # segments are lazy: time the full decode
    out.write(f"  {talker.WHISPER_MODEL} {time.time() - t:.1f}s: {text}\n")
    t = time.time()
    try:
        text = ears.transcribe_gemini(audio)
        out.write(f"  gemini {time.time() - t:.1f}s: {text}\n")
    except Exception as exc:
        out.write(f"  gemini FAIL: {str(exc)[:100]}\n")
    out.flush()
out.close()
