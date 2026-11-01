from sue.participant import compare_run, engine_moves, engine_window, person_moves, settings
from sue.study import group
from sue.target import target_problems


def ev(kind, target="", **payload):
    return {"type": kind, "target": target, "payload": payload}


def step(kind, text=None, route="/app/", value=None):
    return {"route": route, "action": {"type": kind, "original": text, "text": text, "value": value}}


PERSON = [
    ev("session_started"),
    ev("page_viewed", route="#"),
    ev("control_clicked", label="Budgets & caps ⋮"),
    ev("page_viewed", route="#budgets"),
    ev("field_changed", field="Name *", value="Atlas"),
    ev("field_changed", field="Name *", value="Atlas budget"),
    ev("field_changed", field="Email alerts to project owners", value=True),
    ev("scroll"),
    ev("control_clicked", label="Atlas budget"),
]
ENGINE = [
    step("scroll"),
    step("click", "Budgets & caps"),
    step("type", "Name *", "/app/#budgets", "Other name"),
    step("click", "Email alerts to project owners", "/app/#budgets"),
    step("click", "Other name", "/app/#budgets"),
]


def test_both_sides_become_the_same_moves():
    want = ["do budgets & caps", "do name *", "do email alerts to project owners", "do (the name they typed)"]
    assert person_moves(PERSON) == want
    assert engine_moves(ENGINE) == want


def test_settings_leave_out_the_id_and_the_name():
    person = {"id": "a", "name": "x", "amount": "800", "rules": [{"percent": 100}]}
    engine = {"id": "b", "name": "y", "amount": "1000", "rules": [{"percent": 100}]}
    got = settings(person, engine)
    assert (got["fields"], got["same"]) == (2, 1)
    assert list(got["different"]) == ["amount"]


def test_a_run_is_compared_with_the_file():
    person = {"events": PERSON, "product": {"mpsBudgets": [{"id": "a", "amount": "800"}]}}
    run = {"steps": ENGINE, "summary": {"stored": {"mpsBudgets": [{"id": "b", "amount": "800"}]}}}
    got = compare_run(person, run)
    assert got["content"]["recall"] == 1.0
    assert got["settings"]["share"] == 1.0


def test_the_engine_gets_the_persons_page_plus_its_task_bar():
    assert engine_window({"session": {"viewport": {"width": 1512, "height": 681}}}) == "1512x737"


def _run(moves, passed):
    return {"moves": moves, "passed": passed, "checks": {"c": passed}}


def test_the_group_counts_each_persons_runs_as_one():
    people = [
        {"moves": ["a", "b"], "checks": {"c": True}, "runs": [_run(["a"], True), _run(["a", "b"], False)]},
        {"moves": ["a"], "checks": {"c": False}, "runs": [_run(["a"], False)]},
    ]
    g = group(people)
    rows = {r["thing"]: r for r in g["things"]}
    assert rows["a"] == {"thing": "a", "people": 1.0, "runs": 1.0}
    assert rows["b"] == {"thing": "b", "people": 0.5, "runs": 0.25}  # half of one person's runs, none of the other's
    assert g["passed"] == {"people": 0.5, "runs": 0.25}
    assert g["checks"][0] == {"check": "c", "people": 0.5, "runs": 0.25}


def test_a_block_list_must_be_addresses():
    base = {"kind": "web", "start": "https://x.example/", "success": [{"name": "n", "type": "url", "matches": "x"}]}
    assert target_problems({**base, "block": ["https://*.clarity.ms/**"]}) == []
    assert target_problems({**base, "block": "https://*.clarity.ms/**"})
