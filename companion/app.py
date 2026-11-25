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
from PySide6.QtWidgets import (QApplication, QComboBox, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
                               QTabWidget, QVBoxLayout, QWidget)

ROOT = Path(__file__).resolve().parent.parent
SETTINGS = ROOT / "settings.ini"
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from settings_file import ensure_settings, read_text  # noqa: E402  (settings.ini from the example, plus new options)
import redeems  # noqa: E402  (every Twitch redeem the app knows, one list)

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
QLabel#name {{ color: {TEXT}; font-weight: 600; }}
QFrame#hair {{ background: {HAIR}; border: none; }}
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
        "FUN_LEVEL": "Humour", "SLURS": "Slurs", "QUIRK_CHANCE": "Quirks", "MEMORY_KEEP": "Talks kept word for word",
        "CLEAR_MEMORY": "Clear memory on start", "OUTSIDE_TALK": "Talk about life outside", "NEWS_FEEDS": "News feeds",
        "TWITCH_ENABLED": "Twitch", "TWITCH_SOURCE": "Source", "TWITCH_CHANNEL": "Channel",
        "TWITCH_QUEUE_MAX": "Messages waiting, at most", "TWITCH_REWARD": "Speech reward title",
        "TWITCH_UNPREFIXED": "Messages without $ or %", "TWITCH_DISTANCE": "NPC distance",
        "TWITCH_SHOW_NAME": "Nick in the PDA", "TWITCH_LINKS": "Viewer keeps his NPC", "TWITCH_BLOCKED": "Blocked words",
        "LLM_PROVIDER": "Replies by", "CLAUDE_MODEL": "Claude model", "CLAUDE_CLI": "Claude Code program",
        "GEMINI_MODEL": "Gemini model", "GEMINI_SMART_MODEL": "Gemini model for deals",
        "STT_MODELS": "Speech recognition"}
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

    def __init__(self, on_save):
        super().__init__()
        self.on_save = on_save
        self.fields = {}
        self.hints = {}  # key -> the notes above it in settings.ini (the Redeems tab shows its keys' notes too)
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
                if s == "[Twitch]":
                    where = QLabel("Rewards, the Zone event's gap and pack, and the test buttons are on the Redeems tab.")
                    where.setObjectName("muted")
                    self.form.addRow(where)
                hint = []
            elif "=" in s and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", s.split("=", 1)[0].strip()):
                key, value = s.split("=", 1)
                key, value = key.strip(), value.strip()
                text = " ".join(hint)
                hint = []
                self.hints[key] = text
                if key in redeems.KEYS:  # shown on the Redeems tab, which adopts them (adopt)
                    continue
                m = re.search(r"options:\s*([\w, ]+)$", text)
                if m:
                    field = QComboBox()
                    field.addItems([o.strip() for o in m.group(1).split(",") if o.strip()])
                    field.setCurrentText(value)
                    text = text[:m.start()].strip(" .")
                else:
                    field = QLineEdit(value)
                field.setToolTip(text)
                field.setMaximumWidth(240 if isinstance(field, QComboBox) else 720 if key in WIDE else 360)
                label = QLabel(NICE.get(key, key.replace("_", " ").capitalize()))
                label.setToolTip(text)
                label.setContentsMargins(0, 6, 0, 0)  # level with the text inside the field
                cell = QWidget()
                cell.setMaximumWidth(720)
                box = QVBoxLayout(cell)
                box.setContentsMargins(0, 0, 0, 0)
                box.setSpacing(4)
                box.addWidget(field)
                note = QLabel((html.escape(text.rstrip(". ")) + "&nbsp;&nbsp;" if text else "")
                              + span(key, "#6f6c5f", mono=True))
                note.setObjectName("muted")
                note.setWordWrap(True)
                box.addWidget(note)
                self.form.addRow(label, cell)
                self.fields[key] = field
                self.loaded[key] = self.value(key)  # what the form showed, to know later what YOU changed

    def raw(self, key, default=""):
        """A setting as settings.ini had it when the window read it."""
        for line in self.lines:
            k, sep, v = line.partition("=")
            if sep and k.strip() == key:
                return v.split(" #")[0].strip()
        return default

    def adopt(self, key, field):
        """A field another tab shows (the Redeems tab): saved with the rest, by Save on either tab."""
        self.fields[key] = field
        self.loaded[key] = self.value(key)

    def value(self, key):
        f = self.fields[key]
        if hasattr(f, "setting_value"):
            return f.setting_value()
        return f.currentText() if isinstance(f, QComboBox) else f.text().strip()

    def set_value(self, key, value):
        f = self.fields.get(key)
        if hasattr(f, "set_setting_value"):
            f.set_setting_value(value)
        elif isinstance(f, QComboBox):
            f.setCurrentText(value)
        elif f is not None:
            f.setText(value)

    def save(self):
        """Write back only the settings changed in this window, into the file as it is NOW on disk,
        so lines added to settings.ini by hand while the window was open are kept."""
        changed = {k: self.value(k) for k in self.fields if self.value(k) != self.loaded.get(k)}
        current = read_text(SETTINGS).splitlines() if SETTINGS.exists() else self.lines
        out, written = [], set()
        for line in current:
            s = line.strip()
            if "=" in s and not s.startswith(("#", "[")):
                key = s.split("=", 1)[0].strip()
                if key in changed:
                    line = f"{key}={changed[key]}"
                    written.add(key)
            out.append(line)
        out += [f"{k}={v}" for k, v in changed.items() if k not in written]  # its line was gone from the file
        SETTINGS.write_text("\n".join(out) + "\n", encoding="utf-8")
        self.lines = out
        self.loaded.update(changed)
        self.on_save()


OFF = "Off"


class RewardPicker(QComboBox):
    """A reward title from the channel's own rewards (the app only reads them), or Off. Editable, so a title can be
    typed while Twitch can't be asked (helper stopped, or a chat-mode sign-in that may not read rewards yet)."""

    def __init__(self, value):
        super().__init__()
        self.setEditable(True)
        self.lineEdit().setPlaceholderText(OFF)
        self.titles = None  # the channel's rewards once Twitch answered
        self.fill([])
        self.set_setting_value(value)

    def setting_value(self):
        text = self.currentText().strip()
        return "" if text.lower() == OFF.lower() else text

    def set_setting_value(self, value):
        value = (value or "").strip()
        if value and self.findText(value) < 0:
            self.addItem(value)
        self.setCurrentIndex(self.findText(value) if value else 0)

    def fill(self, titles):
        current = self.setting_value() if self.count() else ""
        self.blockSignals(True)
        self.clear()
        self.addItem(OFF)
        self.addItems(titles)
        self.set_setting_value(current)  # a title not on the channel (yet) stays: the helper waits for it
        self.blockSignals(False)

    def state(self):
        """(dot, words) for the row: on, off, or set but not on the channel."""
        title = self.setting_value()
        if not title:
            return "off", "Off"
        if self.titles is not None and title.lower() not in {t.lower() for t in self.titles}:
            return "waiting", "Not on the channel yet: make it on Twitch"
        return "live", "On"


class RedeemsTab(QWidget):
    """Every redeem in redeems.REDEEMS: what it does, the Twitch reward it's tied to, whether it's on, a test."""

    def __init__(self, settings, ask_rewards, send_test):
        super().__init__()
        self.settings, self.ask_rewards, self.send_test = settings, ask_rewards, send_test
        self.pickers, self.states = {}, {}
        self.zone_queue = QLabel("Nothing waiting")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 12, 0, 0)
        outer.setSpacing(12)
        head = QHBoxLayout()
        head.setContentsMargins(4, 0, 16, 0)
        head.setSpacing(12)
        intro = QLabel("Tie each redeem to a channel-points reward you made on Twitch. "
                       "The app only reads your rewards, it never adds or removes any.")
        intro.setObjectName("secondary")
        intro.setWordWrap(True)
        head.addWidget(intro, 1)
        refresh = QPushButton("Refresh rewards")
        refresh.setToolTip("Ask Twitch for the rewards on your channel")
        refresh.clicked.connect(self.refresh)
        head.addWidget(refresh, 0, Qt.AlignTop)
        outer.addLayout(head)
        self.note = QLabel("Rewards not loaded yet: they come in once Twitch is on, or press Refresh rewards")
        self.note.setObjectName("muted")
        self.note.setWordWrap(True)
        self.note.setContentsMargins(4, 0, 16, 0)
        outer.addWidget(self.note)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner = QWidget()
        self.layouts = []  # (row, its picker + Test): side by side, or stacked when the window is narrow
        self.rows = QVBoxLayout(inner)
        self.rows.setContentsMargins(4, 0, 16, 16)
        self.rows.setSpacing(0)
        for i, r in enumerate(redeems.REDEEMS):
            if i:
                line = QFrame()
                line.setObjectName("hair")
                line.setFixedHeight(1)
                self.rows.addWidget(line)
            self.rows.addWidget(self.row(r))
        self.rows.addStretch()
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)

        foot = QHBoxLayout()
        foot.addStretch()
        save = QPushButton("Save and restart")
        save.setObjectName("primary")
        save.clicked.connect(self.settings.save)
        foot.addWidget(save)
        outer.addLayout(foot)

    def row(self, r):
        box = QWidget()
        lay = QHBoxLayout(box)
        lay.setContentsMargins(0, 14, 0, 14)
        lay.setSpacing(16)
        text = QVBoxLayout()
        text.setSpacing(4)
        top = QHBoxLayout()
        top.setSpacing(8)
        dot = QLabel()
        dot.setFixedSize(8, 8)
        name = QLabel(r.name)
        name.setObjectName("name")
        state = QLabel()
        state.setObjectName("muted")
        top.addWidget(dot)
        top.addWidget(name)
        top.addSpacing(4)
        top.addWidget(state, 1)
        text.addLayout(top)
        what = QLabel(r.what)
        what.setObjectName("secondary")
        what.setWordWrap(True)
        what.setContentsMargins(16, 0, 0, 0)  # under the name, past the dot
        text.addWidget(what)
        if r.kind == "zone":
            text.addLayout(self.zone_extras(r))
        lay.addLayout(text, 1)

        picker = RewardPicker(self.settings.raw(r.key))
        picker.setFixedWidth(200)
        picker.setToolTip(f"The reward on your channel that runs it. {OFF} = none.  ({r.key})")
        picker.currentTextChanged.connect(lambda _=None, rid=r.id: self.show_state(rid))
        self.settings.adopt(r.key, picker)
        test = QPushButton("Test")
        test.setToolTip("As if a viewer redeemed it, right now. Needs the helper running and the game on."
                        + (" Queued like a real one." if r.kind == "zone" else ""))
        test.clicked.connect(lambda _=False, a="redeem" if r.kind == "zone" else r.id: self.test(a))
        right = QWidget()
        pick = QHBoxLayout(right)
        pick.setContentsMargins(0, 0, 0, 0)
        pick.setSpacing(8)
        pick.addWidget(picker)
        pick.addWidget(test)
        lay.addWidget(right, 0, Qt.AlignLeft | Qt.AlignTop)
        self.layouts.append((lay, right))
        self.pickers[r.id] = picker
        self.states[r.id] = (dot, state)
        self.show_state(r.id)
        return box

    def zone_extras(self, r):
        """The Zone event's own settings (gap, pack) and its fire-now buttons, under its description."""
        col = QVBoxLayout()
        col.setContentsMargins(16, 8, 0, 0)
        col.setSpacing(8)
        knobs = QHBoxLayout()
        knobs.setSpacing(8)
        for key, label in zip(r.extra, ("Gap, minutes", "Mutants, at most")):
            name = QLabel(label)
            name.setObjectName("secondary")
            field = QLineEdit(self.settings.raw(key))
            field.setFixedWidth(56)
            field.setToolTip(f"{self.settings.hints.get(key, '')}  ({key})".strip())
            name.setToolTip(field.toolTip())
            self.settings.adopt(key, field)
            knobs.addWidget(name)
            knobs.addWidget(field)
            knobs.addSpacing(12)
        knobs.addStretch()
        col.addLayout(knobs)
        now = QHBoxLayout()
        now.setSpacing(8)
        lead = QLabel("Fire now")
        lead.setObjectName("secondary")
        now.addWidget(lead)
        for text, arg, tip in (("Дар", "gift", "A random item in your backpack."),
                               ("Життя", "life", "A random stalker, friend or enemy."),
                               ("Дитя", "child", "Mutants come for you."),
                               ("Random", "any", "One of the three, rolled like a real redemption.")):
            btn = QPushButton(text)
            btn.setToolTip(tip + " Skips the queue.")
            btn.clicked.connect(lambda _=False, a=arg: self.test(a))
            now.addWidget(btn)
        now.addStretch()
        col.addLayout(now)
        self.zone_queue.setObjectName("muted")
        self.zone_queue.setWordWrap(True)
        col.addWidget(self.zone_queue)
        return col

    NARROW = 720  # below this the picker and Test go under the description

    def resizeEvent(self, event):
        super().resizeEvent(event)
        narrow = self.width() < self.NARROW
        for lay, right in self.layouts:
            lay.setDirection(QHBoxLayout.TopToBottom if narrow else QHBoxLayout.LeftToRight)
            lay.setSpacing(10 if narrow else 16)
            right.setContentsMargins(16 if narrow else 0, 0, 0, 0)  # under the name, past the dot

    def show_state(self, rid):
        dot, words = self.pickers[rid].state()
        if redeems.by_id(rid).kind == "speech" and dot == "live" and self.settings.raw("TWITCH_SOURCE") != "reward":
            dot, words = "waiting", "Waits for reward mode (Settings → Twitch → Source)"
        ring, label = self.states[rid]
        ring.setStyleSheet(DOT[dot] + " border-radius: 4px;")
        label.setText(words)

    def test(self, arg):
        if not self.send_test(arg):
            self.note.setText("Start the helper first (Start at the top), then test.")

    def refresh(self):
        self.note.setText("Asking Twitch..." if self.ask_rewards() else "Start the helper and sign in to Twitch first")

    def set_rewards(self, titles):
        """The channel's rewards from Twitch: offered in every picker; a chosen title stays."""
        for rid, picker in self.pickers.items():
            picker.titles = list(titles)
            picker.fill(titles)
            self.show_state(rid)
        self.note.setText(f"{len(titles)} reward(s) on the channel" if titles else "No rewards on the channel yet")


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
            "message on Twitch yourself and pick it on the <b>Redeems</b> tab as Speech; needs Affiliate/Partner.</li>"
            "<li>The app never adds rewards to your channel. You make every reward on Twitch, then tie it to what it "
            "does on the <b>Redeems</b> tab. One that isn't there is named in the status above, and the app waits "
            "for it.</li></ol>")
        guide.setOpenExternalLinks(True)
        guide.setWordWrap(True)
        guide.setMaximumWidth(760)
        tl.addWidget(self.twitch_state)
        tl.addWidget(self.twitch_queue)
        tl.addLayout(auth_row)
        tl.addWidget(self.twitch_code)
        tl.addWidget(guide)
        tl.addStretch()

        tabs = QTabWidget()
        tabs.addTab(self.log, "Log")
        self.settings = SettingsTab(self.restart)
        self.redeems = RedeemsTab(self.settings, self.request_rewards, self.send_zone)
        tabs.addTab(self.settings, "Settings")
        tabs.addTab(twitch, "Twitch")
        tabs.addTab(self.redeems, "Redeems")

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

    def send_zone(self, arg):
        """Test: the helper fires a redeem (or queues a Zone event) as if a viewer redeemed it. False: not running."""
        if not self.proc:
            return False
        self.proc.write(f"zone {arg}\n".encode())
        return True

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
                self.redeems.set_rewards(json.loads(text))
            except ValueError:
                pass
        elif kind in ("REWARDS_ERROR", "REDEEM_NOTE"):
            self.redeems.note.setText(text)
        elif kind == "ZONE":
            try:
                rows = json.loads(text)
            except ValueError:
                rows = []
            lines = []
            for r in rows:
                when = "now (test)" if r.get("test") else "in %d:%02d" % divmod(r["in"], 60)
                lines.append(f"{when} — {r['label']} ({r['user']})")
            self.redeems.zone_queue.setText("\n".join(lines) if lines else "Nothing waiting")
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
