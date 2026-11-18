"""StalkerTalker window: start/stop the helper, live log, usage, Twitch status and settings.

Runs companion/talker.py as a child process and reads its output, so a crash in the helper never takes
the window down, and "Save and restart" applies new settings at once.
"""
import os
import re
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QProcess, QProcessEnvironment, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QFont, QTextCursor
from PySide6.QtWidgets import (QApplication, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
                               QTabWidget, QVBoxLayout, QWidget)

ROOT = Path(__file__).resolve().parent.parent
SETTINGS = ROOT / "settings.ini"
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"


def setting(key, default=""):
    """A value from settings.ini (the window reads only what it needs; the helper loads them all)."""
    try:
        for line in SETTINGS.read_text(encoding="utf-8-sig").splitlines():
            k, sep, v = line.partition("=")
            if sep and k.strip() == key:
                return v.split(" #")[0].strip() or default
    except OSError:
        pass
    return default


GAME_DIR = Path(setting("STALKER_DIR", r"C:\Games\S.T.A.L.K.E.R. Call of Pripyat"))
LOG_DIR = ROOT / "logs"
LOG_FILE = LOG_DIR / "stalkertalker.log"  # everything the window shows; the previous run is kept as .old.log


def open_log():
    LOG_DIR.mkdir(exist_ok=True)
    try:
        if LOG_FILE.exists():
            os.replace(LOG_FILE, LOG_DIR / "stalkertalker.old.log")
        return open(LOG_FILE, "a", encoding="utf-8", buffering=1)
    except OSError:  # another StalkerTalker window is open and owns that file
        return open(LOG_DIR / f"stalkertalker.{os.getpid()}.log", "a", encoding="utf-8", buffering=1)


LOG = open_log()


def crash_hook(kind, value, tb):
    """Any error in the window itself goes to the log instead of silently closing it."""
    import traceback
    LOG.write("WINDOW ERROR:\n" + "".join(traceback.format_exception(kind, value, tb)))
    LOG.flush()


STYLE = """
QWidget { background: #1d1f1a; color: #d9d4c3; font-size: 10pt; }
QPlainTextEdit, QLineEdit, QComboBox { background: #262922; border: 1px solid #3c4134; padding: 4px; }
QPushButton { background: #3a4030; border: 1px solid #56604a; padding: 6px 14px; }
QPushButton:hover { background: #4a523d; }
QPushButton#primary { background: #6b5a2a; border-color: #8f7a3a; }
QTabWidget::pane { border: 1px solid #3c4134; }
QTabBar::tab { background: #262922; padding: 6px 16px; border: 1px solid #3c4134; }
QTabBar::tab:selected { background: #3a4030; }
QLabel#muted { color: #9a9582; }
"""


class SettingsTab(QWidget):
    """A form built from settings.ini: the comment above each key becomes its hint."""

    def __init__(self, on_save):
        super().__init__()
        self.on_save = on_save
        self.fields = {}
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        self.form = QFormLayout(inner)
        self.form.setLabelAlignment(Qt.AlignRight)
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        row = QHBoxLayout()
        row.addStretch()
        open_env = QPushButton("Open .env (keys)")
        open_env.clicked.connect(lambda: os.startfile(ROOT / ".env"))
        save = QPushButton("Save and restart")
        save.setObjectName("primary")
        save.clicked.connect(self.save)
        row.addWidget(open_env)
        row.addWidget(save)
        outer.addLayout(row)
        self.load()

    def load(self):
        self.lines = SETTINGS.read_text(encoding="utf-8-sig").splitlines() if SETTINGS.exists() else []
        self.loaded = {}
        hint = []
        for line in self.lines:
            s = line.strip()
            if s.startswith("#"):
                hint.append(s.lstrip("# "))
            elif s.startswith("["):
                title = QLabel(s.strip("[]"))
                title.setFont(QFont(title.font().family(), 11, QFont.Bold))
                self.form.addRow(title)
                hint = []
            elif "=" in s:
                key, value = s.split("=", 1)
                key, value = key.strip(), value.strip()
                text = " ".join(hint)
                m = re.search(r"options:\s*([\w, ]+)$", text)
                if m:
                    field = QComboBox()
                    field.addItems([o.strip() for o in m.group(1).split(",") if o.strip()])
                    field.setCurrentText(value)
                    text = text[:m.start()].strip(" .")
                else:
                    field = QLineEdit(value)
                field.setToolTip(text)
                label = QLabel(key)
                label.setToolTip(text)
                box = QVBoxLayout()
                box.setSpacing(1)
                box.addWidget(field)
                if text:
                    note = QLabel(text)
                    note.setObjectName("muted")
                    note.setWordWrap(True)
                    box.addWidget(note)
                self.form.addRow(label, box)
                self.fields[key] = field
                self.loaded[key] = self.value(key)  # what the form showed, to know later what YOU changed
                hint = []

    def value(self, key):
        f = self.fields[key]
        return f.currentText() if isinstance(f, QComboBox) else f.text().strip()

    def set_value(self, key, value):
        f = self.fields.get(key)
        if isinstance(f, QComboBox):
            f.setCurrentText(value)
        elif f is not None:
            f.setText(value)

    def save(self):
        """Write back only the settings changed in this window, into the file as it is NOW on disk,
        so lines added to settings.ini by hand while the window was open are kept."""
        changed = {k: self.value(k) for k in self.fields if self.value(k) != self.loaded.get(k)}
        current = SETTINGS.read_text(encoding="utf-8-sig").splitlines() if SETTINGS.exists() else self.lines
        out = []
        for line in current:
            s = line.strip()
            if "=" in s and not s.startswith(("#", "[")):
                key = s.split("=", 1)[0].strip()
                if key in changed:
                    line = f"{key}={changed[key]}"
            out.append(line)
        SETTINGS.write_text("\n".join(out) + "\n", encoding="utf-8")
        self.lines = out
        self.loaded.update(changed)
        self.on_save()


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("StalkerTalker")
        self.resize(900, 640)
        self.proc = None

        top = QHBoxLayout()
        self.state = QLabel("Stopped")
        self.state.setFont(QFont(self.state.font().family(), 11, QFont.Bold))
        self.toggle = QPushButton("Start")
        self.toggle.setObjectName("primary")
        self.toggle.clicked.connect(self.toggle_run)
        install = QPushButton("Reinstall game mod")
        install.clicked.connect(self.install_mod)
        folder = QPushButton("Game logs")
        folder.clicked.connect(lambda: os.startfile(GAME_DIR / "talker"))
        self.mode = QPushButton()
        self.mode.setToolTip("All: NPCs answer your mic and talk on their own.\n"
                             "Chat only: NPCs only say Twitch chat messages ($ word for word, % in their words).")
        self.mode.clicked.connect(self.switch_mode)
        top.addWidget(self.state)
        top.addStretch()
        top.addWidget(self.mode)
        top.addWidget(folder)
        top.addWidget(install)
        top.addWidget(self.toggle)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(3000)
        self.log.setFont(QFont("Consolas", 10))

        twitch = QWidget()
        tl = QVBoxLayout(twitch)
        self.twitch_state = QLabel("Twitch: off (add TWITCH_CLIENT_ID to .env, see the guide below)")
        self.twitch_state.setWordWrap(True)
        self.twitch_queue = QLabel("Waiting messages: 0")
        self.twitch_code = QPushButton("")
        self.twitch_code.setObjectName("primary")
        self.twitch_code.hide()
        self.twitch_code.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self.twitch_code.property("url"))))
        self.auth_requested = False
        auth = self.auth_btn = QPushButton("Authorize Twitch app")
        auth.setObjectName("primary")
        auth.setToolTip("Signs you in to Twitch again (opens the Twitch page). Use it the first time, "
                        "after changing TWITCH_CLIENT_ID, or when Twitch says the sign-in expired.")
        auth.clicked.connect(self.authorize_twitch)
        auth_row = QHBoxLayout()
        auth_row.addWidget(auth)
        auth_row.addStretch()
        guide = QLabel(
            "<b>Setup (once)</b><ol>"
            "<li>Open <a href='https://dev.twitch.tv/console/apps'>dev.twitch.tv/console/apps</a> → Register Your "
            "Application. Name: anything. OAuth Redirect URL: <code>http://localhost</code>. Category: Game "
            "Integration. Client Type: <b>Public</b>.</li>"
            "<li>Copy its Client ID into .env as <code>TWITCH_CLIENT_ID=...</code>.</li>"
            "<li>Press <b>Authorize Twitch app</b>. The Twitch page opens with your code: sign in and allow "
            "access.</li>"
            "<li><b>chat</b> mode (default, no Affiliate needed): a chat message starting with <b>$</b> is said "
            "word for word, one starting with <b>%</b> is retold by the NPC his own way. Other messages are "
            "ignored (Settings → TWITCH_UNPREFIXED). A random NPC near you says it; nobody near? It waits.</li>"
            "<li><b>reward</b> mode (Settings → Twitch → TWITCH_SOURCE): only a channel-points reward with a "
            "message, created for you; needs Affiliate/Partner.</li></ol>")
        guide.setOpenExternalLinks(True)
        guide.setWordWrap(True)
        tl.addWidget(self.twitch_state)
        tl.addWidget(self.twitch_queue)
        tl.addLayout(auth_row)
        tl.addWidget(self.twitch_code)
        tl.addWidget(guide)
        tl.addStretch()

        tabs = QTabWidget()
        tabs.addTab(self.log, "Log")
        self.settings = SettingsTab(self.restart)
        tabs.addTab(self.settings, "Settings")
        tabs.addTab(twitch, "Twitch")

        self.usage = QLabel("Usage: -")
        self.usage.setObjectName("muted")
        self.usage.setWordWrap(True)

        body = QWidget()
        lay = QVBoxLayout(body)
        lay.addLayout(top)
        lay.addWidget(tabs, 1)
        lay.addWidget(self.usage)
        self.setCentralWidget(body)
        self.show_mode()
        self.start()

    # ------------------------------------------------------------ helper process
    def start(self):
        if self.proc:
            return
        self.proc = QProcess(self)
        self.out_buf = b""
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONIOENCODING", "utf-8")
        env.insert("PYTHONUNBUFFERED", "1")
        self.proc.setProcessEnvironment(env)
        self.proc.setWorkingDirectory(str(ROOT))
        self.proc.setProcessChannelMode(QProcess.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self.read_output)
        self.proc.finished.connect(self.on_finished)
        self.proc.start(str(PYTHON), ["-u", str(ROOT / "companion" / "talker.py")])
        self.state.setText("Running")
        self.toggle.setText("Stop")
        self.append("— helper started —")

    # ------------------------------------------------------------ mode + Twitch sign-in
    def show_mode(self):
        chat = self.settings.value("SPEAK_MODE") == "chat" if "SPEAK_MODE" in self.settings.fields else False
        self.mode.setText("Mode: Chat only" if chat else "Mode: All")

    def switch_mode(self):
        chat = self.settings.value("SPEAK_MODE") == "chat"
        self.settings.set_value("SPEAK_MODE", "all" if chat else "chat")
        self.settings.save()  # saves settings.ini and restarts the helper
        self.show_mode()

    def authorize_twitch(self):
        env = (ROOT / ".env").read_text(encoding="utf-8-sig") if (ROOT / ".env").exists() else ""
        if not re.search(r"^\s*TWITCH_CLIENT_ID\s*=\s*\S+", env, re.M):
            QMessageBox.information(self, "StalkerTalker", "First add your Twitch app's Client ID to .env:\n\n"
                                    "TWITCH_CLIENT_ID=...\n\n(Settings tab → Open .env). See the guide below.")
            return
        if self.settings.value("TWITCH_ENABLED") != "1":
            self.settings.set_value("TWITCH_ENABLED", "1")
            self.settings.save()
        try:
            (ROOT / "twitch_token.json").unlink()  # forget the old sign-in so Twitch asks again
        except OSError:
            pass
        self.auth_requested = True
        self.twitch_state.setText("Twitch: getting a sign-in code from Twitch (about 10 seconds)...")
        self.auth_btn.setEnabled(False)  # one click is enough: a second one would restart it all again
        self.auth_btn.setText("Waiting for Twitch...")
        QTimer.singleShot(60000, self.auth_done)  # never stay stuck if something goes wrong
        self.restart()

    def auth_done(self):
        self.auth_btn.setEnabled(True)
        self.auth_btn.setText("Authorize Twitch app")

    def stop(self):
        if not self.proc:
            return
        proc, self.proc = self.proc, None
        proc.finished.disconnect(self.on_finished)
        proc.kill()
        proc.waitForFinished(3000)
        self.state.setText("Stopped")
        self.state.setStyleSheet("")
        self.toggle.setText("Start")
        self.append("— helper stopped —")

    def restart(self):
        self.stop()
        self.start()

    def toggle_run(self):
        self.stop() if self.proc else self.start()

    def on_finished(self, code, _status):
        self.read_output()  # the last lines before it died are usually the error
        self.proc = None
        self.state.setText(f"Stopped (exit {code})")
        self.toggle.setText("Start")
        self.append(f"— helper exited with code {code} —")

    def read_output(self):
        if not self.proc:
            return
        # Output arrives in arbitrary chunks: keep the unfinished last line (and any half of a Ukrainian letter)
        # until the rest comes, so nothing is garbled and "@" status lines are never split.
        self.out_buf = getattr(self, "out_buf", b"") + bytes(self.proc.readAllStandardOutput())
        *done, self.out_buf = self.out_buf.split(b"\n")
        for raw in done:
            line = raw.decode("utf-8", "replace").rstrip("\r")
            if line.startswith("@"):
                self.handle_report(line[1:])
            elif line.strip():
                self.append(line)

    def handle_report(self, line):
        kind, _, text = line.partition("|")
        if kind == "GAME":
            on = text == "running"
            self.state.setText("Running: game on" if on else "Waiting for S.T.A.L.K.E.R.")
            self.state.setStyleSheet("color: #9fcf7a;" if on else "color: #d9b25a;")
        elif kind == "USAGE":
            self.usage.setText(text)
        elif kind == "TWITCH":
            if not text.startswith("sign in"):  # keep the friendlier sign-in hint while waiting
                self.twitch_state.setText(f"Twitch: {text}")
            if text.startswith("on"):
                self.twitch_code.hide()
                self.auth_done()
        elif kind == "TWITCH_QUEUE":
            self.twitch_queue.setText(f"Waiting messages: {text}")
        elif kind == "TWITCH_CODE":
            url, _, code = text.partition("|")
            self.twitch_code.setText(f"Sign in to Twitch: open {url} and enter code {code}")
            self.twitch_code.setProperty("url", url)
            self.twitch_code.show()
            QApplication.clipboard().setText(code)
            if self.auth_requested:  # the user just pressed Authorize: open the page right away
                self.auth_requested = False
                self.auth_done()
                if not QDesktopServices.openUrl(QUrl(url)):
                    import webbrowser
                    webbrowser.open(url)
                self.twitch_state.setText(f"Twitch: the sign-in page is open in your browser. Sign in and press "
                                          f"Authorize there. Code {code} (copied, in case it asks).")
                self.raise_()

    def append(self, text):
        LOG.write(text + "\n")
        self.log.appendPlainText(text)
        self.log.moveCursor(QTextCursor.End)

    def install_mod(self):
        r = subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "install_mod.ps1")],
                           capture_output=True, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        msg = (r.stdout + r.stderr).strip() or "done"
        self.append(msg)
        QMessageBox.information(self, "StalkerTalker", msg + "\n\nLoad a save in the game to pick up the changes.")

    def closeEvent(self, event):
        self.stop()
        event.accept()


def main():
    import faulthandler
    faulthandler.enable(open(LOG_DIR / "window_crash.log", "a"))  # hard crashes (Qt, drivers)
    sys.excepthook = crash_hook
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    w = Window()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
