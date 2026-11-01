"""What went wrong, part by part. The expected answers were read off the six logs by eye before the
code was written, so the code is held to the logs and not the other way round."""

from pathlib import Path

import pytest

from sue.config import load_config
from sue.events import CHANGED, LOST, UNSAVED, WENT_BACK, WRONG, Fact, engine_facts, person_trouble, troubles
from sue.parts import BEFORE
from sue.participant import load

ENGINE = Path(__file__).resolve().parents[1]
FLOW = ENGINE.parent / "data/workflows/billing-config-atlas-budget-ux-team/flow.json"
PEOPLE = ENGINE.parent / "data/participants/billing-config"
# The participants' files are not in the repository (real people; see .gitignore). Without them only the synthetic cases run.
needs_people = pytest.mark.skipif(not PEOPLE.exists(), reason="participant files are kept outside the repository")

# Per person, by part: the kinds of trouble their log shows.
BY_EYE = {
    "001": {BEFORE: {LOST}, "Amount": {WENT_BACK, CHANGED}, "Actions": {CHANGED}},  # 800 to 1000; Forecasted back to Actual
    "002": {BEFORE: {LOST}},  # Reports and the account dialog; the form itself went cleanly
    "003": {"Define": {WENT_BACK}, "Amount": {CHANGED}},  # typed 600, went back from Actions, 600 to 800
    "005": {BEFORE: {LOST}},
    "006": {BEFORE: {LOST}, "Amount": {UNSAVED, CHANGED}, "Actions": {UNSAVED, CHANGED, WRONG}},  # left twice; Last month's spend; no 80% rule at 1000
    "007": {BEFORE: {LOST}},
}


@pytest.fixture(scope="module")
def config():
    return load_config(flow=str(FLOW))


@needs_people
@pytest.mark.parametrize("pid", sorted(BY_EYE))
def test_each_persons_trouble_is_what_their_log_shows(pid, config):
    got = {}
    for part, kind, _ in person_trouble(load(PEOPLE / f"participant-{pid}.json"), config):
        got.setdefault(part, set()).add(kind)
    assert got == BY_EYE[pid]


def test_pressing_ok_twice_or_opening_a_dropdown_and_picking_it_is_no_trouble():
    parts = ["Scope", "Amount"]
    facts = [Fact("Scope", "section", "Scope"), Fact("Scope", "click", "OK"), Fact("Scope", "click", "OK"), Fact("Amount", "section", "Amount"),
             Fact("Amount", "value", "budget type", "specified amount"), Fact("Amount", "value", "budget type", "specified amount"),
             Fact("Amount", "value", "Target amount", "800"), Fact("Amount", "value", "Target amount", "800")]
    assert troubles(facts, parts, []) == []


def test_a_new_form_starts_clean_and_the_engine_is_read_by_the_same_names():
    facts = [Fact("Amount", "section", "Amount"), Fact("Amount", "value", "Target amount", "800"), Fact("Amount", "left"),
             Fact("Amount", "section", "Amount"), Fact("Amount", "value", "Target amount", "1000")]
    assert [t[1] for t in troubles(facts, ["Amount"], [])] == [UNSAVED]
    step = lambda section, **action: {"signature": f"/app|{section}|budgets|x", "action": {"type": "click", **action}}  # noqa: E731
    rows = [step("", original="Billing"), step("3 Amount", type="type", original="Target amount", value="$800"), step("3 Amount", original="NEXT"),
            step("4 Actions", original="FINISH", text="FINISH"), step("", original="Reports ⋮")]
    got = engine_facts(rows, ["Amount", "Actions"], {}, ["FINISH"])
    assert Fact("Amount", "value", "Target amount", "800") in got
    assert Fact("Actions", "saved") in got
    assert not any(f.kind == "left" for f in got)
    assert got[-1] == Fact("After the save", "click", "Reports")
