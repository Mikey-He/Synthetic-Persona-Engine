"""Watch mode (--watch): one window, two panels.

Left: the engine's browser, live. The engine's browser itself runs without a window;
Chromium streams its screen (CDP screencast) to this dashboard, and the pointer is
drawn by the dashboard, never into the page the model's screenshots come from.
Right: the step log, read from the run folder as the run writes it.

At the end the same page, with the data embedded, is saved as report.html."""

from __future__ import annotations

import json
import base64
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

VIEWER = Path(__file__).with_name("viewer.html")


class _Live:
    """What the left panel shows right now: the latest frame and the pointer."""

    def __init__(self, viewport: tuple[int, int]):
        self.frame: bytes = b""
        self.state = {
            "frame": 0, "x": viewport[0] / 2, "y": viewport[1] / 2, "click": 0, "cx": 0, "cy": 0,
            "phase": "Getting ready", "width": viewport[0], "height": viewport[1], "live": True,
        }
        self.lock = threading.Lock()

    def update(self, **values) -> None:
        with self.lock:
            self.state.update(values)

    def snapshot(self) -> bytes:
        with self.lock:
            return json.dumps(self.state, ensure_ascii=False).encode("utf-8")


class _Handler(SimpleHTTPRequestHandler):
    live: _Live | None = None

    def do_GET(self):  # noqa: N802 - http.server's naming
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            return self._send(VIEWER.read_bytes(), "text/html; charset=utf-8")
        if path == "/live/state" and self.live:
            return self._send(self.live.snapshot(), "application/json")
        if path == "/live/frame" and self.live:
            return self._send(self.live.frame, "image/jpeg")
        return super().do_GET()

    def _send(self, body: bytes, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *args):  # keep the terminal for the run's own output
        pass


class Dashboard:
    def __init__(self, run_dir: Path, playwright, engine_page, viewport: tuple[int, int]):
        self.live = _Live(viewport)
        handler = type("Handler", (_Handler,), {"live": self.live})
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), partial(handler, directory=str(run_dir)))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/"

        # Stream the engine's screen. Frames arrive whenever Playwright is waiting or acting.
        self.held = False
        self.pending: bytes | None = None
        self.cdp = engine_page.context.new_cdp_session(engine_page)
        self.cdp.on("Page.screencastFrame", self._frame)
        self.cdp.send("Page.startScreencast", {
            "format": "jpeg", "quality": 80, "maxWidth": viewport[0], "maxHeight": viewport[1], "everyNthFrame": 1,
        })

        # One window for the person, filling the screen.
        self.browser = playwright.chromium.launch(headless=False, args=["--start-maximized"])
        self.page = self.browser.new_context(no_viewport=True).new_page()
        self.page.goto(self.url)

    def _frame(self, params) -> None:
        frame = base64.b64decode(params["data"])
        if self.held:
            self.pending = frame  # shown on release, once the page is rewritten
        else:
            self._show(frame)
        try:
            self.cdp.send("Page.screencastFrameAck", {"sessionId": params["sessionId"]})
        except Exception:  # noqa: BLE001 - the page may be closing
            pass

    def _show(self, frame: bytes) -> None:
        self.live.frame = frame
        self.live.update(frame=self.live.state["frame"] + 1)

    # ---- called by the engine -------------------------------------------------

    def hold(self) -> None:
        """Keep showing the current frame (the page is about to show unrewritten words)."""
        self.held = True

    def release(self) -> None:
        self.held = False
        if self.pending is not None:
            self._show(self.pending)
            self.pending = None

    def phase(self, text: str) -> None:
        """What the engine is doing right now, shown above the live screen."""
        self.live.update(phase=text)

    def move(self, x: float, y: float) -> None:
        self.live.update(x=x, y=y)

    def click(self, x: float, y: float) -> None:
        self.live.update(click=self.live.state["click"] + 1, cx=x, cy=y)

    def finish(self) -> None:
        self.live.update(phase="Finished", live=False)

    def wait_until_closed(self) -> None:
        """Keeps the window up until the person closes it."""
        try:
            self.page.wait_for_event("close", timeout=0)
        except Exception:  # noqa: BLE001 - the window or browser was closed
            pass

    def close(self) -> None:
        try:
            self.cdp.send("Page.stopScreencast")
        except Exception:  # noqa: BLE001
            pass
        try:
            self.browser.close()
        except Exception:  # noqa: BLE001
            pass
        self.server.shutdown()


class LiveFeed:
    """The run as it happens, for the platform's Watch live (2026-10-19): the engine's screen as a
    frame (live.jpg) and where the pointer is, what was clicked and what he is looking at
    (live.json), written into the run folder a few times a second. The same calls as Dashboard,
    without a window of its own; the platform draws the pointer over the frame."""

    EVERY_S = 0.2  # at most five frames a second on disk

    def __init__(self, run_dir: Path, engine_page, viewport: tuple[int, int]):
        self.dir = Path(run_dir)
        self.viewport = viewport
        self.state = {"frame": 0, "x": viewport[0] / 2, "y": viewport[1] / 2, "click": 0, "cx": 0, "cy": 0,
                      "phase": "Getting ready", "width": viewport[0], "height": viewport[1], "live": True, "focus": None}
        self.held, self.pending, self.last, self.cdp = False, None, 0.0, None
        self.lock = threading.Lock()
        self.attach(engine_page)

    def attach(self, page) -> None:
        """Streams this page: a new tab he followed, or the first page."""
        if self.cdp:
            try:
                self.cdp.send("Page.stopScreencast")
            except Exception:  # noqa: BLE001 - the old tab may be gone
                pass
        self.cdp = page.context.new_cdp_session(page)
        self.cdp.on("Page.screencastFrame", self._frame)
        self.cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 70, "maxWidth": self.viewport[0],
                                               "maxHeight": self.viewport[1], "everyNthFrame": 1})

    def _frame(self, params) -> None:
        cdp = self.cdp
        frame = base64.b64decode(params["data"])
        if self.held:
            self.pending = frame
        else:
            self._show(frame)
        try:
            cdp.send("Page.screencastFrameAck", {"sessionId": params["sessionId"]})
        except Exception:  # noqa: BLE001 - the page may be closing
            pass

    def _write(self, name: str, data: bytes) -> None:
        tmp = self.dir / (name + ".tmp")
        tmp.write_bytes(data)
        for _ in range(10):  # the platform may be reading it at this moment
            try:
                tmp.replace(self.dir / name)
                return
            except PermissionError:
                time.sleep(0.02)

    def _show(self, frame: bytes, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self.last < self.EVERY_S:
            self.pending = frame
            return
        self.last = now
        self._write("live.jpg", frame)
        self.update(frame=self.state["frame"] + 1)

    def update(self, **values) -> None:
        with self.lock:
            self.state.update(values)
            self._write("live.json", json.dumps(self.state).encode("utf-8"))

    def hold(self) -> None:
        self.held = True

    def release(self) -> None:
        self.held = False
        if self.pending is not None:
            self._show(self.pending, force=True)
            self.pending = None

    def phase(self, text: str) -> None:
        self.update(phase=text)

    def move(self, x: float, y: float) -> None:
        self.update(x=x, y=y)

    def click(self, x: float, y: float) -> None:
        self.update(click=self.state["click"] + 1, cx=x, cy=y)

    def focus(self, rect) -> None:
        self.update(focus=rect)

    def finish(self) -> None:
        if self.pending is not None:
            self._show(self.pending, force=True)
        self.update(phase="Finished", live=False)

    def wait_until_closed(self) -> None:
        pass

    def close(self) -> None:
        try:
            self.cdp.send("Page.stopScreencast")
        except Exception:  # noqa: BLE001
            pass


def write_report(run_dir: Path) -> Path:
    """The dashboard page with this run's data embedded: open it any time, no server needed.
    The left panel then shows the screenshot of whichever step is selected."""
    steps_file = run_dir / "steps.jsonl"
    data = {
        "run": json.loads((run_dir / "run.json").read_text(encoding="utf-8")),
        "steps": [json.loads(line) for line in steps_file.read_text(encoding="utf-8").splitlines() if line.strip()],
        "summary": json.loads((run_dir / "summary.json").read_text(encoding="utf-8")),
    }
    data["run"].pop("config", None)  # keep the report light; run.json has the full config
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    marker = "<script>\n// Live mode"
    html = VIEWER.read_text(encoding="utf-8")
    assert marker in html, "viewer.html changed; update write_report"
    html = html.replace(marker, f"<script>window.__SUE_DATA = {payload};</script>\n{marker}", 1)
    out = run_dir / "report.html"
    out.write_text(html, encoding="utf-8")
    return out

