from sue.replay import (is_real_move, names_match, pick_target, reachable, replay_moves, row_values, saved_difference, summarise,
                        why_left_out)


def ev(kind, seq=1, **payload):
    return {"type": kind, "seq": seq, "payload": payload}


def ctl(x=0, y=0, w=10, h=10, offscreen=False, **more):
    return {"x": x, "y": y, "w": w, "h": h, "offscreen": offscreen, **more}


def test_repeats_stay_and_echoes_go():
    moves = replay_moves([
        ev("control_clicked", 1, label="Specified amount", x=1, y=2),
        ev("control_clicked", 2, label="Specified amount", x=1, y=40),
        ev("field_changed", 3, field="Target amount", **{"from": ""}, value="800"),
        ev("field_changed", 4, field="Target amount", **{"from": "800"}, value="800"),
        ev("scroll", 5, scrollY=10),
    ])
    assert [m["seq"] for m in moves] == [1, 2, 3]
    assert [m["kind"] for m in moves] == ["control", "control", "field"]


def test_enter_in_a_field_is_a_move_and_a_click_on_nothing_is_not():
    moves = replay_moves([
        ev("key_pressed", 1, key="Enter", field="Search", value="alert"),
        ev("key_pressed", 2, key="Enter", field=None, value=None),
        ev("click_no_effect", 3, x=5, y=6),
    ])
    assert [m["kind"] for m in moves] == ["enter", "nothing"]
    assert is_real_move(moves[0]) and not is_real_move(moves[1])


def test_a_page_change_with_no_click_is_the_browsers_back():
    moves = replay_moves([
        ev("control_clicked", 1, label="View report", x=1, y=2),
        ev("page_viewed", 2, route="#reports"),
        ev("scroll", 3, scrollY=9),
        ev("page_viewed", 4, route="#budgets"),
        ev("control_clicked", 5, label="+ CREATE BUDGET", x=1, y=2),
    ])
    assert [m["kind"] for m in moves] == ["control", "back", "control"]
    assert not is_real_move(moves[1])


def test_field_moves_know_how_their_rows_end_up():
    draft = {"amount": "800", "rules": [{"percent": 80, "trigger": "Actual"}, {"percent": 125, "trigger": "Forecasted"}]}
    assert row_values(draft) == {"percent of budget": ["80%", "125%"], "trigger on": ["Actual", "Forecasted"], "amount": ["$640", "$1000"]}
    moves = replay_moves([ev("field_changed", 1, field="Trigger on", **{"from": "Actual"}, value="Forecasted"),
                          ev("save_clicked", 2, draft=draft)])
    assert moves[0]["rows"] == ["Actual", "Forecasted"]


def test_names_ignore_case_dots_and_the_harness_cut():
    assert names_match("Budgets & caps ⋮", "Budgets &  caps")
    assert not names_match("Budgets", "Budgets & caps")
    long = "x" * 80
    assert names_match(long, long + " more")
    assert not names_match("", "")


def test_a_field_is_the_row_holding_the_old_value_that_ends_up_with_the_new():
    rows = [ctl(value="Actual", checked=None), ctl(value="Actual", checked=None), ctl(value="Forecasted", checked=None)]
    move = {"kind": "field", "from": "Actual", "value": "Forecasted", "rows": ["Forecasted", "Actual", "Forecasted"]}
    assert pick_target(rows, move)["row"] == 0
    move["rows"] = None
    assert pick_target(rows, move)["row"] == 1


def test_a_control_is_the_one_nearest_the_click_on_screen_first():
    rows = [ctl(x=0, y=0, tag="button"), ctl(x=0, y=100, tag="div"), ctl(x=0, y=900, tag="a", offscreen=True)]
    assert pick_target(rows, {"kind": "control", "x": 5, "y": 105})["tag"] == "div"
    assert pick_target(rows, {"kind": "control", "x": 5, "y": 905})["tag"] == "div"


def test_why_the_engines_list_leaves_something_out():
    base = {"offscreen": False, "clickable": True, "covered": None, "shown": True}
    assert why_left_out({**base, "offscreen": True}) == "offscreen"
    assert why_left_out({**base, "clickable": False}) == "not_clickable"
    assert why_left_out({**base, "covered": "div#overlay"}) == "covered"
    assert why_left_out(base) == "not_listed"


def test_saved_ignores_ids_and_the_harness_keys():
    one = {"mpsBudgets": [{"id": "a", "name": "x"}], "uat:study-session": "s"}
    assert saved_difference(one, {"mpsBudgets": [{"id": "b", "name": "x"}]}) == {}
    assert set(saved_difference(one, {"mpsBudgets": [{"id": "b", "name": "y"}]})) == {"mpsBudgets"}


def test_reachable_levels():
    assert reachable(5.0) == ["medium"]
    assert reachable(2.5) == ["low", "medium"]
    assert reachable(7.5) == ["medium", "high"]


def test_summary_counts_moves_not_clicks_on_nothing():
    rows = [
        {"kind": "nothing", "found": True},
        {"kind": "control", "found": True, "status": "found", "own_words": None, "unknown_words": ["Discounts"], "rules": {"blocked": True}, "names_same": False},
        {"kind": "field", "found": True, "status": "found", "own_words": {"level": "sure"}, "unknown_words": [], "rules": {"blocked": False}, "names_same": True, "took": False},
        {"kind": "control", "found": False, "status": "not_in_dom"},
        {"kind": "control", "found": False, "status": "covered"},
    ]
    s = summarise(rows, {})
    assert (s["moves"], s["found"], s["not_found"], s["not_found_real"], s["not_found_lost"]) == (4, 2, 2, 1, 1)
    assert (s["unreadable"], s["void"], s["blocked"], s["named_differently"], s["no_effect"], s["saved_equal"]) == (1, 1, 1, 1, 1, True)
