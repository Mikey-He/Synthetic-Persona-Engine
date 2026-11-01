"""The measure of success: effort, time and repeats by part of the task."""

from sue.parts import AFTER, BEFORE, engine_parts, pass_bounds, person_parts, verdict


def event(kind, target=None, at=0, screen=None):
    return {"clientTs": f"2026-01-01T00:00:{at:02d}.000Z", "type": kind, "target": target, "payload": {"screen": screen} if screen else {}}


def test_a_person_is_cut_into_parts_and_typing_on_is_one_move():
    got = person_parts([event("control_clicked", "Billing", 0, "Welcome"), event("control_clicked", "Create", 10, "Budgets"),
                        event("field_changed", "Name", 20, "Form / Define"), event("field_changed", "Name", 30, "Form / Define"),
                        event("control_clicked", "OK", 40, "Form / Scope"), event("control_clicked", "OK", 44, "Form / Scope"),
                        event("save_succeeded", "x", 46, "Form / Scope"), event("control_clicked", "Home", 50, "Budgets")], ["Define", "Scope"])
    assert got["moves"] == {BEFORE: 2, "Define": 1, "Scope": 2, AFTER: 1}
    assert got["repeats"]["Scope"] == 1 and got["repeats"]["Define"] == 0
    assert got["seconds"][BEFORE] == 20


def step(text, section="", kind="click"):
    return {"signature": f"/app|{section}|budgets|x", "action": {"type": kind, "text": text}, "words_seen": 10}


def test_a_run_counts_after_the_last_final_button_as_after_the_save():
    got = engine_parts([step("Billing"), step("NEXT", "1 Define"), step("FINISH", "4 Actions"), step("Monthly", "2 Scope"),
                        step("FINISH", "4 Actions"), step("Home")], ["Define", "Scope", "Actions"], ["FINISH"])
    assert got["moves"] == {BEFORE: 1, "Define": 1, "Scope": 1, "Actions": 2, AFTER: 1}
    assert got["repeats"]["Actions"] == 1


def test_time_reads_a_place_once():
    once = engine_parts([step("A")], [], [])["seconds"][BEFORE]
    twice = engine_parts([step("A"), step("B")], [], [])["seconds"][BEFORE]
    assert twice < 2 * once


def test_bounds_come_from_the_people():
    low, high = pass_bounds(5, 6)
    assert 0.45 < low < 0.55 and 0.92 < high < 0.99
    people = [{"a": 8, "b": 2}, {"a": 6, "b": 4}, {"a": 7, "b": 3}]
    assert verdict(people, [[{"a": 7, "b": 3}]])["rows"]["a"]["inside"]
    assert not verdict(people, [[{"a": 1, "b": 9}]])["rows"]["a"]["inside"]


def test_a_failed_check_is_narrowed_to_the_part_of_the_field_that_failed():
    from sue.parts import wrong_parts
    success = [{"type": "storage", "key": "k", "row": "last", "expect": {"time": "Monthly", "owners": True}},
               {"type": "storage", "key": "k", "row": "last", "anyOf": [{"expect": {"amount": "1000"}, "includes": {"rules": [{"percent": 80}]}},
                                                                        {"expect": {"amount": "800"}, "includes": {"rules": [{"percent": 100}]}}]}]
    fields = {"time": "Scope", "owners": "Actions", "amount": "Amount", "rules": "Actions"}
    good = {"time": "Monthly", "owners": True, "amount": "800", "rules": [{"percent": 100}]}
    assert wrong_parts({"k": [good]}, success, fields) == set()
    assert wrong_parts({"k": [{**good, "time": "Yearly"}]}, success, fields) == {"Scope"}
    # the amount fits one alternative, so it is the rule that is wrong
    assert wrong_parts({"k": [{**good, "rules": [{"percent": 50}]}]}, success, fields) == {"Actions"}
    assert wrong_parts({}, success, fields) == set()


def test_agreement_is_over_every_two_parts_and_a_tie_counts_half():
    from sue.parts import pairs_agree
    assert pairs_agree({"a": 3, "b": 2, "c": 1}, {"a": 9, "b": 5, "c": 0}) == 1.0
    assert pairs_agree({"a": 3, "b": 2, "c": 1}, {"a": 0, "b": 5, "c": 9}) == 0.0
    assert pairs_agree({"a": 1, "b": 0}, {"a": 1, "b": 1}) == 0.5


def test_the_scorecard_sets_each_person_against_their_runs_and_another_person():
    from sue.parts import scorecard
    one = {"seconds": {"a": 8, "b": 2}, "moves": {"a": 8, "b": 2}, "repeats": {"a": 1, "b": 0}, "troubles": [("a", "went back", "")]}
    two = {"seconds": {"a": 2, "b": 8}, "moves": {"a": 2, "b": 8}, "repeats": {"a": 0, "b": 1}, "troubles": [("b", "went back", "")]}
    card = scorecard([one, two], [[one], [two]])
    assert card["each"][0]["own"] == 1.0 and card["each"][0]["stranger"] == 0.0
    assert card["people"]["trouble"]["a"] == 0.5
