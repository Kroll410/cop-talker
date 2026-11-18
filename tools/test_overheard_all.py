"""A man standing nearby who is named reacts not only in NPC chats but also after a Twitch line and its answer,
and after the player talks to an NPC. His reaction is written while the talk plays and follows it.
With --live, Claude writes the scenes (the Батон case from the log, and a player case)."""
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
import talker  # noqa: E402

gluhar = {"id": 1, "name": "Глухар", "community": "stalker", "rank": 300, "x": 0, "z": 0, "dist": 4, "place": "zat_b55"}
baton = {"id": 2, "name": "Юрась Батон", "community": "bandit", "rank": 300, "x": 2, "z": 0, "dist": 5,
         "place": "zat_b55"}
boroda = {"id": 3, "name": "Борода", "community": "stalker", "rank": 900, "story": True, "x": 4, "z": 0, "dist": 6,
          "place": "zat_b55"}
far = {"id": 4, "name": "Шуляк", "community": "stalker", "rank": 300, "x": 90, "z": 0, "dist": 90, "place": "x"}
state = {"npcs": [gluhar, baton, boroda, far], "level": "zaton", "hours": 21, "weather": "clear"}
ok = True


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    return cond


said, sent = [], []


class FakeBrain:
    last_extras, last_action, chat_emotes = [], None, []

    def reply(self, npc, *a, **k):
        time.sleep(0.3)
        return {"Борода": "Та він тихо сидить, Батон той, платить і не бузить.",
                "Гонта": "Вовк? Та він учора знову в аномалію вліз."}.get(npc["name"], "Ага.")

    def overheard(self, c, a, b, lines, state, remembers=""):
        self.got = (c["name"], a.get("player") or a["name"], b["name"], [l for _, l in lines])
        time.sleep(0.3)
        return [(c, "Я тут сиджу, бо плачу, на відміну від деяких.", None, [])]


def fresh():
    t = talker.Talker.__new__(talker.Talker)
    t.busy, t.recording, t.twitch, t.twitch_queue = threading.Lock(), False, None, []
    t.recent_lines = lambda: []
    t.npc_key = lambda n, s: n["name"]
    t.memory = type("M", (), {"remembers": lambda self, k: "", "history": lambda self, k: [],
                              "add": lambda self, *a: None, "said": lambda self, *a: None})()
    t.game = type("G", (), {"describe_events": lambda self, *x: "", "send": lambda self, *x: sent.append(x),
                            "last_spoke_to_player": (None, 0, "")})()
    t.brain = FakeBrain()
    t.gesture = lambda *a: None
    t.brain_gesture = lambda *a: None
    t.do_deals = lambda *a: None
    t.squad_backup = lambda *a: None
    t.speak = lambda npc, line, *a, **k: (k.get("on_start") or (lambda: None))() or said.append((npc["name"], line))
    t.speak_lines = lambda ls, st, notes=None, gestures=None: said.extend((n["name"], l) for n, l in ls)
    return t


# Twitch: the viewer speaks through Глухар to Борода; Батон, between them, is named and reacts after Борода
talker.TWITCH_SHOW_NAME = 0
t = fresh()
t._twitch_line(gluhar, state, ("kroll", "Борода, а чого цей Юрась Батон тут сидить?", None, "verbatim"), boroda)
order = [n for n, _ in said]
ok &= check(order == ["Глухар", "Борода", "Юрась Батон"], f"Twitch: {order}")
ok &= check(t.brain.got[:3] == ("Юрась Батон", "Глухар", "Борода") and len(t.brain.got[3]) == 2,
            "he hears both lines (the viewer's and Борода's answer)")

# The player asks Гонта about Вовк, who stands nearby: Вовк reacts after Гонта's answer
said.clear()
gonta = {"id": 5, "name": "Гонта", "community": "stalker", "rank": 500, "x": 0, "z": 0, "dist": 2}
vovk = {"id": 6, "name": "Вовк", "community": "stalker", "rank": 500, "x": 3, "z": 1, "dist": 4}
st2 = {"npcs": [gonta, vovk], "level": "zaton", "hours": 21, "weather": "clear"}
talker.CHIME_CHANCE = 0
t = fresh()
t.converse(gonta, st2, "Слухай, а Вовк правда в аномалію вліз?", "reply")
order = [n for n, _ in said]
ok &= check(order == ["Гонта", "Вовк"], f"player talk: {order}")
ok &= check(t.brain.got[1] is True, "the player is one side of the talk he overheard")

# nobody named nearby: nothing extra
said.clear()
t = fresh()
t.converse(gonta, {"npcs": [gonta, dict(vovk, dist=40, x=60)], "level": "zaton"}, "Слухай, а Вовк де?", "reply")
ok &= check([n for n, _ in said] == ["Гонта"], "Вовк too far: he doesn't hear it")

# the player shooting: a [ACTION: hostile] in an overheard scene with the player turns that man hostile
sent.clear()
t = fresh()
done = threading.Thread(target=lambda: None)
done.start()
t.finish_overheard((vovk, talker.PLAYER_TALKER, gonta, [(vovk, "Ну все, тобі капець.", None, [talker.PLAYER_TALKER])],
                    done), st2)
ok &= check(("act", 6, "hostile") in sent, "a quarrel with the player can turn the man hostile")

if "--live" in sys.argv:
    talker.LLM_PROVIDER = "claude"
    brain = talker.Brain()
    print("\nLive, the Батон case from the log:")
    lines = [(gluhar, "Борода, а чого цей Юрась Батон тут узагалі сидить, га? Бандюкам же в бар вхід як кроту в "
                      "філармонію, він що, в тебе в борг наливає, чи ти просто боїшся йому сказати, блін?"),
             (boroda, "Глухарю, та я його не боюсь, просто він сидить тихо, як мишка в тушонці, і нікого не чіпає! "
                      "А наливаю я йому по-дружньому, борг потім якось розрулимо.")]
    for _ in range(3):
        for n, l, e, k in brain.overheard(baton, gluhar, boroda, lines, state):
            print(f"  {n['name']}: {l}" + (f"  [{e}]" if e else "") + (f"  => KILL {k[0].get('name') or 'PLAYER'}"
                                                                         if k else ""))
        print("  --")
    print("Live, the player talks about Вовк to Гонта:")
    lines = [(talker.PLAYER_TALKER, "Гонто, а цей Вовк правда в новачків хабар віджимає? Щур же."),
             (gonta, "Та є таке, Вовк своє не впустить, жаба його душить.")]
    for _ in range(2):
        scene = brain.overheard(vovk, talker.PLAYER_TALKER, gonta, lines, st2)
        for n, l, e, k in scene:
            print(f"  {n['name']}: {l}" + (f"  [{e}]" if e else "") + (f"  => KILL {k[0].get('name') or 'PLAYER'}"
                                                                         if k else ""))
        ok &= check(bool(scene) and all(not n.get("player") for n, *_ in scene), "no lines written for the player")

print("OK" if ok else "FAIL")
