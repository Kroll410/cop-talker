"""Twitch bridge: chat messages (testing) or a channel-points reward with a message go to an NPC in the game.

Sign-in uses Twitch's device code flow (you open a link and type a code, no password ever reaches this app).
Events come over EventSub WebSocket, so no public server or open port is needed.
The token is kept in twitch_token.json next to .env; don't share that file.
"""
import json
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
    def __init__(self, client_id, reward_title, token_file: Path, on_message, log, reward_cost=500,
                 on_code=None, source="reward", channel=""):
        self.client_id = client_id
        self.source = source if source in SCOPES else "reward"
        self.scopes = SCOPES[self.source]
        self.channel = channel_login(channel)  # chat mode: whose chat to read (empty = your own)
        self.channel_id = None
        self.reward_title = reward_title
        self.reward_cost = reward_cost
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

    # ------------------------------------------------------------ auth
    def load_token(self):
        try:
            self.token = json.loads(self.token_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.token = {}

    def save_token(self):
        self.token_file.write_text(json.dumps(self.token), encoding="utf-8")

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
                self.token = r.json()
                self.save_token()
                return True
            if "authorization_pending" not in r.text:
                raise RuntimeError(f"Twitch sign-in failed: {r.text[:200]}")
        return False

    def refresh(self):
        r = self.http.post("https://id.twitch.tv/oauth2/token", data={
            "client_id": self.client_id, "grant_type": "refresh_token", "refresh_token": self.token["refresh_token"]})
        if r.status_code != 200:
            return False
        self.token = r.json()
        self.save_token()
        return True

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
        """Use the reward with our title. If it doesn't exist, create it (needs Affiliate/Partner)."""
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
        r = self.helix("POST", "/channel_points/custom_rewards", params={"broadcaster_id": self.user_id}, json={
            "title": self.reward_title, "cost": self.reward_cost, "is_user_input_required": True,
            "prompt": "Напиши, що має сказати сталкер у грі (до 200 символів)."})
        if r.status_code == 200:
            self.reward_id, self.reward_owned = r.json()["data"][0]["id"], True
            self.log(f"Twitch: created reward «{self.reward_title}» ({self.reward_cost} points)")
        else:
            self.log(f"Twitch: couldn't find or create reward «{self.reward_title}» ({r.text[:120]}). "
                     "Listening to all rewards with a message.")

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
            return
        condition = {"broadcaster_user_id": self.user_id}
        if self.reward_id:
            condition["reward_id"] = self.reward_id
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
                        if self.source == "chat":
                            self.status = f"on: {self.login}, reading chat of #{self.channel} ($ word for word, % retold)"
                            self.log(f"Twitch connected as {self.login}, reading #{self.channel}: "
                                     "$message = said word for word, %message = retold by the NPC.")
                        else:
                            self.status = f"on: {self.login}, reward «{self.reward_title}»"
                            self.log(f"Twitch connected ({self.login}). Waiting for «{self.reward_title}».")
                    elif kind == "notification":
                        ev = msg["payload"]["event"]
                        if self.source == "chat":
                            text = ((ev.get("message") or {}).get("text") or "").strip()
                            user = ev.get("chatter_user_name") or ev.get("chatter_user_login")
                            if text:
                                self.on_message(user, text, None)
                        else:
                            text = (ev.get("user_input") or "").strip()
                            if text:
                                self.on_message(ev.get("user_name") or ev.get("user_login"), text, ev)
                    elif kind == "session_reconnect":
                        url, moved = msg["payload"]["session"]["reconnect_url"], True
                        break
            except websocket.WebSocketTimeoutException:
                pass  # no keepalive in time: reconnect
            finally:
                ws.close()

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
