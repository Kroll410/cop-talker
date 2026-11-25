"""Every Twitch channel-points redeem the app knows, in one list.

The window's Redeems tab and the helper's Twitch routing both read REDEEMS, so a new redeem is one entry here plus
its Talker method (handler) and its settings.ini key (settings.example.ini, [Twitch], empty = off).

The app never creates or deletes rewards on Twitch: the streamer makes each one there, and the window only reads the
channel's list to pick a title from.

kind:
  speech  - the reward with a message: the viewer's text is said by an NPC (TWITCH_SOURCE=reward only)
  zone    - the Zone event: rolled at redemption and queued (TWITCH_ZONE_GAP, TWITCH_ZONE_PACK_MAX)
  trigger - runs at once on a redemption: handler(user, redemption). id is the test arg the window sends
            ("zone <id>") and the "kind" of the Zone item it fires (a failed one is never retried)
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Redeem:
    id: str          # short, stable: the test arg and the fired item's kind
    key: str         # settings.ini key that holds the reward's title on Twitch (empty = off)
    name: str        # what the window calls it
    what: str        # one line: what a redemption does in the game
    handler: str     # Talker method called on a redemption: fn(user, redemption=None)
    kind: str = "trigger"
    extra: tuple = ()  # more settings shown next to it in the window


REDEEMS = [
    Redeem("speech", "TWITCH_REWARD", "Speech",
           "A viewer's message, said by an NPC near you. Needs a reward with a message and TWITCH_SOURCE=reward.",
           "on_twitch", kind="speech"),
    Redeem("zone", "TWITCH_ZONE_REWARD", "Zone event",
           "Rolls a gift, a stalker friend or foe, or mutants. Queued, one per gap.",
           "on_zone", kind="zone", extra=("TWITCH_ZONE_GAP", "TWITCH_ZONE_PACK_MAX")),
    Redeem("suslov", "TWITCH_SUSLOV_REWARD", "Шари Суслова",
           "Two «Вогняна куля» and a «Ковбаса» land on the ground in front of you.", "on_suslov"),
    Redeem("giant", "TWITCH_GIANT_REWARD", "Хуй будеш?",
           "A hostile pseudogiant turns up 15-30 m away and comes for you.", "on_giant"),
    Redeem("vova", "TWITCH_VOVA_REWARD", "Вова Віст",
           "A soldier with a whistling machine gun shoots at everyone but you, until you shoot him.", "on_vova"),
    Redeem("anekdot", "TWITCH_ANEKDOT_REWARD", "Анекдот",
           "Bread, a sausage and bolts roll on the ground; nobody can pick them up.", "on_anekdot"),
    Redeem("gosha", "TWITCH_GOSHA_REWARD", "Гоша",
           "A Mercenary named «Гоша» with a SPAS-12 comes for you from 15-30 m.", "on_gosha"),
    Redeem("62", "TWITCH_62_REWARD", "62",
           "«шиісят два», shouted 7-17 times from all round you.", "on_sixty_two"),
    Redeem("chiki", "TWITCH_CHIKI_REWARD", "Чики-брики",
           "«а ну чики-брики», shouted 7-17 times from all round you.", "on_chiki"),
    Redeem("mochi", "TWITCH_MOCHI_REWARD", "Мочии",
           "A zombie's «Мочи...», groaned 7-17 times from all round you.", "on_mochi"),
]

TRIGGERS = [r for r in REDEEMS if r.kind == "trigger"]
KEYS = {r.key for r in REDEEMS} | {k for r in REDEEMS for k in r.extra}  # settings the Redeems tab owns


def by_id(rid):
    return next((r for r in REDEEMS if r.id == rid), None)


def triggers(titles, talker):
    """{reward title: bound handler} for the trigger redeems that have a title set (titles: key -> title)."""
    out = {}
    for r in TRIGGERS:
        title = (titles.get(r.key) or "").strip()
        if title:
            out[title] = getattr(talker, r.handler)
    return out
