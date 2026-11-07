"""Creates the Facebook session file for the `facebook` source, on your own computer.

Opens a visible Chromium on facebook.com: log in by hand with the scraping account
(2FA and "is this you?" checks included), then the cookies are saved as a Playwright
storage_state file. Copy that file to the worker (see the README, "Source Facebook").

    python -m scraper.facebook_login                      # -> facebook_state.json
    python -m scraper.facebook_login --out path.json --b64

--b64 also prints the file base64-encoded, for FACEBOOK_STORAGE_STATE_B64 in Dokploy.
The file gives full access to the account: don't commit it, don't share it.
"""

import argparse
import base64
import sys
import time
from pathlib import Path

from .facebook.session import save


def _logged_in(context) -> bool:
    return any(c.get("name") == "c_user" for c in context.cookies("https://www.facebook.com"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Log in to Facebook by hand and save the session for the worker")
    parser.add_argument("--out", type=Path, default=Path("facebook_state.json"))
    parser.add_argument("--b64", action="store_true", help="also print the file base64-encoded")
    parser.add_argument("--timeout", type=int, default=600, help="seconds to wait for the login (default 600)")
    args = parser.parse_args()

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(locale="fr-CA", timezone_id="America/Toronto", viewport={"width": 1366, "height": 900})
        page = context.new_page()
        page.goto("https://www.facebook.com/login", wait_until="domcontentloaded")
        print("Log in with the scraping account in the browser window (2FA included)...", file=sys.stderr)
        deadline = time.monotonic() + args.timeout
        while not _logged_in(context):
            if time.monotonic() > deadline:
                sys.exit("Timed out waiting for the login.")
            page.wait_for_timeout(1000)
        # Let the checkpoint / "save browser" screens finish and the home feed load.
        print("Logged in. Finish any remaining screen; saving in 15 s...", file=sys.stderr)
        page.wait_for_timeout(15000)
        user_agent = page.evaluate("navigator.userAgent").replace("HeadlessChrome", "Chrome")
        save(context, args.out, user_agent=user_agent)
        browser.close()

    print(f"Saved {args.out.resolve()}", file=sys.stderr)
    if args.b64:
        print(base64.b64encode(args.out.read_bytes()).decode())


if __name__ == "__main__":
    main()
