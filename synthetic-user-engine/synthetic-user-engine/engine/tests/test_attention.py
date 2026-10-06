from sue.attention import Attention, chunks

VIEW = (1440, 900)
ORDER = ["popup", "main", "nav"]


def region(id, kind, x, y, w, h, group=None):
    r = {"id": id, "kind": kind, "x": x, "y": y, "w": w, "h": h}
    r["group"] = group or {"id": id, "x": x, "y": y, "w": w, "h": h}
    return r


NAV_TOP = region(1, "nav", 0, 136, 256, 764, {"id": 11, "x": 0, "y": 200, "w": 256, "h": 60})
NAV_COST = region(1, "nav", 0, 136, 256, 764, {"id": 12, "x": 0, "y": 280, "w": 256, "h": 160})
NAV_CONTROL = region(1, "nav", 0, 136, 256, 764, {"id": 13, "x": 0, "y": 460, "w": 256, "h": 80})
MAIN = region(2, "main", 256, 184, 1184, 716)
POPUP = region(3, "popup", 330, 500, 420, 200)


def el(id, y, r, x=20, harness=False):
    return {"id": id, "box": {"x": x, "y": y, "w": 100, "h": 30}, "region": r, "harness": harness, "original": id}


ELEMENTS = [
    el("finished", 10, None, harness=True),
    el("overview", 210, NAV_TOP),
    el("reports", 290, NAV_COST), el("cost table", 330, NAV_COST), el("cost breakdown", 370, NAV_COST),
    el("budgets", 470, NAV_CONTROL),
    el("create", 260, MAIN, x=400),
    el("ok", 650, POPUP, x=600), el("atlas", 560, POPUP, x=360),
]


def ids(parts):
    return [[e["id"] for e in c.elements] for c in parts]


def test_a_glance_takes_in_a_whole_opened_part_then_the_page_then_one_menu_group_at_a_time():
    parts = chunks(ELEMENTS, ORDER, VIEW)
    assert ids(parts) == [["atlas", "ok"], ["create"], ["overview"], ["reports", "cost table", "cost breakdown"], ["budgets"]]
    assert parts[0].rect["y"] <= 500 and parts[0].rect["h"] >= 200  # an opened part is read as a whole
    assert all(e["id"] != "finished" for c in parts for e in c.elements)  # the task bar is not part of reading


def test_someone_who_reads_the_whole_screen_takes_each_region_at_once():
    parts = chunks(ELEMENTS, ORDER, VIEW, by_group=False)
    assert ids(parts)[2] == ["overview", "reports", "cost table", "cost breakdown", "budgets"]


def test_attention_moves_on_then_takes_in_the_whole_screen():
    a = Attention(ORDER, VIEW)
    ctx = "/billing|"
    assert a.focus(ctx, ELEMENTS).index == 0
    for _ in range(4):
        what, note = a.advance(ctx, ELEMENTS)
        assert what == "look" and note.startswith("nothing to do in this piece")
    assert a.focus(ctx, ELEMENTS).index == 4
    assert a.advance(ctx, ELEMENTS) == ("look", "every piece looked at; now takes in the whole screen")
    assert a.focus(ctx, ELEMENTS) is None
    assert a.advance(ctx, ELEMENTS) is None  # nowhere further to look
    assert a.focus("/billing/budgets|", ELEMENTS).index == 0  # a new screen starts from the top


def test_reading_the_page_he_scrolls_on_instead_of_turning_to_the_menu():
    a = Attention(ORDER, VIEW)
    ctx = "/billing/budgets/create|Scope"
    a.advance(ctx, ELEMENTS, can_scroll=True)  # popup -> main: still the page
    assert a.focus(ctx, ELEMENTS).kind == "main"
    assert a.advance(ctx, ELEMENTS, can_scroll=True)[0] == "scroll"  # main -> menu would leave the page
    assert a.focus(ctx, ELEMENTS).index == 0  # reads from the top of what he now sees
    assert a.advance(ctx, ELEMENTS, can_scroll=False)[0] == "look"  # at the bottom: on to the next piece
