from sue.compare import compare, moves

LABELS = ["Projects", "Budget type"]
IGNORE = ["page /", "click Close"]


def ev(kind, target="", **payload):
    return {"type": kind, "target": target, "payload": payload}


def test_events_become_moves_the_same_way_for_both_sides():
    events = [
        ev("page_viewed", route="/"),
        ev("page_viewed", route="/billing"),
        ev("control_clicked", label="Projects All projects (2)"),
        ev("control_clicked", label="Projects Atlas"),
        ev("field_changed", field="amount.target", newValue=1),
        ev("field_changed", field="amount.target", newValue=1000),
        ev("field_changed", field="thresholds.0.percent", newValue=80),
        ev("control_clicked", label="Close"),
        ev("field_changed", field="name", newValue="Atlas monthly"),
        ev("control_clicked", label="Atlas monthly"),
        ev("scroll"),
    ]
    assert moves(events, LABELS, IGNORE) == [
        "page /billing", "click Projects", "change amount.target", "change thresholds.percent", "change name",
        "click (the name they typed)",
    ]


def test_content_and_order():
    person = ["a", "b", "c", "b", "d"]
    engine = ["a", "c", "d", "e"]
    r = compare(person, engine)
    assert r["content"]["recall"] == 0.75 and r["content"]["precision"] == 0.75
    assert r["order"]["in_order"] == 3  # a, c, d
    assert r["first_touch_order"]["in_order"] == 3 and r["first_touch_order"]["person_things"] == 4


def test_saved_settings_are_compared_field_by_field_without_the_name():
    from sue.compare import settings
    person = {"name": "A", "scope": {"labels": [], "projectIds": ["atlas-demo"]}, "period": "monthly"}
    engine = {"name": "B", "scope": {"labels": ["env:prod"], "projectIds": ["atlas-demo"]}, "period": "monthly"}
    s = settings(person, engine)
    assert s["fields"] == 3 and s["same"] == 2 and list(s["different"]) == ["scope.labels"]
