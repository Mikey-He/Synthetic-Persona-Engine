"""Records a researcher doing the task once, as the start of a new workflow (engine-design.md 6.3).

A browser window opens on the product. The researcher does the task the way it should be done;
every click, every box filled and every choice is written down with the control it was on (its
text, label, role, the part of the page and the group heading it sits in) and, after each one,
a full-page screenshot and every control on the page. Nothing is added to the product's page.
sue/draft.py turns the recording into a draft flow.json; the platform shows it for review.

    python -m sue.record --start http://127.0.0.1:4100/home --out ../data/workflows/teamspace-invite/recording
    python -m sue.record ... --login-url /login --user TEAMSPACE_USER --password TEAMSPACE_PASSWORD

The product's own data requests (fetch and XHR with JSON) are written down too, with their
answers shortened and anything named like a password or token blanked: they show what the task
saved and where it can be read back, so the draft can check the result exactly.

Also written down: a choice in a native dropdown, Enter pressed in a box, dragging one thing onto
another, the names of files uploaded, a click that opened a new tab (the recording follows it), a
file the product gave to download, and what each page is made of (shadow roots, frames, a canvas,
Chinese text, a CAPTCHA): the platform's capability check reads it.

The recording ends when the window is closed, or when a file named STOP appears in --out (the
platform's Finish button). Passwords are never recorded. --auto steps.json performs the steps
itself (for tests): [{"click": "Members"}, {"fill": "Email address", "value": "..."}, ...].

--name setup or cleanup records the steps the engine replays before or after each run, into
setup.json or cleanup.json. --sign-in-by-hand waits for the researcher to sign in (single sign-on,
a second step) before recording, and saves that sign-in to --session for the runs.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

from .config import load_env
from .screen import PAGE_SCRIPT, route_of
from .target import WebTarget

LISTEN = r"""
(() => {
  if (window.__sueRec) return;
  window.__sueRec = true;
  const send = (e) => { try { window.__sueRecorded(e); } catch (err) {} };
  const field = (el) => el && ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName);
  const typed = (el) => field(el) && !["checkbox", "radio", "button", "submit", "reset", "file"].includes(el.type);
  let lastDrag = 0;
  document.addEventListener("click", (ev) => {
    const control = window.__sue && window.__sue.controlOf(ev.target);
    if (!control || typed(control) || Date.now() - lastDrag < 400) return;  // a click into a text box is not a step; what is typed is
    send({ action: "click", control: window.__sue.describe(control), route: location.href });
  }, true);
  document.addEventListener("change", (ev) => {
    const el = ev.target;
    if (!typed(el)) return;
    const secret = el.type === "password";
    if (el.tagName === "SELECT") {
      const opt = el.options[el.selectedIndex];
      send({ action: "select", control: window.__sue.describe(el), value: opt ? opt.text : "", route: location.href });
    } else {
      send({ action: "type", control: window.__sue.describe(el), value: secret ? "" : el.value, secret, route: location.href });
    }
  }, true);
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && typed(ev.target) && ev.target.tagName !== "TEXTAREA") {
      send({ action: "press", key: "Enter", control: window.__sue.describe(ev.target), route: location.href });
    } else if (ev.key === "Escape") {
      send({ action: "press", key: "Escape", control: null, route: location.href });
    }
  }, true);
  // A file chosen for upload: its name only, never its content.
  document.addEventListener("change", (ev) => {
    const el = ev.target;
    if (!el || el.tagName !== "INPUT" || el.type !== "file") return;
    send({ action: "upload", control: window.__sue.describe(el), files: [...el.files].map((f) => f.name), route: location.href });
  }, true);
  // Dragging: pressed on one control, let go over another, further than a click would move.
  let down = null, dragged = 0;
  document.addEventListener("pointerdown", (ev) => {
    const c = window.__sue && window.__sue.controlOf(ev.target);
    down = { x: ev.clientX, y: ev.clientY, control: c ? window.__sue.describe(c) : null };
  }, true);
  document.addEventListener("pointerup", (ev) => {
    if (!down || Math.hypot(ev.clientX - down.x, ev.clientY - down.y) < 25) { down = null; return; }
    const over = window.__sue.controlOf(window.__sue_hit ? window.__sue_hit(ev.clientX, ev.clientY) : document.elementFromPoint(ev.clientX, ev.clientY));
    if (down.control) {
      send({ action: "drag", control: down.control, target: over ? window.__sue.describe(over) : null, route: location.href });
      dragged = lastDrag = Date.now();
    }
    down = null;
  }, true);
  document.addEventListener("click", (ev) => {  // the click a drag ends with is not a step of its own
    if (Date.now() - dragged < 400) ev.__sueDrag = true;
  }, true);
})();
"""


HIDDEN = re.compile(r"pass|token|secret|auth|cookie|session", re.I)


def blank_secrets(data):
    if isinstance(data, dict):
        return {k: "***" if HIDDEN.search(k) else blank_secrets(v) for k, v in data.items()}
    if isinstance(data, list):
        return [blank_secrets(v) for v in data[:20]]
    if isinstance(data, str):
        return data[:200]
    return data


class Recorder:
    def __init__(self, out: Path, settle_ms: int = 600, name: str = "recording"):
        self.out = out
        self.name = name
        self.page = None
        self.settle_ms = settle_ms
        self.queue: list[dict[str, Any]] = []
        self.states: list[dict[str, Any]] = []
        self.actions: list[dict[str, Any]] = []
        self.meta: dict[str, Any] = {}
        self.network: list[dict[str, Any]] = []
        self.origin = ""

    def on_event(self, source, event: dict[str, Any]) -> None:
        self.queue.append({**event, "at": time.time()})

    def on_page(self, page) -> None:
        """A click opened a new tab: the recording follows it, as the person does."""
        self.watch(page)
        self.page = page
        self.queue.append({"action": "newtab", "control": None, "route": page.url, "at": time.time()})

    def on_download(self, download) -> None:
        self.queue.append({"action": "download", "control": None, "value": download.suggested_filename,
                           "route": self.page.url if self.page else "", "at": time.time()})

    def watch(self, page) -> None:
        page.on("request", self.on_request)
        page.on("response", self.on_response)
        page.on("download", self.on_download)

    def on_request(self, request) -> None:
        """What the product sends when it saves, read as it leaves: the page often moves on before
        the answer can be read."""
        try:
            if request.method == "GET" or request.resource_type not in ("fetch", "xhr") or not request.url.startswith(self.origin):
                return
            try:
                sent = blank_secrets(json.loads(request.post_data)) if request.post_data else None
            except ValueError:
                sent = None
            from urllib.parse import urlparse
            self.network.append({"after": len(self.actions) + len(self.queue), "method": request.method,
                                 "path": urlparse(request.url).path, "status": None, "sent": sent, "answer": None})
        except Exception:  # noqa: BLE001 - a request we cannot read is left out of the recording
            pass

    def on_response(self, response) -> None:
        """A JSON request the product made itself, from its own origin."""
        try:
            request = response.request
            if request.method != "GET" or request.resource_type not in ("fetch", "xhr") or not response.url.startswith(self.origin):
                return
            if "json" not in (response.headers.get("content-type") or ""):
                return
            try:
                sent = blank_secrets(json.loads(request.post_data)) if request.post_data else None
            except ValueError:
                sent = None
            from urllib.parse import urlparse
            self.network.append({"after": len(self.actions) + len(self.queue), "method": request.method,
                                 "path": urlparse(response.url).path, "status": response.status, "sent": sent,
                                 "answer": blank_secrets(response.json())})
        except Exception:  # noqa: BLE001 - a request we cannot read is left out of the recording
            pass

    def settle(self, page) -> None:
        try:
            page.wait_for_load_state("networkidle", timeout=4000)
        except Exception:  # noqa: BLE001 - a page that keeps polling still gets its settle time
            pass
        page.wait_for_timeout(self.settle_ms)

    def capture(self, page) -> int:
        """The page as it is now: a full-page screenshot, every control, and the text."""
        n = len(self.states)
        shot = f"{'' if self.name == 'recording' else self.name + '_'}state_{n:03d}.png"
        page.screenshot(path=str(self.out / shot), full_page=True)
        try:
            probe = page.evaluate("() => window.__sue.probe()")
            probe["frames"] = len(page.frames) - 1
        except Exception:  # noqa: BLE001
            probe = {}
        self.states.append({"probe": probe,
            "n": n, "url": page.url, "route": route_of(page.url), "title": page.title(), "shot": shot,
            "controls": page.evaluate("() => window.__sue.inventory()"),
            "text": page.evaluate("() => (document.body ? document.body.innerText : '').slice(0, 20000)"),
            "scroll": page.evaluate("() => ({w: document.documentElement.scrollWidth, h: document.documentElement.scrollHeight})"),
        })
        return n

    def save(self) -> None:
        data = {**self.meta, "states": self.states, "actions": self.actions, "network": self.network,
                "capabilities": capabilities(self.states, self.actions)}
        tmp = self.out / f"{self.name}.json.tmp"
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        for attempt in range(20):  # on Windows the platform may be reading it at this moment
            try:
                tmp.replace(self.out / f"{self.name}.json")
                return
            except PermissionError:
                time.sleep(0.1)
        tmp.replace(self.out / f"{self.name}.json")

    def drain(self, page=None) -> None:
        """Every action waiting: let the page settle, then capture what they led to. A box filled
        and the button clicked next arrive together (the change event fires as the click starts),
        so they share the screen before them and the one after."""
        if not self.queue:
            return
        page = self.page or page
        self.settle(page)
        batch, self.queue = self.queue, []
        before = len(self.states) - 1
        after = self.capture(page)
        for event in batch:
            self.actions.append({"n": len(self.actions) + 1, "before": before, "after": after, **event})
            c = event.get("control") or {}
            print(f"  {len(self.actions):>3} {event['action']} {c.get('text') or c.get('label') or ''!r}"
                  f" on {route_of(event.get('route') or page.url)}", flush=True)
        self.save()


def capabilities(states: list[dict[str, Any]], actions: list[dict[str, Any]]) -> dict[str, Any]:
    """What the recorded task uses that a plain page would not (engine-design.md 6.3)."""
    probes = [s.get("probe") or {} for s in states]
    most = lambda k: max([p.get(k) or 0 for p in probes] or [0])  # noqa: E731
    used = {a["action"] for a in actions}
    return {
        "shadowDom": most("shadowRoots") > 0, "frames": most("frames") > 0, "canvas": most("canvasShare") >= 0.4,
        "chinese": most("cjkShare") >= 0.2, "captcha": any(p.get("captcha") for p in probes),
        "innerScroll": any(p.get("innerScroll") for p in probes), "nativeSelect": "select" in used,
        "keys": "press" in used, "drag": "drag" in used, "upload": "upload" in used, "newTab": "newtab" in used,
        "download": "download" in used,
    }


def auto(page, steps: list[dict[str, Any]], recorder: Recorder) -> None:
    """Performs scripted steps with real clicks and typing, for tests of the recorder itself."""
    for step in steps:
        page = recorder.page or page
        if "choose" in step:
            page.get_by_label(step["choose"], exact=True).first.select_option(label=step["value"])
        elif "press" in step:
            page.keyboard.press(step["press"])
        elif "drag" in step:
            page.get_by_text(step["drag"], exact=True).first.drag_to(page.get_by_text(step["to"], exact=True).first)
        elif "upload" in step:
            page.get_by_label(step["upload"], exact=True).first.set_input_files(step["file"])
        elif "click" in step:
            how = step.get("by", "text")
            loc = (page.get_by_label(step["click"], exact=True) if how == "label" else
                   page.get_by_role(step["role"], name=step["click"], exact=True) if "role" in step else
                   page.get_by_text(step["click"], exact=True))
            loc.first.click()
        elif "fill" in step:
            box = page.get_by_label(step["fill"], exact=True).first
            box.click()
            box.fill(step["value"])
            box.press("Tab")
        page.wait_for_timeout(300)
        recorder.drain(page)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--start", required=True, help="the full address of the page the task starts on")
    parser.add_argument("--out", required=True, help="folder for recording.json and the screenshots")
    parser.add_argument("--login-url", help="the sign-in page, relative to --start")
    parser.add_argument("--user", help="the variable in engine/.env holding the test account's user name")
    parser.add_argument("--password", help="the variable in engine/.env holding its password")
    parser.add_argument("--reset", help="a URL (relative to --start) to POST to first, so the product starts clean")
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=900, help="the whole window; the page gets it less the task bar")
    parser.add_argument("--auto", help="steps.json to perform instead of a person (tests)")
    parser.add_argument("--written", help="a text file with the right way to do the task, one step per line: "
                                          "the model carries the steps out instead of a person (sue/written.py)")
    parser.add_argument("--task", help="the task as participants read it (with --written)")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--name", default="recording", choices=["recording", "setup", "cleanup"],
                        help="the task, or the steps the engine replays before (setup) or after (cleanup) each run")
    parser.add_argument("--sign-in-by-hand", action="store_true", help="wait for the researcher to sign in first")
    parser.add_argument("--session", help="where the sign-in is saved for the runs (and read, when it exists)")
    args = parser.parse_args(argv)

    load_env()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "STOP").unlink(missing_ok=True)
    (out / "SIGNED_IN").unlink(missing_ok=True)
    spec: dict[str, Any] = {"kind": "web", "start": args.start, "success": []}
    if args.login_url:
        spec["login"] = {"url": args.login_url, "user": args.user, "password": args.password}
    hand = {"mode": "session", "file": Path(args.session).name} if args.session else None
    if args.reset:
        spec["reset"] = {"method": "POST", "url": args.reset}
    target = WebTarget(spec)
    recorder = Recorder(out, name=args.name)
    from urllib.parse import urlparse
    start = urlparse(args.start)
    recorder.origin = f"{start.scheme}://{start.netloc}"
    page_h = args.height - 56  # the engine's task bar (screen.Strip) takes the same room in every run
    recorder.meta = {"format": "sue-recording", "version": 1, "start": args.start, "viewport": {"width": args.width, "height": page_h},
                     "login": hand or spec.get("login"), "reset": spec.get("reset"), "startedAt": time.strftime("%Y-%m-%dT%H:%M:%S")}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=args.headless or bool(args.auto and args.headless))
        saved = args.session if args.session and Path(args.session).exists() and not args.sign_in_by_hand else None
        context = browser.new_context(viewport={"width": args.width, "height": page_h}, device_scale_factor=1,
                                      accept_downloads=True, storage_state=saved)
        context.add_init_script(path=str(PAGE_SCRIPT))
        page = context.new_page()
        target.prepare(page)  # reset and sign in by code: the recording starts on the task's first page
        if args.sign_in_by_hand:
            # Single sign-on or a second step: the researcher signs in; the platform says when (SIGNED_IN).
            page.goto(args.start)
            print("Sign in in the window, then press 'I'm signed in' in the platform.", flush=True)
            while not page.is_closed() and not (out / "SIGNED_IN").exists():
                page.wait_for_timeout(300)
            if args.session:
                context.storage_state(path=args.session)
                print(f"Saved the sign-in to {args.session}", flush=True)
        context.expose_binding("__sueRecorded", recorder.on_event)
        recorder.page = page
        recorder.watch(page)
        context.on("page", recorder.on_page)
        context.add_init_script(script=LISTEN)
        page.goto(args.start)
        page.evaluate(LISTEN)
        recorder.settle(page)
        recorder.capture(page)
        recorder.save()
        print(f"Recording {args.start} into {out}. Do the task in the window; close it (or press Finish) when done.", flush=True)
        if args.auto:
            auto(page, json.loads(Path(args.auto).read_text(encoding="utf-8")), recorder)
        elif args.written:
            from .config import load_config
            from .written import WrittenStepError, perform
            steps = [ln.strip(" -	") for ln in Path(args.written).read_text(encoding="utf-8").splitlines() if ln.strip(" -	")]
            try:
                perform(lambda: recorder.page, steps, args.task or "", recorder, load_config())
            except WrittenStepError as error:
                recorder.meta["stuck"] = str(error)
                print(str(error), flush=True)
        else:
            while not (out / "STOP").exists():
                if recorder.page.is_closed():
                    alive = [p for p in context.pages if not p.is_closed()]
                    if not alive:
                        break
                    recorder.page = alive[-1]
                try:
                    recorder.page.wait_for_timeout(250)
                    recorder.drain()
                except Exception:  # noqa: BLE001 - the window was closed mid-wait
                    continue
        recorder.meta["endedAt"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        recorder.save()
        try:
            browser.close()
        except Exception:  # noqa: BLE001 - already closed by the researcher
            pass
    (out / "STOP").unlink(missing_ok=True)
    (out / "SIGNED_IN").unlink(missing_ok=True)
    print(f"Recorded {len(recorder.actions)} actions on {len(recorder.states)} screens: {out / (args.name + '.json')}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
