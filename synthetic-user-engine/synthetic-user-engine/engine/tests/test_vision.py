"""Text in the screenshot itself (sue/vision.py): OCR, word boxes, painting over words."""

import io
import sys

import pytest
from PIL import Image, ImageDraw, ImageFont

from sue import vision
from sue.vision import TextBox, VisionUnavailable

ENGLISH = "Reconcile the ledger before export"
CHINESE = "保存发票草稿"


def _font(names, size):
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return None


LATIN = _font(vision.LATIN_FONTS, 18)
CJK = _font(vision.CJK_FONTS, 18)


def _png(image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _image(png: bytes):
    return Image.open(io.BytesIO(png)).convert("RGB")


def _near(box, expected, tolerance=6):
    return all(abs(a - b) <= tolerance for a, b in zip(box, expected))


def _drawn(draw, xy, text, font, fill=(20, 20, 20)):
    """Draw text and return the box its ink covers, as x, y, w, h."""
    draw.text(xy, text, fill=fill, font=font)
    left, top, right, bottom = draw.textbbox(xy, text, font=font)
    return left, top, right - left, bottom - top


@pytest.fixture(scope="module")
def ocr():
    if LATIN is None:
        pytest.skip("no TrueType Latin font on this machine")
    try:
        vision._engine()
    except VisionUnavailable as e:
        pytest.skip(str(e))
    return vision.read_text


@pytest.fixture(scope="module")
def page():
    """A small white screen: an English sentence, a button to its right, a Chinese phrase below."""
    image = Image.new("RGB", (640, 240), "white")
    draw = ImageDraw.Draw(image)
    drawn = {ENGLISH: _drawn(draw, (30, 30), ENGLISH, LATIN), "Cancel": _drawn(draw, (420, 30), "Cancel", LATIN)}
    if CJK is not None:
        drawn[CHINESE] = _drawn(draw, (30, 120), CHINESE, CJK)
    return _png(image), drawn


@pytest.fixture(scope="module")
def lines(ocr, page):
    return ocr(page[0])


def test_importing_never_needs_the_backend():
    assert issubclass(VisionUnavailable, RuntimeError)
    assert callable(vision.read_text)


def test_it_reads_english_and_chinese_where_they_were_drawn(lines, page):
    found = {line.text: line for line in lines}
    for text, box in page[1].items():
        assert text in found, f"{text!r} not in {list(found)}"
        assert _near(found[text].box, box), (text, found[text].box, box)
        assert found[text].score >= 0.5


def test_lines_come_top_to_bottom_then_left_to_right(lines):
    texts = [line.text for line in lines]
    assert texts[:2] == [ENGLISH, "Cancel"]
    if CJK is not None:
        assert texts[2] == CHINESE


def test_a_blank_screen_has_no_text(ocr):
    assert ocr(_png(Image.new("RGB", (320, 160), "white"))) == []


def _true_span(text, word, x=30):
    """Where a word of the sentence drawn at x really is."""
    draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    start = text.index(word)
    return x + draw.textlength(text[:start], font=LATIN), x + draw.textlength(text[:start + len(word)], font=LATIN)


@pytest.mark.parametrize("with_image", [False, True])
def test_words_split_a_line_on_spaces_with_boxes_where_the_words_are(lines, page, with_image):
    line = next(line for line in lines if line.text == ENGLISH)
    found = vision.words([line], page[0] if with_image else None)
    assert [w.text for w in found] == ENGLISH.split()
    tolerance = 3 if with_image else 6  # the ink's gaps place words better than character widths
    for word in found:
        left, right = _true_span(ENGLISH, word.text)
        near = abs(word.box[0] - left) <= tolerance and abs(word.box[0] + word.box[2] - right) <= tolerance
        assert near, (word, left, right)
        assert word.box[1] == line.box[1] and word.box[3] == line.box[3]
    assert all(a.box[0] + a.box[2] <= b.box[0] for a, b in zip(found, found[1:]))


def test_spaces_ocr_dropped_come_back_from_the_gaps_in_the_ink(lines, page):
    line = next(line for line in lines if line.text == ENGLISH)
    squashed = TextBox("Reconcilethe ledgerbefore export", line.box, line.score)
    found = vision.words([squashed], page[0])
    assert [w.text for w in found] == ENGLISH.split()
    for word in found:
        left, right = _true_span(ENGLISH, word.text)
        assert abs(word.box[0] - left) <= 3 and abs(word.box[0] + word.box[2] - right) <= 3


def test_chinese_runs_stay_whole_and_split_from_latin_words():
    line = TextBox("Invoice未付款total 草稿", (0, 0, 200, 20), 0.9)
    found = vision.words([line])
    assert [w.text for w in found] == ["Invoice", "未付款", "total", "草稿"]
    assert all(a.box[0] + a.box[2] <= b.box[0] + 1 for a, b in zip(found, found[1:]))
    assert abs(found[-1].box[0] + found[-1].box[2] - 200) <= 1


def test_span_cuts_a_term_out_of_a_chinese_run():
    line = TextBox(CHINESE, (100, 10, 120, 20), 0.9)
    part = vision.span(line, 2, 4)
    assert part.text == "发票" and part.box == (140, 10, 40, 20)


def test_paint_puts_a_made_up_word_where_the_word_was(ocr, lines, page):
    ledger = next(w for w in vision.words(lines, page[0]) if w.text == "ledger")
    out = vision.paint(page[0], [(ledger.box, "pembor")])
    after = " ".join(line.text for line in ocr(out))
    assert "ledger" not in after
    assert "pembor" in after
    # OCR sometimes drops the spaces around a word; the words either side must still be there.
    assert "Reconcilethepemborbeforeexport" in after.replace(" ", "") and "Cancel" in after


def test_paint_replaces_chinese_with_chinese(ocr, lines, page):
    if CJK is None:
        pytest.skip("no CJK font on this machine")
    run = next(w for w in vision.words(lines) if w.text == CHINESE)
    after = " ".join(line.text for line in ocr(vision.paint(page[0], [(run.box, "无知词组合")])))
    assert CHINESE not in after and "发票" not in after
    assert "无知词组合" in after


def test_paint_keeps_the_button_colour_and_the_text_colour():
    if LATIN is None:
        pytest.skip("no TrueType Latin font on this machine")
    image = Image.new("RGB", (300, 80), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle([10, 10, 250, 60], fill=(11, 87, 208))
    box = _drawn(draw, (30, 24), "Submit", LATIN, fill=(255, 255, 255))
    out = _image(vision.paint(_png(image), [(box, "Zamlet")]))
    x, y, w, h = box
    colours = {out.getpixel((i, j)) for i in range(x - 1, x + w + 1) for j in range(y - 1, y + h + 1)}
    assert (11, 87, 208) in colours and (255, 255, 255) in colours  # blue cover, white letters
    assert out.getpixel((15, 15)) == (11, 87, 208) and out.getpixel((5, 5)) == (255, 255, 255)
    assert _image(vision.paint(_png(image), [])) == image


def test_cover_grays_a_region_with_rounded_corners():
    image = Image.new("RGB", (100, 100), (255, 255, 255))
    out = _image(vision.cover(_png(image), [(20, 30, 40, 24)]))
    assert out.getpixel((40, 42)) == (200, 200, 200)
    assert out.getpixel((21, 31)) == (200, 200, 200)
    assert out.getpixel((20, 30)) != (200, 200, 200)  # the corner is rounded off
    assert out.getpixel((19, 42)) == (255, 255, 255) and out.getpixel((60, 42)) == (255, 255, 255)
    assert _image(vision.cover(_png(image), [(0, 0, 10, 10)], colour=(90, 90, 90))).getpixel((5, 5)) == (90, 90, 90)


def test_a_missing_backend_raises_vision_unavailable(monkeypatch):
    monkeypatch.setitem(sys.modules, "rapidocr_onnxruntime", None)
    monkeypatch.setitem(sys.modules, "rapidocr", None)
    vision._engine.cache_clear()
    try:
        with pytest.raises(VisionUnavailable, match="rapidocr-onnxruntime"):
            vision.read_text(_png(Image.new("RGB", (64, 64), "white")))
    finally:
        vision._engine.cache_clear()  # the next caller loads the real backend again
