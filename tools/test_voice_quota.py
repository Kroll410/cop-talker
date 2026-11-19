"""ElevenLabs credits used up (401 "quota_exceeded"): the first line notices it, then for 10 minutes every line
goes out as text at once, with no more API calls, retries or waiting; other voice errors still retry."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker  # noqa: E402

ok = True


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    return cond


class ApiError(Exception):
    def __init__(self, status, body):
        super().__init__(str(body))
        self.status_code, self.body = status, body


calls = []


class FakeTTS:
    def __init__(self, error):
        self.error = error

    def stream(self, voice_id, **kw):
        calls.append("stream")
        raise self.error

    def convert(self, voice_id, **kw):
        calls.append("convert")
        raise self.error


def voice_with(error):
    v = talker.Voice.__new__(talker.Voice)
    v.client = type("C", (), {"text_to_speech": FakeTTS(error)})()
    v.voice_for = lambda npc: "voice_x"
    v.dead = set()
    import threading
    v.lock = threading.Lock()
    return v


talker.time.sleep = lambda s: None  # no real pauses between retries in the test
npc = {"id": 1, "name": "Вовк", "community": "stalker"}
quota = ApiError(401, {"detail": {"status": "quota_exceeded", "message": "This request exceeds your quota"}})
v = voice_with(quota)
shown = []
start = time.time()
for i in range(3):
    v.say(npc, f"Репліка {i}.", on_start=lambda i=i: shown.append(i))
ok &= check(shown == [0, 1, 2], f"every line still shows its subtitle: {shown}")
ok &= check(len(calls) == 1,
            f"credits used up: asked ElevenLabs once, then not again ({calls})")
ok &= check(time.time() - start < 5, "no waiting on the lines after it")

calls.clear()
v = voice_with(ApiError(503, {"detail": "busy"}))
shown.clear()
v.say(npc, "Ще раз.", on_start=lambda: shown.append(1))
ok &= check(calls.count("convert") == 2 and shown == [1], f"a busy server is still retried ({calls})")
print("OK" if ok else "FAIL")
