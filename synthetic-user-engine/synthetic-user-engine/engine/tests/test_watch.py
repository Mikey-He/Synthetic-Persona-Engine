"""The watch on runs: what it calls a problem."""

from sue.watch import going_round, moves_of, problems


def step(n, text, kind="click", candidates=()):
    return {"step": n, "action": {"type": kind, "text": text}, "candidates": list(candidates)}


def test_going_round_needs_the_same_round_three_times():
    assert going_round(["a", "b", "a", "b", "a", "b"]) == (2, ["a", "b"])
    assert going_round(["a", "b", "a", "b", "c", "b"]) is None
    assert going_round(["a", "a", "a", "a", "a", "a"]) is None  # typing on, or scrolling, is not a round


def test_a_round_it_later_left_still_counts():
    steps = [step(i, t) for i, t in enumerate(["x", "y"] * 3 + ["p", "q", "r"])]
    assert "going_round" in [k for k, _ in problems(steps)]
    assert moves_of(steps)[0] == "click:x"


def test_a_rule_refusing_what_the_model_most_wants_is_told_once_per_rule():
    refused = {"purpose": "fix", "hope": 9, "dropped": "Set this box on purpose; leaves it"}
    steps = [step(i, f"m{i}", candidates=[refused]) for i in range(3)]
    assert [k for k, _ in problems(steps)] == ["blocked:Set this box on purpose; leaves it"]


def test_what_the_model_barely_wants_is_no_problem():
    refused = {"purpose": "check", "hope": 3, "dropped": "Not careful"}
    assert problems([step(i, f"m{i}", candidates=[refused]) for i in range(5)]) == []


def test_the_final_button_again_and_again():
    steps = [step(i, "FINISH") for i in (1, 5, 9)]
    assert ("final_again" in [k for k, _ in problems(steps)])
