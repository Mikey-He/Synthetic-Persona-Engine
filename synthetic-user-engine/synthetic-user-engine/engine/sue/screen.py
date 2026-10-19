"""Steps 1 to 3 and 7: read the screen, rewrite it the way this person sees it, take the
screenshot, and carry out the chosen action (engine-design.md 4).

Code reads and changes the DOM here; the model never does. What leaves this module
for the model is the processed screenshot and the list of visible elements."""

from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .persona import EVERYDAY, KNOW, NONE, OTHER
from .words import Hit, Vocabulary, fake

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
    return re.sub(r"\d", "#", re.sub(r"[A-Za-z]+", lambda m: fake(m.group(0)), text))


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
    """The page's route without the session token, e.g. /billing/budgets/create?edit."""
    parsed = urlparse(url)
    path = re.sub(SESSION_PATH, "", parsed.path) or "/"
    query = sorted(parse_qs(parsed.query).keys())
    return path + ("?" + "&".join(query) if query else "")


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


class Screen:
    def __init__(self, page, vocabulary: Vocabulary, config: dict[str, Any], show=None, reveal_hover: bool = False):
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

    def _rewrite(self, text: str):
        if text not in self._cache:
            self._cache[text] = self.vocab.rewrite(text)
        return self._cache[text]

    def _too_small(self, size: float | None) -> bool:
        return bool(self.vision_px) and (size or 0) > 0 and size < self.vision_px

    def settle(self) -> None:
        try:
            self.page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:  # noqa: BLE001 - a page that keeps polling still gets its settle time
            pass
        self.page.wait_for_timeout(self.settle_ms)

    def _collect(self) -> list[dict[str, Any]]:
        return self.page.evaluate("([s, b]) => window.__sue.collect(s, b)", self.harness)

    def _expected(self, node: dict[str, Any]) -> str:
        if node["harness"]:
            return node["orig"]
        if self._too_small(node.get("size")):
            return unreadable(node["orig"])
        return self._rewrite(node["orig"]).text

    def _expanded(self) -> list[str]:
        return self.page.evaluate("([s, b]) => window.__sue.expanded(s, b)", self.harness)

    def _elements(self) -> list[dict[str, Any]]:
        elements = self.page.evaluate("([s, b]) => window.__sue.elements(s, b)", self.harness)
        elements.sort(key=lambda e: (e["box"]["y"], e["box"]["x"]))
        for i, e in enumerate(elements, 1):
            e["id"] = f"el_{i}"
            e["filled"] = _filled(e.pop("background"))
            if e["icon"] and not e["harness"]:  # an icon is read like a word: its name in his vocabulary
                e["original"], e["text"] = e["icon"], self._rewrite(e["icon"]).text
            small = self._too_small((e.get("font") or {}).get("size"))
            e["understanding"] = [] if e["harness"] or small else understanding(self._rewrite(e["original"]).hits)
        return elements

    def observe(self, step: int, gray_icons: list[str], focus=None) -> Observation:
        """Rewrites the page, covers what he is not looking at, takes the screenshot,
        then checks nothing changed back. Retries a few rounds; gives up rather than
        send the model a leaky screenshot.

        focus(context, elements) returns the piece he is looking at, or None."""
        self._gray = list(gray_icons)
        self.page.evaluate("r => window.__sue.focus(r)", None)
        self.settle()
        for rounds in range(1, self.max_rounds + 1):
            unnoticed = self.page.evaluate("h => window.__sue.hideWarnings(h)", self.hide_warnings)
            nodes = self._collect()
            self.page.evaluate("v => window.__sue.apply(v)", [None if n["harness"] else self._expected(n) for n in nodes])
            self.page.evaluate("ids => window.__sue.grayIcons(ids)", gray_icons)
            elements = self._elements()
            piece = focus(context_of(self.page.url, self._expanded()), elements) if focus else None
            hidden = [e for e in (piece.elements if piece else elements) if e["hidden"]]
            shown = hidden if self.reveal_hover else []
            self.page.evaluate("ids => window.__sue.reveal(ids)", [e["index"] for e in shown])
            for e in shown:
                e["hidden"] = False
            elements = [e for e in elements if not e["hidden"]]  # what he cannot see is not on his list
            if piece:
                piece.elements = [e for e in piece.elements if not e["hidden"]]
            self.page.evaluate("r => window.__sue.focus(r)", piece.rect if piece else None)
            shot = self.page.screenshot()
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
                hits += [Hit(w, fake(w), NONE, "vision") for w in re.findall(r"[A-Za-z]+", n["orig"])]
            else:
                hits += self._rewrite(n["orig"]).hits
        for e in elements:  # icons have no text on the page; what they show counts like words
            if e["icon"] and not e["harness"]:
                hits += self._rewrite(e["icon"]).hits
        route = route_of(self.page.url)
        form = self.page.evaluate("() => window.__sue.formState()")
        digest = hashlib.sha1(("\n".join(n["orig"] for n in nodes) + "\0" + form).encode("utf-8")).hexdigest()[:10]
        context = context_of(self.page.url, self._expanded())
        return Observation(
            step=step,
            route=route,
            context=context,
            signature=f"{context}|{digest}",
            screenshot=shot,
            elements=elements,
            visible_text="\n".join(n["cur"] for n in visible),
            hits=hits,
            explanations=self.page.evaluate("() => window.__sue.openExplanations()"),
            scroll=self.page.evaluate("() => window.__sue.scrollState()"),
            rewrite_rounds=rounds,
            gray_icons=list(gray_icons),
            focus=piece,
        )

    # ---- step 7: act ----------------------------------------------------------

    def perform(self, action: str, element: dict[str, Any] | None, value: Any,
                miss: tuple[float, float] | None = None) -> str:
        """Carries out one action with the mouse and keyboard, as a person would.
        Returns a short note for the log. miss: a near miss on a small target (engine-design.md
        4.9), how far from the element's centre the click lands."""
        page = self.page
        # Watch mode: after a click the page first renders its original words; the
        # dashboard keeps the last frame until they are rewritten (it never affected the
        # model, whose screenshots are taken and checked after rewriting).
        holds = bool(self.show) and action in ("click", "open_help", "select", "back")
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
            page.mouse.wheel(0, dy)
            note = "scrolled up" if dy < 0 else "scrolled down"
        elif action == "back":
            if holds:
                self.show.hold()
            page.go_back()
            note = "went back to the previous page"
        else:
            if holds:
                self.show.release()
            return f"not done: {action} has no element or is not supported"
        self.settle()
        if self.show:
            self.refresh()  # the person watching sees the rewritten page, not the original flash
            page.wait_for_timeout(200)  # let the rewritten frame arrive before showing frames again
            self.show.release()
            page.wait_for_timeout(self.watch_pause_ms)  # time for a person to see the result
        return note

    def refresh(self) -> None:
        """Rewrites the page without a screenshot (watch mode only)."""
        self.page.evaluate("r => window.__sue.focus(r)", None)
        nodes = self._collect()
        self.page.evaluate("v => window.__sue.apply(v)", [None if n["harness"] else self._expected(n) for n in nodes])
        self.page.evaluate("ids => window.__sue.grayIcons(ids)", self._gray)


def open_browser(playwright, config: dict[str, Any], headless: bool = True):
    platform = config["platform"]
    browser = playwright.chromium.launch(headless=headless)
    context = browser.new_context(
        viewport={"width": platform["viewport_width"], "height": platform["viewport_height"]},
        device_scale_factor=1,
    )
    context.add_init_script(path=str(PAGE_SCRIPT))
    return browser, context.new_page()
