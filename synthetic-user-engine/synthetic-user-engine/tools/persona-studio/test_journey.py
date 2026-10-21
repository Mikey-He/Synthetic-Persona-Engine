"""Placing engine steps on the steps of the task (journey.py)."""
import json

import journey

FLOW = {
    "name": "Demo", "steps": [
        {"id": "A1", "action": "Click Budgets & caps", "defaults": ""},
        {"id": "A2", "action": "Click + Create new", "defaults": ""},
        {"id": "A3", "action": "Enter 1000 as Target amount, click Next", "defaults": "Target amount starts empty"},
        {"id": "A4", "action": "Untick Email alerts to billing admins and users; click Next", "defaults": ""},
        {"id": "A5", "action": "Click Finish", "defaults": ""},
    ],
    "items": [{"id": "T1", "step": "A2", "kind": "location", "text": "The + Create new link starts a budget"},
              {"id": "T2", "step": "A3", "kind": "word", "text": "Target amount"}],
    "engine": {"grading": {"amount": "The amount is $1,000"}, "gradingSteps": {"amount": "A3"}},
}


def row(n, kind, text, value=None, evidence=(), **state):
    return {"step": n, "screenshot": f"step_{n:03d}.png", "route": "/x", "rule": "r",
            "state": {"wrong": state.get("wrong", 0), "backs": state.get("backs", 0)},
            "action": {"type": kind, "element": "e", "original": text, "value": value, "box": {"x": 1, "y": 1, "w": 2, "h": 2}},
            "candidates": [{"element": "e", "why": f"because {n}", "evidence": [dict(e) for e in evidence]}]}


def test_place_moves_forward_on_evidence_and_names():
    rows = [row(1, "click", "Budgets & caps"),
            row(2, "click", "+ Create new", evidence=[{"type": "item", "ref": "T1"}]),
            row(3, "type", "Target amount *", value="1000"),
            row(4, "click", "Next"),  # named by A3 and A4: stays on the nearest step ahead
            row(5, "click", "Email alerts to billing admins and users"),
            row(6, "click", "Next"),
            row(7, "click", "Finish"),
            row(8, "click", "I'm finished")]
    assert journey.Placer(FLOW).place(rows) == [0, 1, 2, 2, 3, 3, 4, 4]


def test_journey_marks_trouble_on_the_right_step(tmp_path):
    rows = [row(1, "click", "Budgets & caps"), row(2, "click", "Members", wrong=1), row(3, "click", "+ Create new"),
            row(4, "click", "Finish")]
    (tmp_path / "steps.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    (tmp_path / "summary.json").write_text(json.dumps({
        "stop": {"reason": "completion_declared"}, "evaluation": {"overall": False, "criteria": {"amount": False}},
        "missed_defaults": [{"step": 4, "text": "Email alerts to billing admins and users", "why": "Untick it"}]}), encoding="utf-8")
    j = journey.journey(FLOW, tmp_path, "/runs/x")
    status = [s["status"] for s in j["steps"]]
    assert status[0] == "hesitated"  # the wrong turn happened before reaching step 2
    assert status[2] == "wrong" and j["steps"][2]["failed"][0]["key"] == "amount"
    assert status[3] == "wrong" and j["steps"][3]["missed"][0]["text"].startswith("Email alerts")
    assert j["steps"][0]["moves"][0]["shot"] == "/runs/x/step_001.png"
