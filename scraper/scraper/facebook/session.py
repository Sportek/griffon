"""The scraping account's session: a Playwright storage_state file on the worker volume.

Created on a desktop with `python -m scraper.facebook_login` (headed, the user logs in by
hand, 2FA included), then copied to the worker. Saved again after every run so the cookies
Facebook rotates stay fresh. The file is the account: keep it private.

    FACEBOOK_STORAGE_STATE      path of the file (default /data/facebook/storage_state.json)
    FACEBOOK_STORAGE_STATE_B64  optional: the file base64-encoded (e.g. pasted in Dokploy's
                                Environment tab). Written to FACEBOOK_STORAGE_STATE when the
                                file is missing or when the value changes (new login).

Besides Playwright's "cookies" and "origins", the file holds "griffon": {"user_agent": ...}:
the browser that logged in, reused so the session keeps one consistent fingerprint.
"""

import base64
import hashlib
import json
import os
import sys
from pathlib import Path

from ..polite import SourceBlocked
from .store import atomic_write_json

DEFAULT_PATH = "/data/facebook/storage_state.json"
EXPIRED_MESSAGE = "facebook: session expired, re-run facebook_login"


class SessionExpired(SourceBlocked):
    """Logged out, checkpoint or 2FA wall: stop the run instead of retrying (and getting flagged)."""


def state_path() -> Path:
    return Path(os.getenv("FACEBOOK_STORAGE_STATE") or DEFAULT_PATH)


def _bootstrap_from_env(path: Path) -> None:
    encoded = (os.getenv("FACEBOOK_STORAGE_STATE_B64") or "").strip()
    if not encoded:
        return
    digest = hashlib.sha256(encoded.encode()).hexdigest()[:16]
    marker = path.with_name(path.name + ".b64sha")
    if path.exists() and marker.exists() and marker.read_text().strip() == digest:
        return  # already written; the file on disk has fresher cookies than the env value
    try:
        state = json.loads(base64.b64decode(encoded))
    except ValueError as e:
        raise SessionExpired(f"facebook: FACEBOOK_STORAGE_STATE_B64 is not valid base64 JSON ({e})") from e
    atomic_write_json(path, state)
    marker.write_text(digest)
    print(f"[facebook] session written to {path} from FACEBOOK_STORAGE_STATE_B64", file=sys.stderr)


def load(path: Path | None = None) -> tuple[dict, str | None]:
    """Returns (Playwright storage_state, user agent of the login browser)."""
    path = path or state_path()
    _bootstrap_from_env(path)
    if not path.exists():
        raise SessionExpired(f"facebook: no session file at {path}; run python -m scraper.facebook_login")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        raise SessionExpired(f"facebook: unreadable session file {path} ({e}), re-run facebook_login") from e
    if not any(c.get("name") == "c_user" for c in data.get("cookies", [])):
        raise SessionExpired(EXPIRED_MESSAGE)
    state = {"cookies": data.get("cookies", []), "origins": data.get("origins", [])}
    return state, (data.get("griffon") or {}).get("user_agent")


def save(context, path: Path | None = None, *, user_agent: str | None = None) -> None:
    """Writes the context's current cookies back (atomic: the old file survives a crash)."""
    path = path or state_path()
    state = context.storage_state()
    if not any(c.get("name") == "c_user" for c in state.get("cookies", [])):
        return  # logged out mid-run: don't overwrite the file with an anonymous session
    if user_agent:
        state["griffon"] = {"user_agent": user_agent}
    atomic_write_json(path, state)


# Where Facebook sends a session it doesn't trust any more.
_BLOCKED_URL_PARTS = ("/login", "/checkpoint", "two_step_verification", "/recover", "login.php")


def check_page(url: str, html_head: str, cookies: list[dict]) -> None:
    """Raises SessionExpired if the page is a login / checkpoint wall."""
    lowered = url.lower()
    if any(part in lowered for part in _BLOCKED_URL_PARTS):
        raise SessionExpired(f"{EXPIRED_MESSAGE} (redirected to {url.split('?')[0]})")
    if not any(c.get("name") == "c_user" for c in cookies):
        raise SessionExpired(EXPIRED_MESSAGE)
    head = html_head.lower()
    if 'id="login_form"' in head or ('name="login"' in head and 'type="password"' in head):
        raise SessionExpired(EXPIRED_MESSAGE)
