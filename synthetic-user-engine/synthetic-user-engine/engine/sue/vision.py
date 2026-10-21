"""Text found in the screenshot itself, for screens that draw their text on a canvas.

Normally the words a person cannot understand are changed in the page's DOM before the
screenshot is taken (screen.py). A Figma prototype, a map, a chart tool or a design editor
paints its text on a <canvas>, so there is no DOM text to change. For those, code reads
the text in the screenshot with OCR, works out where each word sits, and paints over it:
the background colour first, then the made-up word in the text's own colour.

The OCR model (RapidOCR, PaddleOCR's models on onnxruntime) reads English and Chinese,
runs offline on the CPU and is loaded on first use. Importing this module never needs it."""

from __future__ import annotations

import io
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

Box = tuple[int, int, int, int]  # x, y, w, h in screenshot pixels

LATIN_FONTS = ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf", "Helvetica.ttc")
CJK_FONTS = ("msyh.ttc", "msyh.ttf", "simsun.ttc", "simhei.ttf", "NotoSansCJK-Regular.ttc",
             "NotoSansCJKsc-Regular.otf", "wqy-microhei.ttc", "PingFang.ttc", "Hiragino Sans GB.ttc")

MAX_SQUEEZE = 1.25  # a replacement up to this much wider than the box is squeezed, not made smaller

# Chinese, Japanese and Korean characters, their punctuation and full-width forms.
_CJK = re.compile(r"[\u2e80-\u9fff\uf900-\ufaff\uac00-\ud7af\u3000-\u303f\uff00-\uffef]")
# A word: a run of CJK characters, or Latin text between spaces.
_TOKEN = re.compile(r"[\u2e80-\u9fff\uf900-\ufaff\uac00-\ud7af]+|[^\s\u2e80-\u9fff\uf900-\ufaff\uac00-\ud7af]+")


class VisionUnavailable(RuntimeError):
    """The OCR backend is not installed or would not load."""


@dataclass(frozen=True)
class TextBox:
    text: str
    box: Box
    score: float


# --- reading -------------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _engine():
    """The OCR engine, loaded once. rapidocr-onnxruntime first, the newer rapidocr package second."""
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        try:
            from rapidocr import RapidOCR
        except ImportError as e:
            raise VisionUnavailable("No OCR backend: pip install rapidocr-onnxruntime "
                                    "(engine/requirements.txt)") from e
    try:
        engine = RapidOCR()
    except Exception as e:  # a broken model file or onnxruntime build
        raise VisionUnavailable(f"The OCR backend would not load: {e}") from e
    if hasattr(engine, "use_angle_cls"):
        engine.use_angle_cls = False  # screenshots are upright; the classifier only costs time
    return engine


def _ocr(png: bytes, min_score: float) -> list[tuple[list, str, float]]:
    """(corner points, text, score) for each line, whichever RapidOCR package is installed."""
    engine = _engine()
    try:
        out = engine(png, box_thresh=0.5, unclip_ratio=1.6, text_score=min_score)
    except TypeError:  # the rapidocr package takes its settings differently
        out = engine(png, use_cls=False, text_score=min_score)
    if isinstance(out, tuple):  # rapidocr-onnxruntime: (result or None, timings)
        return [(points, text, float(score)) for points, text, score in out[0] or []]
    if getattr(out, "boxes", None) is None:  # rapidocr: an output object
        return []
    return [(points.tolist(), text, float(score)) for points, text, score in zip(out.boxes, out.txts, out.scores)]


def _reading_order(lines: list[TextBox]) -> list[TextBox]:
    """Top to bottom; lines that share a row (overlap by half their height) left to right."""
    rows: list[list[TextBox]] = []
    for line in sorted(lines, key=lambda t: t.box[1] + t.box[3] / 2):
        x, y, w, h = line.box
        if rows:
            r = rows[-1][0].box
            overlap = min(y + h, r[1] + r[3]) - max(y, r[1])
            if overlap >= min(h, r[3]) / 2:
                rows[-1].append(line)
                continue
        rows.append([line])
    return [t for row in rows for t in sorted(row, key=lambda t: t.box[0])]


def read_text(png: bytes, min_score: float = 0.5) -> list[TextBox]:
    """Text lines in the screenshot, top to bottom, left to right."""
    lines = []
    for points, text, score in _ocr(png, min_score):
        text = text.strip()
        if not text or score < min_score:
            continue
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        x, y = int(min(xs)), int(min(ys))
        lines.append(TextBox(text, (x, y, int(round(max(xs))) - x, int(round(max(ys))) - y), score))
    return _reading_order(lines)


# --- words ---------------------------------------------------------------------------------

def _is_cjk(ch: str) -> bool:
    return bool(_CJK.match(ch))


@lru_cache(maxsize=4096)
def _advance(ch: str) -> float:
    """How wide a character is, in em: the font's own advance, or a rough guess without the font."""
    font = _font(ch, 100)
    try:
        return font.getlength(ch) / 100
    except Exception:
        pass
    if _is_cjk(ch) or unicodedata.east_asian_width(ch) in "WF":
        return 1.0
    return 0.3 if ch == " " else 0.55


def span(line: TextBox, start: int, end: int) -> TextBox:
    """The part of a line from character start to end, its box estimated from the
    characters' widths. OCR gives one box per line; a word's place in it is a share of it."""
    widths = [_advance(ch) for ch in line.text]
    total = sum(widths) or 1.0
    x, y, w, h = line.box
    left = x + w * sum(widths[:start]) / total
    right = x + w * sum(widths[:end]) / total
    return TextBox(line.text[start:end], (int(round(left)), y, max(1, int(round(right - left))), h), line.score)


def words(lines: list[TextBox], png: bytes | None = None) -> list[TextBox]:
    """Word-level boxes. Latin text splits on spaces; Chinese, Japanese and Korean text has
    no spaces to split on, so each run of those characters is one box (span() cuts a term
    out of a run when code knows which characters it wants).

    With the screenshot, a Latin line's words are matched to the gaps in its ink: each box
    is where that word's letters are, and a space OCR dropped ("Reconcilethe ledger") is put
    back where the ink has a gap."""
    image = _open(png) if png else None
    out = []
    for line in lines:
        spans = [(m.start(), m.end()) for m in _TOKEN.finditer(line.text)]
        if image is None or any(_is_cjk(ch) for ch in line.text):
            out += [span(line, start, end) for start, end in spans]
            continue
        out += _by_ink(image, line, spans)
    return out


def _by_ink(image, line: TextBox, spans: list[tuple[int, int]]) -> list[TextBox]:
    """A Latin line's words placed on its runs of ink (see words)."""
    x, y, w, h = _clip(line.box, image.size)
    runs = _runs(image, (x, y, w, h)) if w > 0 and h > 0 else []
    if len(runs) > len(spans) > 0:
        # More runs of ink than words: OCR dropped spaces. Split where the gaps fall.
        widths = [_advance(ch) for ch in line.text]
        left, right = runs[0][0], runs[-1][1]
        scale = (right - left) / (sum(widths) or 1.0)
        edges = [left + scale * sum(widths[:i]) for i in range(len(line.text) + 1)]
        cuts = set()
        for (_, end), (start, _) in zip(runs, runs[1:]):
            gap = (end + start) / 2
            cuts.add(min(range(1, len(line.text)), key=lambda i: abs(edges[i] - gap), default=0))
        spans = [(a, b) for start, end in spans
                 for a, b in zip([start] + sorted(c for c in cuts if start < c < end),
                                 sorted(c for c in cuts if start < c < end) + [end])]
    if len(runs) != len(spans):
        return [span(line, start, end) for start, end in spans]
    return [TextBox(line.text[start:end], (a, line.box[1], b - a + 1, line.box[3]), line.score)
            for (start, end), (a, b) in zip(spans, runs)]


# --- painting ------------------------------------------------------------------------------

def _open(png: bytes):
    from PIL import Image

    return Image.open(io.BytesIO(png)).convert("RGB")


def _png(image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _font(text: str, size: int):
    """A font that has the text's glyphs: a CJK font if any character needs one."""
    return _load_font(any(_is_cjk(ch) for ch in text), size)


@lru_cache(maxsize=128)
def _load_font(cjk: bool, size: int):
    from PIL import ImageFont

    for name in CJK_FONTS + LATIN_FONTS if cjk else LATIN_FONTS + CJK_FONTS:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _clip(box: Box, size: tuple[int, int]) -> Box:
    """The part of the box inside the screenshot."""
    x, y, w, h = (int(round(v)) for v in box)
    left, top = max(0, x), max(0, y)
    return left, top, min(size[0], x + w) - left, min(size[1], y + h) - top


def _background(image, box: Box) -> tuple[int, int, int]:
    """The most common colour in a 2 px ring just outside the box."""
    x, y, w, h = box
    W, H = image.size
    px = image.load()
    counts: dict[tuple[int, int, int], int] = {}
    for d in (2, 3):
        left, top, right, bottom = max(0, x - d), max(0, y - d), min(W - 1, x + w + d - 1), min(H - 1, y + h + d - 1)
        ring = [(i, top) for i in range(left, right + 1)] + [(i, bottom) for i in range(left, right + 1)]
        ring += [(left, j) for j in range(top, bottom + 1)] + [(right, j) for j in range(top, bottom + 1)]
        for p in ring:
            counts[px[p]] = counts.get(px[p], 0) + 1
    return max(counts, key=counts.get) if counts else (255, 255, 255)


@dataclass(frozen=True)
class _Ink:
    background: tuple[int, int, int]
    colour: tuple[int, int, int]
    top: int  # first row with ink, in screenshot pixels
    bottom: int  # last row with ink
    base: int  # last row of the letters' bodies: the baseline, with descenders left out


def _distances(image, box: Box):
    """How far each pixel in the box is from the background, row by row: (background, the
    box's pixels, their squared distances, the largest one)."""
    x, y, w, h = box
    background = _background(image, box)
    crop = image.crop((x, y, x + max(1, w), y + max(1, h)))
    pixels = list(crop.get_flattened_data() if hasattr(crop, "get_flattened_data") else crop.getdata())
    distance = [sum((a - b) ** 2 for a, b in zip(c, background)) for c in pixels]
    return background, pixels, distance, max(distance, default=0)


def _runs(image, box: Box) -> list[tuple[int, int]]:
    """The runs of ink across a line, as (first column, last column), split where the ink
    has a gap wider than a letter's: the line's words."""
    x, y, w, h = box
    _, _, distance, peak = _distances(image, box)
    if peak < 40 ** 2:
        return []
    inked = [any(distance[r * w + c] >= peak * 0.3 for r in range(h)) for c in range(w)]
    gap = max(3, round(h * 0.2))
    runs: list[list[int]] = []
    for c in (c for c in range(w) if inked[c]):
        if runs and c - runs[-1][1] <= gap:
            runs[-1][1] = c
        else:
            runs.append([c, c])
    return [(x + a, x + b) for a, b in runs]


def _ink(image, box: Box) -> _Ink:
    """The text in a box: its colour (among the pixels that differ most from the background,
    the glyph cores rather than their anti-aliased edges, the most common one) and the rows
    its glyphs fill."""
    x, y, w, h = box
    background, pixels, distance, peak = _distances(image, box)
    cw = max(1, w)
    if peak < 40 ** 2:  # nothing stands out: plain contrast against the background
        colour = (32, 33, 36) if sum(background) > 382 else (240, 240, 240)
        return _Ink(background, colour, y, y + h - 1, y + int(h * 0.8))
    counts: dict[tuple[int, int, int], int] = {}
    for c, d in zip(pixels, distance):
        if d >= peak * 0.6:
            counts[c] = counts.get(c, 0) + 1
    colour = max(counts, key=counts.get)
    rows = [sum(1 for d in distance[r * cw:(r + 1) * cw] if d >= peak * 0.3) for r in range(len(pixels) // cw)]
    inked = [r for r, n in enumerate(rows) if n]
    dense = [r for r, n in enumerate(rows) if n >= max(rows) * 0.3]
    return _Ink(background, colour, y + inked[0], y + inked[-1], y + dense[-1])


@lru_cache(maxsize=4)
def _reference(cjk: bool) -> tuple[float, float]:
    """How far a tall glyph reaches above the baseline and below it, in em: what the ink's
    height is measured against to find the original font size."""
    left, top, right, bottom = _load_font(cjk, 100).getbbox("国" if cjk else "Hd", anchor="ls")
    return -top / 100, max(0, bottom) / 100


def _fitted(text: str, ink: _Ink, box: Box):
    """The original text's font size, read from its ink, and its baseline. A made-up word
    a little wider than the box is squeezed to fit (see _draw); one much wider gets a
    smaller font first."""
    cjk = any(_is_cjk(ch) for ch in text)
    up, down = _reference(cjk)
    if cjk:
        size = (ink.bottom + 1 - ink.top) / (up + down)
    else:
        size = (ink.base + 1 - ink.top) / up
        size = max(size, box[3] * 0.8)  # a word without tall letters only shows its x-height
    size = max(6, int(round(size)))
    while size > 6 and _font(text, size).getlength(text) > (box[2] + 1) * MAX_SQUEEZE:
        size -= 1
    baseline = ink.bottom + 1 - down * size if cjk else ink.base + 1
    return _font(text, size), baseline


def _draw(image, x: int, baseline: float, width: int, text: str, font, colour) -> None:
    """Write the text from x on the baseline, squeezed sideways if it runs wider than width."""
    from PIL import Image, ImageDraw

    length = font.getlength(text)
    if length <= width + 1:
        ImageDraw.Draw(image).text((x, baseline), text, fill=colour, font=font, anchor="ls")
        return
    ascent, descent = font.getmetrics()
    layer = Image.new("L", (int(length) + 2, ascent + descent))
    ImageDraw.Draw(layer).text((0, ascent), text, fill=255, font=font, anchor="ls")
    layer = layer.resize((max(1, width), layer.height), Image.LANCZOS)
    image.paste(Image.new("RGB", layer.size, colour), (x, int(round(baseline)) - ascent), layer)


def paint(png: bytes, replacements: list[tuple[Box, str]]) -> bytes:
    """For each (box, text): cover the box in the colour just outside it, then write the
    text (a made-up word, usually) on the original's baseline, in its colour and at its
    size, squeezed or shrunk if it would run past the box."""
    from PIL import ImageDraw

    if not replacements:
        return png
    image = _open(png)
    replacements = [(box, text) for box, text in ((_clip(box, image.size), text) for box, text in replacements)
                    if box[2] > 0 and box[3] > 0]
    # Read every box before painting any, so one new word never colours another.
    inks = [_ink(image, box) for box, _ in replacements]
    draw = ImageDraw.Draw(image)
    for (box, text), ink in zip(replacements, inks):
        x, y, w, h = box
        draw.rectangle([x - 1, y - 1, x + w, y + h], fill=ink.background)
        if text.strip():
            font, baseline = _fitted(text, ink, box)
            _draw(image, x, baseline, w, text, font, ink.colour)
    return _png(image)


def cover(png: bytes, boxes: list[Box], colour: tuple[int, int, int] = (200, 200, 200)) -> bytes:
    """Grey blocks with 3 px rounded corners over the boxes (icons he does not recognise)."""
    from PIL import ImageDraw

    if not boxes:
        return png
    image = _open(png)
    draw = ImageDraw.Draw(image)
    for x, y, w, h in boxes:
        draw.rounded_rectangle([x, y, x + w - 1, y + h - 1], radius=3, fill=colour)
    return _png(image)
