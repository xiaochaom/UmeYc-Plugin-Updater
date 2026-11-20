import asyncio
from contextlib import suppress
from http.client import HTTPException
import json
import os
from pathlib import Path
import re
import secrets
from tempfile import NamedTemporaryFile
import time
from urllib.parse import urlencode

from downloads import https_request


DEVICE_URL = "https://github.com/login/device"
CLIENT_ID_FILE = "github-client-id.txt"
TOKEN_PATTERN = re.compile(r"gho_[A-Za-z0-9]+")
CLIENT_ID_PATTERN = re.compile(r"(?:Ov[0-9]{2}[A-Za-z0-9]{16}|[0-9a-f]{20})")


def is_client_id(value):
    return CLIENT_ID_PATTERN.fullmatch(value) is not None


def configured_client_id():
    value = os.environ.get("UMEYC_GITHUB_CLIENT_ID", "").strip()
    if not value:
        with suppress(OSError, UnicodeError):
            value = Path(__file__).with_name(CLIENT_ID_FILE).read_text(encoding="ascii").strip()
    return value if is_client_id(value) else ""


def oauth_post(path, **fields):
    with https_request(f"https://github.com/login/{path}", {
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
    }, method="POST", body=urlencode(fields).encode("ascii")) as response:
        status = response.status
        if status not in (200, 400):
            raise ValueError("GitHub rejected the device authorization request")
        raw = response.read(16_385)
        if len(raw) > 16_384:
            raise ValueError("GitHub device authorization response is too large")
        payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("Invalid GitHub device authorization response")
    if status == 400:
        error = payload.get("error")
        if not isinstance(error, str) or not error:
            raise ValueError("GitHub rejected the device authorization request")
        return {"error": error}
    return payload


class GitHubAuth:
    def __init__(self, token_path, client_id):
        self.token_path = token_path
        self.client_id = client_id
        self.session = None
        self.lock = asyncio.Lock()

    def token(self):
        if not self.client_id:
            return None
        try:
            with self.token_path.open(encoding="ascii") as stored:
                credentials = json.loads(stored.read(4096))
            token = credentials.get("token")
            expires = credentials.get("expires", 0)
            if (credentials.get("client_id") == self.client_id and isinstance(token, str)
                    and TOKEN_PATTERN.fullmatch(token) and (not expires or expires > time.time())):
                return token
        except (OSError, ValueError, TypeError, AttributeError):
            pass
        return None

    def _store(self, token, expires_in):
        self.token_path.parent.mkdir(mode=0o700, exist_ok=True, parents=True)
        with NamedTemporaryFile(dir=self.token_path.parent, mode="w", encoding="ascii", delete=False) as temp:
            temporary = Path(temp.name)
            try:
                json.dump({"client_id": self.client_id, "token": token,
                           "expires": time.time() + expires_in if expires_in else 0}, temp)
                temp.close()
                temporary.replace(self.token_path)
            finally:
                temporary.unlink(missing_ok=True)

    def status(self):
        return {"available": bool(self.client_id), "connected": bool(self.token())}

    async def start(self):
        if not self.client_id:
            return {"status": "unavailable"}
        async with self.lock:
            if self.token():
                return {"status": "connected"}
            self.session = None
            try:
                result = await asyncio.to_thread(oauth_post, "device/code", client_id=self.client_id, scope="")
                if result.get("error") == "device_flow_disabled":
                    return {"status": "device_flow_disabled"}
                device_code = result["device_code"]
                code = result["user_code"]
                expires = int(result["expires_in"])
                interval = max(1, int(result["interval"]))
                if not isinstance(device_code, str) or not device_code or not re.fullmatch(r"[A-Z0-9-]{4,20}", code):
                    return {"status": "error"}
                if result.get("verification_uri") != DEVICE_URL or expires <= 0:
                    return {"status": "error"}
            except (OSError, HTTPException, KeyError, TypeError, ValueError):
                return {"status": "error"}
            now = time.monotonic()
            session_id = secrets.token_urlsafe(16)
            self.session = {"id": session_id, "device_code": device_code, "expires": now + expires,
                            "interval": interval, "next_poll": now + interval}
            return {"status": "waiting", "id": session_id, "code": code, "url": DEVICE_URL, "retry_in": interval}

    async def poll(self, session_id):
        async with self.lock:
            session = self.session
            now = time.monotonic()
            if not session or session_id != session["id"]:
                return {"status": "expired"}
            if now >= session["expires"]:
                self.session = None
                return {"status": "expired"}
            if now < session["next_poll"]:
                return {"status": "waiting", "retry_in": session["next_poll"] - now}
            session["next_poll"] = now + session["interval"]
            try:
                result = await asyncio.to_thread(oauth_post, "oauth/access_token", client_id=self.client_id,
                                                 device_code=session["device_code"],
                                                 grant_type="urn:ietf:params:oauth:grant-type:device_code")
            except (OSError, HTTPException, TypeError, ValueError):
                result = {"error": "request_failed"}
            if self.session is not session:
                return {"status": "expired"}
            token = result.get("access_token")
            error = result.get("error")
            if error in ("authorization_pending", "slow_down"):
                if error == "slow_down":
                    interval = result.get("interval")
                    session["interval"] = max(session["interval"] + 5, interval if type(interval) is int else 0)
                session["next_poll"] = time.monotonic() + session["interval"]
                return {"status": "waiting", "retry_in": session["interval"]}
            self.session = None
            if error == "access_denied":
                return {"status": "denied"}
            if error in ("expired_token", "token_expired"):
                return {"status": "expired"}
            expires = result.get("expires_in", 0)
            if (not isinstance(token, str) or not TOKEN_PATTERN.fullmatch(token) or result.get("scope") != ""
                    or str(result.get("token_type")).lower() != "bearer" or type(expires) is not int or expires < 0):
                return {"status": "error"}
            try:
                self._store(token, expires)
            except OSError:
                return {"status": "error"}
            return {"status": "connected"}

    def cancel(self, session_id):
        if self.session and self.session["id"] == session_id:
            self.session = None

    def sign_out(self):
        self.session = None
        self.token_path.unlink(missing_ok=True)
