"""Reward titles in Settings are picked from the channel's own rewards: an editable list with a Refresh button.
Offline: the Settings tab (offscreen Qt) on a copy of settings.example.ini, the helper's "rewards" answer and
Twitch's reward list with a fake Helix."""
import io
import json
import re
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
    asked, tests = [], []
    tab = app.SettingsTab(lambda: None)
    red = app.RedeemsTab(tab, lambda: asked.append(1) or True, lambda arg: tests.append(arg) or True)
    zone_f, say_f = red.pickers["zone"], red.pickers["speech"]
    check(isinstance(zone_f, QComboBox) and zone_f.isEditable() and tab.fields["TWITCH_ZONE_REWARD"] is zone_f,
          "the Redeems tab's pickers are editable lists, saved with the other settings")
    check(set(red.pickers) == {r.id for r in app.redeems.REDEEMS}, "a row for every redeem in redeems.py")
    check(not any(k in tab.fields and not isinstance(tab.fields[k], app.RewardPicker) for k in
                  [r.key for r in app.redeems.REDEEMS]), "reward titles are no longer plain Settings fields")
    check(tab.value("TWITCH_ZONE_REWARD") == "" and tab.value("TWITCH_REWARD") == "" and zone_f.currentText() == "Off",
          "all start Off: the app makes no reward of its own")
    check(red.states["zone"][1].text() == "Off", "the row says it's off")
    say_f.set_setting_value("Скажи через сталкера")  # as if picked earlier
    red.refresh()
    check(asked == [1] and "Asking" in red.note.text(), "Refresh asks the helper")

    # the helper answers: the window fills every list
    me = types.SimpleNamespace(settings=tab, redeems=red)
    app.Window.handle_report(me, "REWARDS|" + json.dumps(["Hydrate", "Зона", "Скажи через сталкера"]))
    items = [zone_f.itemText(i) for i in range(zone_f.count())]
    check(items == ["Off", "Hydrate", "Зона", "Скажи через сталкера"], f"Zone list: Off + the channel's rewards {items}")
    check(tab.value("TWITCH_REWARD") == "Скажи через сталкера", "the chosen title stays after a refresh")
    check("3 reward" in red.note.text(), f"status: {red.note.text()}")
    zone_f.setCurrentText("Зона")
    check(red.states["zone"][1].text() == "On", "picked: the row says it's on")
    gap = tab.fields["TWITCH_ZONE_GAP"]
    gap.setText("3-4")
    tab.save()
    saved = settings.read_text(encoding="utf-8")
    check("TWITCH_ZONE_REWARD=Зона" in saved and "TWITCH_REWARD=Скажи через сталкера" in saved
          and "TWITCH_ZONE_GAP=3-4" in saved, "picked titles and the Zone gap saved to settings.ini")
    zone_f.setCurrentIndex(0)
    tab.save()
    check(re.search(r"^TWITCH_ZONE_REWARD=$", settings.read_text(encoding="utf-8"), re.M), "Off saves an empty title")
    zone_f.setCurrentText("Зона")
    app.Window.handle_report(me, "REWARDS|" + json.dumps(["Other"]))
    check(tab.value("TWITCH_ZONE_REWARD") == "Зона" and zone_f.findText("Зона") >= 0,
          "a saved title no longer on the channel is kept in the list")
    check("Not on the channel" in red.states["zone"][1].text(), "and the row says to make it on Twitch")
    app.Window.handle_report(me, "REWARDS_ERROR|Twitch: The broadcaster must have partner or affiliate status.")
    check("affiliate" in red.note.text(), "Twitch's refusal is shown on the tab")
    red2 = app.RedeemsTab(app.SettingsTab(lambda: None), lambda: False, lambda arg: False)
    red2.refresh()
    check("Start the helper" in red2.note.text(), "helper not running: says so")
    red2.test("suslov")
    check("Start the helper" in red2.note.text(), "Test without the helper: says so")

    # Test buttons send the registry's ids (the Zone one queues like a real redemption)
    for b in red.findChildren(app.QPushButton):
        if b.text() == "Test":
            b.click()
    check(tests == ["speech", "redeem"] + [r.id for r in app.redeems.TRIGGERS], f"Test buttons send {tests}")

    # a setting changed by hand in the file while the window was open is kept by Save
    text = settings.read_text(encoding="utf-8").replace("PLAYER_NAME=", "PLAYER_NAME=Бродяга")
    settings.write_text(text, encoding="utf-8")
    red.pickers["suslov"].set_setting_value("Шари")
    tab.save()
    saved = settings.read_text(encoding="utf-8")
    check("PLAYER_NAME=Бродяга" in saved and "TWITCH_SUSLOV_REWARD=Шари" in saved, "Save merges with the file on disk")

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
    check(lines == ['@REWARDS|["A", "Зона"]', "@REWARDS_ERROR|Twitch is off (TWITCH_ENABLED, "
                    "TWITCH_CLIENT_ID)"], f"helper answers {lines}")

    # the app never adds (or deletes) a reward on the channel: only reads them and subscribes to redemptions
    calls = []

    def fake_helix(method, path, **kw):
        calls.append((method, path))
        if method == "GET":
            return types.SimpleNamespace(status_code=200, json=lambda: {"data": [{"id": "h", "title": "Hydrate"}]},
                                         text="")
        return types.SimpleNamespace(status_code=202, json=lambda: {}, text="")

    logs = []
    for source in ("reward", "chat"):
        tw = Twitch("id", "Мій редім", tmp / "tok.json", lambda *a: None, logs.append, source=source,
                    zone_title="Зона", on_zone=lambda *a: None)
        tw.user_id, tw.channel_id, tw.helix = "42", "42", fake_helix
        tw.find_reward()
        tw.find_zone_reward()
        tw.list_rewards()
        tw.subscribe("session")
    tw2 = Twitch("id", "", tmp / "tok.json", lambda *a: None, logs.append, source="reward")
    tw2.user_id, tw2.helix = "42", fake_helix
    tw2.find_reward()
    tw2.subscribe("session")
    reward_writes = [c for c in calls if c[1].startswith("/channel_points/custom_rewards") and c[0] != "GET"
                     and not c[1].endswith("/redemptions")]
    check(calls and not reward_writes, f"no reward is ever created or deleted ({len(calls)} calls, writes: {reward_writes})")
    check(any("no reward «Мій редім»" in m and "create it on Twitch" in m for m in logs)
          and any("no reward «Зона»" in m for m in logs), "a missing reward is named, to make by hand on Twitch")
    src = "".join((ROOT / "companion" / f).read_text(encoding="utf-8") for f in ("twitch.py", "talker.py", "app.py"))
    check(not re.search(r'"(POST|DELETE|PUT)",\s*"/channel_points/custom_rewards"', src),
          "the code has no call that adds or deletes a reward")
    check("delete_reward" not in src and "APP_REWARDS" not in src, "no Delete button or its code is left")
    spoken = []
    tw = Twitch("id", "Мій редім", tmp / "tok.json", lambda u, t, r: spoken.append(t), logs.append, source="reward")
    tw.user_id, tw.helix = "42", fake_helix
    tw.find_reward()
    tw.on_redemption({"id": "1", "user_name": "A", "reward": {"id": "q", "title": "мій редім"}, "user_input": "$hi"})
    tw.on_redemption({"id": "2", "user_name": "B", "reward": {"id": "w", "title": "Hydrate"}, "user_input": "$no"})
    check(spoken == ["$hi"], f"made on Twitch later: matched by its title, other rewards ignored {spoken}")
    tw2.on_message = lambda u, t, r: spoken.append(t)
    tw2.on_redemption({"id": "3", "user_name": "C", "reward": {"id": "w", "title": "Hydrate"}, "user_input": "$x"})
    check(spoken == ["$hi"], "no speech reward set: no reward is spoken")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("OK" if ok else "FAIL")
