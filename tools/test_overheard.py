"""Two NPCs chat and name a third man standing nearby: he answers them both, right after their talk.
A man out of earshot, or one of the talkers, never does. With --live, real AI lines are written too."""
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker  # noqa: E402

a = {"id": 1, "name": "Гонта", "community": "stalker", "rank": 500, "x": 0, "z": 0, "place": "zat_stalker_base_smart"}
b = {"id": 2, "name": "Лоцман", "community": "stalker", "rank": 300, "x": 2, "z": 1, "place": "zat_stalker_base_smart"}
c = {"id": 3, "name": "Вовк", "community": "stalker", "rank": 700, "x": 5, "z": 3, "place": "zat_stalker_base_smart"}
far = {"id": 4, "name": "Шуляк", "community": "stalker", "rank": 300, "x": 80, "z": 0, "place": "zat_stalker_base_smart"}
state = {"npcs": [a, b, c, far], "level": "zaton", "hours": 20, "weather": "clear"}

ok = True
check = lambda cond, what: print(("ok   " if cond else "FAIL ") + what) or cond

ok &= check(talker.in_earshot(c, (a, b)) and not talker.in_earshot(far, (a, b)), "earshot by positions")
lines = [(a, "Слухай, а Вовк учора знову в аномалію вліз?"), (b, "Та він з неї й не вилазить.")]
ok &= check(talker.named_bystander(lines, [c, far], (a, b)) is c, "Вовк is named (\"Вовк\")")
ok &= check(talker.named_bystander([(a, "Вовче, йди сюди!")], [c], (a, b)) is c, "Вовче -> Вовк")
ok &= check(talker.named_bystander([(a, "Лоцмане, наливай")], [a, b, c], (a, b)) is None, "talkers don't count")
ok &= check(talker.named_bystander([(a, "Шуляк десь пропав")], [c], (a, b)) is None, "far man isn't a bystander")

# the flow: chat lines play, the third man's line is written meanwhile and plays last
said, t0 = [], time.time()
t = talker.Talker.__new__(talker.Talker)
t.busy, t.recording = threading.Lock(), False
t.recent_lines = lambda: []
t.npc_key = lambda n, s: n["name"]
t.memory = type("M", (), {"remembers": lambda self, k: ""})()
t.game = type("G", (), {"describe_events": lambda self, *x: ""})()
seen_nearby = []


class FakeBrain:
    chat_emotes = []

    def chat(self, *x, nearby=(), **k):
        seen_nearby.extend(n["name"] for n in nearby)
        return lines

    def overheard(self, *x):
        time.sleep(0.5)
        return [(c, "Що ти там про мене гавкаєш?", None, []), (a, "Правду, щуро.", None, []),
                (c, "Ну все, тобі гаплик.", None, [a])]


t.brain = FakeBrain()
sent = []
t.game.send = lambda *x: sent.append(x)
t.speak_lines = lambda ls, st, notes=None, gestures=None: said.extend((n["name"], l, notes) for n, l in ls)
t._chat(a, b, state)
ok &= check(seen_nearby == ["Вовк"], f"nearby given to the chat prompt: {seen_nearby}")
ok &= check([s[0] for s in said] == ["Гонта", "Лоцман", "Вовк", "Гонта", "Вовк"], f"order {[s[0] for s in said]}")
ok &= check(said[2][2][0] == "(to Гонта and Лоцман)", "his line is kept in his memory as said to both")
ok &= check(("act", 3, "kill:1") in sent, f"Вовк opens fire on Гонта after the words: {sent}")

if "--live" in sys.argv:
    talker.LLM_PROVIDER = "claude"
    brain = talker.Brain()
    print("\nLive (claude, " + talker.CLAUDE_MODEL + "):")
    for i in range(2):
        got = brain.chat(a, b, state, "", nearby=[c])
        for n, l in got:
            print(f"  {n['name']}: {l}")
        named = talker.named_bystander(got, [c], (a, b))
        print(f"  -> named: {named['name'] if named else 'nobody'}")

    def show(title, c, a, b, lines, runs=2):
        print(f"\n{title}")
        for n, l in lines:
            print(f"  {n['name']}: {l}")
        result = []
        for _ in range(runs):
            scene = brain.overheard(c, a, b, lines, state)
            for n, l, e, k in scene:
                print(f"    {n['name']}: {l}" + (f"  [{e}]" if e else "") + (f"  => KILL {k[0]['name']}" if k else ""))
            print("    --")
            result.append(scene)
        return result

    friendly = show("Friendly mention:", c, a, b, [(a, "Вовк учора мені аптечку дав, золотий мужик."),
                                                   (b, "Ага, Вовк свій, не те що деякі.")])
    ok &= check(all(s and s[0][0] is c for s in friendly), "he speaks first")
    ok &= check(not any(k for s in friendly for *_, k in s), "friendly talk: no shooting")
    show("Nasty mention between stalkers:", c, a, b, [(a, "Вовк знову хабар у новачків відібрав, щур."),
                                                      (b, "Такого б у аномалію штовхнути.")])
    band1 = dict(a, community="bandit", name="Шрам")
    band2 = dict(b, community="bandit", name="Кабан")
    duty = dict(c, community="dolg", name="Вовк")
    show("Bandits insult a Duty man:", duty, band1, band2,
         [(band1, "Цей Вовк з Обов'язку — ментяра, стукач, я б його прямо тут поклав."),
          (band2, "Та він ссикло, Вовк і ствол тримати не вміє.")], runs=3)

print("OK" if ok else "FAIL")
