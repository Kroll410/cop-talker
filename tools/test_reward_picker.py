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
    check(tab.value("TWITCH_ZONE_REWARD") == "" and tab.value("TWITCH_REWARD") == "",
          "both start empty: the app makes no reward of its own")
    say_f.setCurrentText("Скажи через сталкера")  # as if picked earlier
    tab.refresh_rewards()
    check(asked == [1] and "asking" in tab.reward_notes[0].text(), "Refresh asks the helper")

    # the helper answers: the window fills both lists
    me = types.SimpleNamespace(settings=tab)
    app.Window.handle_report(me, "REWARDS|" + json.dumps(["Hydrate", "Зона", "Скажи через сталкера"]))
    items = [zone_f.itemText(i) for i in range(zone_f.count())]
    check(items == ["", "Hydrate", "Зона", "Скажи через сталкера"], f"Zone list: off + the channel's rewards {items}")
    check(say_f.itemText(0) == "", "the speech reward can be set to none too")
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
    t.twitch = types.SimpleNamespace(list_rewards=lambda: ["A", "Зона"], app_rewards=lambda: [])
    out = io.StringIO()
    with redirect_stdout(out):
        t.report_rewards()
        t.twitch = None
        t.report_rewards()
    lines = out.getvalue().splitlines()
    check(lines == ['@REWARDS|["A", "Зона"]', "@APP_REWARDS|[]", "@REWARDS_ERROR|Twitch is off (TWITCH_ENABLED, "
                    "TWITCH_CLIENT_ID)"], f"helper answers {lines}")

    # the app never creates a reward; one an older version made can be deleted, only after a yes
    calls = []

    def fake_helix(method, path, **kw):
        calls.append((method, kw.get("params", {}).get("only_manageable_rewards"), kw.get("params", {}).get("id")))
        if method == "GET":
            data = [{"id": "old", "title": "Скажи через сталкера"}]
            if not kw["params"].get("only_manageable_rewards"):
                data.append({"id": "z", "title": "Зона"})
            return types.SimpleNamespace(status_code=200, json=lambda: {"data": data}, text="")
        if method == "DELETE":
            return types.SimpleNamespace(status_code=204, json=lambda: {}, text="")
        return types.SimpleNamespace(status_code=500, json=lambda: {}, text="")

    logs = []
    tw = Twitch("id", "Мій редім", tmp / "tok.json", lambda *a: None, logs.append, source="reward")
    tw.user_id, tw.helix = "42", fake_helix
    tw.find_reward()
    check(not any(c[0] == "POST" for c in calls) and tw.reward_id is None and "no reward" in logs[-1],
          f"a missing speech reward is not created {calls} {logs[-1:]}")
    tw2 = Twitch("id", "", tmp / "tok.json", lambda *a: None, logs.append, source="reward")
    tw2.user_id, tw2.helix = "42", fake_helix
    calls.clear()
    tw2.find_reward()
    check(not calls and tw2.reward_id is None, "no speech reward set: Twitch isn't even asked")
    spoken = []
    tw.on_message = lambda u, t, r: spoken.append(t)
    tw.on_redemption({"id": "1", "user_name": "A", "reward": {"id": "q", "title": "мій редім"}, "user_input": "$hi"})
    tw.on_redemption({"id": "2", "user_name": "B", "reward": {"id": "w", "title": "Hydrate"}, "user_input": "$no"})
    check(spoken == ["$hi"], f"made on Twitch later: matched by its title, other rewards ignored {spoken}")
    tw2.on_message = lambda u, t, r: spoken.append(t)
    tw2.on_redemption({"id": "3", "user_name": "C", "reward": {"id": "w", "title": "Hydrate"}, "user_input": "$x"})
    check(spoken == ["$hi"], "no speech reward set: no reward is spoken")
    check(tw.app_rewards() == [{"id": "old", "title": "Скажи через сталкера"}], "the app's own old reward is found")
    check(tw.delete_reward("old") is None and ("DELETE", None, "old") in calls, "delete removes it on Twitch")

    sent_in = []
    me = types.SimpleNamespace(settings=tab, proc=types.SimpleNamespace(write=lambda b: sent_in.append(b)))
    from PySide6.QtWidgets import QHBoxLayout, QMessageBox, QWidget
    me.app_rewards_box = QWidget()
    me.app_rewards_row = QHBoxLayout(me.app_rewards_box)
    me.show_app_rewards = lambda r: app.Window.show_app_rewards(me, r)
    me.delete_app_reward = lambda r: app.Window.delete_app_reward(me, r)
    app.Window.handle_report(me, "APP_REWARDS|" + json.dumps([{"id": "old", "title": "Скажи через сталкера"}]))
    btns = [me.app_rewards_row.itemAt(i).widget() for i in range(me.app_rewards_row.count())]
    btns = [b for b in btns if b is not None and b.text().startswith("Delete")]
    check(len(btns) == 1 and "Скажи через сталкера" in btns[0].text(), "the window offers Delete for it")
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)
    btns[0].click()
    check(not sent_in, "answered No: nothing is deleted")
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    btns[0].click()
    check(sent_in == [b"delete_reward old\n"], f"answered Yes: the helper is told to delete it {sent_in}")
    app.Window.handle_report(me, "APP_REWARDS|[]")
    check(me.app_rewards_box.isHidden(), "nothing left: the row goes")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("OK" if ok else "FAIL")
