"""Counting several seeded runs of one card (sue/batch.py)."""

from sue.batch import aggregate, report


def summary(seed, overall, recipients, missed=(), slips=None, metrics=None, stop="completion_declared"):
    return {"seed": seed, "evaluation": {"overall": overall, "criteria": {"amount": True, "recipients": recipients}},
            "missed_defaults": [{"original": m} for m in missed], "slips": slips or {}, "stop": {"reason": stop},
            "actions": 20, "dir": f"runs/r{seed}", "metrics": metrics}


def m(content):
    return {"content": content, "precision": 0.9, "direction": 0.7, "order": 0.6, "settings": 0.8}


def test_runs_add_up_to_counts_per_check_default_and_slip():
    runs = [summary(1, True, True, metrics=m(0.8)),
            summary(2, False, False, missed=["Email alerts to billing admins and users"], slips={"lapses": 2}, metrics=m(0.6)),
            summary(3, False, False, missed=["Email alerts to billing admins and users"], slips={"misclicks": 1},
                    metrics=m(0.7), stop="abandoned")]
    agg = aggregate("dev-rushed", runs)
    assert agg["passed"] == 1 and agg["checks_passed"] == {"amount": 3, "recipients": 1}
    assert agg["missed_defaults"] == {"Email alerts to billing admins and users": 2}
    assert agg["slips"] == {"lapses": 2, "misclicks": 1}
    assert agg["stops"] == {"completion_declared": 2, "abandoned": 1}
    assert agg["metrics"]["content"] == {"mean": 0.7, "min": 0.6, "max": 0.8}
    note = report(agg, "person-1")
    assert "1 of 3" in note and "recipients: 1 of 3" in note and "| content | 70% | 60% to 80% |" in note


def test_without_a_person_session_there_are_no_metrics():
    assert "metrics" not in aggregate("x", [summary(1, True, True)])
