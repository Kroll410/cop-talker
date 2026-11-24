"""StalkerTalker window: start/stop the helper, live log, usage, Twitch status and settings.

Runs companion/talker.py as a child process and reads its output, so a crash in the helper never takes
the window down, and "Save and restart" applies new settings at once.
"""
import html
import json
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
sys.path.insert(0, str(Path(__file__).resolve().parent))
from settings_file import ensure_settings, read_text  # noqa: E402  (settings.ini from the example, plus new options)

try:
    SETTINGS_NOTE = ensure_settings(ROOT)
except Exception as exc:  # never keep the window from opening
    SETTINGS_NOTE = f"settings.ini check failed: {exc!r}"


def setting(key, default=""):
    """A value from settings.ini (the window reads only what it needs; the helper loads them all)."""
    try:
        for line in read_text(SETTINGS).splitlines():
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


# The Zone's PDA: one olive-graphite ramp, three text roles, one amber accent for the main action, the
# selection and the "on air" dot. Depth from surface steps and hairlines, no glows.
DEEP, PAGE, RAISED, HOVER = "#141512", "#191a17", "#20221e", "#292b26"
HAIR = "rgba(226, 221, 204, 0.09)"
TEXT, TEXT2, MUTED = "#e2ddcc", "#a9a593", "#868272"
AMBER, ON_AMBER, RED = "#d0a54a", "#1a1608", "#d9655b"
STYLE = f"""
QWidget {{ background: {PAGE}; color: {TEXT}; font-family: "Segoe UI"; font-size: 10pt; }}
QToolTip {{ background: {RAISED}; color: {TEXT}; border: 1px solid {HAIR}; padding: 6px; }}
QPlainTextEdit {{ background: {DEEP}; border: 1px solid {HAIR}; border-radius: 10px; padding: 8px;
                 selection-background-color: #4a3f22; }}
QLineEdit, QComboBox {{ background: {RAISED}; border: 1px solid {HAIR}; border-radius: 8px; padding: 6px 8px; }}
QLineEdit:focus, QComboBox:focus {{ border-color: {AMBER}; }}
QComboBox QAbstractItemView {{ background: {RAISED}; border: 1px solid {HAIR}; selection-background-color: {HOVER};
                              selection-color: {TEXT}; }}
QPushButton {{ background: {RAISED}; color: {TEXT}; border: 1px solid {HAIR}; border-radius: 8px; padding: 6px 14px; }}
QPushButton:hover {{ background: {HOVER}; }}
QPushButton:pressed {{ background: {DEEP}; }}
QPushButton:focus {{ border-color: rgba(208, 165, 74, 0.6); }}
QPushButton:disabled {{ color: {MUTED}; }}
QPushButton#primary {{ background: {AMBER}; color: {ON_AMBER}; border-color: {AMBER}; font-weight: 600; }}
QPushButton#primary:hover {{ background: #dbb25b; }}
QPushButton#primary:pressed {{ background: #bf953f; }}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ background: transparent; color: {TEXT2}; border: none; border-bottom: 2px solid transparent;
               padding: 8px 2px; margin-right: 20px; }}
QTabBar::tab:hover {{ color: {TEXT}; }}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {AMBER}; }}
QScrollArea {{ border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px 2px; }}
QScrollBar::handle:vertical {{ background: rgba(226, 221, 204, 0.14); border-radius: 3px; min-height: 24px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#secondary {{ color: {TEXT2}; }}
QLabel#section {{ color: {TEXT}; font-size: 11pt; font-weight: 500; padding-top: 16px; }}
QLabel#state {{ font-weight: 500; }}
"""

# "On air": the dot next to the status. Lit amber while the game is on, an amber ring while waiting for it.
DOT = {"live": f"background: {AMBER}; border: 1px solid {AMBER};",
       "waiting": f"background: transparent; border: 1px solid {AMBER};",
       "off": f"background: #3d3e37; border: 1px solid #3d3e37;"}

# Settings: what a person reads, the setting's own name stays below in small type.
NICE = {"STALKER_DIR": "Game folder", "SPEAK_MODE": "Speaking", "PTT_KEY": "Push-to-talk key", "MIC": "Microphone",
        "SUBTITLES": "Subtitles", "STREAM_VOICE": "Stream the voice", "TTS_SPEED": "Voice speed",
        "NPC_VOLUME": "NPC volume", "LINE_GAP": "Pause between lines", "GREET_CHANCE": "Greeting chance",
        "GREET_COOLDOWN": "Greeting cooldown", "HOSTILE_CHANCE": "Enemy shout chance",
        "CHIME_CHANCE": "Bystander joins in", "REACT_CHANCE": "Reaction chance", "REACT_COOLDOWN": "Reaction cooldown",
        "GROUP_MAX": "Group answers, at most", "GROUP_DISTANCE": "Group distance", "GROUP_STYLE": "Group style",
        "GROUP_ASIDE_VOLUME": "Mutter volume", "COMPANION_CHANCE": "Companion talk chance",
        "COMPANION_COOLDOWN": "Companion cooldown", "CHAT_CHANCE": "NPC chat chance", "CHAT_COOLDOWN": "NPC chat cooldown",
        "CHAT_DISTANCE": "NPC chat distance", "PLAYER_NAME": "Your nickname", "PLAYER_BIO": "Your backstory",
        "FUN_LEVEL": "Humour", "QUIRK_CHANCE": "Quirks", "MEMORY_KEEP": "Talks kept word for word",
        "CLEAR_MEMORY": "Clear memory on start", "OUTSIDE_TALK": "Talk about life outside", "NEWS_FEEDS": "News feeds",
        "TWITCH_ENABLED": "Twitch", "TWITCH_SOURCE": "Source", "TWITCH_CHANNEL": "Channel",
        "TWITCH_QUEUE_MAX": "Messages waiting, at most", "TWITCH_REWARD": "Speech reward title",
        "TWITCH_UNPREFIXED": "Messages without $ or %", "TWITCH_DISTANCE": "NPC distance",
        "TWITCH_SHOW_NAME": "Nick in the PDA", "TWITCH_LINKS": "Viewer keeps his NPC", "TWITCH_BLOCKED": "Blocked words",
        "TWITCH_ZONE_REWARD": "Zone reward title", "TWITCH_ZONE_GAP": "Minutes between Zone events",
        "LLM_PROVIDER": "Replies by", "CLAUDE_MODEL": "Claude model", "CLAUDE_CLI": "Claude Code program",
        "GEMINI_MODEL": "Gemini model", "GEMINI_SMART_MODEL": "Gemini model for deals",
        "STT_MODELS": "Speech recognition"}
# Reward titles: picked from the channel's own rewards (Refresh asks Twitch), or typed.
REWARD_PICK = {"TWITCH_REWARD", "TWITCH_ZONE_REWARD"}
WIDE = {"STALKER_DIR", "PLAYER_BIO", "NEWS_FEEDS", "CLAUDE_CLI", "TWITCH_BLOCKED", "STT_MODELS"}


def span(text, color, mono=False):
    font = "font-family: Consolas; font-size: 9pt; " if mono else ""
    return f'<span style="{font}color: {color}">{html.escape(text)}</span>'


SPEECH = re.compile(r"^(\s*)([^\W\d_][^:]{0,40}?)(\s\([^)]*\))?: (.+)$")
QUIET = ("Game:", "News:", "Audio:", "NPC replies", "Loading", "  (", "Twitch: ", "memory", "voice ")


def log_html(line):
    """One log line as a radio transcript: the time small and dim, who speaks in amber, what NPCs say bright,
    everything the helper says about itself quieter."""
    m = re.match(r"^(\d\d:\d\d:\d\d) (.*)$", line)
    time, rest = (m.group(1), m.group(2)) if m else ("", line)
    head = span(time, MUTED, mono=True) + "&nbsp;&nbsp;" if time else ""
    indent = "&nbsp;" * 4 * (len(rest) - len(rest.lstrip(" ")) > 0)
    body = rest.lstrip(" ")
    if body.startswith("—"):
        return span(body, MUTED)
    if body.startswith("You died"):
        return head + span(body, RED)
    tw = re.match(r"^Twitch \(([^)]+)\) (via|to) ([^:]+): (.+)$", body)
    if tw:
        return (head + span(f"Twitch · {tw.group(1)}  ", MUTED) + span(tw.group(3), AMBER) + span(": ", MUTED)
                + span(tw.group(4), TEXT))
    ans = re.match(r"^(.+?) (answers|heard his name):\s*(.*)$", body)
    if ans:
        return (head + indent + span(ans.group(1), AMBER) + span(f" {ans.group(2)}: ", MUTED)
                + span(ans.group(3), TEXT))
    sp = SPEECH.match(body)
    if sp and re.search(r"[а-яіїєґА-ЯІЇЄҐ]", sp.group(2)) and not body.startswith(QUIET):
        who = sp.group(2)
        color = TEXT2 if who == "You" else AMBER
        return (head + indent + span(who, color) + span((sp.group(3) or "") + ": ", MUTED)
                + span(sp.group(4), TEXT))
    if body.startswith("You:"):
        return head + span("You", TEXT2) + span(": ", MUTED) + span(body[4:].strip(), TEXT)
    return head + indent + span(body, MUTED if body.startswith(QUIET) else TEXT2)


class SettingsTab(QWidget):
    """A form built from settings.ini: the comment above each key becomes its hint."""

    def __init__(self, on_save, on_refresh_rewards=None):
        super().__init__()
        self.on_save = on_save
        self.on_refresh_rewards = on_refresh_rewards or (lambda: False)
        self.fields = {}
        self.reward_notes = []
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 12, 0, 0)
        outer.setSpacing(12)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        self.form = QFormLayout(inner)
        self.form.setLabelAlignment(Qt.AlignRight | Qt.AlignTop)
        self.form.setContentsMargins(16, 0, 24, 16)
        self.form.setHorizontalSpacing(16)
        self.form.setVerticalSpacing(12)
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        row = QHBoxLayout()
        row.addStretch()
        open_env = QPushButton("Open .env")
        open_env.setToolTip("Keys and voice IDs live there")
        open_env.clicked.connect(lambda: os.startfile(ROOT / ".env"))
        save = QPushButton("Save and restart")
        save.setObjectName("primary")
        save.clicked.connect(self.save)
        row.addWidget(open_env)
        row.addWidget(save)
        outer.addLayout(row)
        self.load()

    def load(self):
        self.lines = read_text(SETTINGS).splitlines() if SETTINGS.exists() else []
        self.loaded = {}
        hint = []
        for line in self.lines:
            s = line.strip()
            if s.startswith("#"):
                hint.append(s.lstrip("# "))
            elif s.startswith("["):
                title = QLabel(s.strip("[]"))
                title.setObjectName("section")
                self.form.addRow(title)
                hint = []
            elif "=" in s and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", s.split("=", 1)[0].strip()):
                key, value = s.split("=", 1)
                key, value = key.strip(), value.strip()
                text = " ".join(hint)
                m = re.search(r"options:\s*([\w, ]+)$", text)
                if key in REWARD_PICK:
                    field = QComboBox()
                    field.setEditable(True)  # Twitch not reachable now: the title can still be typed
                    field.addItem("")  # empty = none
                    if value:
                        field.addItem(value)
                    field.setCurrentText(value)
                elif m:
                    field = QComboBox()
                    field.addItems([o.strip() for o in m.group(1).split(",") if o.strip()])
                    field.setCurrentText(value)
                    text = text[:m.start()].strip(" .")
                else:
                    field = QLineEdit(value)
                field.setToolTip(text)
                field.setMaximumWidth(360 if key in REWARD_PICK else 240 if isinstance(field, QComboBox)
                                      else 720 if key in WIDE else 360)
                label = QLabel(NICE.get(key, key.replace("_", " ").capitalize()))
                label.setToolTip(text)
                label.setContentsMargins(0, 6, 0, 0)  # level with the text inside the field
                cell = QWidget()
                cell.setMaximumWidth(720)
                box = QVBoxLayout(cell)
                box.setContentsMargins(0, 0, 0, 0)
                box.setSpacing(4)
                if key in REWARD_PICK:
                    pick = QHBoxLayout()
                    pick.setSpacing(8)
                    pick.addWidget(field, 1)
                    refresh = QPushButton("Refresh")
                    refresh.setToolTip("Ask Twitch for all channel-points rewards of your channel")
                    refresh.clicked.connect(self.refresh_rewards)
                    pick.addWidget(refresh)
                    status = QLabel("")
                    status.setObjectName("muted")
                    pick.addWidget(status)
                    pick.addStretch()
                    self.reward_notes.append(status)
                    box.addLayout(pick)
                else:
                    box.addWidget(field)
                note = QLabel((html.escape(text.rstrip(". ")) + "&nbsp;&nbsp;" if text else "")
                              + span(key, "#6f6c5f", mono=True))
                note.setObjectName("muted")
                note.setWordWrap(True)
                box.addWidget(note)
                self.form.addRow(label, cell)
                self.fields[key] = field
                self.loaded[key] = self.value(key)  # what the form showed, to know later what YOU changed
                hint = []

    def refresh_rewards(self):
        self.reward_status("asking Twitch..." if self.on_refresh_rewards() else
                           "start the helper and sign in to Twitch first")

    def reward_status(self, text):
        for note in self.reward_notes:
            note.setText(text)

    def set_rewards(self, titles):
        """The channel's rewards from Twitch: offered in every reward picker; the chosen title stays."""
        for key in REWARD_PICK:
            f = self.fields.get(key)
            if not isinstance(f, QComboBox):
                continue
            current = f.currentText()
            f.blockSignals(True)
            f.clear()
            f.addItem("")
            f.addItems(titles)
            if current and current not in titles:
                f.addItem(current)  # not on the channel (yet): keep it, the helper creates or waits for it
            f.setCurrentText(current)
            f.blockSignals(False)
        self.reward_status(f"{len(titles)} reward(s) on the channel" if titles else "no rewards on the channel yet")

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
        current = read_text(SETTINGS).splitlines() if SETTINGS.exists() else self.lines
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
        top.setSpacing(8)
        self.dot = QLabel()
        self.dot.setFixedSize(8, 8)
        self.state = QLabel("Stopped")
        self.state.setObjectName("state")
        self.set_status("Stopped", "off")
        self.toggle = QPushButton("Start")
        self.toggle.setObjectName("primary")
        self.toggle.clicked.connect(self.toggle_run)
        install = QPushButton("Reinstall game mod")
        install.clicked.connect(self.install_mod)
        update = QPushButton("Update")
        update.setToolTip("Gets the newest StalkerTalker from GitHub (git pull), adds new settings to your "
                          "settings.ini, reinstalls the game mod if it changed and restarts.\n"
                          "Your settings.ini, .env and NPC memories are never touched.")
        update.clicked.connect(self.update_self)
        folder = QPushButton("Game logs")
        folder.clicked.connect(lambda: os.startfile(GAME_DIR / "talker"))
        self.mode = QPushButton()
        self.mode.setToolTip("All: NPCs answer your mic and talk on their own.\n"
                             "Chat only: NPCs only say Twitch chat messages ($ word for word, % in their words).")
        self.mode.clicked.connect(self.switch_mode)
        top.addWidget(self.dot)
        top.addSpacing(4)
        top.addWidget(self.state)
        top.addStretch()
        top.addWidget(self.mode)
        top.addWidget(folder)
        top.addWidget(update)
        top.addWidget(install)
        top.addWidget(self.toggle)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(3000)
        self.log.setFont(QFont("Segoe UI", 10))

        twitch = QWidget()
        tl = QVBoxLayout(twitch)
        tl.setContentsMargins(4, 16, 4, 0)
        tl.setSpacing(12)
        self.twitch_state = QLabel("Twitch: off (add TWITCH_CLIENT_ID to .env, see the guide below)")
        self.twitch_state.setWordWrap(True)
        self.twitch_queue = QLabel("Waiting messages: 0")
        self.twitch_queue.setObjectName("secondary")
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
        code = f'style="font-family: Consolas; color: {TEXT2}"'
        guide = QLabel(
            f"<p style='color: {TEXT}; font-weight: 500'>Setup, once</p><ol style='color: {TEXT2}'>"
            f"<li>Open <a style='color: {AMBER}' href='https://dev.twitch.tv/console/apps'>dev.twitch.tv/console/apps</a> → Register Your "
            f"Application. Name: anything. OAuth Redirect URL: <span {code}>http://localhost</span>. Category: Game "
            "Integration. Client Type: <b>Public</b>.</li>"
            f"<li>Copy its Client ID into .env as <span {code}>TWITCH_CLIENT_ID=...</span>.</li>"
            "<li>Press <b>Authorize Twitch app</b>. The Twitch page opens with your code: sign in and allow "
            "access.</li>"
            "<li><b>chat</b> mode (default, no Affiliate needed): a chat message starting with <b>$</b> is said "
            "word for word, one starting with <b>%</b> is retold by the NPC his own way. Other messages are "
            "ignored (Settings → TWITCH_UNPREFIXED). A random NPC near you says it; nobody near? It waits.</li>"
            "<li><b>reward</b> mode (Settings → Twitch → TWITCH_SOURCE): make a channel-points reward with a "
            "message on Twitch yourself and pick it in Settings → TWITCH_REWARD (the app never creates rewards); "
            "needs Affiliate/Partner.</li></ol>")
        guide.setOpenExternalLinks(True)
        guide.setWordWrap(True)
        guide.setMaximumWidth(760)
        tl.addWidget(self.twitch_state)
        tl.addWidget(self.twitch_queue)
        tl.addLayout(auth_row)
        tl.addWidget(self.twitch_code)
        # Rewards an older version created on the channel: shown with a Delete button (asks first)
        self.app_rewards_box = QWidget()
        self.app_rewards_row = QHBoxLayout(self.app_rewards_box)
        self.app_rewards_row.setContentsMargins(0, 0, 0, 0)
        self.app_rewards_box.hide()
        tl.addWidget(self.app_rewards_box)
        # Zone reward: what's waiting (rolled at redemption) and debug buttons that need no real redemption
        zone_title = QLabel("Zone events (Settings → TWITCH_ZONE_REWARD)")
        self.zone_queue = QLabel("Nothing waiting")
        self.zone_queue.setObjectName("secondary")
        self.zone_queue.setWordWrap(True)
        zone_row = QHBoxLayout()
        for text, arg, tip in (
                ("Redeem (debug)", "redeem", "As if a viewer redeemed the Zone reward: rolled now, a PDA notice, "
                                             "queued like a real one (first in the queue: at once)."),
                ("Now: Дар", "gift", "A random item in your backpack, right now."),
                ("Now: Життя", "life", "A random stalker, friend or enemy, right now."),
                ("Now: Дитя", "child", "Mutants come for you, right now."),
                ("Now: random", "any", "One of the three, rolled like a real redemption, right now.")):
            btn = QPushButton(text)
            btn.setToolTip(tip)
            btn.clicked.connect(lambda _=False, a=arg: self.send_zone(a))
            zone_row.addWidget(btn)
        zone_row.addStretch()
        tl.addWidget(zone_title)
        tl.addWidget(self.zone_queue)
        tl.addLayout(zone_row)
        tl.addWidget(guide)
        tl.addStretch()

        tabs = QTabWidget()
        tabs.addTab(self.log, "Log")
        self.settings = SettingsTab(self.restart, self.request_rewards)
        tabs.addTab(self.settings, "Settings")
        tabs.addTab(twitch, "Twitch")

        self.usage = QLabel("Usage: -")
        self.usage.setObjectName("muted")
        self.usage.setWordWrap(True)

        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(16, 16, 16, 12)
        lay.setSpacing(12)
        lay.addLayout(top)
        lay.addWidget(tabs, 1)
        lay.addWidget(self.usage)
        self.setCentralWidget(body)
        self.show_mode()
        if SETTINGS_NOTE:
            self.append(SETTINGS_NOTE)
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
        self.set_status("Running", "waiting")
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
        env = read_text(ROOT / ".env") if (ROOT / ".env").exists() else ""
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

    def request_rewards(self):
        """Ask the helper (it holds the Twitch sign-in) for the channel's rewards; the answer is @REWARDS."""
        if not self.proc:
            return False
        self.proc.write(b"rewards" + bytes([10]))
        return True

    def show_app_rewards(self, rewards):
        while self.app_rewards_row.count():
            w = self.app_rewards_row.takeAt(0).widget()
            if w:
                w.deleteLater()
        if not rewards:
            self.app_rewards_box.hide()
            return
        note = QLabel("Made by StalkerTalker on your channel:")
        note.setObjectName("secondary")
        self.app_rewards_row.addWidget(note)
        for rw in rewards:
            btn = QPushButton(f"Delete «{rw['title']}»")
            btn.setToolTip("Removes this reward from your Twitch channel (asks first)")
            btn.clicked.connect(lambda _=False, r=rw: self.delete_app_reward(r))
            self.app_rewards_row.addWidget(btn)
        self.app_rewards_row.addStretch()
        self.app_rewards_box.show()

    def delete_app_reward(self, rw):
        if not self.proc:
            return
        sure = QMessageBox.question(self, "StalkerTalker", f"Delete the reward «{rw['title']}» from your Twitch "
                                    "channel? Redemptions waiting in its queue go with it. This can't be undone.")
        if sure == QMessageBox.Yes:
            self.proc.write(f"delete_reward {rw['id']}".encode() + bytes([10]))

    def send_zone(self, arg):
        """Debug: tell the helper to fire (or queue) a Zone event without a real Twitch redemption."""
        if not self.proc:
            self.zone_queue.setText("Start the helper first (Start button at the top).")
            return
        self.proc.write(f"zone {arg}\n".encode())

    def auth_done(self):
        self.auth_btn.setEnabled(True)
        self.auth_btn.setText("Authorize Twitch app")

    def stop(self):
        if not self.proc:
            return
        proc, self.proc = self.proc, None
        proc.finished.disconnect(self.on_finished)
        # Ask it to quit first: it finishes a Twitch sign-in renewal that's under way (a hard kill in the middle
        # of one cost a new sign-in), then exits. Only if it doesn't, it's killed.
        proc.write(b"quit\n")
        if not proc.waitForFinished(5000):
            proc.kill()
            proc.waitForFinished(3000)
        self.read_output_from(proc)
        self.set_status("Stopped", "off")
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
        self.set_status(f"Stopped (exit {code})", "off")
        self.toggle.setText("Start")
        self.append(f"— helper exited with code {code} —")

    def read_output(self):
        if self.proc:
            self.read_output_from(self.proc)

    def read_output_from(self, proc):
        # Output arrives in arbitrary chunks: keep the unfinished last line (and any half of a Ukrainian letter)
        # until the rest comes, so nothing is garbled and "@" status lines are never split.
        self.out_buf = getattr(self, "out_buf", b"") + bytes(proc.readAllStandardOutput())
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
            self.set_status("Game on" if on else "Waiting for S.T.A.L.K.E.R.", "live" if on else "waiting")
        elif kind == "USAGE":
            self.usage.setText(text)
        elif kind == "TWITCH":
            if not text.startswith("sign in"):  # keep the friendlier sign-in hint while waiting
                self.twitch_state.setText(f"Twitch: {text}")
            if text.startswith("on"):
                if not getattr(self, "rewards_asked", False):  # fill the reward pickers once Twitch is on
                    self.rewards_asked = self.request_rewards()
                self.twitch_code.hide()
                self.auth_done()
        elif kind == "REWARDS":
            try:
                self.settings.set_rewards(json.loads(text))
            except ValueError:
                pass
        elif kind == "APP_REWARDS":
            try:
                self.show_app_rewards(json.loads(text))
            except ValueError:
                pass
        elif kind == "REWARDS_ERROR":
            self.settings.reward_status(text)
        elif kind == "ZONE":
            try:
                rows = json.loads(text)
            except ValueError:
                rows = []
            lines = []
            for r in rows:
                when = "now (test)" if r.get("test") else "in %d:%02d" % divmod(r["in"], 60)
                lines.append(f"{when} — {r['label']} ({r['user']})")
            self.zone_queue.setText("\n".join(lines) if lines else "Nothing waiting")
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

    def set_status(self, text, dot):
        self.state.setText(text)
        self.dot.setStyleSheet(DOT[dot] + " border-radius: 4px;")

    def append(self, text):
        LOG.write(text + "\n")
        self.log.appendHtml(log_html(text))
        self.log.moveCursor(QTextCursor.End)

    def install_mod(self):
        r = subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "install_mod.ps1")],
                           capture_output=True, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        msg = (r.stdout + r.stderr).strip() or "done"
        self.append(msg)
        QMessageBox.information(self, "StalkerTalker", msg + "\n\nLoad a save in the game to pick up the changes.")

    # ------------------------------------------------------------ self-update
    def git(self, *args, timeout=120):
        """Run git in the StalkerTalker folder (no console window). Returns (ok, output)."""
        try:
            r = subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True, text=True, timeout=timeout,
                               encoding="utf-8", errors="replace",
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, str(exc)
        return r.returncode == 0, (r.stdout + r.stderr).strip()

    def update_self(self):
        """git pull, then whatever the update needs: new settings, packages, game mod, a restart."""
        if not (ROOT / ".git").exists():
            QMessageBox.information(self, "StalkerTalker", "This copy wasn't installed with git, so it can't update "
                                    "itself.\n\nDownload the new version from github.com/Kroll410/cop-talker "
                                    "(Code → Download ZIP) and unpack it over this folder; your settings.ini, .env "
                                    "and memories stay.")
            return
        ok, before = self.git("rev-parse", "HEAD")
        if not ok:
            QMessageBox.warning(self, "StalkerTalker", f"git isn't available here:\n{before}")
            return
        self.append("— updating from GitHub —")
        was_running = self.proc is not None
        self.stop()
        ok, out = self.git("pull", "--ff-only")
        self.append(out or "(no output)")
        if not ok:
            QMessageBox.warning(self, "StalkerTalker", "Update failed:\n\n" + out[-800:] + "\n\nIf it says your "
                                "local changes would be overwritten, you changed StalkerTalker's own files here.")
            if was_running:
                self.start()
            return
        _, after = self.git("rev-parse", "HEAD")
        if after == before:
            if "up to date" not in out.lower():
                self.append("Already up to date.")
            if was_running:
                self.start()
            return
        _, changed = self.git("diff", "--name-only", before, after)
        changed = changed.splitlines()
        done = [f"Updated: {before[:7]} → {after[:7]} ({len(changed)} files)"]
        note = ensure_settings(ROOT)
        if note:
            done.append(note)
        if "requirements.txt" in changed:
            self.append("Updating Python packages (a minute)...")
            r = subprocess.run([str(PYTHON), "-m", "pip", "install", "-q", "-r", str(ROOT / "requirements.txt")],
                               capture_output=True, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            done.append("Python packages updated" if r.returncode == 0 else "Package update failed: "
                        + (r.stderr or r.stdout).strip()[-300:])
        if any(f.startswith("mod/") for f in changed):
            r = subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "install_mod.ps1")],
                               capture_output=True, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            done.append("Game mod reinstalled: LOAD A SAVE in the game to use it" if r.returncode == 0
                        else "Game mod install failed: " + (r.stdout + r.stderr).strip()[-300:])
        for line in done:
            self.append(line)
        if "companion/app.py" in changed or "companion/settings_file.py" in changed:
            QMessageBox.information(self, "StalkerTalker", "\n".join(done) + "\n\nThe window itself was updated: "
                                    "it restarts now.")
            subprocess.Popen([str(ROOT / ".venv" / "Scripts" / "pythonw.exe"), str(ROOT / "companion" / "app.py")],
                             cwd=str(ROOT))
            QApplication.quit()
            return
        QMessageBox.information(self, "StalkerTalker", "\n".join(done))
        self.start()

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
