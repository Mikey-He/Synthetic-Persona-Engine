"""What a run shows while it runs, and the report it leaves.

LiveFeed (--live) writes the screen, the pointer and the phase into the run folder as the run goes,
for the platform's run page, which draws the pointer itself; nothing is drawn into the page the
model's screenshots come from. At the end the viewer page, with the data embedded, is saved as
report.html. The engine's own watch window was removed on 2026-11-01: the platform is where a run
is watched."""

from __future__ import annotations

import json
import base64
import threading
import time
from pathlib import Path

VIEWER = Path(__file__).with_name("viewer.html")


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

