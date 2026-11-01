"""How a person reads the task (sue/task.py): drawn per run, told to the model, thought again on the right screen."""

import random
from collections import Counter

from sue.prompt import build_turn
from sue.task import Readings

AMBIGUITIES = [
    {"about": "the amount", "shows_as": ["Target amount"], "options": ["The budget is $800, the team's target.", "The budget is $1,000, the company's limit."]},
    {"about": "the trigger", "shows_as": ["Trigger on"], "options": ["Alerts go on actual spend.", "Alerts go on forecasted spend."]},
]


def test_each_reading_is_drawn_about_equally_over_many_runs():
    got = Counter(Readings(AMBIGUITIES).draw(random.Random(seed))[0] for seed in range(400))
    assert 150 < got[0] < 250 and got[0] + got[1] == 400


def test_the_line_states_every_chosen_reading_in_order():
    r = Readings(AMBIGUITIES)
    assert r.line({0: 1, 1: 0}) == "The budget is $1,000, the company's limit. Alerts go on actual spend."
    assert Readings([]).line({}) is None


def test_they_think_again_only_where_the_words_show_and_only_once_per_part():
    r = Readings(AMBIGUITIES)
    chosen = {0: 0, 1: 0}
    assert r.rethink(random.Random(1), "Name * Next", "1 Define", 1.0, chosen) is None  # nothing here bears on it
    flips = 0
    for seed in range(60):
        rr, c = Readings(AMBIGUITIES), {0: 0, 1: 0}
        if rr.rethink(random.Random(seed), "Budget type Specified amount Target amount", "3 Amount", 1.0, c):
            flips += 1
            assert c[0] == 1 and c[1] == 0  # only the amount turns on this screen
    assert 15 < flips < 45  # a fresh draw: about half the time the same reading again
    r.rethink(random.Random(2), "Target amount", "3 Amount", 1.0, chosen)
    assert r.rethink(random.Random(3), "Target amount", "3 Amount", 1.0, chosen) is None  # thought about it here already
    careless = Readings(AMBIGUITIES)
    assert all(careless.rethink(random.Random(s), "Target amount", f"part {s}", 0.0, {0: 0, 1: 0}) is None for s in range(30))


def test_the_prompt_tells_the_model_what_they_take_the_task_to_mean():
    from pathlib import Path

    from sue.persona import Persona

    p = Persona(id="x", name="x", card_type="normal", english="fluent", vocab_size=None, task="Set a budget of $800 or less, under a $1,000 limit.",
                words=(), items={}, tendency={}, perception={}, goal={}, steps=(), source=Path("x"))
    turn = build_turn(p, [], {"y": 0, "max": 0}, reading="The budget is $1,000, the company's limit.")
    assert "The task (verbatim):\nSet a budget of $800 or less, under a $1,000 limit.\n\nWhat they take the task to mean: The budget is $1,000, the company's limit." in turn
    assert "take the task to mean" not in build_turn(p, [], {"y": 0, "max": 0})
