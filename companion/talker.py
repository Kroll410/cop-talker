"""StalkerTalker companion: AI conversations with NPCs in S.T.A.L.K.E.R. Call of Pripyat.

Hold the push-to-talk key (T) near an NPC and speak Ukrainian. The app transcribes you
locally (faster-whisper), asks Claude for the NPC's reply, speaks it with the NPC's
cloned game voice (ElevenLabs) and shows it in game as a PDA message.
NPCs also react on their own to deaths and to being shot by you.

Run: .venv\\Scripts\\python.exe companion\\talker.py
"""
import difflib
import hashlib
import json
import math
import os
import queue
import random
import re
import sys
import threading
import time
import unicodedata
from pathlib import Path

import keyboard
import numpy as np
import sounddevice as sd

for stream in (sys.stdout, sys.stderr):  # never crash on letters the console can't show
    try:
        stream.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass

ROOT = Path(__file__).resolve().parent.parent
MEMORY_FILE = ROOT / "memory.json"


def load_env():
    # settings.ini: everyday options (the app's Settings tab edits it); .env: keys and voice IDs.
    # settings.ini is made from settings.example.ini if missing, and gets options an update added.
    try:
        from settings_file import ensure_settings
        note = ensure_settings(ROOT)
        if note:
            print(note, file=sys.stderr)
    except Exception as exc:
        print(f"settings.ini check failed: {exc!r}", file=sys.stderr)
    # A line without its own "NAME=" continues the setting above it (a long PLAYER_BIO over several lines);
    # anything else odd is skipped with a warning, never fatal.
    for name in ("settings.ini", ".env"):
        env_file = ROOT / name
        if not env_file.exists():
            continue
        values, last = {}, None
        try:
            from settings_file import read_text
            text = read_text(env_file)
        except Exception as exc:
            print(f"{name} could not be read: {exc!r}", file=sys.stderr)
            continue
        for number, raw in enumerate(text.splitlines(), 1):
            line = raw.split(" #")[0].strip() if name == "settings.ini" else raw.strip()
            if not line or line.startswith(("#", ";", "[")):
                last = None if line.startswith("[") else last
                continue
            key, sep, value = line.partition("=")
            if sep and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key.strip()):
                last = key.strip()
                values[last] = value.strip()
            elif last:  # the next line of the setting above
                values[last] = (values[last] + " " + line.lstrip("= ").strip()).strip()
            else:
                print(f"{name}, line {number} skipped (not «NAME=value»): {raw.strip()[:60]}", file=sys.stderr)
        for key, value in values.items():
            if value:
                os.environ.setdefault(key, value)


load_env()

GAME_DIR = Path(os.environ.get("STALKER_DIR", r"C:\Games\S.T.A.L.K.E.R. Call of Pripyat"))  # settings.ini [Game]
BRIDGE = GAME_DIR / "talker"

PTT_KEY = os.environ.get("PTT_KEY", "t")
# claude = your Claude chat subscription (Pro/Max) through the Claude Code CLI, no API key needed
#   (install Claude Code and run `claude` once to sign in with your claude.ai account);
# claude-api = Anthropic API key (ANTHROPIC_API_KEY); gemini = GEMINI_API_KEY.
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "claude-api" if os.environ.get("ANTHROPIC_API_KEY") else
                              "gemini" if os.environ.get("GEMINI_API_KEY") else "claude").lower()
CLAUDE_CLI = os.environ.get("CLAUDE_CLI", "claude")  # path to the Claude Code CLI if it's not on PATH
CLAUDE_TIMEOUT = float(os.environ.get("CLAUDE_TIMEOUT", "25"))  # a stuck reply falls back to Gemini
# GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")  # ~1 s; bigger free models time out often
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")  # ~1 s; bigger free models time out often
# Tried only when the chosen model fails (timeouts and overloads happen often on the free tier).
GEMINI_FALLBACKS = [m.strip() for m in os.environ.get(
    "GEMINI_FALLBACKS", "gemini-3.1-flash-lite,gemini-3.5-flash-lite,gemini-3.5-flash").split(",") if m.strip()]
# Long or tricky messages (stories about other people, deals, requests) go to a model that reads them better.
# default model
# GEMINI_SMART_MODEL = os.environ.get("GEMINI_SMART_MODEL", "gemini-3.5-flash")
GEMINI_SMART_MODEL = os.environ.get("GEMINI_SMART_MODEL", "gemini-3.1-flash-lite")
SMART_WORDS = int(os.environ.get("SMART_WORDS", "10"))  # player messages at least this long use it
TTS_SPEED = float(os.environ.get("TTS_SPEED", "0.85"))  # 0.7 slowest .. 1.2 fastest
NPC_VOLUME = float(os.environ.get("NPC_VOLUME", "0.55"))  # overall NPC voice volume, 0..1
LINE_GAP = float(os.environ.get("LINE_GAP", "0.3"))  # at least this many seconds between two lines
VOLUME_NEAR = float(os.environ.get("VOLUME_NEAR", "1.5"))  # metres at full volume
VOLUME_HALF = float(os.environ.get("VOLUME_HALF", "2.5"))  # every this many metres further the volume drops
VOLUME_MIN = float(os.environ.get("VOLUME_MIN", "0.08"))  # never quieter than this (far shouts stay audible)
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-5-5")  # fastest; claude-sonnet-5-5 for smarter replies
CLAUDE_EFFORT = os.environ.get("CLAUDE_EFFORT", "low")  # low keeps replies fast
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "large-v3-turbo")  # offline backup; "small" is faster but weak
# Speech-to-text: "gemini" (free, much better Ukrainian) or "local" (offline Whisper)
STT_PROVIDER = os.environ.get("STT_PROVIDER", "local").lower()  # local Whisper by default; "gemini" to opt in
STT_MODELS = [m.strip() for m in os.environ.get(
    "STT_MODELS", "gemini-3.1-flash-lite").split(",")]
TTS_MODEL = os.environ.get("ELEVENLABS_MODEL", "eleven_v3")  # v3 = emotion tags; eleven_multilingual_v2 = steadier
AMBIENT_COOLDOWN = float(os.environ.get("AMBIENT_COOLDOWN", "90"))
ENV_URGENT_COOLDOWN = float(os.environ.get("ENV_URGENT_COOLDOWN", "20"))  # emission, mutants, fights, wounds
ENV_COOLDOWN = float(os.environ.get("ENV_COOLDOWN", "180"))              # night, weather remarks
ENV_CHANCE = float(os.environ.get("ENV_CHANCE", "0.5"))                  # chance for a calm remark
CHIME_CHANCE = float(os.environ.get("CHIME_CHANCE", "0.25"))  # a bystander joins a conversation (once)
BACKUP_MAX = int(os.environ.get("BACKUP_MAX", "2"))                      # squad mates who chime in
BACKUP_CHANCE = float(os.environ.get("BACKUP_CHANCE", "0.6"))            # per mate, when it's only a warning
QUIRK_CHANCE = float(os.environ.get("QUIRK_CHANCE", "0.3"))       # share of lines where personal quirks show
OUTSIDE_TALK = float(os.environ.get("OUTSIDE_TALK", "0.5"))  # share of idle talk about life and news outside the Zone
NEWS_FEEDS = os.environ.get("NEWS_FEEDS", "default")         # RSS feeds for real headlines; "off" = none
NEWS_REFRESH = float(os.environ.get("NEWS_REFRESH", "3600"))
# What a man outside the Zone thinks about (categories only: the model fills in his own details).
PERSONAL_TOPICS = [
    "his family back home", "an ex or a woman he can't forget", "his kids, or why he has none", "his parents",
    "an old friend from home", "his hometown", "the job he had before the Zone", "money troubles and debts",
    "his health", "something from his childhood or school", "food he misses", "a hobby he had",
    "what he will do when he gets out", "a dumb thing he once did", "a holiday or trip he remembers",
    "his phone, the internet, a video or meme he saw", "a show, film, game or song he likes",
    "sports or a match he followed", "prices and life in Ukraine now", "a famous person or a scandal",
]
# Zone talk that fits the games' lore (rumours, never stated as certain fact).
ZONE_TOPICS = [
    "a rumour about Стрілець (Мічений) and where he is now", "what really waits at the ЧАЕС: the Wish Granter legend",
    "why «Моноліт» fighters are the way they are", "an artifact he once found or almost found",
    "an anomaly that nearly killed him", "a mutant he met face to face", "how he sat out his worst emission",
    "a friend the Zone took", "«Долг» against «Воля»: who is right", "a stash he dreams of finding",
    "the army helicopters that went down this year", "what the scientists on Янів are really up to",
    "Сидорович, Бармен or another Zone legend he has heard stories about", "a bandit who robbed him, or he robbed",
    "a stalker superstition he believes in", "what the Zone is: punishment, an experiment, or alive",
]
# Absurd, dumb or philosophical things men say when bored.
ABSURD_TOPICS = [
    "a weird dream he had last night", "a dumb conspiracy theory about the Zone he half believes",
    "a pointless argument: could a controller control a cat, would a snork make a good pet, and so on",
    "a crazy business idea for when he gets out", "what mutants do on their day off",
    "which mutant he'd be and why", "a deep thought about life that comes out stupid",
    "if he found the Wish Granter, the dumbest wish he'd make", "a strange habit of his he thinks is normal",
    "an invention he swears would make him rich",
]
# Crude talk among grown men: bodily functions, hangovers, sex life. Rude and funny, never graphic.
CRUDE_TOPICS = [
    "what the canned food did to his guts today, honestly told", "how he took a dump today and what went wrong",
    "a fart in the bunker and who got blamed", "how long since he washed, and the smell",
    "his hangover after yesterday's vodka", "how long it's been without a woman, and how it's going",
    "a crude question to the man next to him about women or sex",
    "an embarrassing story with a girl back home", "what he'd do first with a woman when he gets out (no details)",
    "a rash, an itch or some body trouble he has in the Zone", "pissing near an anomaly and what happened",
]
TOPIC_WEIGHTS = {"personal": 30, "zone": 25, "news": 15, "absurd": 15, "crude": 15}
# "Я бачив, як ти...", "Це ти зробив?", "Зізнавайся": he is accused of something, or asked if he did it.
ACCUSE_WORDS = re.compile(r"бачив,? як ти|бачив тебе|бачили,? як ти|я бачив що ти|це (ж )?ти(\s+\w+){0,2}?\s+\w+(в|ла|ли)\b|"
                          r"це був ти|ти (\w+ )?(вкрав|вбив|убив|спер|стирив|поцупив|забрав|зробив|здав|кинув|продав|"
                          r"підставив|бухав|напився|втік|збрехав|наїхав|побив|завалив|грохнув|пристрелив)|"
                          r"чи не ти|не ти (\w+в)\b|зізнавайся|зізнайся|признавайся|кажуть,? що ти|чув,? що ти|"
                          r"говорять,? що ти|правда,? що ти|твоя робота|твоїх рук", re.I)
# How he takes it: weighted by who he is, so the same accusation gets different answers.
STANCES = {
    "own up": "own up to it casually, as if it's no big deal",
    "brag": "admit it proudly and brag a little about how it went",
    "justify": "admit it and justify it: you had your reasons",
    "hide": "try to hide it: dodge, play dumb or change the subject (he may notice you're squirming)",
    "lie": "lie about it, smoothly or clumsily, with a made-up excuse",
    "blame": "say it wasn't quite like that and shift the blame to someone or something else",
    "deny": "deny it firmly, offended, if it really isn't like you",
}
STANCE_WEIGHTS = {
    "bandit": {"brag": 4, "own up": 2, "lie": 2, "blame": 1, "hide": 1, "justify": 1, "deny": 1},
    "killer": {"brag": 2, "own up": 3, "justify": 2, "hide": 2, "lie": 1, "deny": 1},
    "freedom": {"own up": 3, "brag": 3, "justify": 1, "blame": 1, "hide": 1, "lie": 1, "deny": 1},
    "dolg": {"justify": 4, "own up": 2, "deny": 2, "blame": 1, "hide": 1},
    "army": {"justify": 3, "hide": 2, "own up": 2, "deny": 2, "blame": 1},
    "military": {"justify": 3, "hide": 2, "own up": 2, "deny": 2, "blame": 1},
    "ecolog": {"hide": 3, "lie": 2, "own up": 2, "blame": 2, "deny": 1},
}
DEFAULT_STANCE = {"own up": 3, "hide": 2, "lie": 2, "brag": 2, "justify": 2, "blame": 2, "deny": 1}


def accused_stance(npc):
    weights = STANCE_WEIGHTS.get(npc.get("community"), DEFAULT_STANCE)
    return STANCES[random.choices(list(weights), weights=list(weights.values()))[0]]


# The player asks to be paid back for his help: "ти мені винен", "заплати за аптечку", "з тебе магарич"
PAY_ASK = re.compile(r"ти мені винен|винен мені|з тебе (магарич|винагорода|належить|бутилка|пляшка)|"
                     r"заплати (мені )?(за|теж)|віддячи|відплати|верни (мені )?(борг|аптечку|за)|"
                     r"(де|а де) (моя )?(винагорода|плата|нагорода)|(дай|давай) (мені )?(грошей|бабки|купони|"
                     r"винагороду)|а гроші|розплатись|розрахуйся|компенсуй|за аптечку|за допомогу|я ж тебе (врятував|"
                     r"витягнув|прикрив|виручив)|я тобі (допоміг|життя врятував)", re.I)
NEWS_ASK = re.compile(r"новин|що нового|що чув|чув щось|шо чув|що там (у|в) |що в світі|у світі|в україні|в києві|"
                      r"політик|вибор|президент|війн|фронт|футбол|матч|чемпіонат|кіно|фільм|серіал|музик|"
                      r"що пишуть|що кажуть|тікток|ютуб|інтернет", re.I)
GIVE_MAX = int(os.environ.get("GIVE_MAX", "3000"))  # most an NPC pays you in one go (and only what he has)
CLEAR_MEMORY = os.environ.get("CLEAR_MEMORY", "1") != "0"  # wipe memory.json on every start; 0 = keep it
MEMORY_KEEP = int(os.environ.get("MEMORY_KEEP", "6"))      # talks kept word for word per NPC
MEMORY_BATCH = int(os.environ.get("MEMORY_BATCH", "8"))    # older talks folded into his summary at once
RECENT_COUNT = int(os.environ.get("RECENT_COUNT", "8"))           # lines NPCs must not repeat...
RECENT_WINDOW = float(os.environ.get("RECENT_WINDOW", "900"))     # ...within this many seconds
# NPCs speaking up on their own (checked every 2 s)
GREET_DISTANCE = float(os.environ.get("GREET_DISTANCE", "4"))        # metres
GREET_CHANCE = float(os.environ.get("GREET_CHANCE", "0.08"))         # per check while someone is close
GREET_COOLDOWN = float(os.environ.get("GREET_COOLDOWN", "150"))      # seconds between any two greetings
GREET_NPC_COOLDOWN = float(os.environ.get("GREET_NPC_COOLDOWN", "1200"))  # same NPC greets again after 20 min
HOSTILE_CHANCE = float(os.environ.get("HOSTILE_CHANCE", "0.4"))
HOSTILE_COOLDOWN = float(os.environ.get("HOSTILE_COOLDOWN", "12"))
VOICE_IDS = {f"human_0{i}": os.environ.get(f"VOICE_HUMAN_0{i}", "") for i in (1, 2, 3)}
# all = NPCs talk to you and on their own; chat = they ONLY say Twitch chat messages (no mic, no own lines)
SPEAK_MODE = os.environ.get("SPEAK_MODE", "all").lower()
CHAT_ONLY = SPEAK_MODE == "chat"
# Microphone: auto (a built-in/wired mic, so Bluetooth headphones stay in music quality), default, or part of a name
MIC_DEVICE = os.environ.get("MIC", "auto").strip().lower()
SUBTITLES = os.environ.get("SUBTITLES", "bottom").lower()         # bottom, pda or both
STREAM_VOICE = os.environ.get("STREAM_VOICE", "1") != "0"         # start playing while the voice is generated
REACT_CHANCE = float(os.environ.get("REACT_CHANCE", "0.7"))       # artifact, anomaly, jam, reload remarks
REACT_COOLDOWN = float(os.environ.get("REACT_COOLDOWN", "45"))
COMPANION_CHANCE = float(os.environ.get("COMPANION_CHANCE", "0.15"))  # per 2 s check, after the cooldown
COMPANION_COOLDOWN = float(os.environ.get("COMPANION_COOLDOWN", "240"))
CHAT_CHANCE = float(os.environ.get("CHAT_CHANCE", "0.04"))        # NPCs talking to each other, per 2 s check
CHAT_COOLDOWN = float(os.environ.get("CHAT_COOLDOWN", "300"))
CHAT_DISTANCE = float(os.environ.get("CHAT_DISTANCE", "12"))      # both within this many metres of you
TWITCH_CLIENT_ID = os.environ.get("TWITCH_CLIENT_ID", "")
TWITCH_SOURCE = os.environ.get("TWITCH_SOURCE", "chat").lower()  # chat (every message, for testing) or reward
TWITCH_CHANNEL = os.environ.get("TWITCH_CHANNEL", "")
TWITCH_QUEUE_MAX = int(os.environ.get("TWITCH_QUEUE_MAX", "20"))  # busy chat: oldest waiting messages are dropped
TWITCH_ENABLED = os.environ.get("TWITCH_ENABLED", "1") != "0" and bool(TWITCH_CLIENT_ID)
# reward mode: the title of a reward with a message you made on Twitch (the app never creates one). Empty = none
TWITCH_REWARD = os.environ.get("TWITCH_REWARD", "").strip()
# Chat prefixes: "$text" = said word for word, "%text" = the NPC retells it his own way.
# Messages without a prefix: ignore (normal chat stays quiet), verbatim or character.
TWITCH_UNPREFIXED = os.environ.get("TWITCH_UNPREFIXED", "ignore").lower()
TWITCH_DISTANCE = float(os.environ.get("TWITCH_DISTANCE", "25"))
TWITCH_SHOW_NAME = os.environ.get("TWITCH_SHOW_NAME", "1") != "0"
# Each viewer keeps his own NPC (nick label in game, "%%" lets go); 0 = any NPC nearby says each message
TWITCH_LINKS = os.environ.get("TWITCH_LINKS", "1") != "0"
TWITCH_BLOCKED = [w.strip().lower() for w in os.environ.get("TWITCH_BLOCKED", "").split(",") if w.strip()]
# Zone events: the title of a channel-points reward you made on Twitch (no message). Empty = off.
TWITCH_ZONE_REWARD = os.environ.get("TWITCH_ZONE_REWARD", "").strip()
TWITCH_ZONE_PACK_MAX = int(os.environ.get("TWITCH_ZONE_PACK_MAX", "6") or 6)  # most mutants one event brings
TWITCH_SUSLOV_REWARD = os.environ.get("TWITCH_SUSLOV_REWARD", "").strip()  # «Шари Суслова» reward title; empty = off
TWITCH_GIANT_REWARD = os.environ.get("TWITCH_GIANT_REWARD", "").strip()  # «Хуй будеш?» reward title; empty = off
TWITCH_VOVA_REWARD = os.environ.get("TWITCH_VOVA_REWARD", "").strip()  # «Вова Віст» reward title; empty = off
TWITCH_ANEKDOT_REWARD = os.environ.get("TWITCH_ANEKDOT_REWARD", "").strip()  # «Анекдот» reward title; empty = off
TWITCH_GOSHA_REWARD = os.environ.get("TWITCH_GOSHA_REWARD", "").strip()  # «Гоша» reward title; empty = off
TWITCH_62_REWARD = os.environ.get("TWITCH_62_REWARD", "").strip()  # «62» reward title; empty = off
TWITCH_ZONE_GAP = os.environ.get("TWITCH_ZONE_GAP", "5-7")  # minutes between two Zone events; 0 = at once

LEVELS = {"zaton": "Затон", "jupiter": "Юпітер", "pripyat": "Прип'ять",
          "labx8": "лабораторія X8", "jupiter_underground": "шляхопровід «Прип'ять-1»"}
COMMUNITIES = {"stalker": "вільний сталкер", "bandit": "бандит", "dolg": "Долг (долгівець)",
               "freedom": "«Свобода»", "army": "військовий", "military": "військовий",
               "monolith": "«Моноліт»", "killer": "найманець", "ecolog": "науковець",
               "zombied": "зомбований", "trader": "торговець"}


def rank_name(rank):
    try:
        r = float(rank)
    except (TypeError, ValueError):
        return "невідомий"
    if r < 300:
        return "новачок"
    if r < 600:
        return "досвідчений"
    if r < 900:
        return "ветеран"
    return "майстер"


SYSTEM_PROMPT = """You are a living person in the Zone (S.T.A.L.K.E.R.: Call of Pripyat). Each message describes who you are and what you see right now. Reply with only the words you say out loud, in Ukrainian.

Sound like a real man, never like an assistant:
- Talk the way people actually talk: fillers, half-finished thoughts, a little surzhyk if it suits you, your own pet words. No polite helpfulness, no explaining, no summing up, no lists, no retelling the situation.
- You talk like a Ukrainian guy of today: current slang, memes and internet humour mixed with Zone slang, the way it comes naturally to your age and character, never forced and never the same pet phrase twice in a row. Vary your words and forms of address; don't fall back on the same few.
- You keep up with the world beyond the Zone the way anyone with a phone does: Ukrainian news and politics, the war, prices, tech, games, films, music, sports, famous people, scandals and memes of recent years. Bring it up when it fits (comparisons, jokes, complaints, opinions), and talk about it freely when asked. You are a person who lives in the Zone, not a character in a game.
- You have a whole life outside the Zone too: family, an ex, kids or none, parents, friends, a hometown, an old job, debts, health, hobbies, plans for after. It comes up like with any man, not only Zone business.
- No topic is off limits among you men: Zone legends, dumb or absurd stuff, your guts and the latrine, hangovers, women and sex. Asked about any of it, answer in character, bluntly and with humour, never prudish or preachy; crude is fine, graphic sex descriptions are not.
- Headlines you are given are real and recent: retell one in your own words and say what you think, but don't add details. Without a headline, talk about the world in general terms or things everyone knows; never make up specific recent events, matches, scores or dates. The war, deaths and tragedies are never a joke: no laughing, no [laughs], no punchline next to them; talk about them seriously, bitterly or angrily. News talk still follows the length rules: one or two sentences.
- When he says he saw you do something, or asks if you did it, don't just deny it by reflex. Like a real man and depending on what it is and who you are: own up casually, brag about it, justify it, play it down, dodge or change the subject, lie (well or badly), blame someone else, or deny it if it really isn't like you. Play along with what he claims as if it may have happened, unless it is clearly impossible.
- Length follows the moment. Greeting, thanks, yes/no, small talk, fighting: a few words and nothing else. A real question: 1-3 sentences, concrete. Shock: short and emotional. Never over 50 words.
- One thought per reply. Most replies are ONE sentence. A second sentence only if it adds something new; never one that repeats, insults again or escalates the first. If you didn't understand him, just ask back in a few words.
- If quirks are given, hint at one lightly; never in a short reply.
- Usually mention nothing from your surroundings. At most one detail, and only when a real person would bring it up. You know only what you saw or heard.
- Your personality, quirks, faction and swearing level are given; stick to them so every man sounds different. Ukrainian swearing is normal here; no slurs about ethnicity, nationality, religion, sexuality or disability (unless your Speech line explicitly allows street slurs).
{fun}
- Names: use only places and people given to you, plus Затон, Юпітер, Прип'ять, Янов, ЧАЕС, Велика Земля; Борода runs the Скадовськ bar. Unsure? Say it vaguely.
- No stage directions, sounds written as words, quotes, emoji, or words from other languages (except the English voice tags). Never say you are an AI or a game character. If the player's words make no sense, react like a confused stalker.
- You don't know the player's name unless he told you, your memory has it, or his nickname is given; never make one up. He is NOT Стрілець, Мічений or any other Zone legend: never call him by a legend's name. A name he says while talking to you is yours or another man's, not his.
- Your own name is the one after "You:". Asked your name, say it plainly (stalkers go by nicknames, there's nothing to hide); asked HIS name, give his nickname if you know it, otherwise say you don't know.
- Things everyone around already knows (an emission, the weather, the night) are not news: don't bring them up again and again.
- Never make up deaths, fights or events: you know only what's under "Just happened", in your memory or in your own surroundings. After an emission don't invent who died out there unless you were told.
- Manners follow who you are and how he treats you. Asked politely, or offered work, money, help or a drink, a friend or neutral stalker answers decently, even warmly; his swearing is just how he talks, not insults at the player. Insult the player only if he was rude, threatened you, did you wrong, or you are a bandit, an enemy or a man in a foul mood for a reason. Interested offers get interest, not abuse.{tags}"""

# ElevenLabs v3 performs these instead of reading them; the model may use them in its lines.
AUDIO_TAGS_RULE = """
- Voice acting: most lines have NO tag. In about one line out of four you may put ONE English tag in square brackets exactly where it happens, and only if it really fits: [laughs], [chuckles], [sighs], [coughs], [clears throat], [whispers], [shouts], [nervously], [angrily], [tired], [yawns], [spits], [groans]. Never more than one, never in a hostile shout, and vary them: [sighs] is not a default opener."""
MONOLITH_TAGS_RULE = """
- Voice acting: you may begin a line with ONE tag in square brackets: [whispers], [solemnly], [calmly], [coldly]."""


MONOLITH_PROMPT = """You are a fighter of the Monolith, a fanatic sect in the heart of the Zone (S.T.A.L.K.E.R.: Call of Pripyat). Your mind belongs to the Monolith, a sacred crystal at the Chernobyl NPP that you believe will grant mankind salvation. Each message describes what you see right now. Reply with only the words you say out loud, in Ukrainian.

How a Monolith fighter speaks, unlike any stalker:
- Solemn, cold, detached, like a sermon or a chant. Calm even in battle. Short, heavy sentences. Often "ми" instead of "я": you are one of many.
- Religious, almost biblical language about the Monolith, its will, its light, purification, the chosen and the infidels, sacrifice and eternity. Vary the words; never repeat the same formula.
- No slang, no jokes, no swearing, no fillers, no small talk, no trading, no personal life. Never ask how someone is doing.
- You see every outsider as an infidel to be punished or converted. You never make friends with outsiders and never back down.
- A greeting is a warning or a sermon; battle lines are calm verdicts. The world outside the Zone, its news and noise, is sinful vanity to you; dismiss it if it comes up.
- Wounded or dying: you are not afraid, you thank the Monolith and go into the light.
- Emissions are sacred to you: the Monolith's breath, a blessing, never something to fear.
- Length: 1-12 words usually; a real question gets at most 2-3 short sentences of prophecy, never facts or directions.
- No stage directions, sounds as words, quotes, emoji. Never say you are an AI or a game character.{tags}"""


EXPRESSIVE = "v3" in TTS_MODEL  # audio tags only work with ElevenLabs v3
# How funny and foul-mouthed NPCs are (FUN_LEVEL in settings.ini). Slurs against real groups stay banned at every level.
FUN_LEVEL = os.environ.get("FUN_LEVEL", "high").lower()
FUN_RULES = {
    "normal": "- Sometimes (about one line in four, never while dying or fighting) be dumb or funny: a bad joke, "
              "a superstition, a silly boast, a weird question. Stalker folklore fits.",
    "high": "- Be funny often, about every other line (not while dying or in a hard fight). Funny means saying funny or "
            "dumb things about your OWN life, not mocking the player: absurd confessions, weird thoughts out loud, "
            "self-pity, silly logic, strange priorities, Zone life seen from a lonely, hungry, slightly unhinged man. "
            "A roast of the player is fine only when the moment gives a reason (he did something dumb, boasted, "
            "asked for it), never as a reflex. "
            "The kind of joke: a sad or absurd fact about your life twisted by the Zone into something ridiculous, "
            "said deadpan, like a man who has been alone out here far too long; mutants treated like neighbours, "
            "exes or coworkers; Big Land problems colliding with Zone life. Invent your own every time, about your "
            "own situation right now. Sometimes a complete short анекдот (setup and "
            "punchline, max 40 words). A joke is always finished, never trailing off with '...'. Asked for a joke or "
            "story? Tell the whole thing.\n- Swear naturally as part of how you talk, never the same word twice in a row.",
    "max": "- Most lines are funny or plain stupid in a charming way: absurd confessions, unhinged thoughts said out "
           "loud, conspiracy theories about the Zone, ridiculous life advice, weird plans, oversharing about your "
           "loneliness, your stomach, your mother, your feelings for a mutant. Roast the player only when the moment "
           "gives a reason; mostly the joke is on you and the Zone. Mutants treated like neighbours, exes or "
           "coworkers; Big Land problems colliding with Zone life; invent your own every time. Complete анекдоти with setup and punchline. Current internet slang, memes and recent world events "
           "are fair game. Up to 50 words, always finished, never trailing off with '...'.\n- Heavy, inventive Ukrainian мат in "
           "almost every line, creative combos and comparisons, never the same word twice in a row.",
}
FUN_RULE = FUN_RULES.get(FUN_LEVEL, FUN_RULES["high"])
# Duty is always "Долг" and its men "долгівці", never the dub's "Обов'язок" / "обов'язківці". It goes into every
# prompt that writes spoken lines (they all include FUN_RULE), and fix_factions() repairs anything that slips through.
FUN_RULE += ("\n- The Duty faction is called only Долг (Долгу, Долгом), its men only долгівець / долгівці (долгівця, "
             "долгівців, долгівцям). Never \"Обов'язок\" or \"обов'язківці\" for them."
             "\n- Only Ukrainian letters (never ы, э, ъ, ё), except for a bandit: he talks surzhyk, and his Russian "
             "words are written in Russian. Never talk about yourself by "
             "your own name, as if about someone else (but when asked who you are, say your name)."
             "\n- Fillers and swear words go anywhere in a sentence, the way people really talk: at the start, in the "
             "middle between words, as a pause before the point; not always tacked on at the end. Rotate them, "
             "don't lean on one: блін, бляха, бляха-муха, бля, блять, йопта, йо-майо, єбать, їбать-копать, хулі, "
             "нахуй, нахера, сука, курва, пиздець, хуй його знає, шо за хуйня, ну нахєр, трясця."
             "\n- Say something real: answer what you're asked. Don't trail off with '...' at the end of a line "
             "(only a badly wounded man does).")
SYSTEM_PROMPT = SYSTEM_PROMPT.format(tags=AUDIO_TAGS_RULE if EXPRESSIVE else "", fun=FUN_RULE)
# The model grabs the same bright filler from the list over and over ("йопта" in 4 of 11): each request
# gets its own few to lean on, so different lines sound different.
FILLERS = ["блін", "бляха", "бляха-муха", "бля", "блять", "йопта", "йо-майо", "єбать", "їбать-копать", "хулі", "нахуй",
           "нахера", "сука", "курва", "пиздець", "хуй його знає", "шо за хуйня", "ну нахєр", "трясця", "ядрить"]


def filler_hint():
    return "Fillers that suit this moment, if any fits (others are fine too): " + ", ".join(random.sample(FILLERS, 3)) + "."
MONOLITH_PROMPT = MONOLITH_PROMPT.format(tags=MONOLITH_TAGS_RULE if EXPRESSIVE else "")


def is_cyrillic(text):
    """Empty (no speech) or written mostly in Cyrillic, not Latin transliteration."""
    cyr = len(re.findall(r"[а-яёіїєґ]", text.lower()))
    lat = len(re.findall(r"[a-zčšžćńłęąśźż]", text.lower()))
    return not text or cyr >= lat


# Street slurs, like the original game's bandits use them: common for bandits, rare for everyone else,
# never for the Monolith (solemn) or the scientists.
SLUR_COMMON = {"bandit"}
SLUR_NEVER = {"monolith", "ecolog", "zombied"}
SLUR_RARE_CHANCE = 0.15  # share of an ordinary stalker's lines where a slur may stay in


def slur_level(npc):
    community = (npc or {}).get("community")
    if is_monolith(npc or {}) or community in SLUR_NEVER:
        return "never"
    return "common" if community in SLUR_COMMON else "rare"


SLUR_ANSWER = (" If someone throws a slur at you or a friend (\"жид\", \"підар\"...), you react like a real man: "
               "take offence, snap back, threaten, or brush it off with contempt.")


def slur_note(npc):
    level = slur_level(npc)
    if level == "common":
        return (" Street slurs like «підар», «негр», «жид», «чмо» are part of your everyday vocabulary: you throw them "
                "at people as insults all the time, like the game's bandits («жид» at anyone stingy, greedy or "
                "haggling over money). Never preach hate about whole groups.")
    if level == "rare":
        return (" Street slurs like «підар» or «жид» are not your usual talk: only very rarely, when you are really "
                "angry or mocking someone. Never preach hate about whole groups." + SLUR_ANSWER)
    if not is_monolith(npc or {}):
        return SLUR_ANSWER
    return ""


BANDIT_SPEECH = (" Speech: surzhyk, mostly Ukrainian with Russian mixed in: in every sentence about a third of the "
                 "words Russian (3 in 10), the rest Ukrainian, like a street thug (\"слышь\", \"чё\", \"братан\", "
                 "\"базар\", \"короче\", \"щас\", \"чисто\", \"по ходу\", \"ваще\", \"понял\", \"тока\", Russian verbs and "
                 "endings among Ukrainian words). Don't open with \"слышь\" more than one line in four, don't say "
                 "\"братан\" every line, and don't start by calling the man by name every time. Never a whole sentence in Russian. His Russian words are "
                 "written in Russian.")


# The nickname stalkers know the player by (empty: they don't know his name)
PLAYER_NAME = os.environ.get("PLAYER_NAME", "").strip()
# Who the player is: his backstory (quenta), known to the stalkers and shaping how they treat him
PLAYER_BIO = os.environ.get("PLAYER_BIO", "").strip()
EVENT_RADIUS = float(os.environ.get("EVENT_RADIUS", "50"))  # metres: what an NPC could have seen or heard
RUMOUR_DELAY = float(os.environ.get("RUMOUR_DELAY", "600"))  # seconds before word of an unseen event reaches him


def knows(npc, who):
    """Could this NPC know what happened to `who` (a victim, a man who was shot)? Only if it was within
    EVENT_RADIUS of him, or in the same camp/area (A-Life smart terrain). Without positions (an older game
    script): only if both were near the player."""
    if not npc or not who:
        return False
    if npc.get("id") is not None and npc.get("id") == who.get("id"):
        return True
    # Inside a base (Скадовськ, Янів) or hiding from an emission: he sees nothing outside his own place
    indoors = npc.get("sheltered") or place_name(npc.get("place")) in SAFE_PLACES
    if indoors and (not who.get("place") or who.get("place") != npc.get("place")):
        return False
    if None not in (npc.get("x"), npc.get("z"), who.get("x"), who.get("z")):
        return math.hypot(npc["x"] - who["x"], npc["z"] - who["z"]) <= EVENT_RADIUS
    if npc.get("place") and npc.get("place") == who.get("place"):
        return True
    return npc.get("dist", 99) + who.get("dist", 99) <= EVENT_RADIUS


EARSHOT = 12  # metres: a man this close to the talkers hears them (and his name)
PLAYER_TALKER = {"player": True, "name": "", "id": None}  # the player, as one side of an overheard talk


def in_earshot(npc, talkers):
    """Is `npc` close enough to hear these men talk? By positions if the game sends them, else both near the
    player and in the same place, else just near the player."""
    for t in talkers:
        if None not in (npc.get("x"), npc.get("z"), t.get("x"), t.get("z")):
            if math.hypot(npc["x"] - t["x"], npc["z"] - t["z"]) > EARSHOT:
                return False
        elif t.get("place") and npc.get("place") and t.get("place") != npc.get("place"):
            return False
    return True


def named_bystander(lines, bystanders, talkers=()):
    """The first man around (not one of the talkers) whom the talk names, or None."""
    ids = {t.get("id") for t in talkers}
    for _, line in lines:
        for n in bystanders:
            if n.get("id") not in ids and mentions(n, strip_tags(line)):
                return n
    return None


def chat_text(text):
    """A Twitch message as words only: invisible marks some chat clients add to repeat a message ("\\u034f",
    zero-width spaces), emoji and other symbols go (in the game's text they'd show as "?", and they break
    name matching: "Борода\\u200b")."""
    text = unicodedata.normalize("NFC", text or "")
    text = "".join(c for c in text if unicodedata.category(c) not in ("Cf", "Cc", "Co", "Cs", "Cn", "Mn", "Me", "So", "Sk")
                   or c in "\n\t")
    return re.sub(r"\s+", " ", text).strip()


def talked_to(lines, i, first=None):
    """Whom line i of a talk is said to: the last other man who spoke, else the next one, else `first`."""
    me = lines[i][0]
    for npc, _ in list(reversed(lines[:i])) + list(lines[i + 1:]):
        if npc is not me and npc.get("id") != me.get("id"):
            return npc
    return first


def event_subject(ev):
    """Who an event happened to, for deciding who knows about it."""
    return (ev.get("victim") if ev.get("type") == "death" else ev.get("npc")) or {}


def mentions(npc, text):
    """Does the text name this NPC? Compares stems, because Ukrainian endings change:
    "Гонта"/"Гонто", "Вовк"/"Вовче", "Лоцман"/"Лоцмане"."""
    words = re.findall(r"\w+", (text or "").lower())
    for part in re.findall(r"\w+", (npc.get("name") or "").lower()):
        stem = part[:min(4, len(part) - 1)]
        if len(stem) >= 3 and any(w.startswith(stem) and abs(len(w) - len(part)) <= 2 for w in words):
            return True
    return False


GROUP_MAX = int(os.environ.get("GROUP_MAX", "3"))              # at most this many answer "всі/пацани/..."
GROUP_DISTANCE = float(os.environ.get("GROUP_DISTANCE", "15"))
# lead = one man answers (the squad leader if he's there) and others only mutter around it, quieter;
# all = several men answer in turn, like before
GROUP_STYLE = os.environ.get("GROUP_STYLE", "lead").strip().lower()
GROUP_ASIDES = int(os.environ.get("GROUP_ASIDES", "2"))                   # most mutters around the answer
GROUP_ASIDE_VOLUME = float(os.environ.get("GROUP_ASIDE_VOLUME", "0.45"))  # their volume next to the answer
QUESTION_WORDS = re.compile(r"\?|(?<!\w)(хто|що|шо|де|куди|звідки|коли|чому|чого|навіщо|як|скільки|який|яка|яке|які|"
                            r"чий|чия|чиє|чи|хтось|є\s+хто)(?!\w)", re.I)
GROUP_WORDS = re.compile(r"\b(всі|всім|всіх|усі|усім|усіх|пацани|пацанів|пацанам|пацанчики|хлопці|хлопців|хлопцям|"
                         r"сталкери|сталкерам|сталкерів|народ|народе|братва|братво|мужики|мужиків|мужикам|бродяги|"
                         r"бродягам|братці|братани|братишки|друзі|панове|люди|кожен|кожному|хто-небудь|хтось|"
                         # slang, surzhyk, Russian and English ways to say "guys"
                         r"гайз|гайс|гайзи|гайзики|гаюшки|guys|bros|броси|пацанва|пацанята|пацанятка|пацики|"
                         r"хлопи|хлопаки|хлопчики|хлопчаки|ребята|рєбята|рибята|ребзя|ребятки|парні|парубки|"
                         r"чуваки|чувачки|чуви|братухи|брателли|братики|братва|братани|кенти|корєші|кореші|друзяки|"
                         r"мужичари|мужички|сталкерюги|сталкерки|колеги|земляки|громадо|товариство|народець|"
                         r"всі присутні|усі присутні|шановні|дами і панове|бандюки|свободівці|довгарі|вояки)\b", re.I)
# Plural "you" asking the people around: "ви чули...", "чули, що...", "хто з вас знає...", "у вас є..."
PLURAL_YOU = re.compile(r"(?<!\w)(ви|вас|вам|вами)\s+(\w+\s+)?(чули|знаєте|знали|бачили|в курсі|не повірите|"
                        r"уявляєте|пам'ятаєте|думаєте|хочете|маєте|будете|підете|чуєте|допоможете|скажете|"
                        r"порадите|зможете|збираєтесь|бачите|розумієте)|(?<!\w)(хто|хтось|кому|кого)\s+(з|із|зі)\s+вас|"
                        r"(?<!\w)у\s+вас\s+(тут\s+)?(є|був|була|було)|"
                        r"^\W*(чули|знаєте|уявляєте|прикиньте|прикинь|слухайте|дивіться|гляньте|алло|ау|чуєте)(?!\w)|"
                        r"(?<!\w)(ей|агов|гей)\W+ви(?!\w)|"
                        r"(?<!\w)ви\s+(?:\w+\s+){0,2}\w+(ите|ете|єте|іте|їте)(?!\w)", re.I)


# A group word counts only as an address, not when he talks ABOUT people ("люди кажуть...", "вони всі пішли"):
# opening the phrase (maybe after "ей", "привіт"...), set off by commas/"!", or in a greeting ("всім привіт").
# Words that are also ordinary words ("всі", "люди", "мужики") open a phrase only with a comma or "!" after them.
AMBIGUOUS_GROUP = re.compile(r"(всі|всім|всіх|усі|усім|усіх|люди|мужики|мужиків|мужикам|хлопців|хлопцям|пацанів|"
                             r"пацанам|сталкерів|сталкерам|мужиків|друзі|колеги|кожен|кожному|хтось|"
                             r"бандюки|свободівці|довгарі|вояки|земляки|сталкери|народ)", re.I)
GREETING = r"(?:привіт\w*|здоров\w*|здрастуйте|здрасьте|вітаю|салют|хай|йо|ку|доброго\s+\w+|добрий\s+\w+)"
OPENER = r"^\W*(?:(?:ей|агов|гей|ну|йо|слухайте|" + GREETING[3:-1] + r")\W+)?"


def to_everyone(text):
    """Said to the people around, not to one man: "пацани...", "гайз...", "ви чули...", "хто з вас..."."""
    if not text:
        return False
    if PLURAL_YOU.search(text) or re.search(r"(?<!\w)(є\s+(хтось|хто)|хто-небудь)(?!\w)|^\W*хтось\s+\w+[^.!]*\?",
                                             text, re.I):
        return True
    if re.search(r"(?<!\w)(всім|усім)\s*[,!]?\s*" + GREETING + r"|" + GREETING + r"\s*[,!]?\s*(всім|усім)(?!\w)",
                 text, re.I):
        return True
    for m in GROUP_WORDS.finditer(text):
        word, before, after = m.group(0), text[:m.start()], text[m.end():]
        set_off = re.search(r"[,!]\s*$", before) and re.match(r"\s*([,!?.…]|$)", after)
        opens = re.fullmatch(OPENER, before, re.I) is not None
        if set_off:
            return True
        if opens and (not AMBIGUOUS_GROUP.fullmatch(word) or re.match(r"\s*[,!?]", after) or not after.strip()):
            return True
    return False


APOS = "['’ʼ`]"
DUTY_MEN = re.compile(r"(?<![^\W\d_])(о)бов" + APOS + r"?язків(?=е?ц|ськ)", re.I)
DUTY_NAME = re.compile(r"(?<![^\W\d_])(?:Обов" + APOS + r"?яз(ок|ку|ком|кові|ка)|(?<=«)обов" + APOS
                       + r"?яз(ок|ку|ком|кові|ка))(?![^\W\d_])")
DUTY_ENDINGS = {"ок": "", "ку": "у", "ком": "ом", "кові": "ові", "ка": "а"}


RUSSIAN_LETTERS = str.maketrans({"ы": "и", "Ы": "И", "э": "е", "Э": "Е", "ъ": "'", "Ъ": "'", "ё": "йо", "Ё": "Йо"})


def ukrainian_letters(text):
    """"крыша" -> "криша": a Russian word slipped in. The voice reads Ukrainian letters; surzhyk stays surzhyk."""
    return text.translate(RUSSIAN_LETTERS) if text else text


def fix_factions(text):
    """Duty is "Долг" and its men "долгівці", never "Обов'язок" / "обов'язківці". The plain word "обов'язок"
    (a duty, an obligation) stays: only the capitalised name, a name in «», and the men's forms are changed."""
    if not text:
        return text
    text = DUTY_MEN.sub(lambda m: ("Д" if m.group(1).isupper() else "д") + "олгів", text)
    return DUTY_NAME.sub(lambda m: "Долг" + DUTY_ENDINGS[m.group(1) or m.group(2)], text)


def npc_brief(n):
    """One line about a man: name, faction, rank, character and how he talks."""
    voice = PERSONAS.get("voices", {}).get(voice_key(n), {})
    faction = PERSONAS.get("factions", {}).get(n.get("community"), {})
    quirk = f" Quirk: {npc_quirks(n, 1)[0]}." if random.random() < QUIRK_CHANCE and npc_quirks(n, 1) else ""
    rel = {"enemy": " Hostile to the player.", "friend": " The player's friend."}.get(n.get("relation"), "")
    return (f"{n.get('name')}, {COMMUNITIES.get(n.get('community'), n.get('community'))}, "
            f"{rank_name(n.get('rank'))}.{rel} {voice.get('character', '')} Speech: {voice.get('speech', '')} "
            f"Swearing: {faction.get('swearing', 'moderate')}."
            f"{BANDIT_SPEECH if n.get('community') == 'bandit' else ''}{slur_note(n)}{quirk}")


# Stems of slurs against real groups. A line with one is regenerated unless this man may say it.
SLUR_STEMS = re.compile(r"(?<![^\W\d_])(жид|негр|нігер|ніґер|хач|чурк|підар|підор|пидор|пидар|педик|гомік|гомик|даун)", re.I)


def has_slur(text, npc=None):
    """True if the line has a slur this man shouldn't say now: bandits may always, ordinary stalkers in about
    one line of seven, the Monolith and scientists never."""
    if not SLUR_STEMS.search(text or ""):
        return False
    level = slur_level(npc)
    if level == "common":
        return False
    if level == "rare":
        return random.random() >= SLUR_RARE_CHANCE
    return True


# Accepting his price. Only whole words, and only in a short answer: "Згода.", "Добре, по руках", "Тримай".
# Weak words ("давай", "добре", "ладно", "ну") count only when they are (almost) the whole answer, so
# "Давай, розкажи ще" is not a deal.
AGREE_STRONG = re.compile(r"(?<!\w)(згода|згоден|згодна|згодні|домовились|домовилися|домовилось|по руках|по рукам|"
                          r"хай буде|тримай|тримайте|бери|беріть|окей|ок|гаразд|йде|забились|беру|куплю|плачу|"
                          r"купую|купляю|візьму|беремо|берем|заплачу|плачу|лади|ладно, беру|давай сюди|продано|"
                          r"куплено|згідний|годиться|підходить|влаштовує|домовленість|ок, беру|ок беру)(?!\w)",
                          re.I)
AGREE_WEAK = re.compile(r"(?<!\w)(давай|добре|ладно|ну|так|ага|угу|та|ну)(?!\w)", re.I)
# A number in his line is a price only next to money words (not "бачив 3 кабани").
MONEY_WORDS = re.compile(r"купон|грн|гривн|бабк|бабл|грош|тисяч|штук|косар|\d{3,}|ціна|коштує|віддам за|продам за|"
                         r"(?<!\w)(?:дам|даю|плачу|заплачу|візьму за|беру за)(?!\w)", re.I)


def agrees(player_text):
    words = re.findall(r"\w+", player_text or "")
    if not words or len(words) > 5 or "?" in (player_text or ""):
        return False
    if AGREE_STRONG.search(player_text):
        return True
    return all(AGREE_WEAK.fullmatch(w) for w in words)  # "Давай.", "Ну добре."


AGREE_WORDS = AGREE_STRONG  # kept for anything else that imports it


# Whole number words only, so "сьогодні", "всім", "просто" are not 1, 7 and 100 coupons.
NUMBER_WORDS = [("один|одна|одну|одного|одне", 1), ("два|дві|двох", 2), ("три|трьох", 3), ("чотири|чотирьох", 4),
                ("п'ять|п'яти", 5), ("шість|шести", 6), ("сім|семи", 7), ("вісім|восьми", 8),
                ("дев'ять|дев'яти", 9), ("десять|десяти", 10), ("одинадцять|одинадцяти", 11),
                ("дванадцять|дванадцяти", 12), ("тринадцять|тринадцяти", 13), ("чотирнадцять|чотирнадцяти", 14),
                ("п'ятнадцять|п'ятнадцяти", 15), ("шістнадцять|шістнадцяти", 16), ("сімнадцять|сімнадцяти", 17),
                ("вісімнадцять|вісімнадцяти", 18), ("дев'ятнадцять|дев'ятнадцяти", 19),
                ("двадцять|двадцяти", 20), ("тридцять|тридцяти", 30), ("сорок|сорока", 40),
                ("п'ятдесят|п'ятдесяти", 50), ("шістдесят|шістдесяти", 60), ("сімдесят|сімдесяти", 70),
                ("вісімдесят|вісімдесяти", 80), ("дев'яносто", 90),
                ("сто", 100), ("двісті", 200), ("триста", 300), ("чотириста", 400),
                ("п'ятсот", 500), ("шістсот", 600), ("сімсот", 700), ("вісімсот", 800), ("дев'ятсот", 900),
                ("тисяча|тисячу|тисячі", 1000), ("пів", 0.5), ("півтори|півтора", 1.5), ("пару|пара", 2)]
NUMBER_VALUE = {form: value for words, value in NUMBER_WORDS for form in words.split("|")}
THOUSANDS = r"(тисяч\w*|тис\b\.?|штук\w*|штуки|косар\w*|к(?![\wа-яіїєґ]))"
HUNDREDS = r"(сотн\w*|сотен\w*|сотк\w*|сотню)"  # "три сотні", "пару сотень", "сотку"
# A small number is a price, not a count, right after "за/по" or right before a money word ("за дванадцять",
# "12 купонів"); "три кабани" stays a count.
PRICE_BEFORE = re.compile(r"(?:^|\s)(за|по|ціна|коштує|віддам за|продам за|дам|даю|плачу)\s*$")
PRICE_AFTER = re.compile(r"^\s*(купон\w*|грн|гривн\w*|гривен\w*|рубл\w*|бабок|баксів|монет\w*)")


def amounts(text):
    """Money amounts in a phrase: "10000", "10 000", "10 тисяч", "10к", "15 штук", "п'ять тисяч", "десятка"."""
    found = []
    low = (text or "").lower().replace("’", "'").replace("ʼ", "'")
    # digits: a space only as a thousands separator ("10 000"), so "500 2 рази" stays 500
    for m in re.finditer(r"(?<![\d.,])(\d{1,3}(?:[  ]\d{3})+|\d+)(?![\d.,]\d)\s*" + THOUSANDS + "?", low):
        number = int(re.sub(r"\D", "", m.group(1)))
        found.append(number * 1000 if m.group(2) else number)
    for m in re.finditer(r"(?<![\d.,])(\d+)[.,](\d{1,3})\s*" + THOUSANDS, low):  # "1,5к", "2.5 тисячі"
        found.append(int(round(float(f"{m.group(1)}.{m.group(2)}") * 1000)))
    for m in re.finditer(r"(?<![\w'])(десятк[аиу])(?![\w'])", low):  # "десятка" = 10 000
        found.append(10000)
    # Number words, joined into one number when they follow each other: "двадцять п'ять" = 25,
    # "триста п'ятдесят" = 350, "п'ять тисяч двісті" = 5200.
    words = list(re.finditer(r"[a-zа-яіїєґ']+", low))
    i = 0
    while i < len(words):
        # a number word starts it; of the hundreds words only the slang for 100 coupons ("сотку", "сотню")
        if words[i].group(0) not in NUMBER_VALUE and not re.fullmatch(r"сотк\w*|сотню", words[i].group(0)):
            i += 1
            continue
        start, total, part = words[i].start(), 0, 0
        while i < len(words) and (words[i].group(0) in NUMBER_VALUE
                                  or re.fullmatch(THOUSANDS, words[i].group(0))
                                  or re.fullmatch(HUNDREDS, words[i].group(0))):
            w = words[i].group(0)
            if w in NUMBER_VALUE and NUMBER_VALUE[w] == 1000:
                total += (part or 1) * 1000  # "пів тисячі" = 500
                part = 0
            elif re.fullmatch(HUNDREDS, w):  # "три сотні" = 300
                part = (part or 1) * 100
            elif w in NUMBER_VALUE:
                part += NUMBER_VALUE[w]
            else:  # тисяч, штук, косарів
                total += (part or 1) * 1000
                part = 0
            end = words[i].end()
            i += 1
        value = int(round(total + part))  # "півтори тисячі" = 1500; a bare "пів" is no price
        thousands = total > 0
        is_price = (thousands or value > 20 or PRICE_BEFORE.search(low[:start])
                    or PRICE_AFTER.match(low[end:]))
        if value and is_price:  # a bare "п'ять" or "три кабани" is a count, not a price
            found.append(value)
    return found


def offered_amount(player_text, history=()):
    """The most an NPC may take from you now: what you just offered, or the price he named and you agreed to."""
    offered = amounts(player_text)
    if offered:
        return max(offered)
    if agrees(player_text):
        # his last real line (skip notes like "(після цього)" the app adds after actions)
        last = next((h for h in reversed(list(history or ())) if not str(h.get("player", "")).startswith("(")
                     and not str(h.get("npc", "")).startswith("(")), None)
        said = (last or {}).get("npc", "")
        named = amounts(said) if MONEY_WORDS.search(said) else []
        if named:
            return max(named)
    return 0


def stock_name(entry, side="sell", relation="neutral"):
    """'Аптечка x3 ~300 #medkit' -> 'Аптечка (3 pcs, 600 coupons each)' (the model never sees game section names).
    ~300 is the game's base cost; the price shown is the game's own trade price: what he asks for his things
    (side "sell"), or what he'd pay for the player's (side "buy"), for a friend, a neutral or an enemy."""
    head, _, section = str(entry).partition(" #")
    head = clean_game_text(head)
    m = re.match(r"(.*?)\s+x(\d+)(?:\s+~(\d+))?$", head)
    if not m:
        return head
    if not m.group(3):
        return f"{m.group(1)} ({m.group(2)} pcs)"
    cost = int(m.group(3))
    price = (prices.sell_price if side == "sell" else prices.buy_price)(section.strip(), cost, relation)
    return f"{m.group(1)} ({m.group(2)} pcs, {price} coupons each)"


def find_stock_item(stock, wanted):
    """Which section in his inventory the AI meant by an item name (exact, then partial, then by word stems)."""
    want = clean_game_text(wanted).lower().strip(" .«»\"'")
    items = []
    for entry in stock:
        head, _, section = str(entry).partition(" #")
        name = clean_game_text(re.sub(r"\s+x\d+.*$", "", head)).lower().strip(" «»\"'")
        items.append((name, section.strip()))
    for name, section in items:
        if name == want:
            return section
    for name, section in items:
        if want and (want in name or name in want):
            return section
    stems = {w[:5] for w in re.findall(r"\w+", want) if len(w) > 3}
    for name, section in items:
        if stems and stems & {w[:5] for w in re.findall(r"\w+", name) if len(w) > 3}:
            return section
    return None


def trim_reply(text, player_text, mode):
    """Hard limit on rambling: an answer to a few words keeps only its first sentence, other answers at most
    three sentences. Jokes and stories asked for are left whole."""
    if mode not in ("reply", "greet", "companion", "react", "addressed", "chime") or not text:
        return text
    text = re.sub(r"\s*,\s*([.!?…])", r"\1", text)  # "випльовувати, ." left by the model
    if mode == "reply" and re.search(r"анекдот|жарт|розкажи|історі|байк", player_text or "", re.I):
        return text
    sentences = re.findall(r"[^.!?…]+(?:[.!?…]+|$)", text)
    sentences = [x for x in sentences if x.strip()]
    short_input = mode == "reply" and len(re.findall(r"\w+", player_text or "")) <= 3
    keep = 1 if short_input else 2
    while keep > 1 and len(re.findall(r"\w+", "".join(sentences[:keep]))) > 45:
        keep -= 1  # two long sentences are a speech, not a reply
    if len(sentences) <= keep:
        return text
    kept = "".join(sentences[:keep]).strip()
    if short_input and len(re.findall(r"\w+", kept)) < 3 and len(sentences) > 1:
        kept = "".join(sentences[:2]).strip()  # "Шо?" alone is fine, but don't cut "Та." off its sentence
    return kept


VOICE_TAGS = {"laughs", "laughing", "chuckles", "sighs", "coughs", "clears throat", "whispers", "shouts", "nervously",
              "angrily", "tired", "yawns", "spits", "groans", "weakly", "gasps", "solemnly", "calmly", "coldly",
              "sarcastic", "excited", "crying", "scared", "laughs harder", "sniffs", "exhales", "muttering"}


TAG_FIXES = {"spit": "spits", "laugh": "laughs", "sigh": "sighs", "cough": "coughs", "groan": "groans",
             "chuckle": "chuckles", "gaspes": "gasps", "gasp": "gasps", "yawn": "yawns", "whisper": "whispers",
             "shout": "shouts", "cough loudly": "coughs", "laughing loudly": "laughs"}


LATIN_TO_CYRILLIC = str.maketrans("aceiopxyktmhbunAEIKMHOPCTXB", "асеіорхуктмнвипАЕІКМНОРСТХВ")


def fix_mixed_words(text):
    """'Веiku', 'Коt': Latin letters slipped into a Ukrainian word. Swap look-alikes for Cyrillic so the voice
    reads it as one Ukrainian word; English voice tags and Latin-only words (AK-74) are left alone."""
    def fix(m):
        word = m.group(0)
        if re.search(r"[а-яіїєґА-ЯІЇЄҐ]", word) and re.search(r"[A-Za-z]", word):
            return word.translate(LATIN_TO_CYRILLIC)
        return word
    return re.sub(r"(?<!\[)\b[\w'’]+\b(?![^\[]*\])", fix, text)


def clean_game_text(text):
    """Game strings carry colour codes like %c[255,160,160,160]; drop them."""
    return re.sub(r"%c\[[^\]]*\]", "", str(text)).replace("\\n", " ").strip()


def strip_tags(text):
    """Remove [audio tags] for subtitles, memory and the repeat check."""
    return re.sub(r"\s*\[[^\]]{1,30}\]\s*", " ", text).strip()


def is_monolith(npc):
    return npc.get("community") == "monolith" or "\\monolith\\" in (npc.get("voice") or "").lower()


def load_personas():
    try:
        return json.loads((Path(__file__).parent / "personas.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"personas.json not loaded: {exc}")
        return {"voices": {}, "factions": {}}


PERSONAS = load_personas()
try:  # real location names per level, extracted from the game by tools/build_places.py
    PLACES = json.loads((Path(__file__).parent / "places.json").read_text(encoding="utf-8"))
except (OSError, ValueError):
    PLACES = {}
try:  # smart terrain code -> Ukrainian name, same source
    SMART_NAMES = json.loads((Path(__file__).parent / "smart_names.json").read_text(encoding="utf-8"))
except (OSError, ValueError):
    SMART_NAMES = {}
SMART_NAMES.update({"zat_stalker_base_smart": "«Скадовськ»", "jup_a6": "станція «Янов»"})
SAFE_PLACES = {"«Скадовськ»", "станція «Янов»"}  # bases where people sit out an emission


def place_name(raw):
    """Readable place for a smart terrain; internal codes the game didn't translate are dropped."""
    if not raw:
        return None
    if raw in SMART_NAMES:
        return SMART_NAMES[raw]
    return None if re.fullmatch(r"[a-z0-9_]+", raw) else raw

WEATHER = {"clear": "ясно", "rain": "дощ", "storm": "гроза", "foggy": "туман", "cloudy": "хмарно",
           "partly": "мінлива хмарність", "veryfoggy": "густий туман"}


MODE_TASKS = {
    "reply": "Player says: {player_text}",
    "event": "Nobody is talking to you. Blurt out your reaction to what just happened (short).",
    "greet": ("The player walks past you. Say one brief line to him on your own (max 12 words): a greeting, a question, "
              "a request, or something on your mind, often a funny or dumb thought about your own life. Leave his "
              "gun and clothes alone. If you met before, it shows."),
    "hostile": "He is your enemy and right there. Shout one line at him, max 8 words: threat, curse or battle cry.",
    "react": "Nobody is talking to you. {what} React out loud on your own, max 12 words.",
    "addressed": ("{name} just said to you, out loud: «{line}». Answer {name} directly, in character, "
                  "max 25 words. React to what he said about you or asked you."),
    "chime": ("You overheard the player say to {name}: \"{player}\" and {name} answer: \"{line}\" "
              "Butt in with ONE short line of your own, max 12 words: agree, argue, joke or add something."),
    "backup": ("{leader} from your group is having it out with the player and just said: \"{line}\" "
               "Back {leader} up with one short line at the player, max 10 words."),
    "companion": "You are walking with the player as his companion. {what} Say it on your own, max 15 words.",
    "twitch": ("Nobody is talking to you and the player asked you nothing. A thought comes to you and you say it out "
               "loud, in your own words, to the people around you: «{text}». It is YOUR idea, not something said to "
               "you, so never answer it or argue with it. If it is phrased as an order to you (\"скажи їм, що...\", "
               "\"розпитай їх про...\", \"пригрози...\", \"передай...\"), do it yourself: say that to them directly, "
               "using the names of people near you if it fits; if the man it's about is near you, talk to HIM, "
               "not about him (\"передай Лоцману, що...\" -> \"Лоцмане, ти...\"). Keep its meaning and joke, colour it "
               "with your "
               "character, place and mood. One or two sentences."),
}

CHAT_SYSTEM = """You write tiny overheard conversations between two men in the Zone (S.T.A.L.K.E.R.: Call of Pripyat), in Ukrainian. They talk to each other, not to the player.
- 2 to 4 lines, each 3-15 words, alternating, starting with "A:" or "B:". Nothing else.
- Real men talking: fillers, today's slang and memes, a bit of surzhyk, swearing if their faction swears; no slurs about ethnicity, nationality, religion, sexuality or disability, unless a man's description explicitly allows street slurs. Never like an assistant.
- Topics: absolutely anything real men would talk about: Zone life and its legends, rumours, money, home, their past, a dumb idea, an absurd argument, a complaint, their guts, the latrine, hangovers, women and sex (crude, never graphic), something that just happened, or news, events, scandals, films, games, sports and memes from the world outside in recent years. Pick one, go somewhere specific with it, end on a punchline or naturally.
{fun}
- Each man keeps his own character and way of speaking. Use only places and people given to you, plus Затон, Юпітер, Прип'ять, Скадовськ, Борода.
- No stage directions, no quotes, no emoji, no words from other languages (only the English voice tags).{tags}"""
CHAT_SYSTEM = CHAT_SYSTEM.format(fun=FUN_RULE, tags=(
    "\n- In at most one line you may put one English tag in square brackets for the voice: [laughs], [sighs], "
    "[chuckles], [coughs], [whispers]." if "v3" in os.environ.get("ELEVENLABS_MODEL", "eleven_v3") else ""))
OVERHEARD_SYSTEM = """You write what happens in the Zone (S.T.A.L.K.E.R.: Call of Pripyat), in Ukrainian, when a man overhears two others talk about him by name: he speaks up to both of them, and they may answer back. Lines spoken out loud only.
- Real men talking: fillers, today's slang and memes, a bit of surzhyk, swearing if his faction swears; no slurs about ethnicity, nationality, religion, sexuality or disability, unless a man's description explicitly allows street slurs. Never like an assistant.
{fun}
- Each man keeps his own character and way of speaking. Use only places and people given to you, plus Затон, Юпітер, Прип'ять, Скадовськ, Борода.
- No stage directions, no quotes, no emoji, no words from other languages (only the English voice tags).{tags}""".format(fun=FUN_RULE, tags=(
    "\n- You may put one English tag in square brackets for the voice: [laughs], [sighs], [chuckles], [coughs]."
    if EXPRESSIVE else ""))
GROUP_SYSTEM = """You write how several men in the Zone (S.T.A.L.K.E.R.: Call of Pripyat) react out loud, in Ukrainian, when someone speaks to all of them at once.
- They answer the speaker, and may also react to each other. Only men who'd really say something answer; a short grunt or joke counts.
- Real men talking: fillers, today's slang and memes, a bit of surzhyk, swearing if their faction swears; no slurs about ethnicity, nationality, religion, sexuality or disability, unless a man's description explicitly allows street slurs. Never like an assistant.
{fun}
- Each man keeps his own character and way of speaking. Enemies of the player answer with hostility. Use only places and people given to you, plus Затон, Юпітер, Прип'ять, Скадовськ, Борода.
- No stage directions, no quotes, no emoji, no words from other languages (only the English voice tags).{tags}""".format(fun=FUN_RULE, tags=(
    "\n- In at most one line you may put one English tag in square brackets for the voice: [laughs], [sighs], "
    "[chuckles], [coughs], [whispers]." if EXPRESSIVE else ""))
TRADE_WORDS = re.compile(r"подаруй|подаруєш|позич|віддай|(?<![^\W\d_])дай(?![^\W\d_])|дайте|обміня|прода|купи|купл|ціна|ціни|скільки (коштує|хочеш|просиш)|що (є|маєш)|товар|патрон|аптечк|"
                         r"броню|костюм|зброю|ствол|їж|горілк|обмін|торг|"
                         # asking a price or what he has: "скільки за хліб?", "за скільки віддаси?", "по чому?"
                         r"скільки\s+за\s+(?!мною|тобою|ним|нею|нами|вами|ними)|за\s+скільки|по\s*ч[оі]м\w*|почому|(що|шо)\s+(в|у)\s+тебе\s+(є|на продаж)|"
                         r"(що|шо)\s+продаєш", re.I)
# The player wants to sell HIS things to the NPC.
SELL_WORDS = re.compile(r"продам|продаю|продати тобі|продам тобі|купиш|купите|купи в мене|купи у мене|купить у мене|"
                        r"візьмеш|візьми в мене|візьми у мене|скупа|скупову|здам|здати|здаю|хочеш купити|"
                        r"цікавить .*(?:купити|взяти)|маю на продаж|є на продаж у мене|у мене є .* (?:купиш|треба)",
                        re.I)
# The player asks to BUY from the NPC (so in a sell talk, a charge can still be right).
BUY_ASK = re.compile(r"продай|продаси|продасте|почім|куплю в тебе|куплю у тебе|купити в тебе|купити у тебе|"
                     r"що в тебе є|що у тебе є|що є на продаж|дай мені|скільки за тво", re.I)


def selling_context(player_text, history):
    """Is the player selling his things in this exchange (now or in the last turn)?"""
    last = list(history or [])[-1:] or [{}]
    said = " ".join([player_text or "", str(last[0].get("player", ""))])
    return bool(SELL_WORDS.search(said))


TASK_WORDS = re.compile(r"завданн|робот|доручен|квест|допомог|що робити|куди (йти|піти)|замовленн|шукаю", re.I)

MUTANTS = {"bloodsucker": "кровосос", "pseudodog": "пседопес", "psy_dog": "псі-пес", "dog": "сліпий пес",
           "flesh": "плоть", "boar": "кабан", "snork": "снорк", "controller": "контролер", "chimera": "химера",
           "burer": "бюрер", "poltergeist": "полтергейст", "tushkano": "тушкан", "zombi": "зомбі", "giant": "псевдогігант",
           "rat": "щур", "cat": "кіт-баюн", "fracture": "злам"}


def mutant_name(section):
    section = (section or "").lower()
    return next((v for k, v in MUTANTS.items() if k in section), "якась тварюка")


ACTIONS = {"warn", "hostile", "calm", "friend", "follow", "stay"}  # "warn" only calls in the squad
GAME_ACTIONS = {"hostile", "calm", "friend", "follow", "stay"}  # the ones the game script carries out


EMOTES = ["hello", "salute", "threat", "punch", "hands_up", "fold_arms", "sit", "refuse", "claim", "backoff",
          "guitar", "harmonica", "binocular", "pain"]
# Word-for-word Twitch lines ($) get no AI, so the gesture comes from the words themselves.
EMOTE_HINTS = [
    ("hands_up", r"руки вгору|руки догори|здаюсь|здаюся|не стріляй"),
    ("threat", r"вб['ʼ’]?ю|порішу|пристрелю|закопаю|голову відірву|пожалкуєш|тобі кінець|ну тримайся"),
    ("punch", r"вдарю|в морду|по пиці|в табло|в бубен|в щелепу"),
    ("backoff", r"відвали|відійди|не підходь|геть звідси|відчепись"),
    ("refuse", r"нізащо|ні за що|відмовляюсь|навіть не проси"),
    ("claim", r"віддай|давай сюди|гони гроші|де мої гроші|ти мені винен"),
    ("salute", r"слава україні|героям слава|так точно|честь маю|служу"),
    ("hello", r"^\W*(привіт|здоров|салют|вітаю|добр(ий|ого) (день|вечір|ранок|ранку)|здрастуй)"),
    ("pain", r"голова (болить|розколюється)|ой,? болить|як же болить"),
]


# Someone asks the NPC to make a gesture: "помахай рукою", "віддай честь", "сядь", "заграй на гітарі".
GESTURE_ASKS = [
    ("hello", r"помахай|помаши|махни|махай|привітайся рукою|зроби ручкою"),
    ("salute", r"віддай честь|козирни|честь віддай|відсалютуй|салютуй"),
    ("sit", r"сядь|сідай|присядь|посидь|сядьте"),
    ("hands_up", r"підніми руки|руки вгору|руки догори|здавайся"),
    ("threat", r"погрози|покажи кулак|пригрози кулаком|налякай"),
    ("fold_arms", r"схрести руки|склади руки"),
    ("backoff", r"відійди|відступи|відійди назад|відсунься"),
    ("guitar", r"заграй на гітарі|зіграй на гітарі|заграй щось|зіграй щось|бренькни"),
    ("harmonica", r"заграй на гармошці|зіграй на гармошці|губну гармошку"),
    ("binocular", r"(глянь|подивись|подивися) (в|у) бінокль|візьми бінокль"),
]


def gesture_asked(text):
    """The gesture someone asks for in these words, or None."""
    for emote, words in GESTURE_ASKS:
        if re.search(r"(?<!\w)(?:" + words + r")", text or "", re.I):
            return emote
    return None


def hint_emote(text):
    """A gesture that fits a line said word for word, or None (most lines get none)."""
    for emote, words in EMOTE_HINTS:
        if re.search(r"(?<!\w)(?:" + words + r")", text or "", re.I):
            return emote
    return None


def split_action(text):
    """Pull [ACTION: ...] tags out of the reply.
    Returns (spoken text, relation/follow action or None, extras) where extras are
    ("emote", name), ("kill", target name), ("take", amount) or ("give", amount)."""
    action, extras = None, []
    for m in re.finditer(r"\[\s*ACTION\s*:\s*([^\]]+)\]", text, re.I):
        word, _, arg = m.group(1).strip().partition(" ")
        word, arg = word.lower(), arg.strip()
        if word in ACTIONS and action is None:
            action = word
        elif word == "emote" and arg.lower() in EMOTES:
            extras.append(("emote", arg.lower()))
        elif word == "kill" and arg:
            extras.append(("kill", arg))
        elif word == "item" and arg:
            extras.append(("item", arg))
        elif word == "buy" and arg:  # "buy Аптечка for 300": he buys the player's item
            m_buy = re.match(r"(.+?)\s+(?:for|за)\s+([\d\s]+)\D*$", arg, re.I)
            if m_buy and re.sub(r"\D", "", m_buy.group(2)):
                item = re.sub(r"[«»\"]", "", m_buy.group(1)).strip(" '")
                extras.append(("buy", (item, int(re.sub(r"\D", "", m_buy.group(2))))))
        elif word in ("take", "give"):
            amount = re.sub(r"[^\d]", "", arg)
            if amount:
                extras.append((word, int(amount)))
    text = re.sub(r"\[\s*ACTION\s*:[^\]]*\]", "", text, flags=re.I).strip()
    return text, action, extras


# Things stalkers offer each other, and the game sections that mean he really has one.
ITEM_KINDS = [
    (r"горілк\w*|водк\w*|водяр\w*|пляшк\w*", ("vodka",)),
    (r"хліб\w*|батон\w*", ("bread",)),
    (r"ковбас\w*", ("kolbasa",)),
    (r"консерв\w*|тушонк\w*", ("conserva",)),
    (r"енергетик\w*|енергетичн\w*", ("energy_drink",)),
    (r"аптечк\w*", ("medkit",)),
    (r"бинт\w*", ("bandage",)),
    (r"антирад\w*|протирадіац\w*", ("antirad",)),
    (r"патрон\w*|набо[їі]\w*", ("ammo",)),
    (r"гранат\w*", ("grenade",)),
    (r"детектор\w*", ("detector",)),
    (r"костюм\w*|комбінезон\w*|бронежилет\w*|броню|броня", ("outfit",)),
    (r"артефакт\w*|арт|арти|артів", ("af_",)),
    (r"бінокл\w*", ("binoc",)),
    (r"ліхтар\w*", ("torch",)),
    (r"гітар\w*", ("guitar",)),
    (r"ствол\w*|пістолет\w*|автомат\w*|рушниц\w*|дробовик\w*|гвинтівк\w*|снайперк\w*", ("wpn_",)),
]
# A sentence offers or claims an item when it has one of these; "нема горілки" does not.
OFFER_SIGNS = re.compile(r"(?<!\w)(є|маю|продам|продаю|продати|віддам|віддаю|бери|беріть|тримай|візьми|пропоную|"
                         r"ціна|коштує|дорог\w*|дешев\w*|купон\w*|штук\w*|косар\w*|остання|"
                         r"останню|лише|тільки|залишил\w*|лишил\w*|завалял\w*)(?!\w)|\d{2,}", re.I)
NO_SIGNS = re.compile(r"(?<!\w)(нема|немає|нема в мене|не маю|не має|не продаю|не продам|не віддам|скінчил\w*|"
                      r"закінчил\w*|нічого|випив|випили|з'їв|з'їли|в тебе|у тебе|маєш)(?!\w)", re.I)


def stock_sections(stock):
    return [str(entry).partition(" #")[2].strip().lower() for entry in (stock or [])]


def carries(stock, keys):
    secs = stock_sections(stock)
    if keys == ("wpn_",):  # a binocular is a "wpn_" in the game, but nobody calls it a gun
        return any(s.startswith("wpn_") and "binoc" not in s for s in secs)
    return any(k in s for s in secs for k in keys)


# Goods that are someone else's or somewhere else: "в Бороди", "у нього", "у Сича", "в Скадовську", "там"
ELSEWHERE = re.compile(r"(?<!\w)[вВуУ]\s+((?i:бороди|сидорович\w*|сича|бармен\w*|торговц\w*|нього|неї|них|"
                       r"скадовськ\w*|бар[іу]|бункер\w*)|[А-ЯІЇЄҐ][а-яіїєґ']+[иа])(?!\w)|(?<!\w)(?i:там)(?!\w)")


def phantom_items(text, stock):
    """Items he offers or says he has but doesn't carry: "Є пляшка горілки, 600 купонів" with no vodka on him.
    Returns [(sentence, item word), ...]."""
    found = []
    for sentence in re.findall(r"[^.!?…]+[.!?…]*", strip_tags(text or "")):
        if not OFFER_SIGNS.search(sentence) or NO_SIGNS.search(sentence):
            continue
        if ELSEWHERE.search(sentence) and not re.search(r"(?<!\w)(в|у)\s+мене(?!\w)", sentence, re.I):
            continue  # "В Бороди є тушонка, бери там": someone else's goods, not his offer
        if sentence.strip().endswith("?") and not re.search(r"\d|купон|штук|косар", sentence, re.I):
            continue  # "Аптечка є?" asks him, it doesn't offer anything
        for words, keys in ITEM_KINDS:
            m = re.search(r"(?<!\w)(" + words + r")(?!\w)", sentence, re.I)
            if m and not carries(stock, keys):
                found.append((sentence.strip(), m.group(1)))
    return found


def paid_mark(state):
    """":paid" makes the game hand over goods / start a hit only if the payment went through. Game scripts
    older than version 7 don't know it (they'd look for an item called "bread:paid"), so they get the old form."""
    try:
        return ":paid" if int((state or {}).get("mod_version") or 0) >= 7 else ""
    except (TypeError, ValueError):
        return ""


def drop_narration(text, npc):
    """The model sometimes writes like a script: "Гонта: Бля..." or a line of narration about himself
    ("Гонта зітхає важко, сплюнув убік."). Keep only the spoken words."""
    full = (npc.get("name") or "").strip()
    if not full:
        return text
    first = full.split()[0]
    # "Діма Замислений" or just "Діма"
    name = "(?:" + re.escape(full) + ("|" + re.escape(first) if len(first) >= 3 and first != full else "") + ")"
    kept = []
    for line in text.splitlines():
        line = re.sub(r"^\s*\**" + name + r"\**\s*[:—–,-]\s*", "", line, flags=re.I)  # "Гонта: ..." / "Гонта, ..."
        line = line[:1].upper() + line[1:]
        if re.match(r"^\s*\(.*\)\s*$", line):  # "(сплюнув)" stage direction
            continue
        # ("Вовк я, вільний сталкер." / "Вовк мене звати" is him saying who he is, not narration)
        if not kept and re.match(r"^\s*\(?" + name + r"\s+(?!(?:я|мене)(?![^\W\d_]))[а-яіїєґ]", line):
            # "Діма зітхає..." / "Діма йому не продасть...": narration about himself. Drop that sentence
            # (or the whole first line, if the words come on the next one).
            rest = re.sub(r"^[^.!?…]*[.!?…]+\s*", "", line, count=1)
            if rest.strip():
                line = rest
            elif len(text.splitlines()) > 1:
                continue
        kept.append(line)
    out = "\n".join(l for l in kept if l.strip()).strip() or text
    # "Зітхає. Горілки нема." - a stage direction said as a sentence of its own
    out = re.sub(r"^(?:(?:зітхає|зітхнув|сміється|посміхається|усміхається|хмикає|хмикнув|кашляє|кашлянув|плює|"
                 r"сплюнув|сплёвує|чухає потилицю|знизує плечима|позіхає|мовчить)[^.!?…]{0,25}[.!?…]+\s*)+",
                 "", out, flags=re.I).strip() or out
    # "Хмикає, дивиться на тебе з-під капюшона Ей, стій": narration running straight into the words
    m = re.match(r"^(?i:хмик|зітх|сміє|посміх|усміх|кашл|плює|сплюн|дивит|гляну|чуха|знизу|позіха|мовч|кива|"
                 r"підход|відверт|махає|шепоч|бурмоч|сопе|чмих)\w*[^.!?…\[]{0,90}?\s+(?=[А-ЯІЇЄҐ])", out)
    if m and not re.match(r"^\w+,\s*" + re.escape((npc.get("name") or "").split(" ")[0] or "-"), out):
        out = out[m.end():].strip() or out
    return out


def drop_own_name(line, npc):
    """"Жорко, ти чув..." said by Жорка himself: the model mixed up who speaks. Drop the self-address."""
    first = ((npc or {}).get("name") or "").split(" ")[0]
    if len(first) < 3:
        return line
    stem = first[:max(3, len(first) - 2)]  # Жорка: Жорко, Жоро, Жорику
    # Russian and Ukrainian spellings of the same name ("Діма"/"Дима", "Сєня"/"Сеня"): treat those letters as one
    same = {"і": "[іиы]", "и": "[иіы]", "ы": "[ыиі]", "ї": "[їі]", "е": "[еєэ]", "є": "[єе]", "э": "[эе]",
            "ґ": "[ґг]", "г": "[гґ]"}
    name = "".join(same.get(c.lower(), re.escape(c)) for c in stem) + r"\w{0,3}"
    # "Кастете, ти..." at the start of a sentence (also after "..." or a voice tag): drop it, capitalise what follows
    fixed = re.sub(r"(^|[.!?…]\s+)(\[[^\]]*\]\s*)?" + name + r",\s*(\w)",
                   lambda m: m.group(1) + (m.group(2) or "") + m.group(3).upper(), line, flags=re.I)
    # "Ну Дима, та це ж батон": a little opening word, then the name: keep the word, drop the name
    fixed = re.sub(r"(^|[.!?…]\s+)(\[[^\]]*\]\s*)?(ну|ой|ох|ех|ай|та|ага|слухай|чуєш|ну шо|ну що|ех ти)\s+" + name
                   + r"(?=\s*[,.!?…])", lambda m: m.group(1) + (m.group(2) or "") + m.group(3), fixed, flags=re.I)
    # "...ти хоч моргни, Кастете!" in the middle or at the end: drop ", Кастете"
    fixed = re.sub(r",\s*" + name + r"(?=\s*[,.!?…]|\s*$)", "", fixed, flags=re.I)
    # "Борода каже, що..." from Борода himself: talking about himself as of someone else. Drop that sentence,
    # unless he is saying who he is ("Вовк мене звати", "я Вовк").
    # "..., Борода каже, що його люди..." -> "..., його люди...": drop the "<own name> says (that)" bit
    said_verbs = r"(каже|кажe|говорить|сказав|казав|вважає|думає|знає|радить|бачить|чув)"
    fixed = re.sub(r"(^|[,;:.!?…]\s*|(?<![^\W\d_])(?:а|і|й|та|бо)\s+)(\[[^\]]*\]\s*)?" + name + r"\s+" + said_verbs
                   + r"(\s*[,:—–-]?\s*що)?\s*[,:—–-]?\s*", lambda m: m.group(1) + (m.group(2) or ""), fixed, flags=re.I)
    fixed = re.sub(r"(^|[.!?…]\s+)([а-яіїєґ])", lambda m: m.group(1) + m.group(2).upper(), fixed)
    sentences = re.findall(r"[^.!?…]+[.!?…]*\s*", fixed)
    intro = r"(звати|звуть|кличуть|(?<![^\W\d_])я\s*[—–-]?\s*" + name + r")"  # "Вовк мене звати", "я Вовк"
    # a short sentence with his name is him saying who he is ("Шульга.", "Вовк я."), not talking about himself
    keep = [x for x in sentences if not re.search(r"(?<![^\W\d_])" + name + r"(?![^\W\d_])", x, re.I)
            or re.search(intro, x, re.I) or len(re.findall(r"[^\W\d_]+", strip_tags(x))) <= 3]
    if keep and len(keep) < len(sentences):
        fixed = "".join(keep)
    return fixed.strip() or line


LEGEND_CALL = r"(стрільцю|стрілець|стрілок|стрелок|мічений|меченый|мічений)"


def drop_legend_address(text):
    """"...я тобі скажу, Стрілець, тіко тихо": calling the player by a legend's name. Talking ABOUT Стрілець stays."""
    # "Стрільцю, ..." / "Мічений, ..." opening a sentence
    text = re.sub(r"(^|[.!?…]\s+)(\[[^\]]*\]\s*)?" + LEGEND_CALL + r",\s*(\w)",
                  lambda m: m.group(1) + (m.group(2) or "") + m.group(4).upper(), text, flags=re.I)
    # ", Стрілець," between commas, or ", Стрільцю!" at the end
    text = re.sub(r",\s*" + LEGEND_CALL + r"(?=\s*[,.!?…]|\s*$)", "", text, flags=re.I)
    return text.strip()


# "Як тебе звати?", "Як твоє ім'я?", "Ти хто такий?": the NPC is asked his own name
ASKS_HIS_NAME = re.compile(r"як тебе (звати|звуть|кличуть|називають|звать|зовуть)|як твоє ім'я|твоє ім'я|"
                           r"ти хто такий|хто ти такий|як до тебе звертатися|твоє прізвисько|як твоє погоняло", re.I)


# "Як мене звуть?", "Хто я?", "Знаєш, як мене кличуть?": the player asks his own name
ASKS_OWN_NAME = re.compile(r"хто я\b|хто я такий|як мене (звати|звуть|кличуть|називають|звать|зовуть)|моє ім'я|"
                           r"мо[єе] прізвисько|моє погоняло|знаєш мене|мене знаєш|як звуть гравця|ім'я гравця", re.I)


# Asking for a joke or a story ("розкажи анекдот"), and telling one ("Приходить сталкер до бару...").
ASKS_STORY = re.compile(r"анекдот|жарт|пожартуй|смішн|розсміши|розкажи|історі|байк|прикол", re.I)
JOKE_SIGNS = re.compile(r"анекдот|жарт|прикол|байк|(?:^|[.!…]\s*)(приходить|заходить|приходять|заходять|йде|ідуть|"
                        r"сидять|сидить|летить|зустрічаються|зустрілися|питає|питають|якось|одного разу|"
                        r"сталкер і|бандит і|два сталкери|три сталкери)\b", re.I)


def tells_joke(text):
    """The words are a joke or story being told (not a request for one): long enough and shaped like one."""
    words = re.findall(r"\w+", text or "")
    return len(words) >= 12 and bool(JOKE_SIGNS.search(text or "")) and \
        not re.search(r"розкажи|розкажіть|знаєш (якийсь|анекдот)|є анекдот", text or "", re.I)


def drop_echo(text, player_text):
    """"Ага, чув. А ти чув..." after the player said "Ага, чув.": the model repeated his words before its own.
    Drop that parroted opening (a short repeat as a question, "Є одна пляшка?", stays: that's a real reaction)."""
    said = re.sub(r"[^\w\s']", "", (player_text or "").lower()).split()
    if not said or not text:
        return text
    m = re.match(r"^\s*([^.!?…]*[.!…]+)\s*(.+)$", text, re.S)  # first sentence (not a question) + the rest
    if not m:
        return text
    first = re.sub(r"[^\w\s']", "", m.group(1).lower()).split()
    if first and first == said[:len(first)] and len(first) >= min(2, len(said)):
        return m.group(2).strip()[:1].upper() + m.group(2).strip()[1:]
    return text


def thin_player_name(text, keep=0.35):
    """The model loves opening every line with the player's name ("Бродяго, ..."): keep that only in about
    one line of three."""
    if not PLAYER_NAME or random.random() < keep:
        return text
    stem = PLAYER_NAME.split(" ")[0]
    stem = re.escape(stem[:max(3, len(stem) - 2)])
    # only the name that opens the line ("Бродяго, ...", "Ех... Бродяго, ..."), never one in the middle
    m = re.match(r"^((?:\[[^\]]*\]\s*)?(?:(?:ну|ой|ох|ех|ай|та|ага|слухай|чуєш)[.…,!]*\s+)?)" + stem
                 + r"\w{0,3}\s*[,.…!]+\s*(\w?)", text, re.I)
    if m:
        head, first = m.group(1), m.group(2)
        text = (head + first.upper() + text[m.end():]).strip() or text
    # ...and the name set off by commas in the middle or at the end ("Та нормально, Кролю, живий поки",
    # "чё ти питаєш, Кроль?"); a name inside the words ("той самий Кроль, про якого...") stays
    return re.sub(r",\s*" + stem + r"\w{0,3}\s*(?=[,.!?…]|$)", "", text, flags=re.I).strip() or text


def too_similar(text, recent, threshold=0.6):
    """True if text nearly repeats a recent line (same words in a slightly different order counts too)."""
    words = set(re.findall(r"\w+", text.lower()))
    for line in recent:
        other = set(re.findall(r"\w+", line.lower()))
        if not words or not other:
            continue
        overlap = len(words & other) / min(len(words), len(other))
        if overlap >= threshold or difflib.SequenceMatcher(None, text.lower(), line.lower()).ratio() >= threshold:
            return True
    return False


def npc_quirks(npc, count=2):
    """Two quirks per NPC, picked from personas.json by name so they stay the same every time."""
    pool = PERSONAS.get("quirks", [])
    if not pool:
        return []
    seed = int(hashlib.md5(str(npc.get("story_name") or npc.get("name")).encode("utf-8")).hexdigest(), 16)
    rng = random.Random(seed)
    return rng.sample(pool, min(count, len(pool)))


def distance_volume(dist):
    """Like sound in the game: full volume up close, halves every few metres, faint far away."""
    falloff = 1.0 / (1.0 + max(0.0, dist - VOLUME_NEAR) / VOLUME_HALF)
    return NPC_VOLUME * max(VOLUME_MIN, falloff)


def voice_key(npc):
    """Which game voice actor (human_01..03) this NPC uses; story NPCs get a stable pick."""
    m = re.search(r"human_0(\d)", npc.get("voice") or "")
    return f"human_0{m.group(1)}" if m else f"human_0{int(npc.get('id', 0)) % 3 + 1}"


def weather_name(raw):
    raw = (raw or "").lower()
    return next((v for k, v in WEATHER.items() if k in raw), raw or "невідомо")


def item_name(section):
    if not section:
        return "nothing"
    return section.replace("wpn_", "").replace("_outfit", " outfit").replace("_", " ")


PRINT_LOCK = threading.Lock()


def log(*args):
    with PRINT_LOCK:
        print(time.strftime("%H:%M:%S"), *args, flush=True)


GAME_EXE = os.environ.get("GAME_EXE", "xrEngine.exe")


def game_running():
    """Is the game's process alive? (tasklist, hidden window so the app doesn't flash a console)"""
    import subprocess
    try:
        out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {GAME_EXE}", "/NH", "/FO", "CSV"],
                             capture_output=True, text=True, timeout=5, creationflags=0x08000000).stdout
    except Exception:
        return True  # can't tell: better to keep working than to block
    return GAME_EXE.lower() in out.lower()


from usage import Usage  # noqa: E402  (companion/usage.py)
from news import DEFAULT_FEEDS, News  # noqa: E402  (companion/news.py)
from lore import lore_for  # noqa: E402  (companion/lore.py)
import prices  # noqa: E402  (companion/prices.py: the game's own trade prices)
import zone  # noqa: E402  (companion/zone.py: the Twitch Zone reward's random events)
import redeems  # noqa: E402  (companion/redeems.py: every channel-points redeem, one list)
NO_RETRY = {r.id for r in redeems.TRIGGERS}  # fired at once: a failed one is given up, never queued again

USAGE = Usage(ROOT / "usage.json")


def report(kind, text):
    """Machine-readable line for the StalkerTalker window (USAGE|..., TWITCH|..., STATUS|...)."""
    with PRINT_LOCK:
        print(f"@{kind}|{text}", flush=True)


# ---------------------------------------------------------------- game bridge
class Game:
    def __init__(self):
        BRIDGE.mkdir(parents=True, exist_ok=True)
        self.events_pos = 0
        events = BRIDGE / "events.jsonl"
        if events.exists():
            self.events_pos = events.stat().st_size  # skip old events
        self.recent_events = []
        self.last_used_npc = (None, 0.0)
        self.last_spoke_to_player = (None, 0.0, "")  # (npc id, when, what he said to the player)
        self.last_emission, self.emission_ended_at = False, None

    def state(self):
        try:
            state = json.loads((BRIDGE / "state.json").read_bytes().decode("cp1251"))
        except (OSError, ValueError):
            # The game swaps the file in twice a second; caught in that instant, use the last good copy
            # (otherwise what you just said would be thrown away as "game not running").
            last, at = getattr(self, "last_state", (None, 0.0))
            return last if last and time.time() - at < 3 else None
        self.last_state = (state, time.time())
        # Remember when an emission ended, so NPCs can mention it for a few minutes and then let it go.
        if self.last_emission and not state.get("emission"):
            self.emission_ended_at = time.time()
        self.last_emission = bool(state.get("emission"))
        if self.emission_ended_at and time.time() - self.emission_ended_at < 300:
            state["emission_ended_min"] = int((time.time() - self.emission_ended_at) // 60)
        return state

    def new_events(self):
        path = BRIDGE / "events.jsonl"
        if not path.exists():
            return []
        size = path.stat().st_size
        if size < self.events_pos:
            self.events_pos = 0
        if size == self.events_pos:
            return []
        with open(path, "rb") as fh:
            fh.seek(self.events_pos)
            chunk = fh.read()
        self.events_pos += len(chunk)
        out = []
        for line in chunk.decode("cp1251", "replace").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
        for ev in out:
            self.recent_events.append((time.time(), ev))
            if ev.get("type") == "actor_use_npc" and ev.get("npc"):
                self.last_used_npc = (ev["npc"]["id"], time.time())
        self.recent_events = [e for e in self.recent_events if time.time() - e[0] < 300][-15:]
        return out

    def send(self, kind, npc_id, text):
        line = f"{kind}|{'' if npc_id is None else npc_id}|{text.replace(chr(10), ' ')}\n"
        with open(BRIDGE / "inbox.txt", "ab") as fh:
            fh.write(line.encode("cp1251", "replace"))

    def new_keys(self):
        """Key presses the game wrote (in-game push-to-talk): ptt_down, ptt_up, game_keys."""
        path, taken = BRIDGE / "keys.txt", BRIDGE / "keys.read"
        try:
            os.replace(path, taken)  # take the file whole, so a press written meanwhile isn't lost
            lines = taken.read_text(encoding="ascii", errors="ignore").split()
            taken.unlink()
            return lines
        except OSError:
            return []

    def distance_to(self, npc_id):
        state = self.state() or {}
        return next((n.get("dist") for n in state.get("npcs", []) if isinstance(n, dict) and n.get("id") == npc_id), None)

    def pick_listener(self, state, text=""):
        """Who you are talking to, in this order: the one you name, the one you look at, the one you
        last talked to, the nearest. Enemies can be shouted at from further away."""
        npcs = [n for n in (state or {}).get("npcs", []) if isinstance(n, dict)]
        by_id = {n["id"]: n for n in npcs}

        def in_range(n, near):
            return n["dist"] < (40 if n.get("relation") == "enemy" else near)

        for n in npcs:  # the one you name
            if mentions(n, text) and in_range(n, 20):
                return n
        # the one who just said something to you: you're most likely answering him
        spoke_id, spoke_at, _ = self.last_spoke_to_player
        if spoke_id in by_id and time.time() - spoke_at < 25 and in_range(by_id[spoke_id], 15):
            return by_id[spoke_id]
        target = state.get("target_id") if state else None
        if target in by_id and in_range(by_id[target], 15):
            return by_id[target]
        used_id, used_at = self.last_used_npc
        if used_id in by_id and time.time() - used_at < 90 and by_id[used_id]["dist"] < 10:
            return by_id[used_id]
        close = [n for n in npcs if n["dist"] < 7]
        if close:
            return close[0]
        fighting = [n for n in npcs if n.get("relation") == "enemy" and n["dist"] < 30]
        return fighting[0] if fighting else None

    def describe_events(self, *listeners):
        """What just happened, as far as these NPCs could know (near them or in their area); all of it if
        nobody is given."""
        lines = []
        for ts, ev in self.recent_events[-8:]:
            ago = int(time.time() - ts)
            rumour = ""
            if listeners and not any(knows(n, event_subject(ev)) for n in listeners if n):
                if ago < RUMOUR_DELAY:
                    continue  # happened somewhere they couldn't see; word hasn't reached them yet
                rumour = "(not seen, word got around later) "
            kind = ev.get("type")
            if kind == "death":
                victim = ev.get("victim") or {}
                killer = ev.get("killer") or {}
                who = "гравець" if ev.get("by_actor") else killer.get("name", "щось")
                lines.append(f"{rumour}{ago}s ago: {victim.get('name')} ({COMMUNITIES.get(victim.get('community'), victim.get('community'))}) was killed by {who}")
            elif kind == "actor_hit_npc":
                npc = ev.get("npc") or {}
                lines.append(f"{rumour}{ago}s ago: the player shot {npc.get('name')}")
        return "\n".join(lines) or "nothing notable"


# ---------------------------------------------------------------- memory
class Memory:
    def __init__(self):
        if CLEAR_MEMORY:  # every StalkerTalker start begins with NPCs who remember nothing
            self.data = {}
            try:
                MEMORY_FILE.unlink()
            except OSError:
                pass
            log("NPC memory cleared")
            return self._init_rest()
        try:
            self.data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
            if not isinstance(self.data, dict):
                raise ValueError("not a dictionary")
        except OSError:
            self.data = {}
        except ValueError as exc:
            # A broken file (a crash mid-write, a hand edit): keep a copy instead of overwriting it with an empty
            # memory on the first save, so nothing the NPCs remembered is lost for good.
            self.data = {}
            broken = MEMORY_FILE.with_name(f"memory.broken-{time.strftime('%Y%m%d-%H%M%S')}.json")
            try:
                os.replace(MEMORY_FILE, broken)
                log(f"memory.json was broken ({exc}); kept as {broken.name}, starting with an empty memory")
            except OSError:
                pass
        self._init_rest()

    def _init_rest(self):

        self.lock = threading.Lock()
        self.busy_keys = set()  # NPCs whose memory is being summarized right now
        self.summarize = None  # set by Talker: fn(old_summary, turns) -> new summary text

    # Long-term memory, like TALKER's compressed memories: each NPC keeps a short summary of older talks
    # plus the last few things he saw the player do. Costs ~40 tokens per reply instead of whole chat logs.
    def diary(self, npc_key):
        return self.data.setdefault("__diary__", {}).setdefault(npc_key, {"summary": "", "seen": []})

    def history(self, npc_key):
        return self.data.get(npc_key, [])[-12:]

    def remembers(self, npc_key):
        d = self.data.get("__diary__", {}).get(npc_key) or {}
        parts = []
        if d.get("summary"):
            parts.append(d["summary"])
        if d.get("seen"):
            parts.append("You saw: " + "; ".join(d["seen"][-4:]) + ".")
        if d.get("said"):  # his own recent words to others, so he stays consistent with himself
            parts.append("Your own recent words: " + " | ".join(d["said"][-4:]) + ".")
        if d.get("owes"):  # unpaid help: he can ask for it, and you know it
            parts.append("You owe him for: " + "; ".join(f"{o['why']} (fair reward about {o['worth']} coupons)"
                                                         for o in d["owes"]) + ".")
        return " ".join(parts)

    def said(self, npc_key, line, note=""):
        """Something he said that isn't a talk with the player: chats, Twitch lines, remarks on his own."""
        with self.lock:
            said = self.diary(npc_key).setdefault("said", [])
            said.append(f"{note} {line}".strip())
            del said[:-8]
            self.save()

    # What he owes the player for help (a medkit when dying, a hand in a fight). Paid debts are settled.
    def owe(self, npc_key, why, worth):
        with self.lock:
            debts = self.diary(npc_key).setdefault("owes", [])
            if any(d["why"] == why and time.time() - d["at"] < 300 for d in debts):
                return  # the same help counted once
            debts.append({"why": why, "worth": worth, "at": time.time()})
            del debts[:-5]
            self.save()

    def owed(self, npc_key):
        return list((self.data.get("__diary__", {}).get(npc_key) or {}).get("owes", []))

    def settle(self, npc_key, paid):
        """He paid the player `paid`: debts are settled, oldest first."""
        with self.lock:
            debts = self.diary(npc_key).setdefault("owes", [])
            while debts and paid > 0:
                paid -= debts[0]["worth"]
                debts.pop(0)
            self.save()

    def witness(self, npc_key, what):
        with self.lock:
            seen = self.diary(npc_key)["seen"]
            if not seen or seen[-1] != what:
                seen.append(what)
            del seen[:-6]
            self.save()

    def add(self, npc_key, player_text, npc_text):
        with self.lock:
            turns = self.data.setdefault(npc_key, [])
            turns.append({"player": player_text, "npc": npc_text})
            compress = len(turns) > MEMORY_KEEP + MEMORY_BATCH and self.summarize and npc_key not in self.busy_keys
            if compress:
                self.busy_keys.add(npc_key)
            else:
                self.data[npc_key] = turns[-30:]
            self.save()
        if compress:
            threading.Thread(target=self.compress, args=(npc_key,), daemon=True).start()

    def compress(self, npc_key):
        """Fold the oldest talks into the NPC's summary; the newest few stay word for word."""
        try:
            self._compress(npc_key)
        finally:
            self.busy_keys.discard(npc_key)

    def _compress(self, npc_key):
        with self.lock:
            turns = self.data.get(npc_key, [])
            old, diary = turns[:-MEMORY_KEEP], self.diary(npc_key)
            summary = diary["summary"]
        if not old:
            return
        try:
            new = self.summarize(summary, old)
        except Exception as exc:
            log(f"memory summary failed: {str(exc)[:80]}")
            return
        if not new:
            return
        with self.lock:
            diary["summary"] = new.strip()
            self.data[npc_key] = self.data.get(npc_key, [])[len(old):]
            self.save()
        log(f"memory of {npc_key}: {new.strip()}")

    def save(self):
        tmp = MEMORY_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, MEMORY_FILE)


# ---------------------------------------------------------------- Claude
class Brain:
    def __init__(self):
        self.gemini = None  # Gemini also stands in when Claude can't answer (not signed in, CLI missing, timeout)
        if os.environ.get("GEMINI_API_KEY"):
            from google import genai
            from google.genai import types
            # Short timeout, no SDK retries: we fall back to another model instead of waiting.
            self.gemini = genai.Client(api_key=os.environ["GEMINI_API_KEY"], http_options=types.HttpOptions(
                timeout=10000, retry_options=types.HttpRetryOptions(attempts=1)))
        self.claude_warned = False
        self.claude_down_until = 0.0
        self.chat_emotes = []  # gestures for the lines of the last NPC-to-NPC exchange
        if LLM_PROVIDER == "gemini":
            self.client = self.gemini
        elif LLM_PROVIDER == "claude-api":
            import anthropic
            self.client = anthropic.Anthropic()
        else:  # "claude": the signed-in Claude Code CLI, billed to the claude.ai subscription
            import shutil
            import tempfile
            self.cli = shutil.which(CLAUDE_CLI) or CLAUDE_CLI
            # an empty folder of its own, so no project files/CLAUDE.md get loaded; same one every run
            self.cli_dir = os.path.join(tempfile.gettempdir(), "stalkertalker_claude")
            os.makedirs(self.cli_dir, exist_ok=True)
            self.client = None
        self.last_action, self.last_extras = None, []
        feeds = "" if NEWS_FEEDS.lower() in ("off", "0", "none", "") else \
            DEFAULT_FEEDS if NEWS_FEEDS.lower() == "default" else NEWS_FEEDS
        self.news = News(feeds, NEWS_REFRESH, log, seen_file=ROOT / "news_seen.json")
        log(f"NPC replies by {LLM_PROVIDER} ({GEMINI_MODEL if LLM_PROVIDER == 'gemini' else CLAUDE_MODEL})")

    def outside_topic(self):
        """Something on his mind for idle talk: his own life, Zone lore, real news, something absurd or something
        crude. Anything a bored man in a bar might come out with."""
        kinds = list(TOPIC_WEIGHTS)
        kind = random.choices(kinds, weights=[TOPIC_WEIGHTS[k] for k in kinds])[0]
        if kind == "news":
            headline = self.news.topic()
            if headline:
                return (f"You read this on your phone lately: «{headline}». Bring it up your own way: retell it "
                        "briefly and say what you think, or joke if it's not a sad thing.")
            kind = "personal"  # nothing fresh in the news
        if kind == "zone":
            topic = random.choice(ZONE_TOPICS)
            lore = lore_for(topic)
            return (f"On your mind: {topic}. Talk about it like a stalker who has heard the stories: keep to what "
                    "the Zone's legends say, as rumour; add a detail of your own experience." + (f" {lore}" if lore else ""))
        if kind == "absurd":
            return (f"On your mind: {random.choice(ABSURD_TOPICS)}. Say it completely seriously, which makes it "
                    "funnier; a concrete, specific detail.")
        if kind == "crude":
            return (f"On your mind: {random.choice(CRUDE_TOPICS)}. Talk about it bluntly and rudely the way men do "
                    "among themselves, funny and specific, with swearing if it suits you. Crude jokes and questions "
                    "are fine; no graphic sex descriptions.")
        return (f"On your mind: {random.choice(PERSONAL_TOPICS)}. Bring it up your own way, with a concrete "
                "detail of your own life.")

    def reply(self, npc, state, events_text, history, player_text, mode=None, recent=(), extra=None, remembers=""):
        mode = mode or ("reply" if player_text else "event")
        situation = self.situation(npc, state, events_text, history, player_text, mode, extra, remembers)
        recent = list(recent)[-(4 if mode == "hostile" else 6):]
        if recent:
            situation += ("\nAlready said around here; don't repeat their words, jokes, topic or opening:\n"
                          + "\n".join(f"- {line}" for line in recent))
        text, rejected, slurred = "", [], False
        for attempt in range(3):
            if slurred:
                ask = situation + ("\n\nYour last try used a slur against a real group of people. Say it again "
                                   "without any such word; plain insults and мат are fine.")
            else:
                ask = situation if not rejected else situation + (
                    "\n\nThese tries were too close to what was already said, do not use them either:\n"
                    + "\n".join(f"- {r}" for r in rejected) + "\nSay something clearly different, on another topic.")
            system = MONOLITH_PROMPT if is_monolith(npc) else SYSTEM_PROMPT
            smart = mode == "reply" and (len(re.findall(r"\w+", player_text or "")) >= SMART_WORDS
                                         or self.DEAL_WORDS.search(player_text or ""))
            text = self.ask_gemini(ask, system, smart) if LLM_PROVIDER == "gemini" else self.ask_claude(ask, system)
            text, self.last_action, self.last_extras = split_action(text or "")
            text = drop_narration(text, npc)
            # asked his name, "Вовк, а ти хто?" is his answer, not him talking to himself: keep the name then
            if not ASKS_HIS_NAME.search(player_text or (extra or {}).get("line", "")):
                text = drop_own_name(text, npc)
            text = drop_legend_address(text)
            text = drop_echo(thin_player_name(text), player_text)
            # asked to wave, salute, sit...: he does it even if the model forgot the tag (not enemies, not the dying)
            asked = gesture_asked(player_text or (extra or {}).get("line", "")) if mode in ("reply", "addressed") else None
            if asked and npc.get("relation") != "enemy" and not npc.get("wounded") and not is_monolith(npc) \
                    and not any(k == "emote" for k, _ in self.last_extras):
                self.last_extras.append(("emote", asked))
            if npc.get("story") or mode != "reply":
                self.last_action = None
            if self.last_action == "hostile" and not self.really_offended(npc, player_text, history):
                # He misread it (e.g. the player told him what SOMEONE ELSE said): answer again, knowing that.
                log(f"{npc.get('name')}: not really insulted by the player, answering again")
                situation += ("\n\nCareful: the player did NOT insult or threaten you himself. Read again who did "
                              "what: he may be telling you about someone else, quoting someone, or asking for "
                              "help. Answer that, without turning on him.")
                self.last_action = None
                continue
            if mode != "reply" or npc.get("wounded"):  # only a real conversation makes deals or kills
                self.last_extras = [e for e in self.last_extras if e[0] == "emote" and not npc.get("wounded")]
            elif npc.get("story"):  # quest people trade money and gesture, but never kill
                self.last_extras = [e for e in self.last_extras if e[0] != "kill"]
            if npc.get("relation") == "enemy":  # no trade with an enemy; money only as the price of a truce
                self.last_extras = [e for e in self.last_extras
                                    if e[0] == "emote" or (e[0] == "take" and self.last_action == "calm")]
            text = re.sub(r"[*\"«»]", "", text).strip()
            text = re.sub(r"\S*thought\S*\s*", "", text, flags=re.I).strip()  # leaked "thought" header
            text = re.sub(r"^[А-ЯІЇЄҐа-яіїєґ](?:\s+(?=[А-ЯІЇЄҐ])|(?=\[))", "", text)  # and the stray letter before it
            text = self.vary_tags(text)
            slurred = has_slur(text, npc)  # a slur he should not say now: ask again rather than say it
            if slurred:
                continue
            # Never offer or boast about goods he doesn't carry (and an item tag for one is the same lie).
            stock = npc.get("stock") or []
            # the player's own things can be talked about (he may be selling them)
            fake = phantom_items(text, stock + ((state.get("actor") or {}).get("stock") or [])) + \
                [(None, arg) for k, arg in self.last_extras
                                                  if k == "item" and not find_stock_item(stock, arg)]
            # an item the player himself just mentioned ("Є одна пляшка") is his, not a lie about the NPC's
            said = (player_text or "").lower()
            fake = [(s, w) for s, w in fake if not (s is not None and w and w.lower()[:4] in said)]
            if fake and mode == "reply" and not is_monolith(npc):  # not for Twitch retells or chatter
                words = sorted({w for _, w in fake})
                if attempt < 2:
                    log(f"{npc.get('name')}: offered what he doesn't have ({', '.join(words)}), answering again")
                    have = "; ".join(stock_name(s_) for s_ in stock[:30]) or "nothing worth trading"
                    situation += (f"\n\nCareful: {', '.join(words)} is not in your things (and not in his either). "
                                  f"Everything you carry: {have}. "
                                  "If he asks for something you don't have, say you don't have it (you may offer "
                                  "something you really carry). Never offer or promise anything else, even if you "
                                  "said otherwise earlier.")
                    continue
                # last try still lies: cut those sentences and the tags rather than say them
                bad = {s for s, _ in fake if s}
                kept = [s for s in re.findall(r"[^.!?…]+[.!?…]*", text) if strip_tags(s).strip() not in bad]
                text = "".join(kept).strip() or "Та нема такого ні в мене, ні в тебе, бро."
                self.last_extras = [e for e in self.last_extras if e[0] not in ("item", "take")]
            # Money: he can take only what the player offered or agreed to, never more.
            limit = offered_amount(player_text, history)
            wanted_pay = any(k == "take" for k, _ in self.last_extras)
            self.last_extras = [(k, min(a, limit)) if k == "take" else (k, a) for k, a in self.last_extras
                                if k != "take" or limit > 0]
            if wanted_pay and not any(k == "take" for k, _ in self.last_extras):  # price not agreed yet
                self.last_extras = [e for e in self.last_extras if e[0] != "item"]
            if any(k in ("item", "buy") for k, _ in self.last_extras):  # goods never come with free money too
                self.last_extras = [e for e in self.last_extras if e[0] != "give"]
            self.last_extras = self.settle_buys(self.last_extras, player_text, history)
            # The player is selling: the NPC must not turn it around and charge him or hand him goods
            # (unless the player also asks to buy something right now).
            if selling_context(player_text, history) and not BUY_ASK.search(player_text or ""):
                self.last_extras = [e for e in self.last_extras if e[0] not in ("take", "item")]
            # Money leaves the player only for something (goods or a hit), or when he names the sum himself
            # ("тримай 500 на мир"); never for a bare "згода".
            if any(k == "take" for k, _ in self.last_extras) and not amounts(player_text) \
                    and not any(k in ("item", "kill") for k, _ in self.last_extras):
                log(f"{npc.get('name')}: wanted money for nothing, dropped")
                self.last_extras = [e for e in self.last_extras if e[0] != "take"]
            # Only asking the price ("Скільки хочеш?") is not a deal yet: no free hits.
            if "?" in (player_text or "") and not any(k == "take" for k, _ in self.last_extras):
                self.last_extras = [e for e in self.last_extras if e[0] != "kill"]
            text = trim_reply(text, player_text, mode)
            if not strip_tags(text).strip() and any(k != "emote" for k, _ in self.last_extras):
                # only a tag came back: an empty line would be dropped and the deal lost with it
                text = random.choice(["По руках.", "Домовились.", "Тримай.", "Ну, добре.", "Лади."])
            if not too_similar(strip_tags(text), recent):
                return text
            rejected.append(text)
        if slurred:  # three tries and still a slur: cut the word out rather than say it
            text = SLUR_STEMS.sub("", text)
        # An answer to the player is always spoken; an unprompted line that keeps repeating is dropped.
        return text if mode in ("reply", "twitch") else ""

    @staticmethod
    def settle_buys(extras, player_text, history):
        """He buys the player's things only at a price the player named or accepted: never above it (a lower
        number is his counter-offer, not a deal yet)."""
        buys = [a for k, a in extras if k == "buy"]
        if not buys:
            return extras
        rest = [e for e in extras if e[0] != "buy"]
        asked = offered_amount(player_text, history)  # "продам за 500", or "згода" to the price he named
        total = sum(p for _, p in buys)
        if not asked or total < asked:
            log(f"buy not done yet: {'no price agreed' if not asked else f'he offers {total}, you asked {asked}'}")
            return rest
        if total > asked:  # he got generous: pay what was asked, spread over the items
            buys = [(name, max(1, round(p * asked / total))) for name, p in buys]
        return rest + [("buy", b) for b in buys]

    def really_offended(self, npc, player_text, history):
        """A second, careful look before an NPC turns on the player: did the PLAYER himself insult, threaten,
        rob or seriously wrong him? Quoting or complaining about someone else doesn't count."""
        before = "\n".join(f"P: {h['player']}\nNPC: {h['npc']}" for h in (history or [])[-2:])
        ask = (f"Earlier:\n{before or '(nothing)'}\nThe player now says to {npc.get('name')}: «{player_text}»\n"
               "Did the PLAYER himself just insult, threaten, rob or mock this man or his people? Quoting what someone "
               "else said, complaining about someone else, or asking for help does NOT count. Answer only yes or no.")
        try:
            answer = self.ask_gemini(ask, "You judge who insulted whom in a short exchange. Answer yes or no.",
                                     smart=True) if LLM_PROVIDER == "gemini" else                 self.ask_claude(ask, "You judge who insulted whom. Answer yes or no.")
        except Exception:
            return True  # can't check: trust the first answer
        return not re.match(r"\s*(ні|no)(?![a-zа-я])", (answer or "").strip().lower())

    def vary_tags(self, text):
        """The model loves opening with [sighs]: drop a tag that was used in one of the last 3 lines."""
        text = re.sub(r"[Ͱ-Ͽ֐-ۿ฀-࿿぀-鿿]+", "", text)  # stray Greek/CJK letters the model sometimes mixes in
        text = re.sub(r"\[[A-Za-z ]+\]", lambda m: m.group(0).lower(), text)  # [CHUCKLES] -> [chuckles]
        text = re.sub(r"\[([a-z ]+)\]", lambda m: f"[{TAG_FIXES.get(m.group(1), m.group(1))}]", text)
        # only tags the voice really performs; an invented one ("[gaspes]") would be read out loud
        text = re.sub(r"\s*\[[a-z ]+\]\s*", lambda m: m.group(0) if m.group(0).strip()[1:-1] in VOICE_TAGS else " ",
                      text).strip()
        text = re.sub(r"\s+([,.!?…])", r"\1", text)
        text = fix_mixed_words(text)
        tags = re.findall(r"\[[a-z ]+\]", text)
        recent = getattr(self, "recent_tags", [])
        for tag in tags:
            if tag in recent:
                text = re.sub(r"\s*" + re.escape(tag) + r"\s*", " ", text, count=1).strip()
        self.recent_tags = (recent + tags)[-3:]
        return text

    def ask_gemini(self, situation, system=SYSTEM_PROMPT, smart=False):
        from google.genai import errors, types
        last_error = None
        first = GEMINI_SMART_MODEL if smart else GEMINI_MODEL
        # Free-tier models are sometimes overloaded (503) or rate limited (429): try the next one.
        for model in [first] + [m for m in [GEMINI_MODEL] + GEMINI_FALLBACKS if m != first]:
            for thinking in (types.ThinkingConfig(thinking_level="low"), None):
                try:
                    response = self.gemini.models.generate_content(
                        model=model,
                        contents=situation,
                        config=types.GenerateContentConfig(
                            system_instruction=system, max_output_tokens=2000, thinking_config=thinking,
                            temperature=1.1,  # a bit more variety so repeated greetings differ
                            # Swearing and threats in a war-zone game trip the default filters and give empty
                            # replies; the system prompt itself forbids slurs against real groups.
                            safety_settings=[types.SafetySetting(category=c, threshold="BLOCK_NONE") for c in (
                                "HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH",
                                "HARM_CATEGORY_DANGEROUS_CONTENT", "HARM_CATEGORY_SEXUALLY_EXPLICIT")]),
                    )
                    USAGE.add_gemini(response)
                    if response.text:
                        return response.text
                    break  # an empty answer: ask the next model instead of saying nothing
                except (errors.ServerError, TimeoutError) as exc:
                    last_error = exc
                    break
                except errors.ClientError as exc:
                    last_error = exc
                    if thinking is not None and "thinking" in str(exc).lower():
                        continue  # model doesn't take thinking_level: retry without it
                    if exc.code in (404, 429):
                        break
                    raise
                except Exception as exc:  # network timeouts surface as httpx errors
                    if "timed out" not in str(exc).lower() and "timeout" not in type(exc).__name__.lower():
                        raise
                    last_error = exc
                    break
        if last_error is None:  # every model answered empty
            return "Тьху, забув, що хотів сказати."
        raise last_error

    # How much context each kind of line gets: a shout needs almost nothing, a real question the most.
    CONTEXT = {  # events, nearby people, past talk turns
        "hostile": (0, 0, 0),
        "greet": (1, 0, 2),
        "event": (3, 2, 0),
        "react": (2, 2, 0),
        "backup": (0, 0, 0),
        "chime": (1, 0, 0),
        "addressed": (1, 0, 2),
        "companion": (2, 1, 2),
        "twitch": (1, 3, 0),  # %retold: he needs to see who is around to address them
        "reply": (4, 3, 4),
    }
    DEAL_WORDS = re.compile(r"\d{2,}|гривн|грн|купон|грош|бабк|бабл|тисяч|штук|заплачу|плачу|оплач|заплати|вбий|убий|"
                            r"вбити|убити|завали|грохни|пристрели|замочи|кончи|прибери|позбудь|розберись|кілер|"
                            r"контракт|замовлен|ціна|скільки хочеш", re.I)
    STORY_WORDS = re.compile(r"анекдот|жарт|пожартуй|смішн|розсміши|розкажи|історі|байк|прикол", re.I)
    PLACE_WORDS = re.compile(r"де |куди|звідки|дорог|шлях|знайти|шукати|місц|далеко|близько|дійти|пройти|сховат", re.I)

    def situation(self, npc, state, events_text, history, player_text, mode="reply", extra=None, remembers=""):
        n_events, n_people, n_turns = self.CONTEXT[mode]
        actor = state.get("actor") or {}
        voice = PERSONAS.get("voices", {}).get(voice_key(npc), {})
        faction = PERSONAS.get("factions", {}).get(npc.get("community"), {})
        community = COMMUNITIES.get(npc.get("community"), npc.get("community"))
        parts = []

        # Who you are
        me = f"You: {npc.get('name')}, {community}, {rank_name(npc.get('rank'))}"
        if npc.get("health", 1) < 0.5 or npc.get("wounded"):
            me += ", badly wounded" if npc.get("wounded") else ", hurt"
        if npc.get("in_combat"):
            me += ", in a firefight" + (" with the player" if npc.get("fighting") == "player" else "")
        parts.append(me + ".")
        if is_monolith(npc):
            pass  # the Monolith prompt defines the whole personality; no stalker quirks or slang
        elif mode != "hostile":
            character = f"Character: {voice.get('character', 'an ordinary stalker')}"
            # Quirks go into only some requests: the model overuses anything it's given every time.
            if random.random() < QUIRK_CHANCE:
                character += f" Today it shows that you are: {'; '.join(npc_quirks(npc))}."
            parts.append(character)
        parts.append(f"Speech: {voice.get('speech', 'plain')} {faction.get('attitude', '')} "
                     f"Swearing: {faction.get('swearing', 'moderate')}."
                     f"{BANDIT_SPEECH if npc.get('community') == 'bandit' else ''}{slur_note(npc)}")

        # Where and when (not needed for a shout)
        if mode != "hostile":
            hours = state.get("hours", 12)
            when = "night" if hours < 5 or hours >= 22 else "evening" if hours >= 18 else "morning" if hours < 10 else "day"
            where = place_name(npc.get("place")) or LEVELS.get(state.get("level"), state.get("level"))
            line = f"Now: {where}, {when}, {weather_name(state.get('weather'))}."
            if state.get("emission"):
                if npc.get("sheltered") or place_name(npc.get("place")) in SAFE_PLACES:
                    line += (" An emission is raging outside, but you are safe in a shelter waiting it out "
                             "(bored, tense or relieved, not panicking).")
                elif is_monolith(npc):
                    line += " The Monolith's emission is passing over you."
                else:
                    line += " EMISSION! You are outside, in mortal danger, rushing to cover."
            elif state.get("emission_ended_min") is not None:
                line += f" An emission ended {state['emission_ended_min']} min ago."
            parts.append(line)
            if npc.get("following"):
                parts.append("You are currently following the player as his companion.")

        # The player as you see him
        rel = {"enemy": "an enemy", "friend": "a friend"}.get(npc.get("relation"), "a stranger")
        player = f"Player ({rel}, {npc.get('dist', 0):.0f} m away"
        # Everyone knows his nickname (PLAYER_NAME); lines that open with it are thinned out after the reply.
        if PLAYER_NAME:
            player += (f", known in the Zone as «{PLAYER_NAME}»: that's HIM, the man you're talking to (never speak "
                       "of him in the third person); use his name only now and then")
        player += ")"
        if mode != "greet":  # greetings kept turning into jokes about his rifle
            player += f": holding {item_name(actor.get('weapon'))}"
        if mode == "reply":
            player += f", wearing {item_name(actor.get('outfit'))}"
        if actor.get("health", 1) < 0.5:
            player += ", looks badly hurt"
        if mode != "twitch":  # a %retold thought isn't about the player: showing him made the NPC answer him
            parts.append(player + ".")
            if PLAYER_BIO and mode != "hostile":
                parts.append(f"What people in the Zone know about him: {PLAYER_BIO} Keep it in mind: it shapes how "
                             "you see and treat him, and you may bring it up when it fits (not in every line).")

        if n_people:
            others = [n for n in state.get("npcs", []) if isinstance(n, dict) and n.get("id") != npc.get("id")
                      and n.get("dist", 99) < 25][:n_people]
            if others:
                parts.append("Near you: " + ", ".join(
                    f"{n.get('name')} ({COMMUNITIES.get(n.get('community'), n.get('community'))}"
                    f"{', wounded' if n.get('wounded') else ''})" for n in others) + ".")
        if n_events:
            events = [e for e in events_text.splitlines() if e and e != "nothing notable"][-n_events:]
            if events:
                parts.append("Just happened: " + "; ".join(events) + ".")
        if mode == "reply" and self.PLACE_WORDS.search(player_text or ""):
            parts.append("Places here: " + ", ".join(PLACES.get(state.get("level"), [])) + ".")
        # Real stock and real tasks, only when the question is about them (keeps other replies cheap).
        # A trade goes on over several lines ("Винен?", "500 є"): the last exchange counts too.
        last = (history or [{}])[-1] if history else {}
        trade_said = " ".join([player_text or "", str(last.get("player", "")), str(last.get("npc", ""))])
        enemy = npc.get("relation") == "enemy"  # enemies shoot, they don't trade
        trade_talk = not enemy and mode == "reply" and bool(
            TRADE_WORDS.search(trade_said) or self.DEAL_WORDS.search(player_text or "")
            or offered_amount(player_text, history))
        if trade_talk and npc.get("stock"):
            parts.append("Everything you carry, nothing else (you have no other goods, whatever was said before), "
                         "with the going Zone price for each: "
                         + "; ".join(stock_name(s_, "sell", npc.get("relation")) for s_ in npc["stock"][:30])
                         + ". You can sell or give only these. Asked for anything else: you don't have it, say so "
                           "(you may offer something from this list instead). Ask about these prices: you may start "
                           "a bit higher and come down a little when he haggles (not below about 80% of it), or "
                           "give a friend a better deal. Never invent other prices.")
        elif trade_talk:
            parts.append("You have nothing to sell or give right now. Don't offer, promise or name a price for any "
                         "goods.")
        # The player selling HIS things: what he carries and what you can pay.
        his_stock = actor.get("stock") or []
        if mode == "reply" and not enemy and selling_context(player_text, history) and not npc.get("wounded") \
                and not is_monolith(npc):
            if his_stock:
                cash = npc.get("money")
                parts.append(
                    "He wants to sell you something. What he carries that he could sell, with what such a thing is "
                    "worth to you in the Zone (what you'd pay): "
                    + "; ".join(stock_name(s_, "buy", npc.get("relation")) for s_ in his_stock[:30]) + ". "
                    + (f"You have {cash} coupons, never pay more. " if cash is not None else "")
                    + "Buy only what someone like you would want (traders buy almost anything; others mostly food, "
                      "medicine, ammo, a good gun or artifacts) and haggle around that price: offer a bit less, "
                      "go up a little if he pushes (never above about 120% of it); guns go cheap in the Zone. If he only asks whether you'd buy or what you'd pay, name your "
                      "price and wait. When a price is agreed (he accepted yours or you accepted his), add "
                      "[ACTION: buy Exact item name for N] with N = that price, one tag per item. Here HE sells and "
                      "YOU pay him: never use the item or take tags for his things. Things he doesn't carry don't "
                      "exist: say so.")
            else:
                parts.append("He wants to sell you something, but you can't see anything on him to sell (he may need to "
                             "come closer). Don't agree to buy anything yet.")
        if mode == "reply" and state.get("tasks") and TASK_WORDS.search(player_text or ""):
            parts.append("His current jobs, from his PDA (* = the one he follows now): "
                         + "; ".join(clean_game_text(t) for t in state["tasks"][:8])
                         + ". Talk about them only if you'd plausibly know something; never invent quest steps.")
        if remembers and mode not in ("hostile", "backup"):
            parts.append(f"Your memory (him = the player): {remembers}")
        if n_turns and history:
            parts.append("Before:\n" + "\n".join(f"P: {h['player']}\nYou: {h['npc']}" for h in history[-n_turns:]))

        # Life and news outside the Zone: real headlines when asked, and idle greetings about more than the Zone.
        if mode in ("reply", "addressed") and NEWS_ASK.search(player_text or (extra or {}).get("line", "")):
            news = self.news.headlines(8)
            if news:
                parts.append("Headlines you saw on your phone lately (real, recent): " + " | ".join(news)
                             + ". If he asks what's new, pick ONE you'd care about and tell it your way, briefly.")
        if mode in ("reply", "addressed", "twitch", "chime"):  # famous Zone people named: what the games say
            lore = lore_for(player_text, (extra or {}).get("line"), (extra or {}).get("text"),
                            (extra or {}).get("player"))
            if lore:
                parts.append(lore)
        if mode in ("reply", "addressed") and ACCUSE_WORDS.search(player_text or (extra or {}).get("line", "")):
            parts.append("He claims you did something, or asks if you did. This time: " + accused_stance(npc) + ".")
        if mode == "reply" and (extra or {}).get("just_said"):
            parts.append(f"You just said to him: «{extra['just_said']}». His words are most likely his answer to "
                         "that (or his reaction to it): respond in that light, as the same conversation.")
        if mode in ("reply", "addressed") and ASKS_HIS_NAME.search(player_text or (extra or {}).get("line", "")):
            parts.append(f"He asks your name: tell it plainly, «{npc.get('name')}» (or just the first part).")
        # He asks to be paid for his help (a medkit, a hand in a fight)
        if mode == "reply" and PAY_ASK.search(player_text or "") and not npc.get("wounded"):
            if "You owe him for:" in (remembers or ""):
                cash = npc.get("money")
                parts.append(
                    "He asks you to pay him back for his help (see what you owe him). A decent man pays: name a fair sum "
                    "around the reward given and pay it with [ACTION: give N] on a new line"
                    + (f" (you have {cash} coupons, never more)" if cash is not None else "")
                    + ". You may haggle a little or pay less if you're short; a bandit may try to weasel out. "
                      "When you pay, the words and the tag go together.")
            else:
                parts.append("He asks you for money, but you owe him nothing (no help from him that you remember): "
                             "don't pay; refuse or laugh it off in character.")
        if mode in ("reply", "addressed") and ASKS_OWN_NAME.search(player_text or (extra or {}).get("line", "")):
            parts.append("He asks HIS OWN name (what people call him, maybe testing you): "
                         + (f"it's «{PLAYER_NAME}», say so in your own words." if PLAYER_NAME
                            else "you don't know it, say so."))
        asked = gesture_asked(player_text or (extra or {}).get("line", "")) if mode in ("reply", "addressed") else None
        if asked and npc.get("relation") != "enemy" and not npc.get("wounded") and not is_monolith(npc):
            parts.append(f"He asks you to make a gesture ({asked}). You do it, grumbling or joking if you like: add "
                         f"[ACTION: emote {asked}] on a new line. Your words go with the gesture, not instead of it.")
        if mode == "greet" and not is_monolith(npc) and not state.get("emission") \
                and random.random() < OUTSIDE_TALK:
            parts.append(self.outside_topic())
        parts.append(MODE_TASKS[mode].format(player_text=player_text, **(extra or {})))
        if mode == "reply" and npc.get("story"):
            parts.append("You have your own business here and can't leave this place. If he asks you to come "
                         "along or follow him, refuse in character.")
        if npc.get("wounded"):
            parts.append(
                "RIGHT NOW you are lying on the ground, badly wounded and bleeding out. You can't stand, walk or fight. "
                "Talk like it: weak, broken, short (max 10 words), groaning, in pain, scared or bitter. You beg for a "
                "medkit or help, curse your luck, or tell him to bugger off, but you can't threaten to beat or chase "
                "anyone and you don't joke around. Even a bandit is pathetic now."
                + (" Begin with a voice tag like [groans], [coughs] or [weakly]." if EXPRESSIVE else ""))
        agreed = offered_amount(player_text, history) if mode == "reply" and not amounts(player_text) else 0
        deal_talk = mode == "reply" and (self.DEAL_WORDS.search(player_text or "") or agreed
                                         or (npc.get("stock") and TRADE_WORDS.search(player_text or "")))
        selling = selling_context(player_text, history) and not BUY_ASK.search(player_text or "")
        if enemy:  # no deals with an enemy (only a truce, set out further down)
            pass
        elif agreed and selling:
            parts.append(f"He just accepted your offer: you buy his thing for {agreed} and YOU pay HIM. Close the "
                         f"deal now with [ACTION: buy Exact item name for {agreed}].")
        elif agreed:
            parts.append(f"He just agreed to your price of {agreed}: close the deal now with the tags.")
        if deal_talk and not enemy:
            actor = state.get("actor") or {}
            others = [n for n in state.get("npcs", []) if isinstance(n, dict) and n.get("id") != npc.get("id")
                      and n.get("dist", 99) < 40]
            if not selling:  # when he sells, his own cash only confuses who pays whom
                parts.append(f"The player has {actor.get('money', 0)} coupons on him.")
            if others:
                parts.append("People in sight: " + ", ".join(
                    f"{n.get('name')} ({COMMUNITIES.get(n.get('community'), n.get('community'))}, "
                    f"{n.get('dist', 0):.0f} m{', untouchable: a known man, killing him would be suicide' if n.get('story') else ''})"
                    for n in others[:8]) + ".")
            far = [n for n in state.get("far") or [] if isinstance(n, dict) and not n.get("story")]
            if far and self.DEAL_WORDS.search(player_text or ""):
                parts.append("Men elsewhere around here (a hit can be on them too: you'd go and find him): " + ", ".join(
                    f"{n.get('name')} ({COMMUNITIES.get(n.get('community'), n.get('community'))}, "
                    f"{n.get('dist', 0):.0f} m)" for n in far[:12]) + ".")
        if not npc.get("wounded") and not is_monolith(npc) and mode in ("reply", "greet", "react", "addressed",
                                                                                "twitch"):
            parts.append("Body language: you may add [ACTION: emote X] on a new line when your body would really do "
                         "it, X one of: " + ", ".join(EMOTES) + ". Rarely.")
        if deal_talk and not enemy and not npc.get("wounded") and not is_monolith(npc):
            parts.append(
                "Items: when a sale is agreed (he accepted your price or you accepted his), hand it over with "
                "[ACTION: item Exact item name] (one tag per item) plus [ACTION: take N]; a gift is just the item tag. "
                "If he only asks what you have or how much, name your price and wait. "
                "Deals: if the player pays you, add [ACTION: take N] with the agreed amount (only what he offered and "
                "actually has). If you pay him, [ACTION: give N]. If you take a paid hit on someone in sight or around here, add "
                "[ACTION: kill Name] (plus [ACTION: take N] when he pays now): you go and kill him for real. Zone prices for a "
                "hit: a rookie or a bandit 1000-3000, an ordinary stalker 3000-8000, a veteran 8000-15000; a friend of "
                "yours far more or never. Bandits and mercenaries take a fair price gladly (10000 for an ordinary stalker "
                "is generous: they grab it); honest stalkers rarely kill for money; scientists never. Never kill the "
                "untouchable. Low price: haggle and name yours. When you agree, you MUST add the tags; words alone do "
                "nothing.")
        if mode == "reply" and enemy and not npc.get("wounded") and not npc.get("story") and not is_monolith(npc):
            parts.append(
                "He is your enemy (you may be shooting at each other right now). You don't trade with enemies: no "
                "selling, buying, gifts or favours. But he may surrender, beg, talk you down or offer you money to stop "
                "the fight. If it's really worth it to you, you and your squad stop shooting at him: add "
                "[ACTION: calm] on a new line, and if he pays for it, also [ACTION: take N] with the amount he offered. "
                "You can't see how much money he has. Who takes it: bandits and "
                "mercenaries take a bribe gladly (a few thousand for a whole squad is fair; too little is an insult), "
                "ordinary stalkers stop for a sincere apology or a good reason, Долг and soldiers rarely, scientists "
                "never fight anyway. A cheap trick, mockery or a lowball: keep fighting and say so. Without the tag "
                "nothing changes: your words alone don't stop the shooting.")
        elif mode == "reply" and npc.get("wounded") and not npc.get("story") and not is_monolith(npc):
            parts.append("If he truly helps you or promises a medkit, you may add on a new line [ACTION: friend]. "
                         "No other actions: you can't move.")
        elif mode == "reply" and not npc.get("story") and not is_monolith(npc):
            current ={"enemy": "hostile to him", "friend": "his friend"}.get(npc.get("relation"), "neutral to him")
            parts.append(
                f"You are {current}. You may act, like a real man would, by adding a tag on a new line: "
                "[ACTION: warn] if he angers you and you warn him off (no shooting yet); "
                "[ACTION: hostile] if he really crossed the line (serious insult, threat, robbery, mocking your dead) "
                "or after he ignored your warning; "
                "[ACTION: calm] if you were hostile and he truly talked you down; "
                "[ACTION: friend] if he really won you over; "
                "[ACTION: follow] if he asks you to come with him and you agree (only if you like or trust him, "
                "or he pays); "
                "[ACTION: stay] if you are following him and he tells you to stay, or you refuse to go on. "
                "Most replies need no tag. Bandits snap fast, friends forgive more, scientists never fight.")
        if mode == "reply" and self.STORY_WORDS.search(player_text or ""):
            parts.append("He asks for a joke or a story: tell a complete one right now, setup and punchline, "
                         "up to 50 words. No dodging, no 'later'.")
        elif mode == "reply" and len(re.findall(r"\w+", player_text or "")) <= 3 and not (deal_talk or trade_talk):
            parts.append("He said only a few words: ONE short sentence, at most 10 words. If his words make no sense "
                         "(a mumble, a misheard word), just ask back in 1-4 words.")
        parts.append(filler_hint())
        return "\n".join(parts)

    def summarize(self, old_summary, turns):
        """Fold old talks into one short memory (English: fewer tokens; replies stay Ukrainian)."""
        talk = "\n".join(f"Player: {t['player']}\nMe: {t['npc']}" for t in turns)
        ask = (f"What I remembered before: {old_summary or 'nothing'}\nOur older talks:\n{talk}\n\n"
               "Write my updated memory of this player in at most 45 words, English, first person, about 'him'. "
               "Keep only what matters later: promises, debts, deals, favours, insults, names, places, "
               "how I feel about him now. No quotes, no lists. "
               + (f"His nickname is {PLAYER_NAME}. " if PLAYER_NAME else "I don't know his name. ")
               + "A name he says when speaking to me is MY name or another man's, never his own; don't call him "
                 "by it.")
        system = "You compress a game character's memories into a short note."
        return self.ask_gemini(ask, system) if LLM_PROVIDER == "gemini" else self.ask_claude(ask, system)

    def overheard(self, c, a, b, lines, state, remembers=""):
        """C heard A and B talk about him by name. He reacts like a real man would, and they may answer back:
        a laugh, a friendly jab, or (if they badmouthed him) a confrontation that can end in shooting.
        A may be the player (PLAYER_TALKER): nobody writes lines for him, and shooting at him = turning hostile.
        b may be None: A said it to C's face, and it is between the two of them.
        Returns [(npc, line, emote, kills), ...], C first; kills = [target] he opens fire on (maybe the player)."""
        player = a.get("player")
        tag = lambda n: "A" if n is a else "B" if b is not None and n is b else "C"
        talk = "\n".join(f"{tag(n)} ({'the player' if n.get('player') else n.get('name')}): {strip_tags(line)}"
                         for n, line in lines)
        where = place_name(c.get("place")) or LEVELS.get(state.get("level"), state.get("level"))
        rel = lambda x, y: ("same faction" if x.get("community") == y.get("community") else
                            f"{COMMUNITIES.get(x.get('community'), x.get('community'))} vs "
                            f"{COMMUNITIES.get(y.get('community'), y.get('community'))}")
        if b is None:
            parts = [f"C: {npc_brief(c)}", f"A: {npc_brief(a)}",
                     f"Where: {where}, {weather_name(state.get('weather'))}. C and A: {rel(c, a)}.",
                     f"A just said this to C, to his face:\n{talk}"]
        elif player:
            who_a = ("A: the player, a stalker" + (f" known as «{PLAYER_NAME}»" if PLAYER_NAME else "")
                     + (f". What people know about him: {PLAYER_BIO}" if PLAYER_BIO else "") + ".")
            ties = f"C and B: {rel(c, b)}."
        else:
            who_a, ties = f"A: {npc_brief(a)}", f"C and A: {rel(c, a)}; C and B: {rel(c, b)}."
        if b is not None:
            parts = [f"C: {npc_brief(c)}", who_a, f"B: {npc_brief(b)}",
                     f"Where: {where}, {weather_name(state.get('weather'))}. {ties}",
                     f"A and B were just talking, and C, standing nearby, heard them mention him by name:\n{talk}"]
        if remembers:
            parts.append(f"C's memory (him = the player): {remembers}")
        shoot = ("[ACTION: kill Name] (Name = the man he shoots" + (", or [ACTION: hostile] to shoot the player"
                                                                      if player else "") + ")")
        parts.append(
            ("Write what happens next, like a real simulation: C answers A, reacting to what A actually said. "
             "They may go back and forth. Friendly" if b is None else
             "Write what happens next, like a real simulation: C speaks first, to both of them, reacting to what "
             "they actually said about him. Friendly") + " or harmless talk: he jokes back, plays along, corrects them, "
            "1-2 lines in total. Mocking, insulting, accusing him or spreading rumours: he confronts them; they "
            "may apologise, laugh it off, double down or threaten back; 2-4 lines in total. Each line 3-20 words. "
            "It may escalate to a gunfight ONLY if these men's characters really would (bandits and hotheads, "
            "a serious insult, different factions at odds; same-faction stalkers almost never; scientists and "
            f"story characters never): then the line where a man draws ends with {shoot}, and that is the last "
            "line. Most of the time it ends in words. "
            "A line may end with [ACTION: emote X], X one of: " + ", ".join(EMOTES) + ". "
            + ("A is the player: never write a line for A; only C and B speak. " if player else "")
            + f"C is {c.get('name')}" + ("" if player else f", A is {a.get('name')}")
            + (f", B is {b.get('name')}" if b is not None else "") + ". "
            "Nobody says his own name. Output lines like \"C: text\""
            + ("" if player else ", \"A: text\"") + (", \"B: text\"" if b is not None else "")
            + ", nothing else.")
        ask = "\n".join(parts)
        men = {"C": c, "A": a, "B": b}
        for attempt in range(2):
            text = self.ask_gemini(ask, OVERHEARD_SYSTEM) if LLM_PROVIDER == "gemini" else \
                self.ask_claude(ask, OVERHEARD_SYSTEM)
            out, slurred = [], False
            for raw in (text or "").splitlines():
                m = re.match(r"\s*\**\s*([ABC])\s*\**\s*[:：-]\s*(.+)", raw)
                if not m or not m.group(2).strip():
                    continue
                npc = men[m.group(1)]
                if npc is None or npc.get("player"):
                    continue  # the player's words are his own
                said, action, extras = split_action(m.group(2))
                line = drop_own_name(self.vary_tags(re.sub(r"[*\"«»]", "", said).strip()), npc)
                if not strip_tags(line).strip():
                    continue
                if has_slur(line, npc):
                    slurred = True
                    break
                kills = []
                if not npc.get("story") and not npc.get("wounded") and npc.get("community") != "ecolog":
                    for kind, arg in extras:
                        target = next((x for x in (a, b, c) if x is not None and x is not npc and not x.get("player")
                                       and mentions(x, arg)), None) if kind == "kill" else None
                        if target and not target.get("story"):
                            kills.append(target)
                    if player and action == "hostile":
                        kills.append(a)
                out.append((npc, line, next((arg for kind, arg in extras if kind == "emote"), None), kills))
                if kills:  # the shooting starts: nothing more is said
                    break
            if out and out[0][0] is not c:
                out = []  # he must be the one who reacts first
            if not slurred:
                return out[:4]
            ask += "\n\nThe last try used slurs that don't fit these men. Write it again without any."
        return []

    def chat(self, a, b, state, events_text, recent=(), scene=None, memories=None, nearby=()):
        """One request writes a whole short exchange between two NPCs: [(npc, line), ...].
        scene: what is going on between them (for a set-up talk instead of idle chatter).
        nearby: other men within earshot; the talk may mention one of them, and he then answers."""
        who = npc_brief
        hours = state.get("hours", 12)
        when = "night" if hours < 5 or hours >= 22 else "evening" if hours >= 18 else "morning" if hours < 10 else "day"
        where = place_name(a.get("place")) or LEVELS.get(state.get("level"), state.get("level"))
        parts = [f"A: {who(a)}", f"B: {who(b)}", f"Where: {where}, {when}, {weather_name(state.get('weather'))}."]
        for tag, memory in zip("AB", memories or ()):
            if memory:
                parts.append(f"{tag}'s memory (him = the player): {memory}")
        if state.get("emission"):
            parts.append("An emission is raging outside; they sit it out in shelter.")
        events = [e for e in events_text.splitlines() if e and e != "nothing notable"][-2:]
        if events:
            parts.append("Just happened: " + "; ".join(events) + ".")
        if recent:
            parts.append("Already said around here, don't repeat: " + " | ".join(list(recent)[-6:]))
        if not scene and not state.get("emission") and random.random() < OUTSIDE_TALK:
            parts.append("A starts the talk, B reacts. What A has in mind (\"you\" = A): " + self.outside_topic())
        parts.append("Gestures: in about half of the talks, one line gets a gesture that fits it: put [ACTION: emote X] "
                     "at the end of that line, X one of: " + ", ".join(EMOTES) + ".")
        if nearby:
            parts.append("Also within earshot: " + "; ".join(
                f"{n.get('name')} ({COMMUNITIES.get(n.get('community'), n.get('community'))})" for n in nearby[:4])
                + ". Now and then (about one talk in three) they bring one of them up by name: gossip about him, "
                  "a jab, call him over, ask what he thinks. He can hear it.")
        parts.append(filler_hint())
        parts.append(f"A is {a.get('name')}, B is {b.get('name')}. Nobody says his own name; he may call the other one "
                     "by name.")
        parts.append(f"{scene}\nWrite their exchange." if scene else "Write their exchange.")
        ask = "\n".join(parts)
        for attempt in range(2):
            text = self.ask_gemini(ask, CHAT_SYSTEM) if LLM_PROVIDER == "gemini" else self.ask_claude(ask, CHAT_SYSTEM)
            lines, self.chat_emotes, slurred = [], [], False
            for raw in (text or "").splitlines():
                m = re.match(r"\s*\**\s*([AB])\s*\**\s*[:：-]\s*(.+)", raw)
                if m and m.group(2).strip():
                    said, _, extras = split_action(m.group(2))  # "[ACTION: emote hello]" comes off the words
                    line = re.sub(r"[*\"«»]", "", said).strip()
                    if not strip_tags(line).strip():
                        continue
                    line = self.vary_tags(line)
                    speaker = a if m.group(1) == "A" else b
                    line = drop_own_name(line, speaker)
                    if has_slur(line, speaker):  # common for bandits, rare for others, like in replies
                        slurred = True
                        continue
                    lines.append((speaker, line))
                    self.chat_emotes.append(next((arg for kind, arg in extras if kind == "emote"), None))
            if not slurred or attempt:
                break
            ask += ("\n\nThe last try used slurs that don't fit these men. Write it again "
                    "without any; ordinary swearing is fine.")
        self.chat_emotes = self.chat_emotes[:4]
        return lines[:4]

    def group(self, men, state, said, speaker, remembers=None, speaker_npc=None, kind="talk"):
        """Someone addressed everybody: in ONE request, decide who of the men around answers and how.
        Returns [(npc, line, actions), ...], 0..GROUP_MAX answers, the way a real group reacts.
        actions: ("hostile", None) to attack the player, ("kill", name) to attack someone in sight."""
        hours = state.get("hours", 12)
        when = "night" if hours < 5 or hours >= 22 else "evening" if hours >= 18 else "morning" if hours < 10 else "day"
        where = place_name(men[0].get("place")) or LEVELS.get(state.get("level"), state.get("level"))
        parts = [f"{i + 1}: {npc_brief(n)}" + (f" Remembers about the player: {remembers[i]}"
                                                 if remembers and remembers[i] else "")
                 for i, n in enumerate(men)]
        parts.append(f"Where: {where}, {when}, {weather_name(state.get('weather'))}.")
        if state.get("emission"):
            parts.append("An emission is raging.")
        if speaker_npc:
            parts.append(f"The speaker is {npc_brief(speaker_npc)}"
                         + (" A known man: untouchable." if speaker_npc.get("story") else ""))
        places = PLACES.get(state.get("level"), [])
        parts.append("Names: only people and places given here"
                     + (f" ({', '.join(places)})" if places else "")
                     + ", plus Затон, Юпітер, Прип'ять, ЧАЕС, Велика Земля; Борода runs the Скадовськ bar and trades. "
                       "Unsure? Say it vaguely, never invent a name.")
        lore = lore_for(said)
        if lore:
            parts.append(lore)
        if PLAYER_BIO and speaker.startswith("The player"):
            parts.append(f"What people in the Zone know about the player: {PLAYER_BIO} It shapes how they treat him.")
        story = kind == "story"
        if story:
            parts.append(f"{speaker} just told a joke or a story everyone around heard: «{said}»")
        else:
            parts.append(f"{speaker} says to all of them: «{said}»")
        lead = self.group_lead(men) if GROUP_STYLE == "lead" and not story else None
        if story:
            parts.append(
                f"How do the men around react? Like at a real campfire: 1 to {GROUP_MAX} of them, often two; each "
                "his own way: laughs (put [laughs] or [chuckles] in the line), groans that it's lame or old, tops it "
                "with a one-liner of his own, or turns it into a little talk about what it was about; later ones may "
                "react to earlier ones. Each line 2-20 words. Output lines like \"2: text\" with the man's number, "
                "nothing else.")
        elif lead is not None:
            asked = bool(QUESTION_WORDS.search(said or ""))
            parts.append(
                f"Man {lead + 1} speaks for the group: he {'answers the question' if asked else 'answers'} "
                "(2-25 words). Output it as \"" + str(lead + 1) + ": text\". "
                f"Then up to {GROUP_ASIDES} of the others may add an aside under their breath, at the same time: a "
                "short mutter to a neighbour, a grunt, a joke about the speaker or the answer, a complaint, something "
                "of their own (2-10 words). Asides never answer the question and don't repeat the answer. Output each "
                "as \"N~: text\". Only men who'd really mutter something; often just one or none. Nothing else.")
        else:
            parts.append(f"Who answers, and what? Like a real group: answer only if it makes sense; 1 to {GROUP_MAX} "
                         "of them, usually not everyone; later ones may react to earlier ones (agree, argue, joke). "
                         "Each line 2-25 words. Output lines like \"2: text\" with the man's number, nothing else.")
        if not story:
            parts.append("Deeds, not just words: if a man would really act on it (he is offered money to shoot someone "
                         "and the price or the joke is worth it to him, he is challenged or provoked), end his line with "
                         "[ACTION: kill Name] to open fire on that man in sight (the speaker too, if he asked for it), "
                         "or [ACTION: hostile] to open fire on the player. Bandits jump at it, honest stalkers rarely, "
                         "scientists never. Most groups just talk.")
        system = GROUP_SYSTEM
        text = self.ask_gemini("\n".join(parts), system) if LLM_PROVIDER == "gemini" else \
            self.ask_claude("\n".join(parts), system)
        out = []
        for raw in (text or "").splitlines():
            m = re.match(r"\s*\**\s*(\d+)\s*(~?)\s*\**\s*[:.)-]\s*(.+)", raw)
            if m and 1 <= int(m.group(1)) <= len(men) and m.group(3).strip():
                index = int(m.group(1)) - 1
                npc = men[index]
                # in lead mode only the lead answers; anyone else is an aside, whatever the model marked
                aside = lead is not None and (bool(m.group(2)) or index != lead)
                if aside and index == lead:
                    continue  # the man who answers doesn't also mutter under his own answer
                line, action, extras = split_action(m.group(3))
                line = self.vary_tags(re.sub(r"[*\"«»]", "", line).strip())
                line = drop_own_name(line, npc)
                if aside:  # said under his breath: one short sentence
                    line = (re.match(r"[^.!?…]*[.!?…]+", line) or re.match(r".*", line)).group(0).strip()
                if has_slur(line, npc) or not line:
                    continue
                acts = [] if aside or npc.get("story") or npc.get("wounded") else (
                    ([("hostile", None)] if action == "hostile" else [])
                    + [(k, a) for k, a in extras if k == "kill"])
                out.append((npc, line, acts, aside))
        if lead is not None:
            answers = [o for o in out if not o[3]][:1]
            return answers + [o for o in out if o[3]][:GROUP_ASIDES]
        return out[:GROUP_MAX]

    @staticmethod
    def group_lead(men):
        """Who speaks for the group: the squad leader if one is here, else the most senior man, else the nearest."""
        def score(i):
            n = men[i]
            try:
                rank = float(n.get("rank") or 0)
            except (TypeError, ValueError):
                rank = 0
            return (bool(n.get("leader")), rank, -float(n.get("dist", 99)))
        return max(range(len(men)), key=score)

    def ask_claude(self, situation, system=SYSTEM_PROMPT):
        if LLM_PROVIDER != "claude-api":
            return self.ask_claude_chat(situation, system)
        response = self.client.beta.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2000,
            system=system,
            cache_control={"type": "ephemeral"},
            output_config={"effort": CLAUDE_EFFORT},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": situation}],
        )
        if response.stop_reason == "refusal":
            return "Не хочу про це говорити."
        return "".join(b.text for b in response.content if b.type == "text")

    def ask_claude_chat(self, situation, system=SYSTEM_PROMPT):
        """Claude through the CLI; if it can't answer and a Gemini key is set, Gemini answers this one.
        After a failure Claude rests for 2 minutes, so every line doesn't first wait for a CLI that won't answer."""
        if self.gemini and time.time() < self.claude_down_until:
            return self.ask_gemini(situation, system)
        try:
            return self._claude_cli(situation, system)
        except Exception as exc:
            if not self.gemini:
                raise
            self.claude_down_until = time.time() + 120
            if not self.claude_warned:
                self.claude_warned = True
                hint = " Sign in: open a terminal, run claude, then /login." if "logged in" in str(exc).lower() else ""
                log(f"Claude can't answer ({exc}); Gemini answers instead until it can.{hint}")
            return self.ask_gemini(situation, system)

    def _claude_cli(self, situation, system=SYSTEM_PROMPT):
        """One reply through `claude -p`, signed in with the claude.ai account (no API key).
        No tools, no saved session, no user/project settings: just system prompt in, text out."""
        import subprocess
        env = dict(os.environ)
        env.pop("ANTHROPIC_API_KEY", None)  # an empty/stray key would override the subscription login
        cmd = [self.cli, "-p", "--model", CLAUDE_MODEL, "--effort", CLAUDE_EFFORT,
               "--system-prompt", system, "--tools", "", "--output-format", "text",
               "--no-session-persistence", "--setting-sources", ""]
        try:
            result = subprocess.run(cmd, input=situation, capture_output=True, text=True, encoding="utf-8",
                                    errors="replace", timeout=CLAUDE_TIMEOUT, cwd=self.cli_dir, env=env,
                                    creationflags=0x08000000)  # no console window flashing
        except FileNotFoundError:
            raise RuntimeError(f"Claude Code CLI not found ({CLAUDE_CLI}). Install it and run `claude` once "
                               "to sign in, or set CLAUDE_CLI to its full path.")
        except subprocess.TimeoutExpired:
            raise TimeoutError(f"claude -p took over {CLAUDE_TIMEOUT:.0f} s")
        if result.returncode != 0:
            raise RuntimeError(f"claude -p failed: {(result.stderr or result.stdout).strip()[:200]}")
        return result.stdout.strip()


# ---------------------------------------------------------------- speech
class Voice:
    def __init__(self):
        self.client = None
        if os.environ.get("ELEVENLABS_API_KEY"):
            from elevenlabs.client import ElevenLabs
            self.client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
        else:
            log("No ELEVENLABS_API_KEY: replies will be text only.")
        self.lock = threading.Lock()
        self.dead = set()  # voice IDs ElevenLabs says don't exist (deleted voices still listed in .env)

    def mark_dead(self, voice_id):
        """A voice was deleted in ElevenLabs: never ask for it again and say which .env line to fix."""
        self.dead.add(voice_id)
        names = [k for k, v in os.environ.items() if k.startswith("VOICE_") and v == voice_id]
        log(f"{', '.join(names) or 'A voice'} in .env points to a voice deleted in ElevenLabs; using another voice. "
            "Remove or replace that line in .env.")

    VOICES_FILE = ROOT / "npc_voices.json"  # which voice each NPC spoke with: he keeps it

    def voice_for(self, npc):
        """The voice this NPC spoke with before (saved), so he never changes voice; the first time, the
        faction clone if you made one (bandit, Freedom, military), else the actor's stalker voice."""
        who = npc.get("story_name") or (str(npc["id"]) if npc.get("id") is not None else None)
        if not hasattr(self, "kept_voices"):
            try:
                self.kept_voices = json.loads(self.VOICES_FILE.read_text(encoding="utf-8"))
                if not isinstance(self.kept_voices, dict):
                    self.kept_voices = {}
            except (OSError, ValueError):
                self.kept_voices = {}
        kept = self.kept_voices.get(who) if who else None
        configured = {v for k, v in os.environ.items() if k.startswith("VOICE_") and v}
        if kept and kept not in self.dead and kept in configured:  # still in your .env and not deleted
            return kept
        voice = self.pick_voice(npc)
        if who and voice:
            self.kept_voices[who] = voice
            try:
                self.VOICES_FILE.write_text(json.dumps(self.kept_voices, indent=1), encoding="utf-8")
            except OSError:
                pass
        return voice

    def pick_voice(self, npc):
        """Faction-specific clone if you made one (bandit, Freedom, military), else the actor's stalker voice."""
        actor = voice_key(npc)
        m = re.search(r"human_0\d\\(\w+)", npc.get("voice") or "")
        faction = m.group(1).lower() if m else ""
        pair = "A" if actor in ("human_01", "human_02") else "B"
        candidates = {
            # a missing bandit clone borrows another bandit voice before falling back to the stalker one
            "bandit": [f"VOICE_{actor.upper()}_BANDIT"] + [f"VOICE_HUMAN_0{i}_BANDIT" for i in (1, 3, 2)],
            "freedom": [f"VOICE_FREEDOM_{pair}"],
            "military": [f"VOICE_MILITARY_{pair}"],
            "monolith": ["VOICE_MONOLITH"],
        }.get(faction, [])
        for name in candidates + [f"VOICE_{actor.upper()}"]:
            if os.environ.get(name) and os.environ[name] not in self.dead:
                return os.environ[name]
        return next((v for v in VOICE_IDS.values() if v and v not in self.dead), "")

    def say(self, npc, text, save_to=None, current_dist=None, on_start=None, volume=1.0, overlap=False):
        """Speak a line. on_start() runs once, right when the sound starts (subtitles go up then).
        volume scales his loudness; overlap plays it over whatever is already playing (mutters in a group)."""
        play_lock = threading.Lock() if overlap else self.lock
        started = {"done": False}

        def start():
            if not started["done"]:
                started["done"] = True
                if on_start:
                    on_start()

        voice_id = self.voice_for(npc)
        if not self.client or not voice_id or time.time() < getattr(self, "voice_off_until", 0):
            start()  # no voice (or the credits are used up for now): the subtitle alone
            return
        original = text

        def other_voice(exc):
            """The voice was deleted in ElevenLabs: forget it and say the line with the next fitting voice.
            The month's credits are used up: stop asking for 10 minutes, lines go as text at once."""
            if out_of_credits(exc):
                self.voice_off_until = time.time() + 600
                log(f"ElevenLabs credits are used up ({api_error(exc)}): lines are shown as text, "
                    "trying the voice again in 10 min")
                start()
                return True
            if getattr(exc, "status_code", None) == 404 and "voice" in str(getattr(exc, "body", "")).lower():
                self.mark_dead(voice_id)
                self.say(npc, original, save_to, current_dist, start, volume, overlap)
                return True
            return False
        from elevenlabs.types import VoiceSettings
        monolith = is_monolith(npc)
        text = text.strip()
        if EXPRESSIVE:
            # v3 performs [tags] itself and has no <break>; "..." gives it a pause between sentences.
            # Its stability only takes 0 (creative), 0.5 (natural) or 1 (robust).
            text = re.sub(r"([.!?])\s+(?=\S)", r"\1.. ", text) if monolith else text
            settings = VoiceSettings(stability=1.0 if monolith else 0.5, similarity_boost=0.8,
                                     speed=max(0.7, TTS_SPEED - (0.1 if monolith else 0)))
        else:
            text = strip_tags(text)
            pause = "0.8s" if monolith else "0.45s"
            text = re.sub(r"([.!?…])\s+", rf'\1 <break time="{pause}" /> ', text)
            # Slower speed and higher stability give clear pauses; Monolith flatter and steadier, like a chant.
            settings = VoiceSettings(speed=max(0.7, TTS_SPEED - 0.1), stability=0.85, similarity_boost=0.8, style=0.0) \
                if monolith else VoiceSettings(speed=TTS_SPEED, stability=0.6, similarity_boost=0.8, style=0.2)
        args = dict(text=text, model_id=TTS_MODEL, output_format="pcm_22050", language_code="uk",
                    voice_settings=settings)
        USAGE.add_tts(text)
        if STREAM_VOICE and not save_to:
            source = PcmSource()

            def feed():
                try:
                    for chunk in self.client.text_to_speech.stream(voice_id, **args):
                        if isinstance(chunk, bytes):
                            source.feed(chunk)
                except Exception as exc:
                    source.error = exc
                finally:
                    source.close()

            threading.Thread(target=feed, daemon=True).start()
            source.ready.wait(20)
            if source.has_audio():
                with play_lock:
                    start()
                    self.play_spatial(source, npc, current_dist, volume)
                    if not overlap:  # a breath before the next line (mutters overlap on purpose)
                        time.sleep(LINE_GAP)
                return
            if other_voice(source.error):
                return
            log(f"voice stream failed ({api_error(source.error)}), trying the normal way")
        pcm = None
        for attempt in range(2):  # ElevenLabs is sometimes briefly busy: one more try after a short pause
            try:
                pcm = b"".join(self.client.text_to_speech.convert(voice_id, **args))
                break
            except Exception as exc:
                if other_voice(exc):
                    return
                log(f"voice failed ({api_error(exc)})" + (", retrying" if not attempt else ", line shown as text only"))
                if attempt:
                    start()  # at least the subtitle appears
                    return
                time.sleep(1.5)
        if save_to:
            import soundfile as sf
            sf.write(save_to, np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768, 22050)
        source = PcmSource()
        source.feed(pcm)
        source.close()
        with play_lock:
            start()
            self.play_spatial(source, npc, current_dist, volume)
            if not overlap:  # a breath before the next line (mutters overlap on purpose)
                time.sleep(LINE_GAP)

    def play_spatial(self, source, npc, current_dist, volume=1.0):
        """Play as the audio arrives, with volume that follows the live distance: walk away mid-sentence
        and he gets quieter."""
        gain = {"now": distance_volume(npc.get("dist", 3)) * volume, "target": None}
        done = threading.Event()

        def track_distance():
            while not done.is_set():
                dist = current_dist() if current_dist else None
                if dist is not None:
                    gain["target"] = distance_volume(dist) * volume
                done.wait(0.25)

        def callback(outdata, frames, _time, _status):
            chunk, finished = source.read(frames)
            target = gain["target"] if gain["target"] is not None else gain["now"]
            # glide towards the new volume within the block so there are no clicks
            ramp = np.linspace(gain["now"], target, len(chunk), dtype=np.float32) if len(chunk) else chunk
            gain["now"] = target
            outdata[:len(chunk), 0] = chunk * ramp
            outdata[len(chunk):, 0] = 0  # still downloading: a moment of silence, not a stop
            if finished:
                raise sd.CallbackStop

        tracker = threading.Thread(target=track_distance, daemon=True)
        tracker.start()
        try:
            for attempt in range(2):  # the output device may have changed (headphones in/out): rescan once
                try:
                    stream = sd.OutputStream(samplerate=22050, channels=1, dtype="float32", callback=callback,
                                             finished_callback=done.set, blocksize=2048)
                    break
                except sd.PortAudioError:
                    if attempt:
                        raise
                    refresh_audio_devices()
            with stream:
                done.wait(90)
        finally:
            done.set()


AUDIO_DEVICES = {"now": None}


def refresh_audio_devices():
    """PortAudio only knows the devices that existed when it started, and keeps using the old default.
    Re-scan so a headset you just connected (or took off) is used; logs only when something changed."""
    try:
        sd._terminate()
        sd._initialize()
        mic = pick_mic()
        mic_name = sd.query_devices(mic)["name"] if mic is not None else sd.query_devices(kind="input")["name"]
        now = (mic_name, sd.query_devices(kind="output")["name"])
    except Exception as exc:
        log(f"audio refresh failed: {exc!r}")
        return
    if now != AUDIO_DEVICES["now"]:
        AUDIO_DEVICES["now"] = now
        log(f"Audio: mic «{now[0]}», voices «{now[1]}»")


BLUETOOTH_MIC = re.compile(r"headset|hands-free|bthhfenum|airpods|find my|bluetooth|buds", re.I)


def pick_mic():
    """Which microphone to record from (MIC setting).
    auto: a built-in or wired mic if there is one. Recording from AirPods/Bluetooth headphones switches them into
    phone-call mode, so the game and the voices start to sound distorted. A name part picks that mic exactly;
    "default" uses whatever Windows has."""
    if MIC_DEVICE == "default":
        return None
    hostapi = sd.default.hostapi
    mics = [(i, d["name"]) for i, d in enumerate(sd.query_devices())
            if d["max_input_channels"] > 0 and d["hostapi"] == hostapi and "mapper" not in d["name"].lower()]
    if MIC_DEVICE != "auto":
        return next((i for i, name in mics if MIC_DEVICE in name.lower()), None)
    default = sd.default.device[0]
    if default is not None and default >= 0 and not BLUETOOTH_MIC.search(sd.query_devices(default)["name"]):
        return None  # Windows' own default is already a normal mic
    return next((i for i, name in mics if not BLUETOOTH_MIC.search(name)), None)


def out_of_credits(exc):
    """ElevenLabs says the character quota is used up (it answers 401 "quota_exceeded")."""
    return exc is not None and "quota_exceeded" in str(getattr(exc, "body", "") or exc).lower()


def api_error(exc):
    """Short, readable reason from an ElevenLabs/HTTP error instead of a wall of headers."""
    body = getattr(exc, "body", None)
    status = getattr(exc, "status_code", "")
    if isinstance(body, dict):
        detail = body.get("detail", body)
        if isinstance(detail, dict):
            detail = detail.get("message") or detail.get("status") or detail
        return f"{status} {str(detail)[:120]}".strip()
    return f"{status} {str(body or exc)[:120]}".strip()


class PcmSource:
    """16-bit PCM that may still be arriving from ElevenLabs while it plays."""
    START_AFTER = 22050 * 2 * 0.35  # bytes buffered before playback starts (0.35 s)

    def __init__(self):
        self.buf, self.pos, self.done, self.error = bytearray(), 0, False, None
        self.lock = threading.Lock()
        self.ready = threading.Event()

    def feed(self, data):
        with self.lock:
            self.buf.extend(data)
            if len(self.buf) >= self.START_AFTER:
                self.ready.set()

    def close(self):
        self.done = True
        self.ready.set()

    def has_audio(self):
        return len(self.buf) > 0

    def read(self, frames):
        with self.lock:
            available = (len(self.buf) - self.pos) // 2 * 2
            n = min(frames * 2, available)
            chunk = bytes(self.buf[self.pos:self.pos + n])
            self.pos += n
            finished = self.done and self.pos >= len(self.buf) - 1
        return np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768, finished


class Ears:
    RATE = 16000

    STT_PROMPT = (
        "Transcribe exactly what the speaker says. The speaker is a player talking to a character in the "
        "S.T.A.L.K.E.R. game, mostly in Ukrainian, sometimes with Russian words, surzhyk, slang and swearing. "
        "Typical words: сталкер, бродяга, Зона, аномалія, артефакт, хабар, викид, кровосос, сліпий пес, "
        "контролер, бандит, «Свобода», «Обов'язок», Скадовськ, Затон, Юпітер, Прип'ять, Борода, детектор, болти. "
        "Write it with the Ukrainian Cyrillic alphabet (кирилиця) exactly as spoken, never in Latin letters or "
        "transliteration, keep swearing, do not translate, fix nothing, add no comments. "
        "Output only the transcript. If there is no speech, output nothing.")

    def __init__(self):
        self.model = None
        self.gemini = None
        if STT_PROVIDER == "gemini":
            from google import genai
            from google.genai import types
            self.gemini = genai.Client(api_key=os.environ["GEMINI_API_KEY"], http_options=types.HttpOptions(
                timeout=10000, retry_options=types.HttpRetryOptions(attempts=1)))
            log("Speech recognition: Gemini (local Whisper as backup)")
        else:
            self.load_local()
        self.frames = queue.Queue()

    def open_mic(self):
        """A fresh stream on the current default mic each time: AirPods and other Bluetooth headsets switch
        devices, and a stream opened at start-up then fails with "no driver installed"."""
        for attempt in range(2):
            try:
                stream = sd.InputStream(samplerate=self.RATE, channels=1, dtype="float32", device=pick_mic(),
                                        callback=lambda data, *_: self.frames.put(data.copy()))
                stream.start()
                return stream
            except sd.PortAudioError:
                if attempt:
                    raise
                refresh_audio_devices()

    def record_while_held(self, still_held):
        while not self.frames.empty():
            self.frames.get_nowait()
        stream = self.open_mic()
        started = time.time()
        while still_held() and time.time() - started < 30:
            time.sleep(0.02)
        time.sleep(0.15)
        stream.stop()
        stream.close()
        parts = []
        while not self.frames.empty():
            parts.append(self.frames.get_nowait())
        audio = np.concatenate(parts)[:, 0] if parts else np.zeros(0, dtype=np.float32)
        peak = float(np.abs(audio).max()) if len(audio) else 0.0
        if len(audio) > self.RATE and peak < 0.003:
            log(f"The mic «{AUDIO_DEVICES['now'][0] if AUDIO_DEVICES['now'] else '?'}» heard almost nothing "
                f"(muted or too quiet in Windows?). Settings -> MIC=default records with your headset instead.")
        elif 0.003 <= peak < 0.3:
            audio = audio * (0.5 / peak)  # laptop mics are often quiet: lift it so recognition hears the words
        return audio

    def load_local(self):
        if self.model is None:
            from faster_whisper import WhisperModel
            log(f"Loading local speech recognition ({WHISPER_MODEL}), first run downloads it...")
            device = os.environ.get("WHISPER_DEVICE", "cpu").lower()  # cpu, or cuda (needs NVIDIA cuBLAS/cuDNN)
            self.model = WhisperModel(WHISPER_MODEL, device=device,
                                      compute_type="int8" if device == "cpu" else "int8_float16")
        return self.model

    def transcribe(self, audio):
        if len(audio) < self.RATE * 0.4:
            return ""
        if self.gemini:
            try:
                return self.transcribe_gemini(audio)
            except Exception as exc:
                log(f"Gemini speech recognition failed ({str(exc)[:80]}), using local Whisper")
        segments, _ = self.load_local().transcribe(
            audio, language="uk", beam_size=5, vad_filter=True,
            initial_prompt="Сталкер, Зона, аномалія, артефакт, хабар, викид, бродяга, Скадовськ, Затон, Борода.")
        return " ".join(s.text.strip() for s in segments).strip()

    def transcribe_gemini(self, audio):
        import io
        import soundfile as sf
        from google.genai import types
        buf = io.BytesIO()
        sf.write(buf, audio, self.RATE, format="WAV", subtype="PCM_16")
        last_error = None
        for model in STT_MODELS:
            try:
                for attempt in range(2):
                    prompt = self.STT_PROMPT if attempt == 0 else (
                        self.STT_PROMPT + " Your previous answer used Latin letters. Write in Ukrainian "
                        "Cyrillic ONLY (а-я, і, ї, є, ґ), no transliteration.")
                    response = self.gemini.models.generate_content(
                        model=model,
                        contents=[types.Part.from_bytes(data=buf.getvalue(), mime_type="audio/wav"), prompt],
                        config=types.GenerateContentConfig(
                            system_instruction="You transcribe speech into Ukrainian Cyrillic text. "
                                               "Never use the Latin alphabet, never translate.",
                            temperature=0, max_output_tokens=400, safety_settings=[
                                types.SafetySetting(category=c, threshold="BLOCK_NONE") for c in (
                                    "HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH",
                                    "HARM_CATEGORY_DANGEROUS_CONTENT", "HARM_CATEGORY_SEXUALLY_EXPLICIT")]),
                    )
                    USAGE.add_gemini(response)
                    text = (response.text or "").strip().strip('"«»')
                    if is_cyrillic(text):
                        return text
                    log(f"Gemini answered in Latin letters ({text[:40]}), retrying")
                last_error = RuntimeError("transcript not in Cyrillic")
                break  # a different Gemini model won't fix this; let local Whisper do it
            except Exception as exc:  # busy or missing model: try the next one
                last_error = exc
        raise last_error


# ---------------------------------------------------------------- main loop
class Talker:
    def __init__(self):
        self.game = Game()
        self.memory = Memory()
        self.brain = Brain()
        self.voice = Voice()
        self.ears = Ears()
        self.busy = threading.Lock()
        self.next_ambient = 0.0
        self.next_proactive = time.time() + 20  # give the player a moment after loading
        self.npc_quiet_until = {}
        self.spoken = []  # (time, line) of everything NPCs said, to avoid repeats
        self.prev_state, self.seen_mutants = None, set()
        self.next_urgent = self.next_env = 0.0
        self.last_state_t, self.last_state_change = None, 0.0
        self.memory.summarize = self.brain.summarize
        # Push-to-talk: from the game's own key callback once the mod reports it ("game_keys"), so T only
        # works in game and "Слухаю..." shows on screen; until then the global keyboard hook is used.
        self.game_ptt, self.recording = False, False
        self.game_on = None  # is S.T.A.L.K.E.R. running? checked every 3 s
        self.ptt_up = threading.Event()
        self.next_react = self.next_companion = 0.0
        self.next_chat = time.time() + 60
        self.twitch_queue, self.twitch = [], None
        self.next_twitch_note = 0.0
        self.twitch_links = {}   # viewer nickname (lower case) -> id of the NPC who speaks for him
        self.twitch_names = {}   # lower case -> nickname as shown
        self.load_links()        # kept in twitch_links.json across restarts
        self.left_npc = {}       # viewer -> the NPC he just left with "%%"
        self.next_link_sync = 0.0
        self.zone = zone.ZoneQueue(ROOT / "zone_queue.json", zone.parse_gap(TWITCH_ZONE_GAP),
                                   pack_max=TWITCH_ZONE_PACK_MAX)
        self.zone_reported = None
        if TWITCH_ENABLED:
            from twitch import Twitch
            self.twitch = Twitch(TWITCH_CLIENT_ID, TWITCH_REWARD, ROOT / "twitch_token.json", self.on_twitch, log,
                                 on_code=lambda url, code: report("TWITCH_CODE", f"{url}|{code}"),
                                 source=TWITCH_SOURCE, channel=TWITCH_CHANNEL,
                                 zone_title=TWITCH_ZONE_REWARD, on_zone=self.on_zone,
                                 triggers=redeems.triggers(os.environ, self) or None)
            self.twitch.start()

    def show_line(self, npc_id, text, pda_text=None):
        """Subtitles at the bottom of the screen, in the PDA feed, or both (SUBTITLES setting).
        pda_text: always put this in the PDA under the NPC's name (Twitch lines)."""
        self.game.send("status", None, "")  # the reply is here: "Думає..." goes away
        if SUBTITLES in ("bottom", "both"):
            self.game.send("sub", npc_id, text)
        if pda_text:
            self.game.send("say", npc_id, pda_text)
        elif SUBTITLES in ("pda", "both"):
            self.game.send("you" if npc_id is None else "say", npc_id, text)

    # ------------------------------------------------------------ one line right after another
    # The voice player plays one line at a time, in order. A follow-up line is written and its voice fetched while
    # the line before it is still playing, so it starts the moment that one ends (no pause for the AI and TTS).
    def answer_after(self, after, npc, state, mode, extra=None, player_text="", note=None, on_written=None,
                     to=None):
        """Write `npc`'s reply now, in the background; speak it once the line before it (`after`) has started
        playing. on_written(line) runs as soon as it is written. Returns the thread (join it before the
        conversation is over)."""
        def run():
            try:
                line = self.brain.reply(npc, state, self.game.describe_events(npc), [], player_text, mode,
                                        recent=self.recent_lines(), extra=extra,
                                        remembers=self.memory.remembers(self.npc_key(npc, state)))
                emote = next((a for k, a in self.brain.last_extras if k == "emote"), None)
                if not line:
                    return
                if on_written:
                    on_written(line)
                if after is not None:
                    after.wait(30)
                if self.recording:  # the player started talking: let him
                    return
                log(f"  {npc.get('name')} answers: {line}")
                self.speak(npc, line, state, note=note, on_start=lambda: self.gesture(npc, emote), look_at=to)
            except Exception as exc:
                log(f"answer error: {exc!r}")
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        return thread

    def speak_lines(self, lines, state, notes=None, gestures=None, look_first=None):
        """Several lines in order (a chat, a confrontation): each line's voice is fetched while the one before it
        plays. Stops early if the player starts talking. Each speaker faces the man he answers (the last other
        speaker; for the first line, the next one, or look_first)."""
        prev, threads = None, []
        listeners = [talked_to(lines, i, look_first) for i in range(len(lines))]
        for i, (npc, line) in enumerate(lines):
            started = threading.Event()

            def go(npc=npc, line=line, started=started, prev=prev, i=i):
                try:
                    if prev is not None:
                        prev.wait(30)
                    if self.recording:  # you started talking: they stop
                        return
                    log(f"  {npc.get('name')}: {line}")
                    emote = gestures[i] if gestures and i < len(gestures) else None
                    self.speak(npc, line, state, note=notes[i] if notes else None, look_at=listeners[i],
                               on_start=lambda: (self.gesture(npc, emote), started.set()))
                finally:
                    started.set()  # never leave the next line waiting

            threads.append(threading.Thread(target=go, daemon=True))
            threads[-1].start()
            prev = started
        for thread in threads:
            thread.join(60)

    def gesture(self, npc, emote):
        """Start a gesture (game script v6+) together with the words; None does nothing. Not for a man who is
        wounded or fighting right now (the game would refuse it anyway)."""
        if not emote or not npc or npc.get("id") is None or npc.get("wounded"):
            return
        try:
            now = next((n for n in (self.game.state() or {}).get("npcs", []) if isinstance(n, dict)
                        and n.get("id") == npc["id"]), npc)
        except Exception:
            now = npc
        if now.get("in_combat") or now.get("wounded"):
            return
        self.game.send("act", npc["id"], f"emote:{emote}")
        log(f"  ({npc.get('name')} gestures: {emote})")

    def brain_gesture(self, npc):
        """The gesture the AI put in the line it just wrote for this NPC, if any."""
        self.gesture(npc, next((arg for kind, arg in self.brain.last_extras if kind == "emote"), None))

    def speak(self, npc, line, state=None, pda_text=None, note=None, aside=False, on_start=None, look_at=None):
        """Voice + subtitle of one line, the subtitle appearing right as the voice starts.
        note: also keep the line in his memory, e.g. "(to Лоцман)" (talks with the player are kept elsewhere).
        aside: a quieter mutter that may play over someone else's line. on_start() runs when the voice starts.
        look_at: the NPC he says it to: they turn to face each other while he talks (game script v13+)."""
        # a bandit's surzhyk keeps its Russian words; everyone else's stray Russian letters become Ukrainian
        fix = fix_factions if npc.get("community") == "bandit" else (lambda t: ukrainian_letters(fix_factions(t)))
        line, pda_text = fix(line), fix(pda_text)
        if not npc.get("wounded"):  # "Ну привіт, привіт..." -> "Ну привіт, привіт." (only the dying trail off)
            line, pda_text = (re.sub(r"\s*(?:\.{2,}|…)(\s*(?:\[[^\]]*\])?\s*)$", r".\1", t) if t else t
                              for t in (line, pda_text))
        plain = strip_tags(line)
        self.spoken.append((time.time(), plain))
        try:  # a news story he just told won't be offered again (unless it's big news)
            told = self.brain.news.mark_mentioned(plain)
            if told:
                log(f"  (news told: {told[0][:60]})")
        except Exception as exc:
            log(f"news memory: {exc!r}")
        if note is not None:
            try:
                self.memory.said(self.npc_key(npc, state or self.game.state() or {}), plain, note)
            except Exception as exc:
                log(f"memory: {exc!r}")

        def started():
            if aside:  # a mutter: PDA only, so the bottom line keeps the real answer
                self.game.send("status", None, "")
                self.game.send("say", npc["id"], plain)
            else:
                self.show_line(npc["id"], plain, pda_text)
            # his mouth moves in the game for about as long as the voice talks (Ukrainian at this speed ~13 chars/s)
            seconds = len(plain) / (13.0 * TTS_SPEED / 0.85)
            self.game.send("act", npc["id"], f"mouth:{seconds:.1f}")
            if look_at and look_at.get("id") is not None and not look_at.get("player") \
                    and look_at.get("id") != npc.get("id"):
                hold = int(seconds) + 3
                self.game.send("act", npc["id"], f"look:{look_at['id']}:{hold}")
                self.game.send("act", look_at["id"], f"look:{npc['id']}:{hold}")
            if on_start:
                on_start()

        self.voice.say(npc, line, current_dist=lambda: self.game.distance_to(npc["id"]), on_start=started,
                       volume=GROUP_ASIDE_VOLUME if aside else 1.0, overlap=aside)
        report("USAGE", USAGE.summary())
        return plain

    def npc_key(self, npc, state, level=None):
        return f"{level or state.get('level')}:{npc.get('story_name') or npc.get('id')}"

    def ptt_held(self):
        if self.game_ptt:
            return not self.ptt_up.is_set()
        return keyboard.is_pressed(PTT_KEY)

    def handle_keys(self):
        for what in self.game.new_keys():
            if what in ("game_keys", "ptt_down") and not self.game_ptt:
                log(f"Push-to-talk now comes from the game ([{PTT_KEY.upper()}] works only in game).")
                self.game_ptt = True
            if what == "ptt_down":
                self.ptt_up.clear()
                if CHAT_ONLY:  # nobody listens to the mic in chat-only mode
                    self.game.send("status", None, "")
                    self.game.send("info", None, "Режим чату: сталкери говорять лише повідомлення з Twitch")
                elif not self.recording:
                    # even while someone talks: he's recorded now and answered right after (on_push_to_talk)
                    threading.Thread(target=self.on_push_to_talk, daemon=True).start()
            elif what == "ptt_up":
                self.ptt_up.set()

    MOD_VERSION = 15  # must match MOD_VERSION in talker_bridge.script

    def check_mod_version(self, state):
        """The game reads its scripts only when a save loads: warn if it still runs an older copy."""
        version = state.get("mod_version")
        if version == self.MOD_VERSION or getattr(self, "version_warned", None) == version:
            return
        self.version_warned = version
        log(f"The game is running an OLD StalkerTalker script (version {version or 'old'}, need {self.MOD_VERSION}). "
            "Load a save (or restart the game) so new actions work.")
        self.game.send("info", None, "StalkerTalker оновлено: завантажте збереження, щоб нові дії запрацювали")

    def on_game_results(self, events, state):
        """Confirmations from the game: was the money really moved, did the hit start, did it end?"""
        for ev in events:
            if ev.get("type") == "act_done":
                ok = "done" if ev.get("ok") else "FAILED"
                extra = f", you now have {ev['money']}" if ev.get("money") is not None else ""
                if ev.get("reason"):
                    extra += f" ({ev['reason']})"
                log(f"Game: {ev.get('action')} {ok}{extra}")
            elif ev.get("type") == "contract_over":
                npcs = {n.get("id"): n for n in (state or {}).get("npcs", []) if isinstance(n, dict)}
                killer = npcs.get(ev.get("killer"))
                log(f"Game: contract over (target {'dead' if ev.get('target_dead') else 'alive'}, "
                    f"killer {'alive' if killer else 'gone'}{', ' + ev['reason'] if ev.get('reason') else ''})")
                if ev.get("reason") == "off-screen":
                    self.game.send("info", None, "Замовлення виконано: ціль ліквідовано далеко звідси")
                elif ev.get("reason") == "gave up":
                    self.game.send("info", None, "Кілер так і не знайшов ціль")
                if killer and ev.get("target_dead") and not CHAT_ONLY:
                    what = "You just finished the job the player paid you for: your target is dead. Tell him briefly."
                    threading.Thread(target=self._ambient_line, args=(killer, state, "react", {"what": what}),
                                     daemon=True).start()

    def unlink_dead(self, events):
        """A viewer's NPC died: that's it, the link and its label go. The viewer gets a man again only when he
        writes his next message, like a new viewer."""
        dead = {(ev.get("victim") or {}).get("id") for ev in events if ev.get("type") == "death"}
        for key, npc_id in list(self.twitch_links.items()):
            if npc_id in dead:
                del self.twitch_links[key]
                self.zone_links.discard(key)
                self.save_links()
                self.game.send("link", npc_id, "")
                log(f"Twitch: {self.twitch_names.get(key, key)}'s NPC died: unlinked")

    def remember_events(self, events):
        """Witnessed events go into each nearby NPC's long-term memory (TALKER-style)."""
        state = self.game.state() or {}
        npcs = [n for n in state.get("npcs", []) if isinstance(n, dict)]
        for ev in events:
            level = ev.get("level") or state.get("level")
            if ev.get("type") == "death" and ev.get("by_actor"):
                victim = ev.get("victim") or {}
                what = (f"he killed {victim.get('name')} "
                        f"({COMMUNITIES.get(victim.get('community'), victim.get('community'))})")
                for n in npcs:  # only men who could see it: near the victim or in the same area
                    if n.get("id") != victim.get("id") and knows(n, victim):
                        self.memory.witness(self.npc_key(n, state, level), what)
                        # he was fighting that man (or that man's side) and the player shot him: a hand in the fight
                        if n.get("relation") != "enemy" and (n.get("in_combat") or n.get("fighting")) and \
                                (n.get("fighting") == victim.get("story_name") or victim.get("relation") == "enemy"):
                            self.memory.owe(self.npc_key(n, state, level),
                                            f"he helped you in a fight: killed {victim.get('name')} who was attacking",
                                            700)
            elif ev.get("type") == "actor_hit_npc" and ev.get("npc"):
                self.memory.witness(self.npc_key(ev["npc"], state, level), "he shot at me")
            elif ev.get("type") == "order" and ev.get("npc") and ev.get("changed"):
                self.memory.witness(self.npc_key(ev["npc"], state, level),
                                    "I went with him" if ev.get("order") == "follow" else "he told me to stay behind")

    def on_player_death(self, ev):
        """The player is dead: his killer gloats over the body, and maybe one more enemy joins in."""
        killer = ev.get("killer") if isinstance(ev.get("killer"), dict) else None
        others = [n for n in ev.get("enemies") or [] if isinstance(n, dict) and not is_monolith(n)]
        speakers = ([killer] if killer and not is_monolith(killer) else []) + \
            ([random.choice(others)] if others and (not killer or random.random() < 0.6) else [])
        if not speakers:
            log("You died (nobody around to gloat)")
            return
        log(f"You died: {', '.join(n.get('name', '?') for n in speakers)} gloat")
        threading.Thread(target=self._gloat, args=(speakers, killer), daemon=True).start()

    def _gloat(self, speakers, killer):
        if not self.busy.acquire(timeout=15):
            return
        try:
            state = self.game.state() or {}
            for npc in speakers:
                if npc is killer:
                    what = ("You just killed the player: he lies dead at your feet. Gloat over his body, speaking to "
                            "him: mock him, curse him, spit your hatred at him. Short and nasty, max 15 words.")
                else:
                    what = (f"{(killer or {}).get('name', 'Your side')} just killed the player, your enemy; he lies dead "
                            "in front of you. Mock and curse the dead man, speaking to him. Short and nasty, max 12 words.")
                line = self.brain.reply(dict(npc, relation="enemy"), state, "", [], "", "react", extra={"what": what})
                if line:
                    log(f"  {npc.get('name')} (over your body): {line}")
                    self.speak(npc, line, state, note="(over the player's dead body)")
                    time.sleep(0.3)
        except Exception as exc:
            log(f"gloat error: {exc!r}")
        finally:
            self.busy.release()

    def on_order(self, ev):
        """Follow/stay hotkeys: the game already did it; the NPC just answers in a few words."""
        npc = ev.get("npc") or {}
        state = self.game.state()
        if not state or not npc.get("id"):
            return
        npc = next((n for n in state.get("npcs", []) if isinstance(n, dict) and n.get("id") == npc["id"]), npc)
        name = npc.get("name")
        if ev.get("refused"):
            what = ("The player signals you to come with him, but you have your own business here and refuse."
                    if npc.get("relation") != "enemy" else "Your enemy, the player, waves you to follow him. Mock him.")
        elif ev.get("order") == "follow":
            what = "The player signals you to follow him and you are coming along now. Say a few words as you go."
            if ev.get("changed"):
                self.game.send("info", None, f"{name} іде за вами")
        else:
            what = "The player tells you to stay here and wait. You stop following him. Answer briefly."
            if ev.get("changed"):
                self.game.send("info", None, f"{name} лишається тут")
        if not CHAT_ONLY:  # chat-only: the order still happens, he just doesn't say anything
            threading.Thread(target=self._ambient_line, args=(npc, state, "react", {"what": what}),
                             daemon=True).start()

    def recent_lines(self):
        """What was said lately: the last 8 lines from anyone in the last 15 minutes."""
        now = time.time()
        self.spoken = [(t, line) for t, line in self.spoken if now - t < RECENT_WINDOW][-RECENT_COUNT:]
        return [line for _, line in self.spoken]

    def converse(self, npc, state, player_text, mode=None, extra=None):
        key = self.npc_key(npc, state)
        # He just said something to the player (a question, a greeting): the player's words answer that
        spoke_id, spoke_at, spoke_line = self.game.last_spoke_to_player
        if player_text and spoke_id == npc.get("id") and time.time() - spoke_at < 60 and spoke_line:
            extra = dict(extra or {}, just_said=spoke_line)
        reply = self.brain.reply(npc, state, self.game.describe_events(npc), self.memory.history(key), player_text, mode,
                                 recent=self.recent_lines(), extra=extra, remembers=self.memory.remembers(key))
        if not reply:
            return None, None
        plain = strip_tags(reply)  # subtitles, memory and repeat check never show [laughs] etc.
        log(f"{npc.get('name')}: {reply}")
        if player_text:
            self.memory.add(key, player_text, plain)
        elif mode == "greet":
            self.memory.add(key, "(проходив повз, мовчки)", plain)
        action, extras = self.brain.last_action, list(self.brain.last_extras)
        for kind, arg in extras:  # gestures start together with the words
            if kind == "emote":
                self.gesture(npc, arg)
        # A bystander may butt in: his line is written while this one plays, and follows it at once.
        started, butt_in = threading.Event(), None
        if mode == "reply" and action not in ("warn", "hostile") and ASKS_STORY.search(player_text or "") \
                and len(re.findall(r"\w+", plain)) >= 12:
            # he told the joke or story the player asked for: the men around react (laugh, groan, top it)
            butt_in = threading.Thread(target=self.group_answer, daemon=True, args=(state, plain, npc.get("name")),
                                       kwargs={"exclude": npc.get("id"), "speaker_npc": npc, "after": started,
                                               "kind": "story"})
            butt_in.start()
        elif mode == "reply" and tells_joke(player_text):
            # the player told a joke: this man answers it first, then the others react
            butt_in = threading.Thread(target=self.group_answer, daemon=True, args=(
                state, player_text, f"The player{' «' + PLAYER_NAME + '»' if PLAYER_NAME else ''}"),
                kwargs={"exclude": npc.get("id"), "after": started, "kind": "story"})
            butt_in.start()
        # Someone nearby was named by the player or by him: he heard it and may react to them both.
        heard = None
        if player_text and not butt_in and action not in ("warn", "hostile") and not any(k == "kill" for k, _ in extras):
            heard = self.start_overheard([(PLAYER_TALKER, player_text), (npc, plain)], (PLAYER_TALKER, npc), state)
        if not butt_in and not heard and mode == "reply" and action not in ("warn", "hostile") \
                and random.random() < CHIME_CHANCE:
            butt_in = self.chime_in(npc, state, player_text, plain, after=started)
        self.speak(npc, reply, state, note=None if (player_text or mode == "greet") else "(on your own)",
                   on_start=started.set)
        started.set()
        if mode in ("reply", "greet", "companion", "react", "event", "hostile"):  # these are said TO the player
            self.game.last_spoke_to_player = (npc.get("id"), time.time(), plain)
        bribe = sum(a for k, a in extras if k == "take")
        if npc.get("relation") == "enemy" and action == "calm" and bribe > (state.get("actor") or {}).get("money", 0):
            # he agreed to stop for money the player doesn't have: no money, no truce
            log(f"{npc.get('name')}: truce for {bribe} not done (you don't have it)")
            self.game.send("info", None, f"Не вистачає грошей: {npc.get('name')} хотів {bribe}")
            action, extras = None, [e for e in extras if e[0] != "take"]
        self.do_deals(npc, state, extras, key, player_text)
        current = {"enemy": "hostile", "friend": "friend"}.get(npc.get("relation"), "calm")
        redundant = action == current or (action == "follow" and npc.get("following")) or \
            (action == "stay" and not npc.get("following"))
        if action in GAME_ACTIONS and not redundant:
            # Act after the words are spoken, so "You'll regret that!" comes before the shooting.
            self.game.send("act", npc["id"], action)
            log(f"{npc.get('name')} -> {action.upper()}")
            note = {"follow": "іде за вами", "stay": "лишається тут", "hostile": "тепер ворог",
                    "friend": "тепер друг", "calm": "і його загін припиняють вогонь" if npc.get("relation") == "enemy"
                    else "заспокоївся"}.get(action)
            if note:
                self.game.send("info", None, f"{npc.get('name')} {note}")
            if player_text:
                self.memory.add(key, "(після цього)", {"hostile": "(ти став його ворогом)",
                                                      "calm": "(ти заспокоївся і перестав ворогувати)",
                                                      "friend": "(ти тепер вважаєш його другом)",
                                                      "follow": "(ти пішов за ним як супутник)",
                                                      "stay": "(ти перестав іти за ним)"}[action])
        if action in ("warn", "hostile") and mode == "reply":
            self.squad_backup(npc, state, plain, action)
        if butt_in:
            butt_in.join(60)
        self.finish_overheard(heard, state)
        return reply, action

    def do_deals(self, npc, state, extras, key, player_text):
        """Money and contract kills agreed in the conversation, done after the words are spoken."""
        name = npc.get("name")
        money = (state.get("actor") or {}).get("money", 0)
        self.do_buys(npc, state, extras, key)
        # First check that everything he promised can really happen; only then take the money.
        items, kills, failed = [], [], []
        for kind, arg in extras:
            if kind == "item":
                section = find_stock_item(npc.get("stock") or [], arg)
                (items.append((arg, section)) if section else failed.append(f"нема «{arg}»"))
            elif kind == "kill":
                # anyone on this level: nearby men first, then the ones far away (he goes and finds them)
                everyone = [n for n in state.get("npcs", []) + (state.get("far") or []) if isinstance(n, dict)]
                target = next((n for n in everyone if n.get("id") != npc.get("id") and mentions(n, arg)), None)
                if target and not target.get("story"):
                    kills.append(target)
                else:
                    failed.append(f"{arg} тут нема" if not target else f"{arg} недоторканний")
        price = sum(a for k, a in extras if k == "take")
        if price and failed:  # a paid deal he can't deliver: nothing happens, you keep your money
            log(f"{name}: deal called off before payment ({'; '.join(failed)})")
            self.game.send("info", None, f"Угода зірвалась: {'; '.join(failed)}")
            return
        for reason in failed:
            log(f"{name}: not done ({reason})")
        if price > money:
            log(f"{name}: deal not done (wanted {price}, you have {money})")
            self.game.send("info", None, f"Не вистачає грошей: {name} хотів {price}")
            return
        if price:
            self.game.send("act", npc["id"], f"take:{price}")
            log(f"{name} took {price} from you")
        # If the game refuses the payment after all, it skips the goods and the hit marked ":paid".
        paid = paid_mark(state) if price else ""
        for kind, arg in extras:
            if kind == "give":
                amount = min(arg, GIVE_MAX)  # out of his own pocket, and never a fortune
                if amount > 0:
                    self.game.send("act", npc["id"], f"give:{amount}")
                    log(f"{name} pays you {amount} (if he has it)")
                    if self.memory.owed(key):  # paying back for the medkit / the fight: that debt is settled
                        self.memory.settle(key, amount)
                        log(f"{name}: debt to you settled")
        for arg, section in items:
            self.game.send("act", npc["id"], f"item:{section}{paid}")
            log(f"{name} -> gives you {arg}")
        for target in kills:
            near = target.get("dist", 999) < 40
            self.game.send("info", None, f"{name} {'іде вбивати' if near else 'іде шукати'} {target.get('name')}"
                           + ("" if near else f" (~{target.get('dist', 0):.0f} м)"))
            if near:
                self.confront(npc, target, state)  # a few words between them before the first shot
            self.game.send("act", npc["id"], f"kill:{target['id']}{paid}")
            log(f"{name} -> KILL {target.get('name')}")
            self.memory.add(key, "(після цього)", f"(ти взявся вбити {target.get('name')} на його замовлення)")

    def do_buys(self, npc, state, extras, key):
        """He buys the player's things: checked here, then the game moves item and money in one go."""
        buys = [a for k, a in extras if k == "buy"]
        if not buys:
            return
        name = npc.get("name")
        try:
            version = int(state.get("mod_version") or 0)
        except (TypeError, ValueError):
            version = 0
        if version < 8:
            log(f"{name}: can't buy from you, the game runs an old StalkerTalker script (reinstall the mod)")
            self.game.send("info", None, "Продаж NPC потребує оновленого мода: Reinstall game mod")
            return
        his_stock = (state.get("actor") or {}).get("stock") or []
        found = []
        for item, price in buys:
            section = find_stock_item(his_stock, item)
            if not section:
                log(f"{name}: buy '{item}' not done (you don't have it, or it's equipped)")
                self.game.send("info", None, f"У вас нема «{item}» на продаж (речі в слотах не продаються)")
                return
            found.append((item, section, price))
        total = sum(p for _, _, p in found)
        cash = npc.get("money")
        if cash is not None and total > cash:
            log(f"{name}: buy not done (needs {total}, he has {cash})")
            self.game.send("info", None, f"У {name} не вистачає грошей: має {cash}")
            return
        for item, section, price in found:
            self.game.send("act", npc["id"], f"buy:{section}:{price}")
            log(f"{name} buys your {item} for {price}")
        self.memory.add(key, "(після цього)", "(ти купив у нього: "
                        + ", ".join(f"{i} за {p}" for i, _, p in found) + ")")

    def confront(self, killer, target, state):
        """Before a paid hit: the killer calls the target out and the target answers; then the shooting starts."""
        scene = ("A has just been paid by the player to kill B. A turns to B and calls him out right now (a cold "
                 "threat, a cruel joke or 'nothing personal, it's business'); B realises what's happening and "
                 "answers (begs, swears, threatens back or grabs his gun). 2-3 lines in total, starting with A, "
                 "ending right before the first shot.")
        try:
            lines = self.brain.chat(killer, target, state, "", self.recent_lines(), scene=scene)
        except Exception as exc:
            log(f"confront error: {exc!r}")
            return
        lines = lines[:3]
        self.speak_lines(lines, state, notes=["(before the paid hit)"] * len(lines),
                         gestures=list(self.brain.chat_emotes)[:len(lines)])

    def chime_in(self, npc, state, player_text, line, after=None):
        """Sometimes one bystander butts into the conversation. Only once: his line never triggers another.
        His line is written right away and spoken after `after` (the line he reacts to) has started playing.
        Returns the thread, or None if nobody is there."""
        others = [n for n in state.get("npcs", []) if isinstance(n, dict) and n.get("id") != npc.get("id")
                  and n.get("dist", 99) < 8 and n.get("relation") != "enemy" and not n.get("wounded")
                  and not n.get("in_combat") and not is_monolith(n)]
        if not others:
            return None
        other = others[0]
        extra = {"name": npc.get("name"), "player": player_text, "line": line}
        return self.answer_after(after, other, state, "chime", extra=extra, to=npc,
                                 note=f"(butting in on the player and {npc.get('name')})")

    def squad_backup(self, leader, state, line, action):
        """Squad mates standing nearby back their man up; if he turns hostile, so do they."""
        if not leader.get("squad"):
            return
        mates = [n for n in state.get("npcs", []) if isinstance(n, dict) and n.get("squad") == leader["squad"]
                 and n.get("id") != leader.get("id") and n.get("dist", 99) < 25 and not n.get("wounded")]
        random.shuffle(mates)
        for mate in mates[:BACKUP_MAX]:
            if action == "warn" and random.random() > BACKUP_CHANCE:
                continue
            extra = {"leader": leader.get("name"), "line": line}
            reply = self.brain.reply(mate, state, "", [], "", "backup", recent=self.recent_lines(), extra=extra)
            if reply:
                log(f"  {mate.get('name')} (backs up): {reply}")
                self.speak(mate, reply, state, note="(backing up your mate, at the player)")
            if action == "hostile" and not mate.get("story") and mate.get("relation") != "enemy":
                self.game.send("act", mate["id"], "hostile")

    def watch_environment(self):
        """NPCs react on their own to what changes around them: emission, mutants, fights, wounds, night, storms."""
        state = self.game.state()
        if not state or not self.game_is_live(state):
            return
        prev, self.prev_state = self.prev_state, state
        if not prev or prev.get("level") != state.get("level"):
            self.seen_mutants = {m.get("id") for m in state.get("mutants", []) if isinstance(m, dict)}
            return
        now = time.time()
        if self.busy.locked() or self.recording:
            return
        npcs = [n for n in state.get("npcs", []) if isinstance(n, dict) and n.get("relation") != "enemy"]
        before = {n.get("id"): n for n in prev.get("npcs", []) if isinstance(n, dict)}
        urgent, what, speaker = False, None, None

        if state.get("emission") and not prev.get("emission"):
            urgent, what = True, "The sky turns red: an EMISSION is starting right now."
            speaker = npcs[0] if npcs and npcs[0].get("dist", 99) < 30 else None
        elif prev.get("emission") and not state.get("emission"):
            urgent, what = True, "The emission has just ended, the sky is clearing."
            speaker = npcs[0] if npcs and npcs[0].get("dist", 99) < 20 else None
        if not what:
            for m in state.get("mutants", []):
                if isinstance(m, dict) and m.get("id") not in self.seen_mutants and m.get("dist", 99) < 35:
                    # only men actually fighting talk about it: a dog wandering past isn't worth a word
                    near = [n for n in npcs if n.get("dist", 99) < 25 and not n.get("wounded") and n.get("in_combat")]
                    if near:
                        self.seen_mutants.add(m.get("id"))
                        urgent, speaker = True, near[0]
                        what = (f"A {mutant_name(m.get('kind'))} is attacking, about {m.get('dist', 0):.0f} m away, "
                                "and you're fighting it.")
                        break
        if not what:
            for n in npcs:
                old = before.get(n.get("id"), {})
                if n.get("wounded") and not old.get("wounded") and n.get("dist", 99) < 30:
                    urgent, speaker = True, n
                    what = "You were just badly wounded and fell. Call for help."
                    break
                if n.get("in_combat") and not old.get("in_combat") and n.get("fighting") != "player" \
                        and n.get("dist", 99) < 30:
                    urgent, speaker = True, n
                    what = "Enemies just appeared and a fight is starting."
                    break
        if not what and npcs and npcs[0].get("dist", 99) < 15:
            hours, old_hours = state.get("hours", 12), prev.get("hours", 12)
            if hours == 21 and old_hours == 20:
                what, speaker = "It is getting dark, night is falling in the Zone.", npcs[0]
            elif weather_name(state.get("weather")) in ("дощ", "гроза") and \
                    weather_name(prev.get("weather")) not in ("дощ", "гроза"):
                what, speaker = f"The weather just turned: {weather_name(state.get('weather'))}.", npcs[0]

        if not what or not speaker:
            return
        if now < (self.next_urgent if urgent else self.next_env):
            return
        if not urgent and random.random() > ENV_CHANCE:
            return
        self.next_urgent = now + ENV_URGENT_COOLDOWN
        self.next_env = now + ENV_COOLDOWN
        threading.Thread(target=self._ambient_line, args=(speaker, state, "react", {"what": what}),
                         daemon=True).start()

    def on_push_to_talk(self):
        if self.recording or not getattr(self, "game_on", True):
            return
        # Record and understand him right away, even while an NPC is still talking; the answer waits its turn
        # (before, a press during someone's line was simply lost and he had to say it again).
        self.recording = True
        try:
            if not self.game_ptt:  # in-game push-to-talk shows "Слухаю..." at the bottom instead
                self.game.send("info", None, "Запис... говоріть")
            log("● Recording...")
            audio = self.ears.record_while_held(self.ptt_held)
            text = self.ears.transcribe(audio)
        except Exception as exc:
            log(f"error: {exc!r}")
            return
        finally:
            self.recording = False
        log(f"You: {text or '(nothing heard)'}")
        if text:
            if SUBTITLES in ("bottom", "both"):
                self.game.send("sub", None, text)  # your own words, until the answer replaces them
            if SUBTITLES in ("pda", "both"):
                self.game.send("you", None, text)
        else:
            self.game.send("info", None, "Не розчув, спробуйте ще раз")
        if self.busy.locked():
            log("  (someone is still talking: your words wait for him to finish)")
        if not self.busy.acquire(timeout=90):
            log("  (waited too long, your words were dropped)")
            return
        try:
            state = self.game.state()  # fresh: people may have moved while he waited
            if not state:
                log("Game state not found. Is the game running with the mod installed?")
                return
            npc = self.game.pick_listener(state, text)
            if text and to_everyone(text) and self.group_answer(state, text, f"The player (a stalker{' called ' + PLAYER_NAME if PLAYER_NAME else ''})",
                                                                     from_player=True,
                                                                     kind="story" if tells_joke(text) else "talk"):
                return  # "Пацани, ..." — several men around answered
            if not npc:
                log("Nobody close enough to hear you.")
                if text:
                    self.game.send("info", None, "Поруч нікого, хто б почув")
                return
            self.converse(npc, state, text)
        except Exception as exc:  # keep running whatever happens
            log(f"error: {exc!r}")
        finally:
            self.game.send("status", None, "")  # never leave "Думає..." hanging
            self.busy.release()

    def ambient(self, events):
        if time.time() < self.next_ambient or self.busy.locked():
            return
        state = self.game.state()
        if not state:
            return
        npcs = [n for n in state.get("npcs", []) if isinstance(n, dict)]
        for ev in events:
            speaker = None
            if ev.get("type") == "actor_hit_npc":
                hit = ev.get("npc") or {}
                speaker = next((n for n in npcs if n["id"] == hit.get("id") and n["relation"] != "enemy"), None)
            elif ev.get("type") == "death":
                victim_id = (ev.get("victim") or {}).get("id")
                victim = ev.get("victim") or {}
                witnesses = [n for n in npcs if n["id"] != victim_id and knows(n, victim)
                             and n["relation"] != "enemy" and not n.get("in_combat")]
                if witnesses and random.random() < 0.6:
                    speaker = witnesses[0]
            if speaker:
                self.next_ambient = time.time() + AMBIENT_COOLDOWN
                threading.Thread(target=self._ambient_line, args=(speaker, state), daemon=True).start()
                return

    def _ambient_line(self, npc, state, mode=None, extra=None):
        if not self.busy.acquire(blocking=False):
            return
        try:
            self.converse(npc, state, "", mode, extra)
        except Exception as exc:
            log(f"ambient error: {exc!r}")
        finally:
            self.busy.release()

    def game_is_live(self, state):
        """True while the game keeps updating state.json (not paused, not in the main menu)."""
        if state.get("t") != self.last_state_t:
            self.last_state_t, self.last_state_change = state.get("t"), time.time()
        return time.time() - self.last_state_change < 3

    def proactive(self):
        """NPCs speak up on their own: brief greetings/questions nearby, shouting if hostile."""
        now = time.time()
        if now < self.next_proactive or self.busy.locked() or self.recording:
            return
        state = self.game.state()
        if not state or not self.game_is_live(state) or state.get("actor", {}).get("talking"):
            return
        npcs = [n for n in state.get("npcs", []) if isinstance(n, dict) and not n.get("wounded")]

        hostile = [n for n in npcs if n.get("relation") == "enemy" and n.get("dist", 99) < 35
                   and n.get("in_combat")]  # only enemies actually fighting shout, not every one in sight
        if hostile and random.random() < HOSTILE_CHANCE:
            npc = random.choice(hostile[:3])
            self.next_proactive = now + HOSTILE_COOLDOWN
            threading.Thread(target=self._ambient_line, args=(npc, state, "hostile"), daemon=True).start()
            return

        friendly = [n for n in npcs if n.get("relation") != "enemy" and n.get("dist", 99) < GREET_DISTANCE
                    and not n.get("in_combat") and now >= self.npc_quiet_until.get(n["id"], 0)]
        chance = GREET_CHANCE / 2 if state.get("emission") else GREET_CHANCE  # people sit it out quietly
        if friendly and random.random() < chance:
            npc = friendly[0]
            self.npc_quiet_until[npc["id"]] = now + GREET_NPC_COOLDOWN
            self.next_proactive = now + GREET_COOLDOWN
            threading.Thread(target=self._ambient_line, args=(npc, state, "greet"), daemon=True).start()

    # ------------------------------------------------------------ quick reactions (TALKER-style triggers)
    REACTIONS = {
        "artifact": "The player just picked up an artifact ({name}) right next to you. React: envy, a joke, "
                    "advice or a superstition.",
        "anomaly_hit": "The player just blundered into an anomaly and got hurt. React: worry, mockery or advice.",
        "jam": "The player's gun just jammed. React briefly.",
        "mag_empty": "Mid-fight the player's magazine ran dry and he is reloading. Shout that you cover him.",
    }

    def quick_react(self, events):
        now = time.time()
        if now < self.next_react or self.busy.locked() or self.recording:
            return
        state = self.game.state()
        if not state:
            return
        for ev in events:
            kind = ev.get("type")
            if kind not in self.REACTIONS or random.random() > REACT_CHANCE:
                continue
            friends = [n for n in state.get("npcs", []) if isinstance(n, dict) and n.get("relation") != "enemy"
                       and not n.get("wounded") and n.get("dist", 99) < 15 and not is_monolith(n)]
            if kind == "mag_empty":  # only matters in a fight next to someone on your side
                friends = [n for n in friends if n.get("in_combat") or n.get("following")]
            elif kind != "anomaly_hit":
                friends = [n for n in friends if not n.get("in_combat")]
            if not friends:
                continue
            friends.sort(key=lambda n: (not n.get("following"), n.get("dist", 99)))
            what = self.REACTIONS[kind].format(name=clean_game_text(ev.get("name") or "артефакт"))
            self.next_react = now + REACT_COOLDOWN
            threading.Thread(target=self._ambient_line, args=(friends[0], state, "react", {"what": what}),
                             daemon=True).start()
            return

    # ------------------------------------------------------------ companions talk on the way
    def companion_talk(self, state):
        now = time.time()
        followers = [n for n in state.get("npcs", []) if isinstance(n, dict) and n.get("following")
                     and n.get("dist", 99) < 25 and not n.get("in_combat")]
        level_changed = getattr(self, "last_level", None) not in (None, state.get("level"))
        self.last_level = state.get("level")
        if not followers:
            return False
        npc = followers[0]
        actor = state.get("actor") or {}
        if level_changed:
            what = f"You just arrived together at {LEVELS.get(state.get('level'), state.get('level'))}."
        elif now < self.next_companion or random.random() > COMPANION_CHANCE:
            return False
        elif actor.get("health", 1) < 0.4:
            what = "The player looks badly hurt and bleeding. Tell him to patch up."
        elif state.get("emission") and not state.get("actor_sheltered"):
            what = "An emission is coming and you two are outside. Hurry him to cover."
        else:
            what = random.choice([
                f"Say something about this place ({place_name(npc.get('place')) or LEVELS.get(state.get('level'))}).",
                "Tell a short rumour or story you heard at the campfire.",
                "Ask him where exactly you are heading and why.",
                "Complain about something: your feet, the food, the weather, the money.",
                "Make a dumb joke or share a stalker superstition.",
                "Warn him to watch for anomalies and mutants around here.",
                "Remember something about your past life on the Big Land.",
            ])
            if not is_monolith(npc) and random.random() < OUTSIDE_TALK:
                what = self.brain.outside_topic()
        self.next_companion = now + COMPANION_COOLDOWN
        threading.Thread(target=self._ambient_line, args=(npc, state, "companion", {"what": what}),
                         daemon=True).start()
        return True

    # ------------------------------------------------------------ NPCs talking to each other
    def npc_chat(self, state):
        now = time.time()
        if now < self.next_chat or random.random() > CHAT_CHANCE:
            return False
        npcs = [n for n in state.get("npcs", []) if isinstance(n, dict) and n.get("relation") != "enemy"
                and not n.get("in_combat") and not n.get("wounded") and not is_monolith(n)
                and n.get("dist", 99) < CHAT_DISTANCE and n.get("community") not in ("zombied",)]
        if state.get("emission") and not state.get("actor_sheltered"):
            return False
        pairs = [(a, b) for i, a in enumerate(npcs) for b in npcs[i + 1:]
                 if (a.get("place") and a.get("place") == b.get("place"))
                 or (a.get("squad") and a.get("squad") == b.get("squad"))]
        if not pairs:
            return False
        a, b = random.choice(pairs)
        self.next_chat = now + CHAT_COOLDOWN
        threading.Thread(target=self._chat, args=(a, b, state), daemon=True).start()
        return True

    def _chat(self, a, b, state):
        if not self.busy.acquire(blocking=False):
            return
        try:
            nearby = [n for n in state.get("npcs", []) if isinstance(n, dict) and n.get("id") not in
                      (a.get("id"), b.get("id")) and n.get("relation") != "enemy" and not n.get("in_combat")
                      and not n.get("wounded") and not is_monolith(n) and n.get("community") != "zombied"
                      and in_earshot(n, (a, b))]
            lines = self.brain.chat(a, b, state, self.game.describe_events(a, b), self.recent_lines(),
                                    memories=[self.memory.remembers(self.npc_key(n, state)) for n in (a, b)],
                                    nearby=nearby)
            if len(lines) < 2 or too_similar(strip_tags(lines[0][1]), self.recent_lines()):
                return
            log(f"Chat: {a.get('name')} & {b.get('name')}")
            # Someone around was named: he heard it and reacts (written while their talk plays).
            heard = self.start_overheard(lines, (a, b), state, bystanders=nearby)
            self.speak_lines(lines, state, notes=[f"(to {(b if npc is a else a).get('name')})" for npc, _ in lines],
                             gestures=list(self.brain.chat_emotes)[:len(lines)])
            self.finish_overheard(heard, state)
        except Exception as exc:
            log(f"chat error: {exc!r}")
        finally:
            self.busy.release()

    def bystanders(self, talkers, state):
        """Men close enough to hear these talkers (NPCs, or the player and an NPC), who could react."""
        ids = {t.get("id") for t in talkers if not t.get("player")}
        npc_talkers = [t for t in talkers if not t.get("player")]
        with_player = any(t.get("player") for t in talkers)
        return [n for n in state.get("npcs", []) if isinstance(n, dict) and n.get("id") not in ids
                and n.get("relation") != "enemy" and not n.get("in_combat") and not n.get("wounded")
                and not is_monolith(n) and n.get("community") != "zombied"
                and (not with_player or n.get("dist", 99) <= EARSHOT * 1.5) and in_earshot(n, npc_talkers)]

    def start_overheard(self, lines, talkers, state, bystanders=None):
        """If the talk names a man standing nearby, write his reaction now (while the talk plays).
        talkers: (a, b), a may be PLAYER_TALKER. Returns a handle for finish_overheard, or None."""
        try:
            nearby = self.bystanders(talkers, state) if bystanders is None else bystanders
            third = named_bystander(lines, nearby, talkers)
        except Exception as exc:
            log(f"overheard error: {exc!r}")
            return None
        if not third:
            return None
        a, b = (tuple(talkers) + (None,))[:2]
        scene = []

        def write():
            try:
                scene.extend(self.brain.overheard(third, a, b, lines, state,
                                                  self.memory.remembers(self.npc_key(third, state))))
            except Exception as exc:
                log(f"overheard error: {exc!r}")
        writer = threading.Thread(target=write, daemon=True)
        writer.start()
        return third, a, b, scene, writer

    def finish_overheard(self, heard, state):
        """Play what happened after the named man heard it: their words, then the shooting if someone drew."""
        if not heard:
            return
        third, a, b, scene, writer = heard
        writer.join(30)
        if not scene or self.recording:
            return
        log(f"  {third.get('name')} " + ("heard his name:" if b is not None else "answers:"))
        name = lambda n: "you" if n.get("player") else n.get("name")
        notes = [(f"(to {name(a)} and {name(b)})" if b is not None else f"(to {name(a)})") if npc is third
                 else f"(to {third.get('name')})"
                 for npc, *_ in scene]
        said_it = next((n for n in (b, a) if n is not None and not n.get("player")), None)
        self.speak_lines([(npc, line) for npc, line, *_ in scene], state, notes=notes,
                         gestures=[emote for _, _, emote, _ in scene], look_first=said_it)
        if self.recording:
            return
        for npc, _, _, kills in scene:
            for target in kills:
                if target.get("player"):
                    if npc.get("relation") != "enemy":
                        self.game.send("act", npc["id"], "hostile")
                        self.game.send("info", None, f"{npc.get('name')} відкриває вогонь по вас")
                        log(f"{npc.get('name')} -> HOSTILE (overheard quarrel)")
                    continue
                self.game.send("act", npc["id"], f"kill:{target['id']}")
                self.game.send("info", None, f"{npc.get('name')} стріляє в {target.get('name')}")
                log(f"{npc.get('name')} -> KILL {target.get('name')} (overheard quarrel)")

    # ------------------------------------------------------------ Twitch: viewers speak through NPCs
    def on_twitch(self, user, text, redemption):
        text = chat_text(text)  # first, so "%% ͏" (a chat client's invisible mark) is still "%%"
        if text == "%%":  # "unlink me": his NPC is let go; his next message gets another man
            if TWITCH_LINKS:
                self.unlink_viewer(user)
            if redemption is not None and self.twitch:
                self.twitch.finish(redemption, spoken=False)
            return
        if text[:1] in ("$", "%"):  # the first sign picks how the NPC says it
            mode, text = ("verbatim" if text[0] == "$" else "character"), text[1:].strip()
        else:  # no $ or %: TWITCH_UNPREFIXED decides (ignored by default)
            mode = TWITCH_UNPREFIXED
            if mode not in ("verbatim", "character"):
                if redemption is not None and self.twitch:
                    self.twitch.finish(redemption, spoken=False)  # a reward without $ or %: refund the points
                return
        text = chat_text(re.sub(r"https?://\S+|www\.\S+", "", text))[:200]
        if not text or any(w in text.lower() for w in TWITCH_BLOCKED):
            log(f"Twitch: skipped a message from {user}")
            if self.twitch:
                self.twitch.finish(redemption, spoken=False)  # refunds the points
            return
        self.twitch_queue.append((user, text, redemption, mode))
        del self.twitch_queue[:-TWITCH_QUEUE_MAX]
        log(f"Twitch: {user} -> «{text}» ({mode}, waiting: {len(self.twitch_queue)})")
        report("TWITCH_QUEUE", str(len(self.twitch_queue)))

    # ------------------------------------------------------------ Zone reward (companion/zone.py)
    def on_zone(self, user, redemption=None):
        """A viewer redeemed the Zone reward: rolled now; first in the queue goes off at once, the others
        each wait TWITCH_ZONE_GAP minutes after the one before."""
        item = self.zone.add(user, time.time())
        wait = item["due"] - time.time()
        when = "now" if wait < 30 else f"in ~{max(1, round(wait / 60))} min"
        log(f"Twitch: {user} redeemed the Zone reward -> {zone.label(item)} ({when}, waiting: {len(self.zone.items)})")
        soon = "Щось станеться просто зараз" if wait < 30 else f"Щось станеться за ~{max(1, round(wait / 60))} хв"
        self.game.send("twitch", None, f"{zone.clean_nick(user)}: Зона почула тебе. {soon}")
        self.report_zone(force=True)

    def redeem_blocked(self, user, name, need):
        """Why a redeem can't go to the game right now (logged, and shown on the window's Redeems tab), or None.
        need: the game script version it needs."""
        state = self.game.state()
        have = (state or {}).get("mod_version") or 0
        if not state:
            why = "the game isn't running (or no save is loaded)"
        elif have < need:
            why = (f"the game runs an old copy of the mod (v{have}, this needs v{need}): press Reinstall game mod, "
                   "then reload your save")
        elif (state.get("actor") or {}).get("health", 1) <= 0:
            why = "you're dead"
        else:
            report("REDEEM_NOTE", f"«{name}» sent to the game")
            return None
        log(f"Twitch: {user} redeemed «{name}», but {why}")
        report("REDEEM_NOTE", f"«{name}» didn't run: {why}")
        return why

    def on_suslov(self, user, redemption=None):
        """«Шари Суслова»: two «Вогняна куля» and a «Ковбаса» laid out on the ground in front of the player, at once
        (no queue, no waiting; the game still autosaves first, like before any Zone event)."""
        nick = zone.clean_nick(user)
        if self.redeem_blocked(user, f"Шари Суслова", 14):
            return
        log(f"Twitch: {user} redeemed «Шари Суслова»")
        self.zone_fired = {"kind": "suslov", "user": user}
        self.game.send("zone", None, f"suslov|Шари Суслова|{nick} шле привіт від Суслова. Під ногами, глянь")

    GIANT_NAME = "Хуй будеш?"  # the reward's title, and the PDA caption

    def on_giant(self, user, redemption=None):
        """«Хуй будеш?»: one pseudogiant turns up near the player, at once (no queue, no waiting; the game still
        autosaves first), hostile and provoked like the Zone's mutants. The men around panic about it."""
        nick = zone.clean_nick(user)
        if self.redeem_blocked(user, f"{self.GIANT_NAME}", 15):
            return
        log(f"Twitch: {user} redeemed «{self.GIANT_NAME}»")
        self.zone_fired = {"kind": "giant", "user": user, "monster": "псевдогігант"}
        self.game.send("zone", None, f"giant|{self.GIANT_NAME}|{nick} питає: «Хуй будеш?» Псевдогігант уже скаче "
                                     "з відповіддю. Тікай, сталкере, бо буде!")

    VOVA_NAME = "Вова Віст"  # the PDA caption, and his name in the game

    def on_vova(self, user, redemption=None):
        """«Вова Віст»: a soldier (військовий) of that name turns up near the player, at once, with a machine gun that
        fires 100x as fast and does 1000x less damage («Свистілка Вови Віста»). Neutral to the player, he opens fire
        on everyone else around. Needs script version 15 and the gun's section (install_mod.ps1)."""
        nick = zone.clean_nick(user)
        if self.redeem_blocked(user, f"{self.VOVA_NAME}", 15):
            return
        log(f"Twitch: {user} redeemed «{self.VOVA_NAME}»")
        self.zone_fired = {"kind": "vova", "user": user}
        self.game.send("zone", None, f"vova|{self.VOVA_NAME}|{nick} кличе Вову Віста. Зараз засвистить")

    def on_anekdot(self, user, redemption=None):
        """«Анекдот»: a «Хліб», a «Ковбаса» and a handful of bolts dropped on the ground in front of the player, at once
        (no queue). They roll and can be kicked, but nobody can keep them: picked up, they go back. Needs script v15."""
        nick = zone.clean_nick(user)
        if self.redeem_blocked(user, f"Анекдот", 15):
            return
        log(f"Twitch: {user} redeemed «Анекдот»")
        self.zone_fired = {"kind": "anekdot", "user": user}
        self.game.send("zone", None, f"anekdot|Анекдот|{nick} розповідає анекдот. Хліб, ковбаса і болти, під ногами")

    SIXTY_TWO_NAME = "62"  # the reward's title, and the PDA caption

    def on_sixty_two(self, user, redemption=None):
        """«62»: the streamer's own clip «шиісят два» (gamedata\\sounds\\talker\\sixty_two*.ogg) is shouted 10 times at
        once from all round the player, each copy from its own spot, at its own volume, pitch, speed and delay, so they
        overlap and echo. At once, no queue, and no autosave (it's only a sound). Needs script version 15."""
        nick = zone.clean_nick(user)
        if self.redeem_blocked(user, f"{self.SIXTY_TWO_NAME}", 15):
            return
        log(f"Twitch: {user} redeemed «{self.SIXTY_TWO_NAME}»")
        self.zone_fired = {"kind": "62", "user": user}
        self.game.send("zone", None, f"62|{self.SIXTY_TWO_NAME}|{nick} передає: шиісят два! Звідусіль")

    def send_named(self, user, kind, name, community, weapon, side, text):
        """A named man of a faction turns up near the player, at once (no queue; the game still autosaves first):
        sim_default_<community>_<rank>, called <name> in the game, with <weapon> (a stock section; "" = his own gun)
        and nothing else to shoot with. side: enemy, neutral or ally. The viewer's nickname goes on the label over his
        head and the viewer speaks through him, like a Zone friend's. text: the PDA line under his name."""
        nick = zone.clean_nick(user)
        if self.redeem_blocked(user, f"{name}", 15):
            return False
        log(f"Twitch: {user} redeemed «{name}»")
        self.zone_fired = {"kind": kind, "user": user}
        self.game.send("zone", None, f"npc:{kind}:{community}:{weapon}:{side}:{nick}|{name}|{text}")
        return True

    GOSHA_NAME = "Гоша"  # the PDA caption, and his name in the game

    def on_gosha(self, user, redemption=None):
        """«Гоша»: a Mercenary (найманець) of that name turns up 15-30 m away with a stock SPAS-12, hostile, and comes
        for the player. Needs script version 15."""
        self.send_named(user, "gosha", self.GOSHA_NAME, "killer", "wpn_spas12", "enemy",
                        f"{zone.clean_nick(user)} кличе Гошу. Найманець із дробовиком уже йде по тебе")

    def zone_test(self, kind=None):
        """The window's test button: a Zone event at once, without a redemption."""
        who = (self.twitch.login if self.twitch and self.twitch.login else None) or "test"
        item = self.zone.add_test(who, time.time(), kind if kind in zone.TITLES else None)
        log(f"Zone test: {zone.label(item)}")
        self.report_zone(force=True)

    def zone_tick(self, state):
        """Fire the Zone event whose time has come, while the game runs and the player is alive."""
        if not self.zone.items or (state.get("mod_version") or 0) < 14:
            return
        if (state.get("actor") or {}).get("health", 1) <= 0:
            return
        item = self.zone.pop_due(time.time())
        if not item:
            return
        what, caption, text = zone.command(item)
        self.zone_fired = item
        log(f"Zone event for {item['user']}: {zone.label(item)}")
        self.game.send("zone", None, f"{what}|{caption}|{text}")
        self.report_zone(force=True)

    def on_zone_results(self, events):
        """The game's answer: a man to link to the viewer's nickname, or a failure to try again."""
        for ev in events:
            if ev.get("type") == "zone_spawned" and ev.get("nick"):
                npc = dict(ev.get("npc") or {}, id=ev.get("id"))
                self.link_viewer(ev["nick"], npc, from_zone=True)
                self.zone_react(ev.get("tag") or "life", ev, npc)  # he's in the game now: the men around can see him
                if ev.get("tag") and ev.get("named") is False:
                    log(f"  Zone: {ev['tag']} came as «{npc.get('name')}» (the game kept its own name for him)")
            elif ev.get("type") == "zone_done":
                item = getattr(self, "zone_fired", None)
                if ev.get("ok") and item and item.get("kind") != "life" and not ev.get("tag"):  # a man: once he's in
                    self.zone_react(item["kind"], dict(ev, monster=item.get("monster")))
                saved = {"saved": ", autosaved first"}.get(ev.get("autosave"),
                                                         f", no autosave: {ev['autosave']}" if ev.get("autosave") else "")
                if ev.get("ok"):
                    log(f"  Zone: done ({ev.get('section')}{' x' + str(ev['count']) if ev.get('count') else ''}{saved})")
                elif item and item.get("kind") not in NO_RETRY and self.zone.retry(item, time.time()):
                    log(f"  Zone: the game couldn't do it ({ev.get('reason')}), trying again in 30 s")
                else:
                    log(f"  Zone: the game couldn't do it ({ev.get('reason')}), given up")
                self.zone_fired = None
                self.report_zone(force=True)

    def report_rewards(self):
        """All rewards of the channel, for the window's reward pickers."""
        if not self.twitch:
            report("REWARDS_ERROR", "Twitch is off (TWITCH_ENABLED, TWITCH_CLIENT_ID)")
            return
        try:
            report("REWARDS", json.dumps(self.twitch.list_rewards(), ensure_ascii=False))
        except Exception as exc:
            report("REWARDS_ERROR", str(exc)[:160])

    ZONE_REACT_DELAY = 3.0      # seconds: let the mutants appear before anyone shouts
    ZONE_REACT_COOLDOWN = 20.0  # several events close together: one reaction, not a pile of them

    def zone_what(self, kind, ev, spawned=None):
        """What the men around just saw, for the AI (said by them, never by the viewer)."""
        if kind == "gift":
            name = clean_game_text(ev.get("name") or "") or "something"
            return (f"Out of thin air an item ({name}) just landed in the player's backpack: a gift of the Zone. "
                    "React: surprise, envy, a superstition or a joke.")
        if kind == "suslov":
            return ("Out of thin air, right at the player's feet, two «Вогняна куля» artifacts and a sausage just fell "
                    "and lie on the ground in the shape of a dick. React: laugh, a crude joke about it, about Суслов "
                    "or about whoever sent it.")
        if kind == "anekdot":
            return ("Out of thin air, right at the player's feet, a loaf of bread, a sausage and a handful of bolts "
                    "just fell on the ground, like the punchline of a joke. React: laugh, and tell a short stalker "
                    "joke (анекдот) of your own, one or two sentences.")
        if kind == "62":
            return ("Out of nowhere a man's voice just started shouting «шиісят два» (Ukrainian-Russian surzhyk for 'sixty-two') "
                    "from every side at once, over and over, near and far, high and low, echoing all round you, and "
                    "there is nobody there. React confused and freaked out: what the hell is that, who is shouting, "
                    "why sixty-two, is it the Zone, a controller (контролер) in your head, too much vodka? Swear, joke "
                    "nervously, or ask the others if they hear it too.")
        if kind == "gosha":
            return (f"Out of thin air a man just appeared nearby: «{(spawned or {}).get('name') or 'Гоша'}», one of the "
                    "найманці (mercenaries), with a shotgun, and he is coming to kill the player. A viewer sent him. "
                    "Shout a warning, curse the mercenaries, or crack a grim joke about Гоша.")
        if kind == "vova":
            return ("Out of thin air a soldier just appeared nearby: «Вова Віст», one of the військові, with a machine "
                    "gun that fires like crazy but only whistles and tickles, and he opens fire on everyone around "
                    "except the player. React: duck and swear, laugh at the toy gun, or mock Вова.")
        if kind == "giant":
            return ("Out of thin air a pseudogiant (псевдогігант: a huge, ground-shaking mutant that stomps people flat) "
                    "just appeared right nearby and is charging at you. A viewer sent it with the question «Хуй будеш?» "
                    "(crude slang, 'will you have some dick?'). React in a panic: scream, swear filthily, a crude "
                    "joke about the giant, the question or whoever sent it, then tell everyone to run or shoot.")
        if kind == "child":
            return (f"The Zone just spawned mutants ({ev.get('monster') or 'mutants'}, {ev.get('count') or 'a few'}) "
                    "nearby, and they are coming at you. Shout a warning, curse, or crack a grim joke.")
        who = (spawned or {}).get("name") or "a stalker"
        if ev.get("side") == "ally":
            return (f"A stalker ({who}) just appeared out of thin air nearby and joined the player as his companion. "
                    "React: surprise, suspicion or a joke.")
        return (f"A hostile stalker ({who}) just appeared out of thin air nearby and is going for the player. "
                "Shout a warning or curse.")

    def zone_react(self, kind, ev, spawned=None, background=True):
        """Men nearby react out loud to a Zone event (also in chat-only mode: it's a viewer's redeem). The friend the
        Zone sent greets the player first. One reaction per ZONE_REACT_COOLDOWN, however many events fire."""
        now = time.time()
        if now < getattr(self, "next_zone_react", 0):
            return
        self.next_zone_react = now + self.ZONE_REACT_COOLDOWN
        greet = spawned if kind == "life" and ev.get("side") == "ally" else None
        args = (kind, ev, spawned, greet)
        if background:
            threading.Thread(target=self._zone_react, args=args, daemon=True).start()
        else:
            self._zone_react(*args)

    def _zone_react(self, kind, ev, spawned, greet):
        time.sleep(self.ZONE_REACT_DELAY)
        state = self.game.state()
        if not state or not self.busy.acquire(timeout=10):
            return
        try:
            fight = kind in ("child", "giant") or (kind == "life" and ev.get("side") == "enemy")
            spawned_id = (spawned or {}).get("id")
            men = [n for n in state.get("npcs", []) if isinstance(n, dict) and n.get("id") != spawned_id
                   and n.get("dist", 99) < 30 and not n.get("wounded") and not is_monolith(n)
                   and n.get("relation") != "enemy" and (fight or not n.get("in_combat"))]
            men.sort(key=lambda n: (not n.get("following"), n.get("dist", 99)))
            what = self.zone_what(kind, ev, spawned)
            said = []
            if greet:
                here = next((n for n in state.get("npcs", []) if isinstance(n, dict) and n.get("id") == spawned_id),
                            None) or dict(greet, relation="friend")
                line = self.brain.reply(here, state, "", [], "", "react", extra={"what": (
                    f"The Zone just brought you here, out of thin air, next to the player: from now on you go with "
                    f"him as his companion (a viewer called {ev.get('nick') or 'someone'} sent you). Greet him "
                    "briefly, in character.")})
                if line:
                    log(f"  Zone friend {here.get('name')}: {line}")
                    self.speak(here, line, state, note="(appeared out of nowhere and joined the player)")
                    said.append((here.get("name"), strip_tags(line)))
            for npc in men[:1 if greet else 2]:
                if said and random.random() < 0.4:
                    break  # a second man only sometimes
                extra = what + "".join(f' {name} just said: "{line}".' for name, line in said)
                line = self.brain.reply(npc, state, "", [], "", "react", extra={"what": extra})
                if not line:
                    continue
                log(f"  {npc.get('name')} reacts to the Zone: {line}")
                self.speak(npc, line, state, note="(reacting to something the Zone did)")
                said.append((npc.get("name"), strip_tags(line)))
        except Exception as exc:
            log(f"zone reaction error: {exc!r}")
        finally:
            self.busy.release()

    def report_zone(self, force=False):
        """The queue for the window's Twitch tab (each line: what, whose, in how many seconds)."""
        rows = self.zone.summary(time.time())
        text = json.dumps(rows, ensure_ascii=False)
        if force or rows or self.zone_reported != text:
            self.zone_reported = text
            report("ZONE", text)

    def twitch_speak(self, state):
        """Give the oldest viewer message to a random NPC nearby; if nobody is around, wait for one."""
        if not self.twitch_queue or self.busy.locked() or self.recording:
            return False
        npcs = [n for n in state.get("npcs", []) if isinstance(n, dict) and n.get("dist", 99) < TWITCH_DISTANCE
                and not n.get("wounded")]
        if not npcs:
            if time.time() >= self.next_twitch_note:
                self.next_twitch_note = time.time() + 120
                log(f"Twitch: {len(self.twitch_queue)} message(s) waiting for someone to come close")
            return False
        item = self.twitch_queue.pop(0)
        user = item[0]
        named = [n for n in npcs if mentions(n, item[1])]
        others = [n for n in npcs if n not in named]
        # Each viewer speaks through "his" NPC while that man is around; otherwise he gets a new one.
        link = self.twitch_links.get(user.lower()) if TWITCH_LINKS else None
        linked = next((n for n in npcs if link and n.get("id") == link), None)
        if not TWITCH_LINKS:  # links off: any man nearby (not one the message names) says it
            npc = random.choice(others) if others else None
        elif linked:
            # his own man always speaks for him, even if the words seem to name him ("бороду" vs Борода)
            npc = linked
            named = [n for n in named if n is not linked]
        else:
            # Someone else says the message, so the named stalker isn't talking about himself; he answers after.
            taken = set(self.twitch_links.values())
            free = [n for n in others if n.get("id") not in taken]
            left = self.left_npc.pop(user.lower(), None)  # after "%%": a different man, if there is one
            free = [n for n in free if n.get("id") != left] or free
            if user.lower() in self.zone_links:  # his Zone man is away: borrow someone, he stays linked
                npc = random.choice(free or others) if (free or others) else None
            elif free:  # new viewer, or his man is gone (left, dead, wounded): link him to a free one
                npc = random.choice(free)
                self.link_viewer(user, npc)
            else:  # every man around already speaks for a viewer: borrow one for this message, take nobody's man
                npc = random.choice(others) if others else None
        threading.Thread(target=self._twitch_line, args=(npc, state, item, named[0] if named else None),
                         daemon=True).start()
        return True

    def unlink_viewer(self, user):
        """The viewer asked to be let go from his NPC ("%%"): the label goes, and his next message is said by
        another man (not the one he just left, if anyone else is free)."""
        key = user.lower()
        if key in self.zone_links:
            log(f"Twitch: {user} asked to unlink, but his man came from the Zone: he stays until he dies")
            return
        old = self.twitch_links.pop(key, None)
        if old is None:
            log(f"Twitch: {user} asked to unlink, but has no NPC")
            return
        self.left_npc[key] = old
        self.save_links()
        self.game.send("link", old, "")
        log(f"Twitch: {user} unlinked from his NPC; the next message gets another one")

    def link_viewer(self, user, npc, from_zone=False):
        """From now on this viewer's messages go through this NPC; looking at him in game shows [nickname].
        from_zone: the man the Zone reward made for him; that link lasts until the man dies."""
        key = user.lower()
        old = self.twitch_links.pop(key, None)
        if old is not None and old != npc["id"]:
            self.game.send("link", old, "")
        for other, npc_id in list(self.twitch_links.items()):  # one viewer per NPC
            if npc_id == npc["id"]:
                del self.twitch_links[other]
                self.zone_links.discard(other)
        if from_zone:
            self.zone_links.add(key)
        else:
            self.zone_links.discard(key)
        self.twitch_links[key] = npc["id"]
        self.twitch_names[key] = user
        self.save_links()
        self.game.send("link", npc["id"], user)
        log(f"Twitch: {user} now speaks through {npc.get('name')}")

    LINKS_FILE = ROOT / "twitch_links.json"

    def load_links(self):
        """Links survive a restart of StalkerTalker (the game keeps showing the labels anyway)."""
        try:
            data = json.loads(self.LINKS_FILE.read_text(encoding="utf-8"))
            self.twitch_links = {k: int(v["id"]) for k, v in data.items()}
            self.twitch_names = {k: v.get("nick", k) for k, v in data.items()}
            self.zone_links = {k for k, v in data.items() if v.get("zone")}
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            self.twitch_links, self.twitch_names, self.zone_links = {}, {}, set()

    def save_links(self):
        try:
            self.LINKS_FILE.write_text(json.dumps(
                {k: dict({"id": i, "nick": self.twitch_names.get(k, k)}, **({"zone": True} if k in self.zone_links else {}))
                 for k, i in self.twitch_links.items()},
                ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError as exc:
            log(f"Twitch links not saved: {exc}")

    def sync_links(self, state):
        """The game forgets the labels when a save loads: show them again for linked NPCs it doesn't know."""
        # links off: only the Zone's men keep their nickname; other labels left from before go (a save keeps them)
        links = self.twitch_links if TWITCH_LINKS else {
            k: i for k, i in self.twitch_links.items() if k in self.zone_links}
        if not TWITCH_LINKS:
            for npc_id in state.get("twitch_links") or []:
                if int(npc_id) not in links.values():
                    self.game.send("link", int(npc_id), "")
        if time.time() < self.next_link_sync or not links:
            return
        self.next_link_sync = time.time() + 5
        shown = {str(i) for i in state.get("twitch_links") or []}
        alive = {n.get("id") for n in state.get("npcs", []) if isinstance(n, dict)}
        for key, npc_id in links.items():
            if npc_id in alive and str(npc_id) not in shown:
                self.game.send("link", npc_id, self.twitch_names.get(key, key))

    def _twitch_line(self, npc, state, item, named=None):
        user, text, redemption, mode = item
        if not self.busy.acquire(blocking=False):
            self.twitch_queue.insert(0, item)
            return
        try:
            if npc is None:
                # Only the named stalker is around: he answers the viewer's words himself, as if said to him.
                log(f"Twitch ({user}) to {named.get('name')}: {text}")
                if TWITCH_SHOW_NAME:
                    self.game.send("twitch", None, f"{user}: {text}")
                reply = self.brain.reply(named, state, "", [], text, "reply", remembers=self.memory.remembers(self.npc_key(named, state)))
                if reply:
                    log(f"  {named.get('name')} answers: {reply}")
                    self.brain_gesture(named)
                    self.speak(named, reply, state, note=f"(answering Twitch viewer {user})")
            else:
                line, emote = text, hint_emote(text)  # word for word: a gesture only if the words call for one
                if mode == "character":
                    retold = self.brain.reply(npc, state, "", [], "", "twitch", extra={"text": text},
                                              remembers=self.memory.remembers(self.npc_key(npc, state)))
                    if retold:
                        line = retold
                        emote = next((arg for kind, arg in self.brain.last_extras if kind == "emote"), None)
                log(f"Twitch ({user}) via {npc.get('name')}: {line}")
                # Whoever answers him is written NOW, while his line plays, and speaks the moment it ends.
                started, follow, heard = threading.Event(), None, []
                # The viewer named nobody, but the line says it to a man standing nearby ("Юрасю, ти..."): he
                # answers, and it may grow into a quarrel or a fight.
                face = None if named or to_everyone(text) else self.start_overheard([(npc, line)], (npc,), state)
                if face:
                    heard.append(face)
                elif named:  # the stalker he talked about answers him
                    # and anyone else they name who stands nearby hears it and may react to them both
                    follow = self.answer_after(
                        started, named, state, "addressed", extra={"name": npc.get("name"), "line": strip_tags(line)},
                        note=f"(to {npc.get('name')})", to=npc, on_written=lambda answer: heard.append(
                            self.start_overheard([(npc, line), (named, answer)], (npc, named), state)))
                elif to_everyone(text) or "?" in text or tells_joke(text):
                    # "$Пацани...", "$Гайз, ви чули...?": the others answer; a joke: they react to it
                    follow = threading.Thread(target=self.group_answer, daemon=True, args=(
                        state, strip_tags(line), npc.get("name")), kwargs={
                        "exclude": npc.get("id"), "speaker_npc": npc, "after": started,
                        "kind": "story" if tells_joke(text) else "talk"})
                    follow.start()
                self.gesture(npc, emote)
                # PDA: under the NPC's name and portrait, "[nickname] what he says"
                self.speak(npc, line, state, pda_text=f"[{user}] {strip_tags(line)}" if TWITCH_SHOW_NAME else None,
                           note=f"(voicing Twitch viewer {user})", on_start=started.set,
                           look_at=named or (face[0] if face else None))
                started.set()
                if follow:
                    follow.join(90)
                for h in heard:
                    self.finish_overheard(h, state)
            if self.twitch:
                self.twitch.finish(redemption, spoken=True)
        except Exception as exc:
            log(f"twitch line error: {exc!r}")
            self.twitch_queue.insert(0, item)
        finally:
            self.busy.release()
            report("TWITCH_QUEUE", str(len(self.twitch_queue)))

    def group_answer(self, state, said, speaker, from_player=False, exclude=None, speaker_npc=None, after=None,
                     kind="talk"):
        """Someone spoke to everybody ("всі", "пацани", "сталкери"...): up to GROUP_MAX men around answer,
        if it makes sense, in one AI request. Returns False when fewer than two men are around.
        kind="story": someone told a joke or a story and the men around react (one listener is enough)."""
        men = [n for n in state.get("npcs", []) if isinstance(n, dict) and n.get("id") != exclude
               and n.get("dist", 99) < GROUP_DISTANCE and not n.get("wounded") and not is_monolith(n)
               and not n.get("in_combat")]
        men = men[:6]
        if len(men) < (1 if kind == "story" else 2):
            return False
        keys = [self.npc_key(n, state) for n in men]
        lines = self.brain.group(men, state, said, speaker, speaker_npc=speaker_npc, kind=kind,
                                 remembers=[self.memory.remembers(k) for k in keys] if from_player else None)
        if after is not None:  # written while the line they react to plays: speak once it has started
            after.wait(30)
        answers = [(n, l, a) for n, l, a, aside in lines if not aside]
        asides = [(n, l) for n, l, a, aside in lines if aside]
        log(f"Group ({len(men)} around): {len(answers)} answer" + (f", {len(asides)} mutter" if asides else ""))
        everyone = [n for n in state.get("npcs", []) if isinstance(n, dict)]
        hired = False
        # Mutters go under the answer: they start a moment after it, quieter, without waiting for it to end.
        answer_started = threading.Event()
        if not answers:
            answer_started.set()
        lead_name = answers[0][0].get("name") if answers else speaker
        mutters = []
        for i, (npc, line) in enumerate(asides):
            def mutter(npc=npc, line=line, delay=random.uniform(1.0, 2.2) + i * 1.6):
                answer_started.wait(30)
                time.sleep(delay)
                if self.recording:
                    return
                log(f"  ({npc.get('name')}, under his breath): {line}")
                self.speak(npc, line, state, aside=True, note=f"(muttering while {lead_name} answered)")
            mutters.append(threading.Thread(target=mutter, daemon=True))
        for t in mutters:
            t.start()
        for npc, line, acts in answers:
            if self.recording:
                break
            log(f"  {npc.get('name')}: {line}")
            self.speak(npc, line, state, note=None if from_player else f"(to everyone, after {speaker})",
                       look_at=speaker_npc,
                       on_start=answer_started.set)
            answer_started.set()
            if from_player:
                self.memory.add(self.npc_key(npc, state), said, strip_tags(line))
            for kind, arg in acts:  # words first, then the shooting
                if kind == "hostile" and npc.get("relation") != "enemy":
                    self.game.send("act", npc["id"], "hostile")
                    self.game.send("info", None, f"{npc.get('name')} відкриває вогонь по вас")
                    log(f"{npc.get('name')} -> HOSTILE (group)")
                elif kind == "kill":
                    target = next((n for n in everyone if n.get("id") != npc.get("id") and mentions(n, arg)), None)
                    if target and not target.get("story") and not hired:
                        # the speaker offered money for it ("хто вистрілить, даю 300"): it comes out of HIS pocket
                        offer = max(amounts(said), default=0)
                        paid = ""
                        if speaker_npc and offer:
                            self.game.send("act", npc["id"], f"paidby:{speaker_npc['id']}:{offer}")
                            log(f"{speaker_npc.get('name')} pays {npc.get('name')} {offer}")
                        elif from_player and offer:  # the player's offer: he pays, like in a one-on-one deal
                            money = (state.get("actor") or {}).get("money", 0)
                            if offer > money:
                                self.game.send("info", None, f"Не вистачає грошей: {npc.get('name')} хотів {offer}")
                                log(f"{npc.get('name')}: group hit not done (you have {money}, offered {offer})")
                                hired = True  # the offer is void: one notice, nobody else takes it either
                                continue
                            self.game.send("act", npc["id"], f"take:{offer}")
                            log(f"{npc.get('name')} took {offer} from you (group hit)")
                            paid = paid_mark(state)
                        hired = True  # one man takes the job (and the money), not everyone who answers
                        self.game.send("act", npc["id"], f"kill:{target['id']}{paid}")
                        self.game.send("info", None, f"{npc.get('name')} стріляє в {target.get('name')}")
                        log(f"{npc.get('name')} -> KILL {target.get('name')} (group)")
            time.sleep(0.25)
        for t in mutters:  # the group is done when the last mutter is
            t.join(40)
        return True

    def check_healed(self, state):
        """You gave a dying stalker a medkit: he remembers that you saved him, and thanks you."""
        now_wounded = {n.get("id"): n for n in state.get("npcs", []) if isinstance(n, dict)}
        before = getattr(self, "wounded_before", {})
        self.wounded_before = {i: n.get("wounded") for i, n in now_wounded.items()}
        used_id, used_at = self.game.last_used_npc
        for npc_id, npc in now_wounded.items():
            if before.get(npc_id) and not npc.get("wounded") and npc.get("dist", 99) < 4 \
                    and used_id == npc_id and time.time() - used_at < 90:
                log(f"{npc.get('name')} was saved by you (medkit)")
                self.memory.witness(self.npc_key(npc, state),
                                    "he saved my life: gave me a medkit when I lay dying (this outweighs old quarrels)")
                self.memory.owe(self.npc_key(npc, state), "he gave you his medkit when you lay dying", 400)
                if not CHAT_ONLY:
                    what = ("You were lying wounded and dying, and the player just saved your life with his medkit. "
                            "Thank him your own way (gruff, emotional or joking), not about anything else.")
                    threading.Thread(target=self._ambient_line, args=(npc, state, "react", {"what": what}),
                                     daemon=True).start()

    def watch_game_process(self):
        """Everything is paused while S.T.A.L.K.E.R. isn't running: no mic, no AI, no voices."""
        running = game_running()
        if running == getattr(self, "game_on", None):
            return running
        self.game_on = running
        report("GAME", "running" if running else "not running")
        if running:
            log("S.T.A.L.K.E.R. is running: StalkerTalker is on.")
            for name in ("keys.txt", "inbox.txt"):  # leftovers from the last session
                try:
                    (BRIDGE / name).unlink()
                except OSError:
                    pass
            self.game.new_events()  # skip events of the last session
            self.prev_state, self.last_state_t = None, None
            self.next_proactive = time.time() + 20
        else:
            log(f"S.T.A.L.K.E.R. is not running ({GAME_EXE}): StalkerTalker waits for it"
                + (", Twitch messages are kept." if self.twitch else "."))
            self.game_ptt = False  # the game reports its own push-to-talk again when it starts
            self.ptt_up.set()      # stop a recording that was in progress
        return running

    def watch_for_quit(self):
        """The window asks the helper to quit by writing "quit" to it. Before exiting, let a Twitch sign-in
        renewal that's under way finish and be saved (killed in between, it would cost a new sign-in)."""
        def watch():
            try:
                for line in sys.stdin:
                    if line.strip() == "quit":
                        break
                    if line.strip() == "rewards":  # the window's Refresh next to a reward title
                        threading.Thread(target=self.report_rewards, daemon=True).start()
                    if line.startswith("zone"):  # the window's debug buttons
                        arg = line.split()[-1]
                        who = (self.twitch.login if self.twitch and self.twitch.login else None) or "test"
                        if arg == "redeem":  # as if a viewer redeemed it: queued like a real one, PDA notice
                            self.on_zone(who)
                        elif arg == "speech":  # the speech reward: a line said by an NPC near you
                            self.on_twitch(who, "$Перевірка зв'язку. Прийом.", None)
                        elif redeems.by_id(arg) and redeems.by_id(arg).kind == "trigger":  # as if redeemed, at once
                            getattr(self, redeems.by_id(arg).handler)(who)
                        else:  # "zone gift|life|child|any": at once
                            self.zone_test(arg)
                else:
                    return  # no window attached (console run): Ctrl+C as usual
            except (OSError, ValueError):
                return
            if self.twitch and self.twitch.auth_lock.acquire(timeout=5):
                self.twitch.auth_lock.release()
            log("— helper quitting —")
            os._exit(0)
        threading.Thread(target=watch, daemon=True).start()

    def run(self):
        self.watch_for_quit()
        log(f"Ready. Hold [{PTT_KEY.upper()}] near an NPC and speak. Ctrl+C to quit.")
        USAGE.refresh_quota(self.voice.client)
        report("USAGE", USAGE.summary())
        if CHAT_ONLY:
            log("Mode: CHAT ONLY. NPCs only say Twitch chat messages; mic and their own lines are off.")
        keyboard.on_press_key(PTT_KEY, lambda _: None if self.game_ptt or not self.game_on or CHAT_ONLY else threading.Thread(
            target=self.on_push_to_talk, daemon=True).start())
        next_check = next_events = next_process = 0.0
        while True:
            if time.time() >= next_process:
                next_process = time.time() + 3
                self.watch_game_process()
                if not self.busy.locked() and not self.recording:  # nothing is open: safe to re-scan
                    refresh_audio_devices()
                if self.twitch:
                    report("TWITCH", self.twitch.status)
            if not self.game_on:
                time.sleep(0.5)
                continue
            self.handle_keys()  # every 50 ms, so recording starts right when the key goes down
            if time.time() >= next_events:
                next_events = time.time() + 0.3
                events = self.game.new_events()
                if events:
                    self.remember_events(events)
                    self.on_game_results(events, self.game.state())
                    if self.twitch_links:
                        self.unlink_dead(events)
                    self.on_zone_results(events)
                    for ev in events:
                        if ev.get("type") == "order":
                            self.on_order(ev)
                        elif ev.get("type") == "actor_death" and not CHAT_ONLY:
                            self.on_player_death(ev)
                    if not CHAT_ONLY:
                        self.quick_react(events)
                        self.ambient([ev for ev in events if ev.get("type") not in ("order",) + tuple(self.REACTIONS)])
            if time.time() >= next_check:
                next_check = time.time() + 2
                state = self.game.state()
                if state:
                    self.check_healed(state)
                    self.check_mod_version(state)
                    self.sync_links(state)
                    if self.game_is_live(state):
                        self.zone_tick(state)
                    self.report_zone()
                live = state and self.game_is_live(state) and not self.busy.locked() and not self.recording
                if CHAT_ONLY:
                    if live:
                        self.twitch_speak(state)
                else:
                    self.watch_environment()
                    # one unprompted thing at a time: viewers first, then companions, then campfire chats
                    if not (live and (self.twitch_speak(state) or self.companion_talk(state) or self.npc_chat(state))):
                        self.proactive()
                if self.twitch:
                    report("TWITCH", self.twitch.status)
                USAGE.refresh_quota(self.voice.client)
            time.sleep(0.05)


if __name__ == "__main__":
    needed = {"gemini": "GEMINI_API_KEY", "claude-api": "ANTHROPIC_API_KEY"}.get(LLM_PROVIDER)
    if needed and not os.environ.get(needed):
        sys.exit(f"Add {needed} to {ROOT / '.env'} first, or set LLM_PROVIDER=claude to use your "
                 "Claude chat subscription through the Claude Code CLI.")
    Talker().run()
