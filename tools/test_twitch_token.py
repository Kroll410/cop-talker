"""Twitch sign-in survives restarts: atomic save, a refused renewal falls back to a key another run saved,
and the helper quits only after a renewal under way has been saved."""
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import twitch  # noqa: E402

fails = []


def check(name, ok):
    print(("ok  " if ok else "FAIL") + " " + name)
    if not ok:
        fails.append(name)


class Resp:
    def __init__(self, code, data=None):
        self.status_code, self._data, self.text = code, data or {}, json.dumps(data or {})

    def json(self):
        return self._data


d = Path(tempfile.mkdtemp())
tw = twitch.Twitch("cid", "", d / "twitch_token.json", lambda *a: None, lambda m: None, source="chat")
tw.token = {"access_token": "a1", "refresh_token": "r1"}
tw.save_token()
check("saved in one go, no temp file left", (d / "twitch_token.json").exists() and not (d / "twitch_token.tmp").exists())

tw.http = type("H", (), {"post": lambda self, url, data: Resp(200, {"access_token": "a2", "refresh_token": "r2"})})()
check("renewal OK -> new key saved", tw.refresh() and json.loads((d / "twitch_token.json").read_text())["refresh_token"] == "r2")

# another run renewed it meanwhile (r2 -> r3 on disk); our old r2 is refused -> we pick up r3, no new sign-in
(d / "twitch_token.json").write_text(json.dumps({"access_token": "a3", "refresh_token": "r3"}))
tw.token = {"access_token": "a2", "refresh_token": "r2"}
tw.http = type("H", (), {"post": lambda self, url, data: Resp(400, {"message": "Invalid refresh token"})})()
check("refused, but another run saved a newer key -> use it", tw.refresh() and tw.token["refresh_token"] == "r3")
check("refused and nothing newer -> sign in again", not tw.refresh())

# graceful quit: the helper waits for a renewal under way before exiting
child = r'''
import sys, threading, time
sys.path.insert(0, "companion")
import talker
t = talker.Talker.__new__(talker.Talker)
t.twitch = type("T", (), {"auth_lock": threading.Lock()})()
t.twitch.auth_lock.acquire()
def renew():
    time.sleep(2)  # a renewal in progress
    print("renewal saved", flush=True)
    t.twitch.auth_lock.release()
threading.Thread(target=renew).start()
t.watch_for_quit()
print("ready", flush=True)
time.sleep(30)
'''
p = subprocess.Popen([sys.executable, "-u", "-c", child], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                     stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                     cwd=str(Path(__file__).resolve().parent.parent))
while "ready" not in p.stdout.readline():
    pass
start = time.time()
p.stdin.write("quit\n")
p.stdin.flush()
out = p.stdout.read()
p.wait(10)
took = time.time() - start
check(f"quit waited for the renewal to be saved ({took:.1f}s), exit code {p.returncode}",
      "renewal saved" in out and out.index("renewal saved") < out.index("helper quitting") and p.returncode == 0)
print(f"\n{len(fails)} failed" if fails else "\nall passed")
