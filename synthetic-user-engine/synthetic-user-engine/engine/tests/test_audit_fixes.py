"""The defects found by checking the engine against real sessions (2026-10-31)."""

import random

import pytest

from sue.attention import chunks
from sue.choose import Policy, decide, is_loop, score
from sue.completion import save_refused
from sue.evidence import SURE, Verdict
from sue.memory import SessionMemory
from sue.participant import engine_moves, person_moves, thing
from sue.screen import PAGE_SCRIPT, context_of, page_of, route_of
from sue.study import group, passed
from sue.target import json_check
from sue.variability import Traits, make
from sue.words import CommonWords, Vocabulary
from sue.workflow import problems

SURELY = [Verdict("word", "x", SURE, "")]


def el(text="OK", **more):
    region = more.pop("region", {"kind": "main"})
    return {"id": "el_1", "original": text, "text": text, "tag": "button", "role": "", "type": "",
            "box": {"x": 0, "y": 0, "w": 90, "h": 30}, "region": region, "harness": False, "expanded": None, **more}


def cand(action="click", purpose="advance", value=None):
    return {"action": action, "purpose": purpose, "value": value, "why": "", "evidence": []}


def test_the_page_is_kept_apart_from_the_route():
    url = "https://x.example/app/#budgets"
    assert route_of(url) == "/app/" and page_of(url) == "budgets"
    assert context_of(url, ["2 Scope"]) == "/app/|2 Scope|budgets"
    assert context_of(url, []).split("|")[0] == "/app/"
    assert page_of("https://x.example/app/#/members") == "" and context_of("https://x.example/app/", []) == "/app/|"


def test_going_round_is_a_loop_whatever_the_screen_says():
    assert is_loop([("a",)] * 6, 6)
    assert is_loop([("a",), ("b",)] * 3, 6)
    assert is_loop([("a",), ("b",), ("c",)] * 2, 6)
    assert not is_loop([("a",), ("b",)] * 2, 6)  # a real person changed a filter back and forth four times
    assert not is_loop([("a",), ("b",), ("c",), ("d",), ("a",), ("b",)], 6)


def test_a_filled_box_keeps_what_it_holds_and_an_empty_one_can_be_filled_again():
    memory, policy = SessionMemory(), Policy(risk="medium", check="medium")

    def typing(holding, value, place="/app/|3 Amount|budgets"):
        s = score(cand("type", value=value), el("Target amount", tag="input", value=holding), SURELY, "same screen")
        return s, decide([s], memory, policy, context="same screen", page="/app/", piece=[s.element], place=place)

    first, _ = typing("", "800")
    memory.record(first.key, 1)
    memory.type_in("/app/", "Target amount", "800")
    again, got = typing("", "800")  # a new empty form looks the same
    assert again.dropped is None and got.chosen is again
    assert typing("800", "$800")[0].dropped == "The box already holds this"
    assert typing("1000", "800")[0].dropped == "Already typed this here and changed it"
    assert typing("800", "1000")[0].dropped is None  # a real person changed their mind once
    assert typing("1000", "800", place="/app/||budgets")[0].dropped is None  # outside a form, a search box is searched again


def test_a_warning_on_screen_is_reason_enough_for_a_rough_checker_to_change_something():
    memory = SessionMemory()

    def fixing(warned):
        s = score(cand("click", purpose="fix"), el("Select time range"), SURELY, "same screen")
        decide([s], memory, Policy(risk="medium", check="low", warned=warned), context="same screen", page="/app/", piece=[s.element], sim=lambda e: 0)
        return s.dropped

    assert fixing(False) == "Rough form checker: changes only what literally matches the task"
    assert fixing(True) is None


def test_a_refused_save_lets_them_type_it_again():
    memory = SessionMemory()
    memory.type_in("/app/", "Target amount", "800")
    memory.save_refused()
    assert not memory.has_typed("/app/", "Target amount", "800")


def test_a_frame_button_tried_once_is_not_the_most_prominent_pick_again():
    memory, policy = SessionMemory(), Policy(risk="medium", check="medium", viewport=(1000, 800))
    avatar = el("A", region={"kind": "header"}, filled=True, id="el_1")
    menu = el("Reports", region={"kind": "nav"}, id="el_2")
    memory.record(score(cand(), avatar, [], "first screen").key, 1)
    got = decide([], memory, policy, context="other screen", piece=[avatar, menu])
    assert got.chosen.element is menu


def test_a_medium_checker_may_open_a_dropdown_they_can_read_but_not_flip_a_box_to_look():
    memory, policy = SessionMemory(), Policy(risk="medium", check="medium")
    closed = score(cand(purpose="check"), el("Select services", expanded=False, dropdown=True), SURELY, "s")
    section = score(cand(purpose="check"), el("3 Amount", expanded=False), SURELY, "s")
    decide([section], memory, policy, context="s", page="/app/", piece=[section.element])
    assert section.dropped == "Not a careful form checker; does not look into unclear things"
    box = score(cand(purpose="check"), el("Owners", type="checkbox", checked=True), SURELY, "s")
    memory.flip("/app/", "Owners")
    got = decide([closed, box], memory, policy, context="s", page="/app/", piece=[closed.element, box.element])
    assert got.chosen is closed
    careful = score(cand(purpose="check"), box.element, SURELY, "s")
    decide([careful], memory, Policy(risk="medium", check="high"), context="s", page="/app/", piece=[box.element])
    assert careful.dropped == "Already set this box; flipping it to look would undo it"


def test_an_opened_list_hanging_out_of_its_parent_is_inside_what_he_sees():
    region = {"id": 1, "kind": "popup", "x": 300, "y": 380, "w": 200, "h": 50, "group": None}
    option = el("Atlas", region=region, box={"x": 280, "y": 450, "w": 260, "h": 30})
    rect = chunks([option], ["popup"], (1000, 800))[0].rect
    assert rect["x"] == 280 and rect["x"] + rect["w"] == 540 and rect["y"] + rect["h"] >= 480


def test_a_refusal_takes_the_button_still_on_the_page_and_a_warning_he_saw():
    assert save_refused(True, ["Enter a valid amount."])
    assert not save_refused(True, []) and not save_refused(False, ["Alerts are off"])


def test_cancel_does_not_complete_the_task(config):
    assert not any(x.lower().startswith("cancel") for x in config["run"]["commit_labels"])


def test_only_targets_small_both_ways_can_be_missed():
    cfg = {"click_miss": {"low": 1.0}, "small_target_px": 24, "miss_gap_px": 4}
    var = make(Traits(click="low"), {"variability": cfg, "patience": {"limit": {}}}, 1)
    assert var.miss_offset({"box": {"x": 0, "y": 0, "w": 530, "h": 24}}) is None
    assert var.miss_offset({"original": "?", "box": {"x": 0, "y": 0, "w": 20, "h": 20}}) is not None


class _Reader:
    card_type = "normal"
    words = ()


def test_a_word_cut_off_is_read_as_the_word_it_begins():
    common = CommonWords({"discounts": 900, "use": 10}, 20000)
    v = Vocabulary(_Reader(), common, [], [], [])
    assert v.rewrite("use discou…").text == "use discou…"
    assert v.rewrite("use zzqqx…").text != "use zzqqx…"
    assert v.rewrite("use di…").text != "use di…"  # two letters say nothing


def test_both_sides_name_a_control_the_same_way():
    assert thing("▾ Atlas budget") == "atlas budget" and thing("3 Amount ⌄") == "3 amount"
    fields = ["3 Amount"]
    person = [{"type": "control_clicked", "payload": {"label": "3 Amount Specified amount · $800 ⌄"}}]
    assert person_moves(person, fields) == ["do 3 amount"]
    steps = [
        {"action": {"type": "click", "original": "3 Amount ⌄"}},
        {"action": {"type": "click", "original": "×", "aria": "Close dialog"}},
        {"action": {"type": "click", "original": "Name *", "tag": "input"}},  # changed nothing
        {"action": {"type": "click", "original": "Save", "misclick": True}},
        {"action": {"type": "click", "original": "I'm finished", "note": "clicked el_9 (I'm finished, the test's own bar)"}},
    ]
    assert engine_moves(steps, fields) == ["do 3 amount", "do close dialog"]


def test_a_pass_cannot_be_put_together_from_different_rows():
    rows = [{"amount": "800", "owners": False}, {"amount": "500", "owners": True}]
    check = {"where": {}, "row": "last", "expect": {"amount": "800"}}
    assert not json_check(rows, check)[0]
    assert json_check(rows, {"where": {}, "expect": {"amount": "800"}})[0]  # without it, any row


def test_a_run_passes_only_if_it_also_said_it_was_done():
    assert passed({"overall": True}, "completion_declared")
    assert not passed({"overall": True}, "step_limit") and not passed({"overall": False}, "completion_declared")


def test_a_run_the_tooling_broke_is_left_out_of_the_rates():
    run = lambda ok, stop: {"moves": ["a"], "passed": ok, "checks": {"c": ok}, "stop": stop}  # noqa: E731
    people = [{"moves": ["a"], "checks": {"c": True}, "runs": [run(True, "completion_declared"), run(False, "technical_error")]}]
    assert group(people)["passed"]["runs"] == 1.0


def test_commit_labels_are_checked():
    flow_problems = problems({"engine": {"labels": {"commit": "FINISH"}}})
    assert any("engine.labels.commit" in p for p in flow_problems)


@pytest.fixture(scope="module")
def page():
    sync = pytest.importorskip("playwright.sync_api")
    with sync.sync_playwright() as pw:
        try:
            browser = pw.chromium.launch()
        except Exception as error:  # noqa: BLE001
            pytest.skip(f"no browser: {error}")
        p = browser.new_page(viewport={"width": 800, "height": 300})
        yield p
        browser.close()


def load(page, html):
    page.set_content(html)
    page.evaluate(PAGE_SCRIPT.read_text(encoding="utf-8"))


def listed(page):
    return page.evaluate("() => window.__sue.elements('#none', null)")


def test_a_control_that_left_the_list_loses_its_number(page):
    load(page, '<button id="a">A</button><div style="height:900px"></div><button id="b">B</button>')
    listed(page)
    page.evaluate("() => window.scrollTo(0, 800)")
    got = listed(page)
    assert [e["text"] for e in got] == ["B"]
    assert page.evaluate("""() => [...document.querySelectorAll('[data-sue-i]')].map(e => e.id)""") == ["b"]


def test_a_control_cut_off_by_the_window_is_aimed_at_what_shows(page):
    load(page, '<button style="position:fixed;top:280px;height:40px">FINISH</button>')
    box = next(e for e in listed(page) if e["text"] == "FINISH")
    assert box["box"]["y"] + box["box"]["h"] > 300 and box["aim"]["y"] < 300


def test_a_control_scrolled_out_of_its_panel_is_not_listed(page):
    load(page, '<div style="height:100px;overflow:auto"><div style="height:400px"></div><button>Lost</button></div>')
    assert "Lost" not in [e["text"] for e in listed(page)]


def test_a_button_below_the_fold_is_still_on_the_page(page):
    load(page, '<div style="height:900px"></div><button>FINISH</button>')
    assert page.evaluate("() => window.__sue.controlShown('#none', null, 'finish')")
    assert not page.evaluate("() => window.__sue.controlShown('#none', null, 'cancel')")


def test_a_slip_onto_the_label_is_still_that_control(page):
    load(page, '<label style="display:block;width:300px"><input type="checkbox" id="c"> Owners</label><p>Other</p>')
    box = next(e for e in listed(page) if e["type"] == "checkbox")
    assert page.evaluate("([i, x, y]) => window.__sue.sameControlAt(i, x, y)", [box["index"], box["box"]["x"] + 40, box["box"]["y"] + 5])
    assert not page.evaluate("([i, x, y]) => window.__sue.sameControlAt(i, x, y)", [box["index"], 700, 250])


def test_a_scroll_inside_a_list_shows_in_the_stamp(page):
    load(page, '<div id="l" style="height:50px;overflow:auto"><div style="height:400px"></div></div>')
    before = page.evaluate("() => window.__sue.scrollStamp()")
    page.evaluate("() => { document.getElementById('l').scrollTop = 60; }")
    assert page.evaluate("() => window.__sue.scrollStamp()") != before


def test_a_new_form_forgets_the_last_one_but_not_the_frame():
    memory = SessionMemory()
    memory.record(("/app/|1 Define|budgets|abc", "next", "click", ""), 1)
    memory.record(("nav|None", "reports", "click", ""), 2)
    memory.record(("/app/||budgets|abc", "+ create budget", "click", ""), 3)
    memory.type_in("/app/", "Name", "Atlas")
    memory.new_form()
    assert len(memory.tried) == 2 and not memory.has_typed("/app/", "Name", "Atlas")


def test_a_medium_checker_takes_one_look_before_the_final_button():
    from sue.choose import ONE_LOOK
    memory, policy = SessionMemory(), Policy(risk="medium", check="medium", consequential=["FINISH"])
    finish = score(cand(), el("FINISH"), SURELY, "s")
    preview = score(cand(purpose="check"), el("Preview"), SURELY, "s")
    got = decide([finish, preview], memory, policy, context="s", page="/app/", piece=[finish.element, preview.element])
    assert got.rule == ONE_LOOK and got.chosen is preview
    memory.peeked.add("/app/")
    finish, preview = score(cand(), el("FINISH"), SURELY, "s"), score(cand(purpose="check"), el("Preview"), SURELY, "s")
    assert decide([finish, preview], memory, policy, context="s", page="/app/", piece=[finish.element]).chosen is finish


def test_what_they_learned_counts_as_understood():
    from sue.evidence import HALF, check_word
    from sue.persona import EVERYDAY
    from sue.words import Hit
    hit = Hit("Time range", "Time range", EVERYDAY, "item", "T05")
    assert check_word("Time range", [hit]).level == HALF
    assert check_word("Time range", [hit], learned={"T05"}).level == SURE


def test_task_bar_words_do_not_raise_how_the_product_reads():
    from sue.evidence import check_word
    from sue.persona import KNOW
    from sue.words import Hit
    assert check_word("services", [Hit("cloud services", "cloud services", KNOW, "harness")]).level == "void"


def test_product_names_and_task_words_are_read_and_a_fake_is_never_a_real_word():
    from sue.words import fake
    class Reader(_Reader):
        task = "configure the budget"
    v = Vocabulary(Reader(), CommonWords({"use": 10}, 20000), [], [], [])
    assert v.rewrite("BigQuery").text == "BigQuery" and v.rewrite("configure").text == "configure"
    real = fake("xylo")
    assert Vocabulary(Reader(), CommonWords({real.lower(): 5}, 20000), [], [], []).rewrite("xylo").text.lower() != real.lower()


def test_a_way_the_product_lacks_is_found_even_when_another_works():
    from types import SimpleNamespace
    from sue.completion import lacking_confirmation, missing_confirmation
    p = SimpleNamespace(goal={"confirmBy": ["toast", "test"], "productSignals": {"toast": True, "test": False}})
    assert missing_confirmation(p) == [] and lacking_confirmation(p) == ["test"]


def test_the_window_used_longest_is_the_one_they_get():
    from sue.participant import engine_window
    person = {"session": {"viewport": {"width": 100, "height": 200}}, "events": [
        {"type": "session_started", "clientTs": "2026-10-30T15:00:00.000Z", "payload": {"viewport": {"width": 100, "height": 200}}},
        {"type": "viewport_changed", "clientTs": "2026-10-30T15:00:06.000Z", "payload": {"width": 100, "height": 150}},
        {"type": "control_clicked", "clientTs": "2026-10-30T15:07:00.000Z", "payload": {}},
    ]}
    assert engine_window(person) == "100x206"


def test_deleting_a_saved_row_is_not_removing_a_default():
    from sue.choose import removes_default
    memory = SessionMemory()
    assert not removes_default(el("Delete"), memory, "/app/||budgets")
    assert removes_default(el("Remove threshold 2"), memory, "/app/|4 Actions|budgets")


def test_a_dropdown_is_named_without_its_options_and_closed_text_is_not_visible(page):
    load(page, '<label>Projects <select><option>All</option><option>Atlas</option></select></label><details><summary>More</summary><p>Hidden help</p></details>')
    box = next(e for e in listed(page) if e["tag"] == "select")
    assert box["text"] == "Projects" and "All" in box["original"] and box["optionNames"] == ["All", "Atlas"]
    nodes = page.evaluate("() => window.__sue.collect('#none', null)")
    assert not next(n for n in nodes if "Hidden help" in n["orig"])["visible"]


def test_the_row_saved_last_is_graded_even_when_an_older_row_was_edited():
    edited = {"id": "a", "amount": "800"}
    rows = [edited, {"id": "b", "amount": "500"}]
    check = {"where": {}, "row": "last", "expect": {"amount": "800"}}
    assert json_check(rows, check, edited)[0]
    assert not json_check(rows, check)[0]
    assert not json_check(rows, check, {"id": "gone", "amount": "800"})[0]  # deleted since: the final row


def test_counting_draws_changes_no_number():
    from sue.variability import CountingRandom
    plain, counted = random.Random(7), CountingRandom(7)
    assert [plain.random() for _ in range(3)] == [counted.random() for _ in range(3)]
    assert [plain.randrange(9) for _ in range(5)] == [counted.randrange(9) for _ in range(5)]
    assert plain.choice("abcd") == counted.choice("abcd")
    assert counted.draws >= 8 and CountingRandom(1).draws == 0


def test_a_card_with_no_draws_is_reported_as_one_sample():
    from sue.study import draws_note
    assert draws_note([{"draws": 0}, {"draws": 0}]).startswith("none")
    assert draws_note([{"draws": 3}, {"draws": 9}]) == "3 to 9"


def test_a_card_run_gets_the_page_its_person_saw(tmp_path):
    import json
    from types import SimpleNamespace
    from sue.batch import set_window
    (tmp_path / "seen.json").write_text(json.dumps({"persona": {"window": {"width": 1512, "height": 681}}}), encoding="utf-8")
    (tmp_path / "plain.json").write_text(json.dumps({"persona": {}}), encoding="utf-8")
    config = {"platform": {"viewport_width": 1440, "viewport_height": 900}, "paths": {"personas": tmp_path}}
    web = SimpleNamespace(harness="strip")
    set_window(config, web, "seen")
    assert (config["platform"]["viewport_width"], config["platform"]["viewport_height"]) == (1512, 737)
    set_window(config, web, "plain")
    assert (config["platform"]["viewport_width"], config["platform"]["viewport_height"]) == (1440, 900)


def test_a_field_that_opens_a_list_is_a_dropdown_and_a_folding_section_is_not(page):
    load(page, '<div><label>Time</label><button aria-expanded="false">Select</button></div><section><button aria-expanded="false">3 Amount</button></section>')
    got = {e["text"]: e["dropdown"] for e in listed(page) if e["tag"] == "button"}
    assert got == {"Select": True, "3 Amount": False}


def test_a_box_set_on_purpose_stays_until_a_new_form():
    memory, policy = SessionMemory(), Policy(risk="medium", check="medium")
    box = el("Owners", type="checkbox", checked=True)
    memory.settle("/app/", "Owners")
    for _ in range(3):  # correcting a slip is allowed, going back and forth is not
        memory.flip("/app/", "Owners")
    undo = score(cand(purpose="fix"), box, SURELY, "s")
    decide([undo], memory, policy, context="s", page="/app/", piece=[box])
    assert undo.dropped == "Set this box on purpose; leaves it"
    memory.new_form()
    again = score(cand(purpose="fix"), box, SURELY, "s")
    decide([again], memory, policy, context="s", page="/app/", piece=[box])
    assert again.dropped is None


def test_only_an_open_list_holds_what_is_ticked_not_an_open_section():
    from sue.choose import list_is_open
    assert list_is_open([el("Select services", expanded=True, dropdown=True), el("Select all")])
    assert not list_is_open([el("4 Actions", expanded=True, dropdown=False), el("Owners")])
    assert not list_is_open([el("Select services", expanded=False, dropdown=True)])


def test_the_one_look_is_at_a_button_not_a_folding_section():
    from sue.choose import ONE_LOOK
    memory, policy = SessionMemory(), Policy(risk="medium", check="medium", consequential=["FINISH"])
    finish = score(cand(), el("FINISH"), SURELY, "s")
    section = score(cand(purpose="check"), el("1 Define", expanded=False), SURELY, "s")
    got = decide([finish, section], memory, policy, context="s", page="/app/", piece=[finish.element, section.element])
    assert got.rule != ONE_LOOK and got.chosen is finish


def test_a_ticked_box_is_a_move_and_a_click_that_changes_nothing_is_not():
    steps = [
        {"signature": "a", "action": {"type": "click", "original": "Select all", "tag": "input"}},
        {"signature": "b", "action": {"type": "click", "original": "Name *", "tag": "input"}},
        {"signature": "b", "action": {"type": "click", "original": "OK", "tag": "button"}},
    ]
    assert engine_moves(steps) == ["do select all", "do ok"]


def test_a_person_sure_of_the_way_takes_the_best_and_one_who_is_not_spreads_out():
    from sue.choose import draw
    best, other = score({**cand(), "hope": 9}, el("Budgets"), SURELY, "s"), score({**cand(), "hope": 5}, el("Billing"), SURELY, "s")
    share = lambda spread: sum(draw([best, other], spread, rng) is other for rng in [random.Random(1)] for _ in range(4000)) / 4000  # noqa: E731
    assert share(0.5) < 0.01
    assert 0.25 < share(5.0) < 0.45


def test_looking_elsewhere_competes_with_the_task_when_choosing_by_hope():
    move = score({**cand(), "hope": 6}, el("Set up"), SURELY, "s")
    wander = score({**cand(purpose="explore"), "hope": 6}, el("Reports"), SURELY, "s")
    rng = random.Random(3)
    got = {decide([score(move.candidate, move.element, SURELY, "s"), score(wander.candidate, wander.element, SURELY, "s")],
                  SessionMemory(), Policy(risk="medium", check="medium", spread=5.0, rng=rng), context="s", page="/a", piece=[move.element]).chosen.element["text"]
           for _ in range(60)}
    assert got == {"Set up", "Reports"}
    # the way a v2 card always chose: the task first, whatever the draw
    assert decide([score(move.candidate, move.element, SURELY, "s"), score(wander.candidate, wander.element, SURELY, "s")],
                  SessionMemory(), Policy(risk="medium", check="medium"), context="s", page="/a", piece=[move.element]).chosen.element["text"] == "Set up"


def test_the_final_button_still_waits_however_hopeful():
    finish = score({**cand(), "hope": 10}, el("FINISH"), SURELY, "s")
    other = score({**cand(), "hope": 1}, el("Reports"), SURELY, "s")
    for seed in range(30):
        got = decide([score(finish.candidate, finish.element, SURELY, "s"), score(other.candidate, other.element, SURELY, "s")], SessionMemory(),
                     Policy(risk="medium", check="low", consequential=["FINISH"], spread=5.0, rng=random.Random(seed)), context="s", page="/a", piece=[finish.element])
        assert got.chosen.element["text"] == "Reports"


def test_a_tried_move_fades_from_memory():
    memory = SessionMemory()
    key = ("s", "reports", "click", "")
    recalled = 0
    for seed in range(400):
        memory.tried[key] = 1
        recalled += memory.still_remembers(key, 13, 12, random.Random(seed))
    assert 120 < recalled < 180  # about 1 in 3 after one span
    memory.tried[key] = 1
    assert memory.still_remembers(key, 1000, None, None)  # no span: nothing fades


def test_how_unsure_comes_from_knowing_where_things_are_and_from_daring():
    cfg = {"variability": {"fatigue_max_drop": 4, "pressure_risk_gain": 3, "pressure_find_drop": 3, "pressure_check_drop": 3, "fatigue_horizon": 30},
           "patience": {"limit": {}}, "choice": {"daring_weight": 0.5, "spread_sure": 0.5, "spread_unsure": 5.0, "read_on": 0.5, "look_after": 0.5}}
    calm, bold = make(Traits(risk=5.0), cfg, 1), make(Traits(risk=10.0), cfg, 1)
    assert calm.unsure(1.0) == 0 and calm.unsure(0.0) == 1
    assert bold.unsure(1.0) == 0.5
    assert calm.spread(0.0) == 0.5 and calm.spread(1.0) == 5.0


def test_a_session_has_a_shape_whatever_its_path():
    from sue.study import shape
    assert shape(["do a", "do + create budget", "do a"], ["+ CREATE BUDGET"]) == {"moves": 3, "before the task": 1, "repeats": 1}


def test_steps_between_groups_are_compared_0_to_1():
    from sue.study import step_distance
    a = [["x", "y", "z"]]
    assert step_distance(a, a) == 0
    assert step_distance(a, [["p", "q", "r"]]) == 1


def test_another_real_person_is_the_mark_to_beat():
    from sue.study import strangers
    people = [{"name": "A", "moves": ["do a", "do b"]}, {"name": "B", "moves": ["do a", "do c"]}]
    assert strangers(people)["A"]["content"] == 0.5


def test_in_a_form_nothing_outranks_finishing_it_and_what_was_done_stays_done():
    finish = {**cand(), "hope": 9}
    away = {**cand(purpose="explore"), "hope": 2}
    for seed in range(30):
        policy = Policy(risk="medium", check="low", consequential=["FINISH"], spread=5.0, rng=random.Random(seed))
        got = decide([score(finish, el("FINISH"), SURELY, "s"), score(away, el("View report"), SURELY, "s")], SessionMemory(), policy,
                     context="s", page="/a", place="/a|4 Actions|budgets", piece=[el("FINISH")])
        assert got.chosen.element["text"] == "FINISH"
    memory = SessionMemory()
    done = score(cand(), el("Next one"), SURELY, "s")
    memory.record(done.key, 1)
    policy = Policy(risk="medium", check="low", spread=5.0, rng=random.Random(1), memory_span=1, now=500)
    decide([done], memory, policy, context="s", page="/a", place="/a|2 Scope|budgets", piece=[done.element])
    assert done.dropped == "Already tried on this screen"


def test_a_refused_save_lets_them_go_back_to_what_they_tried_in_the_form():
    memory = SessionMemory()
    memory.tried[("/app|2 Scope|budgets|abc", "Select projects")] = 3
    memory.tried[("/app||budgets|abc", "Billing")] = 1
    memory.save_refused()
    assert list(memory.tried) == [("/app||budgets|abc", "Billing")]


def test_a_box_the_page_put_back_is_not_settled():
    memory = SessionMemory()
    memory.settle("/app/", "Atlas", True)
    assert memory.is_settled("/app/", "Atlas", True)
    assert not memory.is_settled("/app/", "Atlas", False)


def test_someone_can_correct_their_own_slip_on_a_box_but_not_toggle_it_by_the_way():
    memory = SessionMemory()
    memory.settle("/app/", "Admins", True)
    memory.flip("/app/", "Admins")
    box = el("Admins", tag="input", type="checkbox", checked=True)

    def dropped(purpose):
        s = score(cand("click", purpose=purpose), dict(box), SURELY, "same screen")
        decide([s], memory, Policy(risk="medium", check="medium"), context="same screen", page="/app/", piece=[s.element])
        return s.dropped

    assert dropped("advance") == "Set this box on purpose; leaves it"
    assert dropped("fix") is None


def _at(text, y):
    return {**el(text), "box": {"x": 100, "y": y, "w": 80, "h": 20}}


def test_in_a_form_moves_about_as_good_go_down_the_page_and_a_much_better_one_comes_first():
    policy = Policy(risk="medium", check="low", spread=5.0, rng=random.Random(1), about_as_good=3)
    place = "/a|2 Scope|budgets"
    projects = score({**cand(), "hope": 8}, _at("Select projects", 200), SURELY, "s", place=place)
    time_range = score({**cand(), "hope": 7}, _at("Select time range", 100), SURELY, "s", place=place)
    services = score({**cand(), "hope": 6}, _at("Select services", 300), SURELY, "s", place=place)
    got = decide([projects, time_range, services], SessionMemory(), policy, context="s", page="/a", place=place, piece=[])
    assert got.chosen is time_range
    # A field already set, reopened only to look, does not hold them up though it is higher on the page.
    again = score({**cand(), "hope": 2}, _at("Monthly", 100), SURELY, "s", place=place)
    onward = score({**cand(), "hope": 8}, _at("Select projects", 200), SURELY, "s", place=place)
    got = decide([again, onward], SessionMemory(), policy, context="s", page="/a", place=place, piece=[])
    assert got.chosen is onward


def test_looking_around_does_not_fill_things_in_on_little_hope():
    policy = Policy(risk="medium", check="low", spread=5.0, rng=random.Random(1))
    rename = score({**cand(action="type"), "value": "Atlas", "hope": 4}, el("Account name"), SURELY, "s")
    decide([rename], SessionMemory(), policy, context="s", page="/a", piece=[])
    assert rename.dropped == "Came to look; does not change anything on so little hope"
    search = score({**cand(action="type"), "value": "budget", "hope": 7}, el("Search"), SURELY, "s")
    assert decide([search], SessionMemory(), policy, context="s", page="/a", piece=[]).chosen is search
    # A v2 card has no hope to go by.
    old = score({**cand(action="type"), "value": "Atlas", "hope": 1}, el("Account name"), SURELY, "s")
    assert decide([old], SessionMemory(), Policy(risk="medium", check="low"), context="s", page="/a", piece=[]).chosen is old
