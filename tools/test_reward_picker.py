"""Reward titles in Settings are picked from the channel's own rewards: an editable list with a Refresh button.
Offline: the Settings tab (offscreen Qt) on a copy of settings.example.ini, the helper's "rewards" answer and
Twitch's reward list with a fake Helix."""
import io
import json
import os
import shutil
import sys
import tempfile
import types
from contextlib import redirect_stdout
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "companion"))
import app  # noqa: E402
import talker  # noqa: E402
from PySide6.QtWidgets import QApplication, QComboBox  # noqa: E402
from twitch import Twitch  # noqa: E402

ok = True


def check(cond, what):
    global ok
    ok &= bool(cond)
    print(("ok   " if cond else "FAIL ") + what)


tmp = Path(tempfile.mkdtemp())
try:
    qt = QApplication.instance() or QApplication([])
    settings = tmp / "settings.ini"
    shutil.copy(ROOT / "settings.example.ini", settings)
    app.SETTINGS = settings
    asked = []
    tab = app.SettingsTab(lambda: None, lambda: asked.append(1) or True)
    zone_f, say_f = tab.fields["TWITCH_ZONE_REWARD"], tab.fields["TWITCH_REWARD"]
    check(isinstance(zone_f, QComboBox) and zone_f.isEditable() and isinstance(say_f, QComboBox),
          "both reward titles are editable lists")
    check(tab.value("TWITCH_ZONE_REWARD") == "" and tab.value("TWITCH_REWARD") == "Скажи через сталкера",
          "they start with the saved titles")
    tab.refresh_rewards()
    check(asked == [1] and "asking" in tab.reward_notes[0].text(), "Refresh asks the helper")

    # the helper answers: the window fills both lists
    me = types.SimpleNamespace(settings=tab)
    app.Window.handle_report(me, "REWARDS|" + json.dumps(["Hydrate", "Зона", "Скажи через сталкера"]))
    items = [zone_f.itemText(i) for i in range(zone_f.count())]
    check(items == ["", "Hydrate", "Зона", "Скажи через сталкера"], f"Zone list: off + the channel's rewards {items}")
    check(tab.value("TWITCH_REWARD") == "Скажи через сталкера", "the chosen title stays after a refresh")
    check("3 reward" in tab.reward_notes[0].text(), f"status: {tab.reward_notes[0].text()}")
    zone_f.setCurrentText("Зона")
    tab.save()
    saved = settings.read_text(encoding="utf-8")
    check("TWITCH_ZONE_REWARD=Зона" in saved and "TWITCH_REWARD=Скажи через сталкера" in saved,
          "picked title saved to settings.ini")
    app.Window.handle_report(me, "REWARDS|" + json.dumps(["Other"]))
    check(tab.value("TWITCH_ZONE_REWARD") == "Зона" and zone_f.findText("Зона") >= 0,
          "a saved title no longer on the channel is kept in the list")
    app.Window.handle_report(me, "REWARDS_ERROR|Twitch: The broadcaster must have partner or affiliate status.")
    check("affiliate" in tab.reward_notes[1].text(), "Twitch's refusal is shown next to the list")
    tab2 = app.SettingsTab(lambda: None, lambda: False)
    tab2.refresh_rewards()
    check("start the helper" in tab2.reward_notes[0].text(), "helper not running: says so")

    # Twitch: the list, and its refusal
    tw = Twitch("id", "Скажи", tmp / "tok.json", lambda *a: None, lambda m: None, source="chat")
    try:
        tw.list_rewards()
        check(False, "not signed in: refused")
    except RuntimeError:
        check(True, "not signed in: refused")
    tw.user_id = "42"
    resp = types.SimpleNamespace(status_code=200, json=lambda: {"data": [{"title": "A"}, {"title": "Зона"}]}, text="")
    tw.helix = lambda method, path, **kw: resp
    check(tw.list_rewards() == ["A", "Зона"], "Twitch: titles of all the channel's rewards")
    tw.helix = lambda method, path, **kw: types.SimpleNamespace(
        status_code=403, json=lambda: {"message": "The broadcaster must have partner or affiliate status."}, text="")
    try:
        tw.list_rewards()
        check(False, "403 becomes a readable error")
    except RuntimeError as exc:
        check("affiliate" in str(exc), f"403 becomes a readable error: {exc}")

    # the helper's side: "rewards" -> @REWARDS / @REWARDS_ERROR
    t = talker.Talker.__new__(talker.Talker)
    t.twitch = types.SimpleNamespace(list_rewards=lambda: ["A", "Зона"])
    out = io.StringIO()
    with redirect_stdout(out):
        t.report_rewards()
        t.twitch = None
        t.report_rewards()
    lines = out.getvalue().splitlines()
    check(lines[0] == '@REWARDS|["A", "Зона"]' and lines[1].startswith("@REWARDS_ERROR|"), f"helper answers {lines}")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("OK" if ok else "FAIL")
