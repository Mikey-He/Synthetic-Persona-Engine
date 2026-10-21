"""End-to-end check of the Teamspace invite flow with Playwright (sync API, Chromium).

Usage (server already running):
    python examples/teamspace/check_flow.py --base-url http://127.0.0.1:4100

Or let the script start and stop its own server:
    python examples/teamspace/check_flow.py --start-server --port 4100

Optional: --screenshots DIR saves a screenshot of each step, --headed shows the browser.
Exit code 0 means every check passed.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

HERE = Path(__file__).resolve().parent
EMAIL = "admin@lumenlabs.example"
PASSWORD = "teamspace-demo"
INVITEE_EMAIL = "priya.shah@lumenlabs.example"
INVITEE_NAME = "Priya Shah"

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + (f"  ({detail})" if detail else ""), flush=True)


def wait_for_server(base: str, timeout: float = 10.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(base + "/login", timeout=1).read()
            return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError(f"server at {base} did not come up")


def run(base: str, shots: Path | None, headed: bool) -> None:
    def shot(page, name: str) -> None:
        if shots:
            page.screenshot(path=str(shots / f"{name}.png"), full_page=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()
        api = context.request

        r = api.post(base + "/api/reset")
        check("reset before run", r.ok and r.json() == {"ok": True}, r.text())

        # 1. Signed-out pages redirect to /login
        page.goto(base + "/members")
        check("signed-out /members redirects to /login", "/login" in page.url, page.url)
        r = api.get(base + "/api/members")
        check("signed-out API returns 401", r.status == 401, str(r.status))

        # 2. Sign in (lands back on /members because of ?next=, so sign in from /login directly)
        page.goto(base + "/login")
        shot(page, "01-login")
        page.get_by_label("Email address").fill(EMAIL)
        page.get_by_label("Password").fill(PASSWORD)
        page.get_by_role("button", name="Sign in").click()
        page.wait_for_url("**/home")
        check("sign-in lands on /home", page.url.endswith("/home"), page.url)
        expect(page.locator("#stat-members")).to_have_text("5")
        shot(page, "02-home")

        # 3. Members via the left navigation
        page.get_by_role("navigation", name="Main").get_by_role("link", name="Members").click()
        page.wait_for_url("**/members")
        rows = page.locator("#members-body tr")
        expect(rows).to_have_count(6)
        check("members table has 6 seed rows", rows.count() == 6)
        shot(page, "03-members")

        # 4. Invite flow, step 1
        page.get_by_role("link", name="Invite people").click()
        page.wait_for_url("**/members/invite")
        check("Invite people opens /members/invite", page.url.endswith("/members/invite"), page.url)

        continue_btn = page.get_by_role("button", name="Continue")
        continue_btn.click()
        err = page.locator(".field-error[role=alert]")
        expect(err).to_be_visible()
        check("empty email shows inline error", err.is_visible(), err.inner_text())
        check("empty email does not advance", page.locator("#step-2").is_hidden())

        page.get_by_label("Email address").fill("priya.shah@")
        continue_btn.click()
        check("invalid email shows inline error", err.is_visible(), err.inner_text())
        check("invalid email does not advance", page.locator("#step-2").is_hidden())
        shot(page, "04-invite-error")

        page.get_by_label("Email address").fill(INVITEE_EMAIL)
        check("error clears once email is valid", err.count() == 0)
        page.get_by_label("Display name").fill(INVITEE_NAME)

        check("Contributor is selected by default", page.get_by_role("radio", name="Contributor").is_checked())

        help_btn = page.get_by_role("button", name="About roles")
        help_btn.click()
        tip = page.get_by_role("tooltip")
        expect(tip).to_be_visible()
        check("About roles opens the roles popover", tip.is_visible(), tip.inner_text().replace("\n", " ")[:60] + "...")
        shot(page, "05-invite-help")
        help_btn.click()
        check("About roles toggles the popover closed", tip.is_hidden())

        # Click the card's visible text (label click), not the radio itself.
        page.locator("label.radio-card", has_text="Viewer").click()
        check("clicking the Viewer card selects Viewer", page.get_by_role("radio", name="Viewer").is_checked())
        check("Contributor is no longer selected", not page.get_by_role("radio", name="Contributor").is_checked())

        continue_btn.click()
        expect(page.locator("#step-2")).to_be_visible()
        check("valid step 1 advances to step 2", page.locator("#step-1").is_hidden())

        # 5. Step 2 defaults
        cb = lambda n: page.get_by_role("checkbox", name=n, exact=True)
        defaults = {n: cb(n).is_checked() for n in ["Orion", "Vega", "Lyra", "Atlas-Retail", "Send a welcome email"]}
        check("step 2 defaults (Orion, Vega, welcome ticked)",
              defaults == {"Orion": True, "Vega": True, "Lyra": False, "Atlas-Retail": False, "Send a welcome email": True},
              json.dumps(defaults))

        # Back and forth keeps the values.
        page.get_by_role("button", name="Back").click()
        check("Back returns to step 1", page.locator("#step-1").is_visible())
        check("step 1 values kept", page.get_by_label("Email address").input_value() == INVITEE_EMAIL
              and page.get_by_role("radio", name="Viewer").is_checked())
        continue_btn.click()

        # Toggle via label text.
        page.locator("label.check-row", has_text="Orion").click()
        page.locator("label.check-row", has_text="Vega").click()
        page.locator("label.check-row", has_text="Lyra").click()
        picked = {n: cb(n).is_checked() for n in ["Orion", "Vega", "Lyra", "Atlas-Retail"]}
        check("only Lyra ticked after label clicks", picked == {"Orion": False, "Vega": False, "Lyra": True, "Atlas-Retail": False},
              json.dumps(picked))
        shot(page, "06-invite-step2")

        # 6. Confirmation dialog
        page.get_by_role("button", name="Send invite").click()
        dialog = page.get_by_role("dialog")
        expect(dialog).to_be_visible()
        title = dialog.get_by_role("heading").inner_text()
        check("dialog asks to confirm", title == f"Send invite to {INVITEE_EMAIL}?", title)
        check("dialog is aria-modal", dialog.get_attribute("aria-modal") == "true")
        shot(page, "07-confirm")
        dialog.get_by_role("button", name="Go back").click()
        check("Go back closes the dialog", dialog.is_hidden())
        r = api.get(base + "/api/invites")
        check("nothing stored before Send", r.json()["invites"] == [])

        page.get_by_role("button", name="Send invite").click()
        dialog.get_by_role("button", name="Send", exact=True).click()
        page.wait_for_url("**/members")

        # 7. Toast and table
        toast = page.locator(".toast", has_text="Invite sent")
        expect(toast).to_be_visible()
        check("toast 'Invite sent' appears", toast.is_visible())
        row = page.locator("#members-body tr", has_text=INVITEE_NAME)
        expect(row).to_have_count(1)
        check("new person in table with status Invited", "Invited" in row.inner_text(), row.inner_text().replace("\n", " | "))
        check("table now has 7 rows", page.locator("#members-body tr").count() == 7)
        shot(page, "08-members-after")
        expect(toast).to_have_count(0, timeout=6000)
        check("toast disappears after a few seconds", toast.count() == 0)

        # 8. API state
        invites = api.get(base + "/api/invites").json()["invites"]
        inv = invites[0] if len(invites) == 1 else {}
        check("GET /api/invites has exactly one invite", len(invites) == 1, json.dumps(invites))
        check("invite fields correct",
              inv.get("email") == INVITEE_EMAIL and inv.get("name") == INVITEE_NAME and inv.get("role") == "viewer"
              and inv.get("projects") == ["Lyra"] and inv.get("welcomeEmail") is True and inv.get("status") == "Invited")

        # 9. Reset
        r = api.post(base + "/api/reset")
        check("POST /api/reset returns {ok:true}", r.ok and r.json() == {"ok": True}, r.text())
        check("invites empty after reset", api.get(base + "/api/invites").json()["invites"] == [])
        check("members back to 6 after reset", len(api.get(base + "/api/members").json()["members"]) == 6)

        browser.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--port", type=int, default=4100)
    ap.add_argument("--start-server", action="store_true", help="start server.py for the run and stop it afterwards")
    ap.add_argument("--screenshots", default=None, help="directory for step screenshots")
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()
    base = (args.base_url or f"http://127.0.0.1:{args.port}").rstrip("/")
    shots = Path(args.screenshots) if args.screenshots else None
    if shots:
        shots.mkdir(parents=True, exist_ok=True)

    proc = None
    if args.start_server:
        proc = subprocess.Popen([sys.executable, str(HERE / "server.py"), "--port", str(args.port), "--quiet"])
    try:
        wait_for_server(base)
        run(base, shots, args.headed)
    except Exception as exc:  # report a crash as a failed check
        check("run completed without exceptions", False, f"{type(exc).__name__}: {exc}")
    finally:
        if proc:
            proc.terminate()
            proc.wait(timeout=10)

    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
