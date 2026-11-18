"""Offline checks of today's helper logic (no AI calls): gestures, accusations, trimming, narration, chat parsing,
Claude -> Gemini fallback, own-words memory."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker  # noqa: E402

fails = []


def check(name, ok):
    print(("ok  " if ok else "FAIL") + " " + name)
    if not ok:
        fails.append(name)


# keyword gestures for $ lines
cases = {"Привіт усім!": "hello", "Хай буде так.": None, "Руки вгору!": "hands_up", "Я тебе вб'ю": "threat",
         "Тиждень назад був на Юпітері": None, "Відвали": "backoff", "Слава Україні!": "salute",
         "Як справи?": None, "Ти мені винен 500": "claim", "Я винен тобі": None}
for text, want in cases.items():
    check(f"hint_emote {text!r} -> {want}", talker.hint_emote(text) == want)

# accusations
for text, want in {"Я бачив, як ти вкрав аптечку": True, "Це ти вчора напився?": True, "Зізнавайся": True,
                   "Ти знаєш дорогу?": False, "Привіт": False, "Це ти, Лоцмане?": False}.items():
    check(f"accuse {text!r}", bool(talker.ACCUSE_WORDS.search(text)) == want)
stances = {talker.accused_stance({"community": "bandit"}) for _ in range(200)}
check("bandit stances vary", len(stances) >= 5)

# trimming: 2 sentences max, long pair cut to one, greetings too
long = "Слово " * 30 + "кінець. " + "Друге " * 20 + "речення. Третє."
check("reply trimmed to 1 when two are long", talker.trim_reply(long, "Що там на Затоні цікавого?", "reply").count(".") == 1)
check("greet trimmed to 2", talker.trim_reply("Раз. Два. Три.", "", "greet") == "Раз. Два.")
check("comma before dot fixed", talker.trim_reply("Добре, .", "ок ок ок ок", "reply") == "Добре.")
check("joke asked stays whole", talker.trim_reply("Раз. Два. Три.", "розкажи анекдот", "reply") == "Раз. Два. Три.")

# narration cut
n = {"name": "Лоцман"}
check("narration into words", talker.drop_narration("хмикає, дивиться на тебе Ей, стій.", n) == "Ей, стій.")
check("normal line kept", talker.drop_narration("Та я вчора бачив Бороду.", n) == "Та я вчора бачив Бороду.")
check("Дивись kept", talker.drop_narration("Дивись, Борода злий.", n) == "Дивись, Борода злий.")

# chat parsing: gestures come off the words, one per line
brain = talker.Brain.__new__(talker.Brain)
brain.news = talker.News("", 3600, lambda m: None)
brain.vary_tags = lambda line: line
reply = "A: Здоров, бродяго! [ACTION: emote hello]\nB: [ACTION: emote fold_arms]\nB: Ну привіт."
import random  # noqa: E402
talker.LLM_PROVIDER = "claude"
brain.ask_claude = lambda s, system=None: reply
a, b = {"id": 1, "name": "A"}, {"id": 2, "name": "B"}
lines = brain.chat(a, b, {"hours": 12}, "")
check("chat lines", [l for _, l in lines] == ["Здоров, бродяго!", "Ну привіт."])
check("chat gestures aligned", brain.chat_emotes == ["hello", None])

# Claude CLI down -> Gemini answers, then Claude rests for 2 minutes
calls = []
brain.gemini = object()
brain.claude_warned, brain.claude_down_until = False, 0.0
brain._claude_cli = lambda s, system=None: calls.append("claude") or (_ for _ in ()).throw(RuntimeError("Not logged in"))
brain.ask_gemini = lambda s, system=None, smart=False: calls.append("gemini") or "ok"
r1, r2 = brain.ask_claude_chat("x"), brain.ask_claude_chat("y")
check("fallback answers", r1 == r2 == "ok")
check("claude rests after failure", calls == ["claude", "gemini", "gemini"])
brain.claude_down_until = time.time() - 1
brain._claude_cli = lambda s, system=None: "claude ok"
check("claude used again after rest", brain.ask_claude_chat("z") == "claude ok")

# own words kept per NPC and shown back
mem = talker.Memory.__new__(talker.Memory)
mem.data, mem.lock, mem.busy_keys, mem.summarize = {}, __import__("threading").Lock(), set(), None
mem.save = lambda: None
for i in range(10):
    mem.said("zaton:t1", f"фраза {i}", "(to Кастет)")
check("said keeps last 8", len(mem.diary("zaton:t1")["said"]) == 8)
check("remembers shows own words", "Your own recent words" in mem.remembers("zaton:t1")
      and "фраза 9" in mem.remembers("zaton:t1"))
check("other NPC untouched", mem.remembers("zaton:t2") == "")

print(f"\n{len(fails)} failed" if fails else "\nall passed")
sys.exit(1 if fails else 0)
