"""Time each Gemini Flash model on the same prompt and show why a reply was empty."""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker  # noqa: E402
from google import genai  # noqa: E402
from google.genai import types  # noqa: E402

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"],
                      http_options=types.HttpOptions(timeout=20000, retry_options=types.HttpRetryOptions(attempts=1)))
prompt = ("NPC you voice: Толік Шпана, бандит, rude. Swearing allowed: heavy.\n"
          "The player now says to you: Слухай, пропусти мене, мені треба на той бік.")
out = open(Path(__file__).resolve().parent.parent / "probe_result.txt", "w", encoding="utf-8")
for model in ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-2.5-flash", "gemini-2.5-flash-lite"]:
    t = time.time()
    try:
        r = client.models.generate_content(model=model, contents=prompt, config=types.GenerateContentConfig(
            system_instruction=talker.SYSTEM_PROMPT, max_output_tokens=2000,
            safety_settings=[types.SafetySetting(category=c, threshold="BLOCK_NONE") for c in (
                "HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH", "HARM_CATEGORY_DANGEROUS_CONTENT")]))
        cand = r.candidates[0] if r.candidates else None
        out.write(f"{model}: {time.time() - t:.1f}s finish={cand.finish_reason if cand else None} "
                  f"block={r.prompt_feedback} text={r.text!r}\n")
    except Exception as exc:
        out.write(f"{model}: {time.time() - t:.1f}s ERROR {str(exc)[:120]}\n")
    out.flush()
out.close()
