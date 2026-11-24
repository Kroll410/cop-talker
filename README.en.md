# cop-talker

![](docs/strilecky.jpg)

Українською: [README.md](README.md)

## Requirements

- CoP 1.6.02 (GOG or Steam) with [OpenXRay](https://github.com/OpenXRay/xray-16/wiki/%5BEN%5D-How-to-install-and-play)
- `xukrainian.db` with the Ukrainian voice pack, only for cutting voice samples
- Windows 10/11 and Python 3.10–3.13 (on PATH)
- a Gemini key (free) or a Claude subscription
- ElevenLabs with voice cloning (Starter plan or above)

## What's in it

A mod for S.T.A.L.K.E.R.: Call of Pripyat that lets you talk to NPCs by voice. Look at a stalker, hold T, say something in Ukrainian, and he answers in an in-game voice. Each NPC always keeps the same voice.

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

There's Twitch support: a chat message is said by an NPC nearby, each viewer sticks to one NPC, and the viewer's nick shows next to his name.

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

Settings are in the Settings tab (which is just `settings.ini`). The main ones:
- `PLAYER_NAME`: what stalkers call you; `PLAYER_BIO`: your backstory;
- `LLM_PROVIDER`: `gemini` or `claude`;
- `FUN_LEVEL`: how many jokes and how much swearing;
- `GROUP_STYLE`: `lead` (one answers, the others mutter) or `all` (in turn);
- `OUTSIDE_TALK`, `NEWS_FEEDS`: talk about life outside the Zone and the news.

After changing them, click **Save and restart**.

### Twitch

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

**The "Zone" reward** (Affiliate/Partner). Make a channel-points reward on Twitch with no message and put its title in `TWITCH_ZONE_REWARD`. Each redemption rolls a random event right away, and the PDA shows that the Zone heard it. The event happens 5-7 minutes later (`TWITCH_ZONE_GAP`), with 5-7 minutes between events too:
- **Дар Зони** (gift, 25%): a random item of the game (no quest items) in your backpack;
- **Життя для Зони** (life, 50%): a random stalker appears 15-30 m away, half the time a friend who follows you, half an enemy. He wears the viewer's nick until he dies;
- **Дитя Зони** (child, 25%): 1 to 10 mutants of one kind appear 25-50 m away and come for you. Weak ones come in packs, strong ones mostly alone (10 pseudogiants: about 1 in 100).

The Twitch tab shows the queue: what was rolled and when it happens. It also has buttons to try it without a real redemption: **Redeem (debug)** (like a real one, queued) and **Now: …** (at once). Needs the v14 game script: load a save after updating.

## Keys

- T (hold): talk
- Y: the NPC follows you
- U: the NPC stays put

You can rebind them in `gamedata\configs\scripts\talker.ltx`.

## How it works

Two parts: a Lua script in the game (`mod\gamedata`) and a Python app (`companion\`). They talk through files in `<game>\talker\`:
- the game writes `state.json` (who's around, the player, the level) and `events.jsonl` (what happened);
- the app writes `inbox.txt` (what to say and do).

The app transcribes your speech, asks an LLM for a reply, voices it with ElevenLabs and plays it with distance-based volume. In a dialogue the next line is prepared while the previous one plays. The game shows subtitles, moves the NPC's mouth and carries out actions.

Besides `talker_bridge.script`, the mod touches 6 original game scripts, adding a one-line hook to each (see `tools\patch_hooks.py`).

Built with:
- [OpenXRay](https://github.com/OpenXRay/xray-16)
- Claude Haiku (through Claude Code or the API) or Gemini. If Claude doesn't answer, Gemini takes over.
- faster-whisper `large-v3-turbo` locally for speech recognition, or Gemini
- ElevenLabs `eleven_v3`, with voices cloned from the game's Ukrainian dub
- PySide6 for the window, sounddevice/soundfile for audio
- Twitch EventSub

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

## Updating and removing

Update with the **Update** button in the window. It runs `git pull`, adds new options to your `settings.ini`, reinstalls the mod in the game if needed and restarts. Your `settings.ini`, `.env`, NPC memory and Twitch sign-in are never touched.

After the mod changes, reload your save, since the game only reads scripts on load. The app tells you if the game is still running an older script.

To remove the mod from the game, run `uninstall_mod.ps1`.

`settings.ini` (your settings, made from `settings.example.ini`), `.env`, logs, NPC memory and the Twitch token stay out of the repo. Don't share your `.env`.

## License

MIT, see [LICENSE](LICENSE). Except the 6 original game scripts in `mod\gamedata\scripts` (all but `talker_bridge.script`): they belong to GSC Game World and are included only with the hooks added.
