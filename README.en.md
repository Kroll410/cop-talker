# cop-talker

Talk to the stalkers of S.T.A.L.K.E.R.: Call of Pripyat by voice, in Ukrainian, and let Twitch chat drop events into the Zone.

![Stalkers at a campfire in Call of Pripyat](docs/strilecky.jpg)

Українською: [README.md](README.md)

## What it is

Look at a stalker, hold T, say something in Ukrainian, and he answers in a voice from the game. Each NPC always keeps the same voice.

How NPCs talk:
- they go by faction, rank, wounds, the weather, emissions and what you talked about before (memory survives restarts);
- they know your name and backstory from the settings and treat you accordingly;
- they only know what happened near them. Far-away events reach them later, as rumours;
- they recognise characters from the series (Strelok, the Marked One, Sidorovich…) and talk about them true to the lore;
- they talk about anything: the Zone, home, real news (Suspilne, BBC Ukrainian and TSN RSS; a story isn't repeated unless it's big), jokes, dirty stuff, nonsense;
- they react to accusations in different ways: own up, brag, wriggle out;
- they swear; bandits also use slurs, Monolith and scientists never do.

They also speak up on their own: greetings, reactions when you pick up an artifact or walk into an anomaly, combat remarks (only when they're actually fighting), chats with each other. Tell a joke and the people around laugh or say it was lame. If you get killed, the killer mocks you.

Conversations can change things in the game:
- a gesture (wave, salute…), also on request;
- following you or staying put;
- turning hostile or becoming a friend;
- in a fight, apologising, surrendering or paying off an enemy: if it's worth it to him, his whole squad stops shooting (enemies don't trade);
- selling or buying an item (at the game's own trade prices: cheaper for a friend, dearer for an enemy), handing over money;
- paying a debt: if you gave him a medkit or helped him fight someone off, you can ask for money;
- taking a paid hit. If the target is far away, the killer's squad goes looking for him.

With Twitch on, a chat message is said by an NPC nearby, each viewer sticks to one NPC with their nick next to his name, and channel-point rewards set off events in the game.

## Requirements

- CoP 1.6.02 (GOG or Steam) with [OpenXRay](https://github.com/OpenXRay/xray-16/wiki/%5BEN%5D-How-to-install-and-play)
- `xukrainian.db` with the Ukrainian voice pack, only for cutting voice samples
- Windows 10/11 and Python 3.10–3.13 (on PATH)
- a Gemini key (free) or a Claude subscription
- ElevenLabs with voice cloning (Starter plan or above)

## Install

1. `git clone` the repo anywhere (that's what makes the Update button work).
2. Run `setup.bat`. It:
   - installs dependencies into `.venv`;
   - asks where the game is;
   - copies the mod into `gamedata`;
   - creates `.env` and `settings.ini`;
   - adds a desktop shortcut;
   - optionally cuts voice samples into `samples\`.
3. Fill in `.env`:
   - `GEMINI_API_KEY` (https://aistudio.google.com/apikey)
   - `ELEVENLABS_API_KEY`
   - `VOICE_HUMAN_01`, `02`, `03`. These are clone Voice IDs: in ElevenLabs go to Voices → Instant Voice Clone, upload `samples\human_0N_ukr.mp3`, copy the ID. Faction voices are optional.
4. To use Claude instead of Gemini:
   - install Claude Code;
   - run `claude` and `/login`;
   - set `LLM_PROVIDER=claude` in `settings.ini`.

## How to use

1. Start the game and load a save.
2. Open StalkerTalker from the desktop and click **Start**. The window shows a log: what you said and who answered what.
3. Walk up to a stalker, look at him, hold **T** and talk. Let go when you're done. If you aren't looking at anyone, the nearest one answers.

Things you can say (in Ukrainian, in your own words):
- "Привіт, що нового?", "Що чув у новинах?", "Розкажи анекдот"
- "Гайз, ви чули…", "Пацани, всі сюди": the group answers (the leader, the others mutter around him)
- "Помахай мені", "Віддай честь": a gesture
- "Ходи за мною" / "Стій тут" (or the **Y** / **U** keys)
- "Продай хліб за 50", "Купую", "Візьми мою ковбасу за 100"
- "Ти мені винен за аптечку"
- "Вбий Борова, дам 5000"
- "Це ти вбив Фаната?": an accusation

You can press T while an NPC is still talking: your line is recorded and queued. The one who just spoke to you answers, keeping in mind what he said.

Settings are on the Settings tab (which is just `settings.ini`). The main ones:
- `PLAYER_NAME`: what stalkers call you; `PLAYER_BIO`: your backstory;
- `LLM_PROVIDER`: `gemini` or `claude`;
- `FUN_LEVEL`: how many jokes and how much swearing;
- `GROUP_STYLE`: `lead` (one answers, the others mutter) or `all` (in turn);
- `OUTSIDE_TALK`, `NEWS_FEEDS`: talk about life outside the Zone and the news.

After changing them, click **Save and restart**.

## Keys

- T (hold): talk
- Y: the NPC follows you
- U: the NPC stays put

You can rebind them in `gamedata\configs\scripts\talker.ltx`.

## Twitch

1. Register an app on dev.twitch.tv (Public type).
2. Put the Client ID in `.env` (`TWITCH_CLIENT_ID`).
3. In Settings: `TWITCH_ENABLED=1`, your channel in `TWITCH_CHANNEL`.
4. In the window, click **Authorize Twitch app** and enter the code on Twitch. The sign-in is kept between runs.

In chat:
- `$text`: the NPC says it word for word;
- `%text`: the NPC retells it his own way;
- `%%`: let go of your NPC (your next message is said by another one);
- talking to everyone ("гайз", plural "ви"): several NPCs answer.

A viewer gets linked to a free NPC within `TWITCH_DISTANCE`. If that NPC dies, the link goes; the viewer gets a new one with his next message. Nobody's NPC is taken from them. Links can be turned off (`TWITCH_LINKS=0`): then any NPC nearby says each message, with no nick labels.

### Rewards

Channel-point rewards need Affiliate or Partner. The app never adds rewards to your channel: you make each one on Twitch yourself, with no message unless noted, and pick it in its row on the **Redeems** tab (**Refresh rewards** lists the channel's rewards; you can also type the title). Each row shows what the reward does, whether it's on, and a **Test** button that runs it without points. If a reward you picked isn't on the channel, the Twitch tab's status says so, and the app waits until you make it.

Every reward except Speech and the Zone event goes off at once, with no queue. After each one, the NPCs nearby react out loud.

| Reward | Setting | What happens |
|---|---|---|
| Speech | `TWITCH_REWARD` | With `TWITCH_SOURCE=reward`, an NPC says the text of the redemption. This one has a message |
| Zone event | `TWITCH_ZONE_REWARD` | A random gift, stalker or mutant pack, queued (below) |
| «Шари Суслова» | `TWITCH_SUSLOV_REWARD` | Two «Вогняна куля» and a «Ковбаса» land in front of you, in a well-known shape |
| «Хуй будеш?» | `TWITCH_GIANT_REWARD` | A hostile pseudogiant turns up 15–30 m away and comes for you |
| «Вова Віст» | `TWITCH_VOVA_REWARD` | A soldier with «Свистілка Вови Віста», a PKM that fires 100× as fast for 1000× less damage |
| «Анекдот» | `TWITCH_ANEKDOT_REWARD` | A «Хліб», a «Ковбаса» and 12 bolts land in front of you; nobody can keep them |
| «Гоша» | `TWITCH_GOSHA_REWARD` | A hostile Mercenary named «Гоша» with a plain SPAS-12, 15–30 m away |
| «62» | `TWITCH_62_REWARD` | «шиісят два» shouted 10 times from all round you |
| «Чики-брики» | `TWITCH_CHIKI_REWARD` | «а ну чики-брики» shouted 10 times from all round you |
| «Мочии» | `TWITCH_MOCHI_REWARD` | A zombified stalker's «Мочи...» groaned 10 times from all round you |

Details:
- **«Шари Суслова»**: the items are props. They don't roll, can't be picked up (they go back to their spot), and the fireballs stay visible even without a detector.
- **«Анекдот»**: unlike «Шари Суслова», the items roll and can be kicked about, but whatever anyone picks up goes back to where it last lay. Someone nearby tells a short joke.
- **«Вова Віст»**: neutral to you until you shoot him, then your enemy for good. He opens fire on every other man and mutant around, and whoever he hits shoots back. His 5000-round belt never runs out. Once he's dead, the gun comes with an ordinary belt (5000 rounds would weigh about 65 kg), and in your hands it never runs out of ammo. The gun and his soldier type live in the mod's own item file, which the installer hooks in with one `#include` line in `gamedata\configs\external.ltx`. After an update, restart the game, not just the save. Load a save where someone carries this gun only with the mod installed.
- **«Гоша»**: he carries two packs of buckshot and no other gun or grenade. Like the Zone's men, he wears the viewer's nick, and that viewer's chat messages are said by him.
- **The sound rewards** («62», «Чики-брики», «Мочии»): each copy comes from its own spot 3–15 m away, at its own volume, pitch, speed and short delay, so they overlap and echo. No autosave. «62» and «Чики-брики» ship their sounds with the mod (`gamedata\sounds\talker\sixty_two*.ogg`, `chiki_briki*.ogg`); «Мочи...» is the game's own zombified stalker (`characters_voice\human_01\zombied\fight\attack\script_attack_5`), so the mod doesn't ship it.

Before every reward except the sound ones, the game is saved as `talker_autosave` (one save, overwritten each time), so you can always load back. No save while you're dead or talking, during an emission or a scripted scene, or if one was made in the last 10 seconds.

### The Zone event

Each redemption rolls an event right away, and the PDA shows that the Zone heard it. The first event in the queue happens at once; each one behind it waits 5–7 minutes after the one before (`TWITCH_ZONE_GAP`; with `0`, every event happens at once). The Zone event's row on the Redeems tab shows the queue, the gap, the biggest pack, and two test buttons: **Test** (queued like a real one) and **Fire now** (at once).

- **Дар Зони** (gift, 25%): a random item of the game (no quest items) in your backpack. The cheaper an item, the more often it comes: bread about 40 times as often as an exoskeleton. Weapon add-ons (scopes, silencer, grenade launchers) are rarer still than their price says. `python tools/check_zone_sections.py --odds` lists each item's chance.
- **Життя для Зони** (life, 50%): a stalker appears 15–30 m away, half the time a friend who follows you (always a Loner), half an enemy of any faction. He wears the viewer's nick until he dies, and a friend greets you first.
- **Дитя Зони** (child, 25%): mutants of one kind appear 25–50 m away and come for you. Mostly one or two (89%), 3–4 in 9.5% of cases, 5 or more in 1.4%. Weak kinds (tushkans, blind dogs, flesh) come more often and sometimes in packs; dangerous ones (bloodsucker, chimera, pseudogiant) seldom and almost always alone. The biggest pack is `TWITCH_ZONE_PACK_MAX` (default 6); tushkans have their own, up to 10. All the odds are in one table in `companion/zone.py`: `python companion/zone.py 6` prints them, and `python tools/zone_sim.py` checks them by simulation.

The PDA line shows the chance of what happened, e.g. «шанс 25%». A mutant event shows two: the chance of the kind among all mutant kinds, and of the pack size among that kind's sizes, then the two multiplied, e.g. «бюрер (шанс 1.0%), кількість 1 (шанс 95%) — шанс саме «бюрер (1)»: 0.95%». Among all Zone events, that pack's chance is 25% times both. Chances under 1% keep two significant digits (0.25%, 0.00059%), so a rare event never reads 0.00%.

After an event, one or two NPCs nearby react out loud: surprise, a joke, a curse or a warning. This works in Chat only mode too. Several events in a row get one reaction per 20 seconds.

## Updating and removing

Update with the **Update** button in the window. It runs `git pull`, adds new options to your `settings.ini`, reinstalls the mod in the game if needed and restarts. Your `settings.ini`, `.env`, NPC memory and Twitch sign-in are never touched. To put the mod back into the game by hand, use **Reinstall game mod**. With the game open, sounds it holds are skipped and the window says so.

After the mod changes, reload your save, since the game only reads scripts on load. New items (like Вова's gun) need a full game restart. The app tells you if the game is still running an older script.

To remove the mod from the game, run `uninstall_mod.ps1`.

`settings.ini` (your settings, made from `settings.example.ini`), `.env`, logs, NPC memory and the Twitch token stay out of the repo. Don't share your `.env`.

## How it works

Two parts: a Lua script in the game (`mod\gamedata`) and a Python app (`companion\`). They talk through files in `<game>\talker\`:
- the game writes `state.json` (who's around, the player, the level) and `events.jsonl` (what happened);
- the app writes `inbox.txt` (what to say and do).

The app transcribes your speech, asks an LLM for a reply, voices it with ElevenLabs and plays it with distance-based volume. In a dialogue the next line is prepared while the previous one plays. The game shows subtitles, moves the NPC's mouth and carries out actions.

Besides `talker_bridge.script`, the mod touches 6 original game scripts, adding a one-line hook to each (see `tools\patch_hooks.py`).

Built with:
- [OpenXRay](https://github.com/OpenXRay/xray-16)
- Claude Haiku (through Claude Code or the API) or Gemini. If Claude doesn't answer, Gemini takes over
- faster-whisper `large-v3-turbo` locally for speech recognition, or Gemini
- ElevenLabs `eleven_v3`, with voices cloned from the game's Ukrainian dub
- PySide6 for the window, sounddevice/soundfile for audio
- Twitch EventSub

## License

MIT, see [LICENSE](LICENSE). Except the 6 original game scripts in `mod\gamedata\scripts` (all but `talker_bridge.script`): they belong to GSC Game World and are included only with the hooks added.
