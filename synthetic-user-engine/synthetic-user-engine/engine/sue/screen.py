"""Steps 1 to 3 and 7: read the screen, rewrite it the way this person sees it, take the
screenshot, and carry out the chosen action (engine-design.md 4).

Code reads and changes the DOM here; the model never does. What leaves this module
for the model is the processed screenshot and the list of visible elements."""

from __future__ import annotations

import hashlib
import io
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .persona import EVERYDAY, KNOW, NONE, OTHER
from .words import LETTERS, Hit, Vocabulary, fake, tokens, unreadable_text

PAGE_SCRIPT = Path(__file__).with_name("page_script.js")

# Colour vision (engine-design.md 4.9): the screenshot the model gets is filtered. Reduced is
# deuteranopia (Machado et al. 2009, severity 1); no colour cues is plain luminance.
COLOR_MATRICES = {
    "reduced": (0.367322, 0.860646, -0.227968, 0, 0.280085, 0.672501, 0.047413, 0, -0.011820, 0.042940, 0.968881, 0),
    "no_color_cues": (0.299, 0.587, 0.114, 0, 0.299, 0.587, 0.114, 0, 0.299, 0.587, 0.114, 0),
}


def color_filter(png: bytes, kind: str) -> bytes:
    matrix = COLOR_MATRICES.get(kind)
    if not matrix:
        return png
    from PIL import Image  # only cards with reduced colour vision need it

    out = io.BytesIO()
    Image.open(io.BytesIO(png)).convert("RGB").convert("RGB", matrix).save(out, format="PNG")
    return out.getvalue()


def unreadable(text: str) -> str:
    """Text too small for him to read: every word becomes a made-up word, digits blur to #."""
    return unreadable_text(text)


class RewriteError(RuntimeError):
    """The page kept putting original words back. Better no screenshot than a leaky one."""


@dataclass
class Observation:
    step: int
    route: str
    context: str  # route plus open sections
    signature: str  # context plus a digest of every text and every value on the page: the screen state
    screenshot: bytes
    elements: list[dict[str, Any]]
    visible_text: str  # what he can read in the viewport, after rewriting
    hits: list[Hit]  # every word in the viewport and how he sees it
    explanations: list[dict[str, str]]  # open help text that names the item it explains
    scroll: dict[str, int]
    rewrite_rounds: int
    gray_icons: list[str] = field(default_factory=list)
    focus: Any = None  # the piece of the screen he is looking at (attention.Chunk), or None for all of it
    unnoticed: list[str] = field(default_factory=list)  # warning text hidden this step: he did not notice it

    @property
    def seen(self) -> list[dict[str, Any]]:
        """The elements he is looking at: the focus piece, or every product element."""
        return self.focus.elements if self.focus else [e for e in self.elements if not e["harness"]]


# How the platform puts the session into its URLs (config.toml platform.session_path); Screen sets it.
SESSION_PATH = r"^/s/[^/]+"


def route_of(url: str) -> str:
    """The page's route without the session token, e.g. /billing/budgets/create?edit. A product
    that routes in the address's fragment (#/members/invite) has that path added."""
    parsed = urlparse(url)
    path = re.sub(SESSION_PATH, "", parsed.path) or "/"
    query = sorted(parse_qs(parsed.query).keys())
    frag = parsed.fragment.split("?")[0]
    if frag.startswith("!/"):
        frag = frag[1:]
    hashed = "#" + frag if frag.startswith("/") else ""
    return path + hashed + ("?" + "&".join(query) if query else "")


def _filled(background: str) -> bool:
    """A coloured solid background, which is how a primary button looks."""
    m = re.match(r"rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)", background or "")
    if not m:
        return False
    r, g, b = (int(m.group(i)) for i in (1, 2, 3))
    alpha = float(m.group(4)) if m.group(4) is not None else 1.0
    return alpha > 0.5 and max(r, g, b) - min(r, g, b) > 60


def context_of(url: str, expanded: list[str]) -> str:
    """The screen as memory and attention see it: the route plus what is open on the
    whole page (sections, dropdowns), whether or not it is scrolled into view. It used
    to count only what was in view, so scrolling made a new screen and the same
    dropdown could be opened and closed again and again (2026-10-04)."""
    return f"{route_of(url)}|{'/'.join(sorted(expanded))}"


def understanding(hits: list[Hit]) -> list[str]:
    """What he takes the words of one element to mean, for the element list (4.1)."""
    out = []
    for h in hits:
        if h.level == EVERYDAY and h.gloss:
            out.append(f"{h.shown} (knows only the everyday meaning: {h.gloss})")
        elif h.level == OTHER and h.gloss:
            out.append(f"{h.shown} (reads it as: {h.gloss})")
    return out


class Strip:
    """The test's own task bar, drawn by the engine below the product's page (engine-design.md 6.3).

    On our platform the task bar is part of the page. A product that is not ours has none, and
    putting one into its page would cover part of it (a fixed footer, a cookie banner, a chat
    button) and could break its layout. So the page gets a window shorter by the bar's height,
    exactly as the platform's own bar takes room from the product, and the bar is drawn into the
    screenshot below it. Its I'm finished button is an element like any other on his list; code
    clicks it when he is done, and nothing is sent to the product."""

    HEIGHT = 56

    def __init__(self, task: str, button: str, width: int, height: int = HEIGHT):
        self.task, self.button, self.width, self.height = task, button, width, height
        self.button_box = {"w": 132, "h": 36}
        # As much of the task as fits on one line before the button, like the platform's bar.
        text = "Task: " + re.sub(r"\s+", " ", task.strip())
        room = width - self.button_box["w"] - 64
        font = self._font(15)
        if font.getlength(text) > room:
            while text and font.getlength(text + "...") > room:
                text = text[:-1]
            text = text.rstrip() + "..."
        self.line = text

    def element(self, page_height: int) -> dict[str, Any]:
        w, h = self.button_box["w"], self.button_box["h"]
        box = {"x": self.width - w - 16, "y": page_height + (self.height - h) // 2, "w": w, "h": h}
        return {"index": -1, "hidden": False, "tag": "button", "role": "", "type": "", "text": self.button, "icon": "",
                "original": self.button, "value": None, "checked": None, "disabled": False, "expanded": None,
                "kl": None, "explains": None, "harness": True, "virtual": True,
                "region": {"id": 0, "kind": "other", **box, "group": {"id": 0, **box, "heading": ""}},
                "box": box, "font": {"size": 14.0, "weight": "500", "color": "rgb(255, 255, 255)"},
                "background": "rgb(11, 87, 208)"}

    def texts(self) -> list[str]:
        return [self.line, self.button]

    @staticmethod
    def _font(size: int):
        from PIL import ImageFont

        for name in ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf", "Helvetica.ttc"):
            try:
                return ImageFont.truetype(name, size)
            except OSError:
                continue
        return ImageFont.load_default(size=size)

    def compose(self, png: bytes) -> bytes:
        from PIL import Image, ImageDraw

        page = Image.open(io.BytesIO(png)).convert("RGB")
        out = Image.new("RGB", (page.width, page.height + self.height), (241, 243, 244))
        out.paste(page, (0, 0))
        draw = ImageDraw.Draw(out)
        top = page.height
        draw.line([(0, top), (page.width, top)], fill=(218, 220, 224), width=1)
        draw.text((16, top + self.height // 2), self.line, fill=(32, 33, 36), font=self._font(15), anchor="lm")
        b = self.element(page.height)["box"]
        draw.rounded_rectangle([b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"]], radius=18, fill=(11, 87, 208))
        draw.text((b["x"] + b["w"] // 2, b["y"] + b["h"] // 2), self.button, fill=(255, 255, 255), font=self._font(14),
                  anchor="mm")
        buf = io.BytesIO()
        out.save(buf, format="PNG")
        return buf.getvalue()


class Screen:
    def __init__(self, page, vocabulary: Vocabulary, config: dict[str, Any], show=None, reveal_hover: bool = False,
                 strip: Strip | None = None):
        """show is the watch-mode dashboard (or None). It draws the pointer in its own
        panel, so nothing is ever drawn into the page the screenshots come from.

        reveal_hover: he checks a form row by row (detail when checking: high), so controls
        that only appear under the mouse, such as a row's delete icon, show up for him in
        the piece he is reading. Otherwise he sees them only where the mouse is."""
        self.page = page
        self.reveal_hover = reveal_hover
        self.vocab = vocabulary
        platform = config["platform"]
        self.harness = [platform["harness_selector"], platform["harness_button_text"]]
        global SESSION_PATH
        SESSION_PATH = platform.get("session_path", SESSION_PATH)
        self.settle_ms = platform["settle_ms"]
        self.max_rounds = config["words"]["max_rewrite_rounds"]
        self._cache: dict[str, Any] = {}
        self.show = show
        self._gray: list[str] = []
        self.watch_pause_ms = config["watch"]["pause_ms"]
        self.watch_move_ms = config["watch"]["move_ms"]
        # Perception and states set by the run (engine-design.md 4.9); the defaults change nothing.
        self.vision_px = 0.0  # text smaller than this he cannot read
        self.color = "typical"
        self.hide_warnings = False  # this step he does not notice warning text
        # The product's own marks, or the flow's locators put on the page (engine-design.md 6.3).
        self.locators = (config.get("workflow") or {}).get("locators") or []
        self.marks: dict[str, Any] = {}  # this look's mark report: item -> how many found, and how
        self.strip = strip
        self.page_height = platform["viewport_height"] - (strip.height if strip else 0)
        # Any web product (engine-design.md 6.3): a page that polls never goes network-idle, so
        # web targets wait until the page stops changing instead; Version A keeps its timing.
        self.quiet = (config.get("workflow") or {}).get("target", {}).get("kind") == "web"
        self.tabs: list = []  # pages he came from when a click opened a new tab
        self.downloads: list[str] = []  # files the product gave him to save
        self.download_dir: Path | None = None
        self.files = sample_files((config.get("workflow") or {}).get("files") or [])
        self._frames_now: list = []
        self._counts: list[int] = []
        self._scroll: dict[str, int] = {}
        self._canvas: dict[str, Any] = {}  # this look's text read off a canvas (vision.py)
        self.vision_note = ""  # why the canvas could not be read, when it could not
        self._watch(page)

    # ---- the page, its frames and its tabs ----------------------------------------------

    def _watch(self, page) -> None:
        """A file the product asks for is the task's sample file, picked as a person picks theirs;
        a file it gives him is saved, so a check can see it."""
        page.on("filechooser", self._choose_file)
        page.on("download", self._download)

    def _choose_file(self, chooser) -> None:
        try:
            accept = (chooser.element.get_attribute("accept") or "").lower()
        except Exception:  # noqa: BLE001
            accept = ""
        wanted = [f for f in self.files if not accept or any(a.strip() and (f.suffix.lower() == a.strip() or a.strip().endswith("/*")
                  and a.strip().split("/")[0] in MIME_GROUPS.get(f.suffix.lower(), "")) for a in accept.split(","))]
        chooser.set_files([str(f) for f in (wanted or self.files)[: (None if chooser.is_multiple() else 1)]])

    def _download(self, download) -> None:
        name = download.suggested_filename
        if self.download_dir:
            try:
                download.save_as(str(self.download_dir / name))
            except Exception:  # noqa: BLE001 - a download the product cancels is still recorded
                pass
        self.downloads.append(name)

    def _frames(self) -> list:
        """The page and every visible frame in it, with where each frame sits in the window.
        Embedded frames (a payment form, a help widget) are read and rewritten like the page."""
        out = [(self.page.main_frame, 0.0, 0.0)]
        for f in self.page.frames[1:]:
            try:
                box = f.frame_element().bounding_box()
            except Exception:  # noqa: BLE001 - a frame that is going away
                continue
            if box and box["width"] > 2 and box["height"] > 2:
                out.append((f, box["x"], box["y"]))
        return out

    def _each(self, script: str, arg: Any = None, frames: list | None = None) -> list:
        """script run in every frame: [(frame index, x offset, y offset, result)]."""
        out = []
        for k, (f, ox, oy) in enumerate(frames if frames is not None else self._frames()):
            try:
                out.append((k, ox, oy, f.evaluate(script, arg)))
            except Exception:  # noqa: BLE001 - only the main frame must answer
                if k == 0:
                    raise
        return out

    def follow_tabs(self, before: list) -> str:
        """A click that opened a new tab takes him there, as it would a person."""
        new = [p for p in self.page.context.pages if p not in before and not p.is_closed()]
        if not new:
            return ""
        page = new[-1]
        try:
            page.wait_for_load_state("domcontentloaded", timeout=10000)
        except Exception:  # noqa: BLE001
            pass
        self.tabs.append(self.page)
        self.page = page
        self._watch(page)
        if self.show and hasattr(self.show, "attach"):
            self.show.attach(page)
        return " (it opened in a new tab)"

    def back_to_tab(self) -> bool:
        """The tab he is on closed itself, or he went back from its first page: he is on the tab he came from."""
        if not self.tabs:
            return False
        if not self.page.is_closed():
            self.page.close()
        self.page = self.tabs.pop()
        self.page.bring_to_front()
        if self.show and hasattr(self.show, "attach"):
            self.show.attach(self.page)
        return True

    def _rewrite(self, text: str):
        if text not in self._cache:
            self._cache[text] = self.vocab.rewrite(text)
        return self._cache[text]

    def _too_small(self, size: float | None) -> bool:
        return bool(self.vision_px) and (size or 0) > 0 and size < self.vision_px

    def settle(self) -> None:
        if self.page.is_closed():
            self.back_to_tab()
        if self.quiet:
            try:
                self.page.wait_for_load_state("networkidle", timeout=1500)
            except Exception:  # noqa: BLE001 - a page that keeps polling
                pass
            try:
                self.page.evaluate("() => window.__sue.quiet(300, 3000)")
            except Exception:  # noqa: BLE001 - the page is navigating
                self.page.wait_for_load_state("domcontentloaded")
            self.page.wait_for_timeout(min(self.settle_ms, 200))
            return
        try:
            self.page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:  # noqa: BLE001 - a page that keeps polling still gets its settle time
            pass
        self.page.wait_for_timeout(self.settle_ms)

    def _collect(self) -> list[dict[str, Any]]:
        """Every text node in every frame; self._counts says how many came from each, for _apply."""
        self._frames_now = self._frames()
        got = self._each("([s, b]) => window.__sue.collect(s, b)", self.harness, self._frames_now)
        self._counts = [len(r) for _, _, _, r in got]
        self._frames_now = [self._frames_now[k] for k, _, _, _ in got]
        return [n for _, _, _, r in got for n in r]

    def _apply(self, values: list) -> None:
        start = 0
        for (f, _, _), n in zip(self._frames_now, self._counts):
            try:
                f.evaluate("v => window.__sue.apply(v)", values[start:start + n])
            except Exception:  # noqa: BLE001 - checked again after the screenshot
                pass
            start += n

    def _all(self, script: str, arg: Any = None) -> None:
        self._each(script, arg, self._frames_now or None)

    def _mark(self) -> None:
        if self.locators:
            route = route_of(self.page.url)
            self.marks = {}
            for _, _, _, r in self._each("([l, r]) => window.__sue.mark(l, r)", [self.locators, route]):
                for k, v in (r or {}).items():
                    old = self.marks.get(k)
                    self.marks[k] = v if not old else {"n": old["n"] + v["n"], "how": old["how"] if old["n"] else v["how"]}

    def marks_all(self) -> set[str]:
        return {m for _, _, _, r in self._each("() => window.__sue.marks()") for m in r}

    def _expected(self, node: dict[str, Any]) -> str:
        if node["harness"]:
            return node["orig"]
        if self._too_small(node.get("size")):
            return unreadable(node["orig"])
        return self._rewrite(node["orig"]).text

    def _expanded(self) -> list[str]:
        return [x for _, _, _, r in self._each("([s, b]) => window.__sue.expanded(s, b)", self.harness) for x in r]

    def _elements(self) -> list[dict[str, Any]]:
        elements = []
        for k, ox, oy, found in self._each("([s, b]) => window.__sue.elements(s, b)", self.harness, self._frames_now or None):
            for e in found:
                e["frame"] = k
                if k:  # a frame's boxes are in the frame; the mouse needs them in the window
                    for b in (e["box"], e["region"], e["region"]["group"]):
                        b["x"], b["y"] = round(b["x"] + ox), round(b["y"] + oy)
                elements.append(e)
        elements.sort(key=lambda e: (e["box"]["y"], e["box"]["x"]))
        if self.strip:
            elements.append(self.strip.element(self.page_height))
        for i, e in enumerate(elements, 1):
            e["id"] = f"el_{i}"
            e["filled"] = _filled(e.pop("background"))
            if e["icon"] and not e["harness"]:  # an icon is read like a word: its name in his vocabulary
                e["original"], e["text"] = e["icon"], self._rewrite(e["icon"]).text
            if e.get("options") is not None:  # a native dropdown's options, as he reads them
                e["options"] = [self._rewrite(o).text for o in e["options"]]
            small = self._too_small((e.get("font") or {}).get("size"))
            e["understanding"] = [] if e["harness"] or small else understanding(self._rewrite(e["original"]).hits)
        return elements

    def observe(self, step: int, gray_icons: list[str], focus=None) -> Observation:
        """Rewrites the page, covers what he is not looking at, takes the screenshot,
        then checks nothing changed back. Retries a few rounds; gives up rather than
        send the model a leaky screenshot.

        focus(context, elements) returns the piece he is looking at, or None."""
        self._gray = list(gray_icons)
        self.settle()
        self.page.evaluate("r => window.__sue.focus(r)", None)
        for rounds in range(1, self.max_rounds + 1):
            unnoticed = [t for _, _, _, r in self._each("h => window.__sue.hideWarnings(h)", self.hide_warnings) for t in r]
            self._mark()
            nodes = self._collect()
            self._apply([None if n["harness"] else self._expected(n) for n in nodes])
            self._all("ids => window.__sue.grayIcons(ids)", gray_icons)
            elements = self._elements()
            elements += self._read_canvas(len(elements) + 1)
            piece = focus(context_of(self.page.url, self._expanded()), elements) if focus else None
            hidden = [e for e in (piece.elements if piece else elements) if e["hidden"]]
            shown = hidden if self.reveal_hover else []
            for k, (f, _, _) in enumerate(self._frames_now):
                try:
                    f.evaluate("ids => window.__sue.reveal(ids)", [e["index"] for e in shown if e.get("frame", 0) == k])
                except Exception:  # noqa: BLE001
                    pass
            for e in shown:
                e["hidden"] = False
            elements = [e for e in elements if not e["hidden"]]  # what he cannot see is not on his list
            if piece:
                piece.elements = [e for e in piece.elements if not e["hidden"]]
            self.page.evaluate("r => window.__sue.focus(r)", piece.rect if piece else None)
            if self.show and hasattr(self.show, "focus"):
                self.show.focus(piece.rect if piece else None)
            shot = self.page.screenshot()
            if self._canvas.get("replacements"):
                from .vision import paint
                shot = paint(shot, self._canvas["replacements"])
            if self.strip:
                shot = self.strip.compose(shot)
            after = self._collect()
            if all(n["cur"] == self._expected(n) for n in after):
                obs = self._build(step, color_filter(shot, self.color), after, rounds, gray_icons, elements, piece)
                obs.unnoticed = unnoticed
                return obs
            self.page.wait_for_timeout(self.settle_ms)
        raise RewriteError(f"step {step}: original words came back {self.max_rounds} times in a row")

    def _build(self, step, shot, nodes, rounds, gray_icons, elements, piece) -> Observation:
        visible = [n for n in nodes if n["visible"]]
        hits: list[Hit] = []
        for n in visible:
            if n["harness"]:
                hits.append(Hit(n["orig"].strip(), n["orig"].strip(), KNOW, "harness"))
            elif self._too_small(n.get("size")):
                hits += [Hit(w, fake(w), NONE, "vision") for w in tokens(n["orig"], LETTERS)]
            else:
                hits += self._rewrite(n["orig"]).hits
        for e in elements:  # icons have no text on the page; what they show counts like words
            if e["icon"] and not e["harness"]:
                hits += self._rewrite(e["icon"]).hits
        bar = self.strip.texts() if self.strip else []
        hits += [Hit(t, t, KNOW, "harness") for t in bar]
        hits += self._canvas.get("hits", [])
        bar = list(self._canvas.get("texts", [])) + bar
        route = route_of(self.page.url)
        form = "\u0002".join(r for _, _, _, r in self._each("() => window.__sue.formState()"))
        digest = hashlib.sha1(("\n".join(n["orig"] for n in nodes) + "\0" + form).encode("utf-8")).hexdigest()[:10]
        context = context_of(self.page.url, self._expanded())
        return Observation(
            step=step,
            route=route,
            context=context,
            signature=f"{context}|{digest}",
            screenshot=shot,
            elements=elements,
            visible_text="\n".join([n["cur"] for n in visible] + bar),
            hits=hits,
            explanations=[x for _, _, _, r in self._each("() => window.__sue.openExplanations()") for x in r],
            scroll=self._scroll_state(),
            rewrite_rounds=rounds,
            gray_icons=list(gray_icons),
            focus=piece,
        )

    def _scroll_state(self) -> dict[str, int]:
        self._scroll = self.page.evaluate("() => window.__sue.scrollState()")
        return self._scroll

    # ---- canvas: text with no DOM behind it (engine-design.md 6.3) ------------------------

    CANVAS_SHARE = 0.1  # a canvas this big a share of the window is read from the screenshot

    def _canvas_rects(self) -> list[dict[str, float]]:
        return self.page.evaluate(
            "s => [...document.querySelectorAll('canvas')].map(c => { const r = c.getBoundingClientRect();"
            " const x = Math.max(r.left, 0), y = Math.max(r.top, 0);"
            " return {x, y, w: Math.min(r.right, innerWidth) - x, h: Math.min(r.bottom, innerHeight) - y}; })"
            ".filter(r => r.w > 0 && r.h > 0 && r.w * r.h > innerWidth * innerHeight * s)", self.CANVAS_SHARE)

    def _read_canvas(self, first_id: int) -> list[dict[str, Any]]:
        """Text a canvas draws (a Figma prototype, a map, an editor): read from the screenshot,
        changed the way he reads it, and offered as places he can click. Painted into the
        screenshot after it is taken (observe)."""
        self._canvas = {}
        rects = self._canvas_rects()
        if not rects:
            return []
        from .vision import VisionUnavailable, read_text, words
        png = self.page.screenshot()
        inside = lambda b: any(r["x"] <= b[0] + b[2] / 2 <= r["x"] + r["w"] and r["y"] <= b[1] + b[3] / 2 <= r["y"] + r["h"]  # noqa: E731
                               for r in rects)
        try:
            lines = [t for t in read_text(png) if inside(t.box)]
        except VisionUnavailable as error:
            self.vision_note = str(error)
            return []
        replacements, hits, texts, out = [], [], [], []
        for w in words(lines, png):
            rw = self._rewrite(w.text)
            hits += rw.hits
            if rw.text != w.text:
                replacements.append((w.box, rw.text))
        for k, line in enumerate(lines):
            x, y, bw, bh = line.box
            box = {"x": x, "y": y, "w": bw, "h": bh}
            shown = self._rewrite(line.text).text
            texts.append(shown)
            out.append({"index": -1, "hidden": False, "tag": "canvas-text", "role": "", "type": "", "text": shown, "icon": "",
                        "original": line.text, "value": None, "checked": None, "disabled": False, "expanded": None,
                        "kl": None, "explains": None, "harness": False, "frame": 0, "canvas": True,
                        "region": {"id": -1, "kind": "main", **box, "group": {"id": -1, **box, "heading": ""}},
                        "box": box, "font": {"size": float(bh), "weight": "400", "color": ""}, "filled": False,
                        "id": f"el_{first_id + k}", "understanding": understanding(self._rewrite(line.text).hits)})
        self._canvas = {"replacements": replacements, "hits": hits, "texts": texts}
        return out

    # ---- step 7: act ----------------------------------------------------------

    def _handle(self, element: dict[str, Any]):
        """The element in its own frame, for what the mouse alone cannot do (a native dropdown)."""
        frames = self._frames_now or self._frames()
        f = frames[element.get("frame", 0)][0] if element.get("frame", 0) < len(frames) else self.page.main_frame
        return f.locator(f'[data-sue-i="{element["index"]}"]').first

    def perform(self, action: str, element: dict[str, Any] | None, value: Any,
                miss: tuple[float, float] | None = None) -> str:
        """Carries out one action with the mouse and keyboard, as a person would.
        Returns a short note for the log. miss: a near miss on a small target (engine-design.md
        4.9), how far from the element's centre the click lands."""
        page = self.page
        # Watch mode: after a click the page first renders its original words; the
        # dashboard keeps the last frame until they are rewritten (it never affected the
        # model, whose screenshots are taken and checked after rewriting).
        if element and element.get("virtual"):
            # The engine's own task bar (Strip): the click ends his test; the product never sees it.
            return f"clicked {element['id']} ({element['original']}, the test's own bar)"
        holds = bool(self.show) and action in ("click", "open_help", "select", "back")
        before = list(page.context.pages)
        if action in ("click", "open_help", "select", "type") and element:
            box = element["box"]
            x, y = box["x"] + box["w"] / 2, box["y"] + box["h"] / 2
            if miss and action in ("click", "select"):
                x, y = x + miss[0], y + miss[1]
            if self.show:
                self.show.move(x, y)  # the dashboard glides its pointer there
                page.wait_for_timeout(self.watch_move_ms)
            if holds:
                self.show.hold()
            page.evaluate("([x, y]) => window.__sue.labelForLog(x, y)", [x, y])  # platform logs the original name
            page.mouse.click(x, y)
            if self.show:
                self.show.click(x, y)
            try:
                page.evaluate("() => window.__sue.clearLabelForLog()")
            except Exception:  # noqa: BLE001 - the click may have replaced the page
                pass
        if action in ("click", "select") and element and miss:
            note = f"aimed at {element['id']} but the click landed {abs(round(miss[0] or miss[1]))}px off centre"
        elif action in ("click", "open_help", "select") and element:
            note = f"clicked {element['id']}"
        elif action == "type" and element:
            page.keyboard.press("Control+A")
            page.keyboard.type(str(value or ""), delay=70 if self.show else 0)
            note = f"typed {value!r} into {element['id']}"
        elif action == "scroll":
            dy = -600 if str(value).lower() in ("up", "-1") else 600
            if "cx" in self._scroll:  # the page scrolls inside a panel: the wheel goes over the panel
                page.mouse.move(self._scroll["cx"], self._scroll["cy"])
            page.mouse.wheel(0, dy)
            note = "scrolled up" if dy < 0 else "scrolled down"
        elif action == "back":
            if holds:
                self.show.hold()
            if page.go_back() is None and self.back_to_tab():
                note = "closed the tab and went back to the one before"
            else:
                note = "went back to the previous page"
        elif action == "choose" and element and element.get("options") is not None:
            # A native dropdown opens outside the page, so it is set the way the browser sets it.
            want = str(value or "").strip().lower()
            opts = [o.strip().lower() for o in element["options"]]
            i = opts.index(want) if want in opts else next((k for k, o in enumerate(opts) if want and want in o), None)
            if i is None:
                return f"not done: {value!r} is not one of the options of {element['id']}"
            self._handle(element).select_option(index=i)
            note = f"chose {element['options'][i]!r} in {element['id']}"
        elif action == "press":
            key = str(value or "").strip()
            if key not in KEYS:
                return f"not done: {key!r} is not a key the engine presses"
            if element and element.get("tag") in ("input", "textarea", "select"):
                self._handle(element).focus()
            page.keyboard.press(KEYS[key])
            note = f"pressed {key}" + (f" in {element['id']}" if element else "")
        elif action == "hover" and element:
            box = element["box"]
            page.mouse.move(box["x"] + box["w"] / 2, box["y"] + box["h"] / 2, steps=8)
            note = f"rested the mouse on {element['id']}"
        elif action == "drag" and element and isinstance(value, dict):
            a, b = element["box"], value["box"]
            page.mouse.move(a["x"] + a["w"] / 2, a["y"] + a["h"] / 2)
            page.mouse.down()
            page.mouse.move(b["x"] + b["w"] / 2, b["y"] + b["h"] / 2, steps=12)
            page.mouse.up()
            note = f"dragged {element['id']} onto {value['id']}"
        else:
            if holds:
                self.show.release()
            return f"not done: {action} has no element or is not supported"
        self.settle()
        note += self.follow_tabs(before)
        if self.show:
            self.refresh()  # the person watching sees the rewritten page, not the original flash
            page.wait_for_timeout(200)  # let the rewritten frame arrive before showing frames again
            self.show.release()
            page.wait_for_timeout(self.watch_pause_ms)  # time for a person to see the result
        return note

    def refresh(self) -> None:
        """Rewrites the page without a screenshot (watch mode only)."""
        self.page.evaluate("r => window.__sue.focus(r)", None)
        self._mark()
        nodes = self._collect()
        self._apply([None if n["harness"] else self._expected(n) for n in nodes])
        self._all("ids => window.__sue.grayIcons(ids)", self._gray)


# Keys a person presses (prompt.py): what he calls them, what the browser calls them.
KEYS = {"Enter": "Enter", "Tab": "Tab", "Escape": "Escape", "ArrowDown": "ArrowDown", "ArrowUp": "ArrowUp",
        "Space": "Space", "Backspace": "Backspace"}
MIME_GROUPS = {".png": "image", ".jpg": "image", ".jpeg": "image", ".gif": "image", ".pdf": "application", ".csv": "text",
               ".txt": "text", ".json": "application", ".mp4": "video"}
_SAMPLES: dict[str, bytes] = {
    ".txt": b"Sample file for a usability test.\n",
    ".csv": b"name,amount\nAtlas,1000\n",
    ".json": b'{"sample": true}\n',
    ".pdf": b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n",
}


def sample_files(named: list[str]) -> list[Path]:
    """The files a person in this task would upload: the workflow's own (engine.files), else one
    small sample of each common kind, so whatever the product accepts there is one to pick."""
    paths = [Path(f) for f in named if Path(f).is_file()]
    if paths:
        return paths
    folder = Path(tempfile.gettempdir()) / "sue-samples"
    folder.mkdir(exist_ok=True)
    out = []
    for ext, data in _SAMPLES.items():
        f = folder / f"sample{ext}"
        if not f.exists():
            f.write_bytes(data)
        out.append(f)
    png = folder / "sample.png"
    if not png.exists():
        from PIL import Image

        Image.new("RGB", (64, 64), (66, 133, 244)).save(png)
    return [png, *out]


def open_browser(playwright, config: dict[str, Any], headless: bool = True, strip: Strip | None = None,
                 state: str | None = None):
    """strip: the engine draws the task bar, so the product's page gets the window less its height.
    state: a saved sign-in (cookies and storage) to start from, for a product with single sign-on."""
    platform = config["platform"]
    browser = playwright.chromium.launch(headless=headless)
    context = browser.new_context(
        viewport={"width": platform["viewport_width"], "height": platform["viewport_height"] - (strip.height if strip else 0)},
        device_scale_factor=1, accept_downloads=True, storage_state=state,
    )
    context.add_init_script(path=str(PAGE_SCRIPT))
    return browser, context.new_page()
