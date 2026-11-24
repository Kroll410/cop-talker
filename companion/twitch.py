"""Twitch bridge: chat messages (testing) or a channel-points reward with a message go to an NPC in the game.
The app never creates rewards: the channel owner makes them on Twitch and picks their titles in Settings.
A second reward, made by the channel owner on Twitch (no message), can trigger a random Zone event (zone_title).

Sign-in uses Twitch's device code flow (you open a link and type a code, no password ever reaches this app).
Events come over EventSub WebSocket, so no public server or open port is needed.
The token is kept in twitch_token.json next to .env; don't share that file.
"""
import json
import os
import threading
import time
from pathlib import Path

import httpx
import websocket

SCOPES = {"chat": "user:read:chat",  # read chat as your own account
          "reward": "channel:read:redemptions channel:manage:redemptions"}
EVENTSUB_URL = "wss://eventsub.wss.twitch.tv/ws"
HELIX = "https://api.twitch.tv/helix"


def channel_login(text):
    """'some_channel', '#some_channel' or a link like https://www.twitch.tv/some_channel -> 'some_channel'."""
    return (text or "").strip().rstrip("/").split("/")[-1].split("?")[0].lstrip("#@").lower()


class Twitch:
    def __init__(self, client_id, reward_title, token_file: Path, on_message, log,
                 on_code=None, source="reward", channel="", zone_title="", on_zone=None):
        self.client_id = client_id
        self.source = source if source in SCOPES else "reward"
        self.scopes = SCOPES[self.source]
        self.zone_title = (zone_title or "").strip()  # the Zone reward's title on Twitch; empty = off
        self.on_zone = on_zone or (lambda user, redemption: None)
        self.zone_reward_id = None
        self.zone_seen = []  # redemption ids already handed on (two subscriptions may both deliver one)
        if self.zone_title and "channel:read:redemptions" not in self.scopes.split():
            self.scopes += " channel:read:redemptions"  # chat mode too: the Zone reward is on your own channel
        self.channel = channel_login(channel)  # chat mode: whose chat to read (empty = your own)
        self.channel_id = None
        self.reward_title = (reward_title or "").strip()  # reward mode: the speech reward's title; empty = none
        self.token_file = token_file
        self.on_message = on_message  # fn(user, text, redemption) -> None
        self.log = log
        self.on_code = on_code or (lambda url, code: None)  # show the sign-in code in the UI
        self.token = {}
        self.user_id = self.login = None
        self.reward_id, self.reward_owned = None, False
        self.status = "off"
        self.stop = threading.Event()
        self.http = httpx.Client(timeout=15)
        self.auth_lock = threading.Lock()  # held while a sign-in is renewed and saved

    # ------------------------------------------------------------ auth
    def load_token(self):
        try:
            self.token = json.loads(self.token_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.token = {}

    def save_token(self):
        """Written in one go (temp file + rename): a helper killed mid-write never leaves a broken sign-in."""
        tmp = self.token_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.token), encoding="utf-8")
        os.replace(tmp, self.token_file)

    def device_login(self):
        r = self.http.post("https://id.twitch.tv/oauth2/device", data={"client_id": self.client_id, "scopes": self.scopes})
        r.raise_for_status()
        dev = r.json()
        self.status = f"sign in: open {dev['verification_uri']} code {dev['user_code']}"
        self.log(f"Twitch: open {dev['verification_uri']} and enter code {dev['user_code']}")
        self.on_code(dev["verification_uri"], dev["user_code"])
        deadline = time.time() + dev.get("expires_in", 1800)
        while time.time() < deadline and not self.stop.is_set():
            time.sleep(dev.get("interval", 5))
            r = self.http.post("https://id.twitch.tv/oauth2/token", data={
                "client_id": self.client_id, "scopes": self.scopes, "device_code": dev["device_code"],
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code"})
            if r.status_code == 200:
                with self.auth_lock:
                    self.token = r.json()
                    self.save_token()
                return True
            if "authorization_pending" not in r.text:
                raise RuntimeError(f"Twitch sign-in failed: {r.text[:200]}")
        return False

    def refresh(self):
        """Renew the sign-in. Twitch's refresh key works once, so the request and saving the new key happen
        under auth_lock: the helper waits for it before quitting (a kill in between would cost a new sign-in)."""
        with self.auth_lock:
            used = self.token.get("refresh_token")
            r = self.http.post("https://id.twitch.tv/oauth2/token", data={
                "client_id": self.client_id, "grant_type": "refresh_token", "refresh_token": used})
            if r.status_code == 200:
                self.token = r.json()
                self.save_token()
                return True
            # Refused: maybe another run already renewed it and saved the new key. Use that if so.
            self.load_token()
            if self.token.get("refresh_token") and self.token.get("refresh_token") != used:
                self.log("Twitch: using the sign-in renewed by another run")
                return True
            self.log(f"Twitch: sign-in renewal refused ({r.status_code}), you'll need to sign in again")
            return False

    def validate(self):
        if not self.token.get("access_token"):
            return False
        r = self.http.get("https://id.twitch.tv/oauth2/validate",
                          headers={"Authorization": f"OAuth {self.token['access_token']}"})
        if r.status_code == 200:
            info = r.json()
            if not set(self.scopes.split()) <= set(info.get("scopes") or []):
                return False  # signed in for another mode: ask for the right permission once
            self.user_id, self.login = info["user_id"], info["login"]
            return True
        return bool(self.token.get("refresh_token")) and self.refresh() and self.validate()

    def headers(self):
        return {"Client-Id": self.client_id, "Authorization": f"Bearer {self.token['access_token']}"}

    def helix(self, method, path, **kw):
        r = self.http.request(method, HELIX + path, headers=self.headers(), **kw)
        if r.status_code == 401 and self.refresh():
            r = self.http.request(method, HELIX + path, headers=self.headers(), **kw)
        return r

    # ------------------------------------------------------------ reward
    def find_reward(self):
        """Find the speech reward by its title (made by the channel owner on Twitch). Never creates one."""
        self.reward_id, self.reward_owned = None, False
        if not self.reward_title:
            self.log("Twitch: no speech reward set (Settings → TWITCH_REWARD): viewers speak through chat only")
            return
        mine = self.helix("GET", "/channel_points/custom_rewards",
                          params={"broadcaster_id": self.user_id, "only_manageable_rewards": "true"})
        for rw in mine.json().get("data", []) if mine.status_code == 200 else []:
            if rw["title"].strip().lower() == self.reward_title.strip().lower():
                self.reward_id, self.reward_owned = rw["id"], True
                return
        every = self.helix("GET", "/channel_points/custom_rewards", params={"broadcaster_id": self.user_id})
        for rw in every.json().get("data", []) if every.status_code == 200 else []:
            if rw["title"].strip().lower() == self.reward_title.strip().lower():
                self.reward_id, self.reward_owned = rw["id"], False  # made by hand on Twitch: we only listen
                return
        self.log(f"Twitch: no reward «{self.reward_title}» on your channel yet (create it on Twitch, with a "
                 "message). Listening for it by title.")

    def app_rewards(self):
        """Rewards this app created earlier (only those can be deleted from here): [{"id", "title"}]."""
        if not self.user_id:
            return []
        r = self.helix("GET", "/channel_points/custom_rewards",
                       params={"broadcaster_id": self.user_id, "only_manageable_rewards": "true"})
        return [{"id": rw["id"], "title": rw["title"]} for rw in r.json().get("data", [])] if r.status_code == 200 else []

    def delete_reward(self, reward_id):
        """Remove a reward this app created from the channel. Returns None if done, else Twitch's reason."""
        r = self.helix("DELETE", "/channel_points/custom_rewards",
                       params={"broadcaster_id": self.user_id, "id": reward_id})
        if r.status_code == 204:
            if reward_id == self.reward_id:
                self.reward_id, self.reward_owned = None, False
            return None
        try:
            return (r.json().get("message") or r.text)[:150]
        except ValueError:
            return r.text[:150] or str(r.status_code)

    def list_rewards(self):
        """Titles of all channel-points rewards of your channel (made here or by hand on Twitch)."""
        if not self.user_id:
            raise RuntimeError("Twitch is not signed in yet")
        r = self.helix("GET", "/channel_points/custom_rewards", params={"broadcaster_id": self.user_id})
        if r.status_code != 200:
            try:
                why = r.json().get("message") or r.text
            except ValueError:
                why = r.text
            if r.status_code == 401 and "channel:read:redemptions" not in self.scopes.split():
                # chat mode without a Zone reward: this sign-in may not read rewards yet
                why = "type the reward title and Save: Twitch then asks to read rewards, and Refresh works"
            raise RuntimeError(f"Twitch: {why[:150]}")
        return [rw["title"] for rw in r.json().get("data", [])]

    def find_zone_reward(self):
        """The Zone reward is made by hand on Twitch: we only find its id to listen to it."""
        r = self.helix("GET", "/channel_points/custom_rewards", params={"broadcaster_id": self.user_id})
        for rw in r.json().get("data", []) if r.status_code == 200 else []:
            if rw["title"].strip().lower() == self.zone_title.lower():
                self.zone_reward_id = rw["id"]
                return
        self.zone_reward_id = None
        self.log(f"Twitch: no reward «{self.zone_title}» on your channel yet (create it on Twitch, no message "
                 "needed). Listening for it by title.")

    def is_zone(self, ev):
        reward = ev.get("reward") or {}
        if self.zone_reward_id and reward.get("id") == self.zone_reward_id:
            return True
        return bool(self.zone_title) and (reward.get("title") or "").strip().lower() == self.zone_title.lower()

    def finish(self, redemption, spoken=True):
        """Mark the redemption done (or refund it). Works only for rewards this app created."""
        if not self.reward_owned or not redemption:
            return
        try:
            self.helix("PATCH", "/channel_points/custom_rewards/redemptions",
                       params={"broadcaster_id": self.user_id, "reward_id": redemption["reward"]["id"],
                               "id": redemption["id"]},
                       json={"status": "FULFILLED" if spoken else "CANCELED"})
        except Exception:
            pass

    # ------------------------------------------------------------ events
    def find_channel(self):
        login = self.channel or self.login
        r = self.helix("GET", "/users", params={"login": login})
        data = r.json().get("data", []) if r.status_code == 200 else []
        if not data:
            raise RuntimeError(f"Twitch channel '{login}' not found")
        self.channel, self.channel_id = data[0]["login"], data[0]["id"]

    def subscribe(self, session_id):
        if self.source == "chat":
            r = self.helix("POST", "/eventsub/subscriptions", json={
                "type": "channel.chat.message", "version": "1",
                "condition": {"broadcaster_user_id": self.channel_id, "user_id": self.user_id},
                "transport": {"method": "websocket", "session_id": session_id}})
            if r.status_code not in (200, 202, 409):  # 409: already subscribed, which is fine
                raise RuntimeError(f"Twitch subscribe failed: {r.text[:200]}")
        elif self.reward_title:
            self.subscribe_redemptions(session_id, self.reward_id)
        if self.zone_title:
            self.subscribe_redemptions(session_id, self.zone_reward_id)

    def subscribe_redemptions(self, session_id, reward_id):
        condition = {"broadcaster_user_id": self.user_id}
        if reward_id:
            condition["reward_id"] = reward_id
        r = self.helix("POST", "/eventsub/subscriptions", json={
            "type": "channel.channel_points_custom_reward_redemption.add", "version": "1",
            "condition": condition, "transport": {"method": "websocket", "session_id": session_id}})
        if r.status_code not in (200, 202, 409):  # 409: already subscribed, which is fine
            raise RuntimeError(f"Twitch subscribe failed: {r.text[:200]}")

    def listen(self):
        url, moved = EVENTSUB_URL, False
        seen = []  # Twitch delivers "at least once": the same message may come twice
        while not self.stop.is_set():
            ws = websocket.create_connection(url, timeout=30)
            url = EVENTSUB_URL
            try:
                while not self.stop.is_set():
                    msg = json.loads(ws.recv())
                    kind = msg["metadata"]["message_type"]
                    message_id = msg["metadata"].get("message_id")
                    if message_id:
                        if message_id in seen:
                            continue
                        seen = (seen + [message_id])[-200:]
                    if kind == "session_welcome":
                        if not moved:  # after a session_reconnect the subscription comes along by itself
                            self.subscribe(msg["payload"]["session"]["id"])
                        moved = False
                        zone = f", Zone reward «{self.zone_title}»" if self.zone_title else ""
                        if self.source == "chat":
                            self.status = (f"on: {self.login}, reading chat of #{self.channel} ($ word for word, "
                                           f"% retold){zone}")
                            self.log(f"Twitch connected as {self.login}, reading #{self.channel}: "
                                     "$message = said word for word, %message = retold by the NPC.")
                        else:
                            say = f"reward «{self.reward_title}»" if self.reward_title else "no speech reward"
                            self.status = f"on: {self.login}, {say}{zone}"
                            self.log(f"Twitch connected ({self.login}). {say[0].upper() + say[1:]}{zone}.")
                    elif kind == "notification":
                        ev = msg["payload"]["event"]
                        sub_type = (msg["payload"].get("subscription") or {}).get("type", "")
                        if sub_type.startswith("channel.channel_points"):
                            self.on_redemption(ev)
                        elif self.source == "chat":
                            text = ((ev.get("message") or {}).get("text") or "").strip()
                            user = ev.get("chatter_user_name") or ev.get("chatter_user_login")
                            if text:
                                self.on_message(user, text, None)
                    elif kind == "session_reconnect":
                        url, moved = msg["payload"]["session"]["reconnect_url"], True
                        break
            except websocket.WebSocketTimeoutException:
                pass  # no keepalive in time: reconnect
            finally:
                ws.close()

    def on_redemption(self, ev):
        user = ev.get("user_name") or ev.get("user_login")
        if self.is_zone(ev):
            if ev.get("id") in self.zone_seen:
                return
            self.zone_seen = (self.zone_seen + [ev.get("id")])[-200:]
            self.on_zone(user, ev)
            return
        if self.source != "reward" or not self.reward_title:
            return
        reward = ev.get("reward") or {}
        if self.reward_id and reward.get("id") != self.reward_id:
            return  # another reward of the channel (the Zone subscription may listen to all of them)
        if not self.reward_id and (reward.get("title") or "").strip().lower() != self.reward_title.lower():
            return  # not made on Twitch yet when we connected: matched by title
        text = (ev.get("user_input") or "").strip()
        if text:
            self.on_message(user, text, ev)

    def run(self):
        """Keeps trying: no internet at start, a dropped connection or a Twitch outage only delay it."""
        wait = 10
        while not self.stop.is_set():
            try:
                self.status = "connecting"
                self.load_token()
                if not self.validate():
                    if not self.device_login() or not self.validate():
                        self.status = "sign-in cancelled (press Stop and Start to try again)"
                        return
                if self.source == "chat":
                    self.find_channel()
                else:
                    self.find_reward()
                if self.zone_title:
                    self.find_zone_reward()
                wait = 10
                while not self.stop.is_set():
                    self.listen()
            except Exception as exc:
                if "sign-in failed" in str(exc):
                    self.status = f"error: {str(exc)[:80]}"
                    self.log(f"Twitch error: {exc}")
                    return
                self.status = f"reconnecting in {wait} s ({str(exc)[:60]})"
                self.log(f"Twitch: {str(exc)[:120]}, trying again in {wait} s")
                self.stop.wait(wait)
                wait = min(wait * 2, 120)

    def start(self):
        threading.Thread(target=self.run, daemon=True).start()
