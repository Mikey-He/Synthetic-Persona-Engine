"""The one mechanism (sue/mind.py): every behaviour here follows from the same value and chance."""

import random

from sue.mind import Move, Outlook, appraise, scan, settle

PARAMS = {"aspiration": 6.0, "aspiration_form": 2.5, "aspiration_find": 1.0, "noise_sure": 0.7, "noise_unsure": 2.5, "half_low": 0.3, "void_low": 0.0, "void_high": 0.5,
          "fix_floor": 0.5, "check_floor": 0.2, "explore_in_form": 0.2, "retreat": 0.6, "memory_span": 12, "change_floor": 5.0, "floor": 0.5, "doubt": 0.3, "look_changes": 0.3}


def outlook(**more):
    return Outlook(**{"risk": 5, "find": 5, "check": 5, "unsure": 0.0, "in_form": False, "saved": False, "params": PARAMS, **more})


def move(text, hope, y=0, level="sure", purpose="advance", action="click", **more):
    return Move({"action": action, "purpose": purpose, "hope": hope}, {"box": {"x": 0, "y": y}, "original": text}, level, (text,), [], **more)


def share_taken(make, o, tries=2000):
    rng, got = random.Random(1), 0
    for _ in range(tries):
        moves = make()
        for m in moves:
            appraise(m, o, None, 1)
        got += scan(moves, rng) is moves[0]
    return got / tries


def test_going_down_a_form_and_the_final_button_last_follow_from_reading_order():
    o = outlook(in_form=True)
    make = lambda: [move("Time range", 7, 100), move("Projects", 8, 200), move("FINISH", 9, 900, final=True)]  # noqa: E731
    assert share_taken(make, o) > 0.75  # the first good enough, though not the most hopeful


def test_someone_unsure_strays_to_what_looks_poor_and_someone_sure_does_not():
    make = lambda: [move("A link", 3, 100), move("The way", 9, 200)]  # noqa: E731
    assert share_taken(make, outlook(unsure=1.0)) > 0.1
    assert share_taken(make, outlook(unsure=0.0)) < 0.03


def test_what_was_done_in_a_form_stays_done_and_elsewhere_recovers():
    m = move("Next", 9)
    assert appraise(m, outlook(in_form=True), 5, 6) == 0
    assert 0 < appraise(m, outlook(), 5, 6) < appraise(m, outlook(), 5, 60)


def test_daring_decides_what_a_half_understood_move_is_worth_and_more_so_a_final_button():
    half = lambda **more: move("Alerts", 8, level="half", **more)  # noqa: E731
    assert appraise(half(), outlook(risk=0), None, 1) < appraise(half(), outlook(risk=10), None, 1) == 8
    assert appraise(half(final=True), outlook(risk=5), None, 1) < appraise(half(), outlook(risk=5), None, 1)


def test_what_they_cannot_read_goes_by_codes_word_overlap_not_the_models_hope():
    assert appraise(move("Xqz", 10, level="void"), outlook(risk=10), None, 1) == 0.5
    assert appraise(move("Xqz", 10, level="void", alike=2), outlook(risk=10), None, 1) == 1.5


def test_detail_when_checking_weighs_looks_and_corrections():
    check = lambda: move("Labels", 8, purpose="check")  # noqa: E731
    assert appraise(check(), outlook(check=0), None, 1) < appraise(check(), outlook(check=10), None, 1)
    fix = lambda: move("Row", 8, purpose="fix")  # noqa: E731
    assert appraise(fix(), outlook(check=0), None, 1) < appraise(fix(), outlook(check=10), None, 1)


def test_once_saved_they_change_nothing_and_looking_around_changes_no_value_on_little_hope():
    assert appraise(move("Save", 9), outlook(saved=True), None, 1) == 0
    assert appraise(move("Anomalies", 5, purpose="explore"), outlook(saved=True), None, 1) == 5
    assert appraise(move("Account name", 4, action="type"), outlook(), None, 1) == 0
    assert appraise(move("Name", 4, action="type"), outlook(in_form=True), None, 1) == 4


def test_doubt_takes_hope_off_only_outside_a_form_for_someone_unsure():
    assert appraise(move("The way", 9), outlook(unsure=1.0), None, 1) < appraise(move("The way", 9), outlook(), None, 1) == 9
    assert appraise(move("Field", 9), outlook(unsure=1.0, in_form=True), None, 1) == 9


def test_folding_a_section_is_leaving_it_and_a_look_that_ticks_a_box_is_not_just_a_look():
    fold = move("3 Amount", 8)
    fold.element["expanded"] = False
    assert appraise(fold, outlook(in_form=True), None, 1) == 8 * 0.2
    opens = move("Budget type", 8)
    opens.element.update(expanded=False, dropdown=True)
    assert appraise(opens, outlook(in_form=True), None, 1) == 8
    box = move("Admins", 8, purpose="check")
    box.element["type"] = "checkbox"
    assert appraise(box, outlook(in_form=True, check=10), None, 1) < appraise(move("Budget type", 8, purpose="check"), outlook(in_form=True, check=10), None, 1)


def test_read_everything_and_nothing_good_enough_takes_the_likeliest_or_nothing():
    o, rng = outlook(), random.Random(1)
    low, lower = move("A", 5), move("B", 0.2)
    for m in (low, lower):
        appraise(m, o, None, 1)
    assert settle([low, lower], o, rng) is low
    assert settle([lower], o, rng) is None
