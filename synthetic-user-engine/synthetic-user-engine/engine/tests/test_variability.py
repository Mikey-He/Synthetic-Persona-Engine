"""Human variability (engine-design.md 4.9): scores, states and slips, all seeded."""

import io
import random

from sue.screen import color_filter, unreadable
from sue.variability import Traits, level_from, make, traits_of

V2 = {"risk": {"level": "medium"}, "patience": {"level": "high"}, "detailFind": {"level": "high"},
      "detailCheck": {"level": "low"}}


def test_a_v2_card_is_scores_0_5_10_with_every_state_off():
    t = traits_of(2, V2, {"fatigue": 9}, {"vision": "reduced"})
    assert (t.risk, t.patience, t.find, t.check) == (5.0, 10.0, 10.0, 0.0)
    assert t == Traits(risk=5.0, patience=10.0, find=10.0, check=0.0)  # v2 state and perception are not read


def test_levels_at_0_5_10_never_draw_from_the_generator():
    rng = random.Random(1)
    before = rng.getstate()
    assert [level_from(s, rng) for s in (0, 5, 10)] == ["low", "medium", "high"]
    assert rng.getstate() == before


def test_a_score_between_levels_mixes_them_in_proportion():
    rng = random.Random(7)
    draws = [level_from(2.5, rng) for _ in range(4000)]
    assert set(draws) == {"low", "medium"}
    assert 0.45 < draws.count("medium") / len(draws) < 0.55
    draws = [level_from(9, rng) for _ in range(4000)]
    assert 0.75 < draws.count("high") / len(draws) < 0.85


def test_a_level_held_for_a_screen_part_stays_until_he_moves_on(config):
    var = make(traits_of(3, {"detailCheck": {"score": 2.5}}, None, None), config, seed=9)
    first = var.level("detailCheck", held_for="/create|Actions")
    assert all(var.level("detailCheck", held_for="/create|Actions") == first for _ in range(200))
    parts = {var.level("detailCheck", held_for=f"/create|part{i}") for i in range(200)}
    assert parts == {"low", "medium"}  # each new part draws afresh


def test_a_v2_card_takes_no_draws_and_keeps_its_patience_limits(config):
    for level, limit in config["patience"]["limit"].items():
        tendency = {**V2, "patience": {"level": level}}
        var = make(traits_of(2, tendency, None, None), config, seed=3)
        before = var.rng.getstate()
        assert var.patience_limit() == limit
        assert [var.level(n) for n in ("risk", "detailCheck", "detailFind")] == ["medium", "low", "high"]
        var.read(5)
        assert var.lapse([{"id": "a", "box": {}}, {"id": "b", "box": {}}], lambda e: 0) is None
        assert var.notices_warnings() is True
        assert var.miss_offset({"box": {"x": 0, "y": 0, "w": 12, "h": 12}}) is None
        assert var.vision_px() == 0
        assert var.rng.getstate() == before


def v3(**state):
    return {"fatigue": 0, "distraction": 0, "timePressure": {"score": 0, "pattern": "steady"}, "warningAttention": 10, **state}


def test_fatigue_lowers_carefulness_as_reading_builds_up(config):
    var = make(traits_of(3, {"detailCheck": {"score": 6}}, v3(fatigue=10), {}), config, seed=1)
    fresh = var.score("detailCheck")
    var.read(config["variability"]["fatigue_horizon"])
    assert fresh == 6 and var.score("detailCheck") == 6 - config["variability"]["fatigue_max_drop"]


def test_time_pressure_rising_after_setbacks_makes_them_bolder_and_less_patient(config):
    var = make(traits_of(3, {"risk": {"score": 5}, "patience": {"score": 5}},
                         v3(timePressure={"score": 2, "pattern": "rises_after_setbacks"}, stressTolerance=0), {}), config, seed=1)
    calm_risk, calm_limit = var.score("risk"), var.patience_limit()
    var.setbacks = 3
    assert var.score("risk") > calm_risk and var.patience_limit() < calm_limit


def test_distraction_misses_a_less_prominent_element_at_the_configured_rate(config):
    var = make(traits_of(3, {}, v3(distraction=10), {}), config, seed=11)
    seen = [{"id": f"e{i}", "original": f"e{i}", "box": {}} for i in range(6)]
    loud = {"e0", "e1", "e2"}
    misses = [var.lapse(seen, lambda e: 10 if e["id"] in loud else 0) for _ in range(3000)]
    hit = [m for m in misses if m]
    assert 0.17 < len(hit) / len(misses) < 0.23
    assert all(m["id"] not in loud for m in hit)


def test_warnings_go_unnoticed_in_proportion(config):
    var = make(traits_of(3, {}, v3(warningAttention=3), {}), config, seed=5)
    noticed = [var.notices_warnings() for _ in range(3000)]
    assert 0.25 < sum(noticed) / len(noticed) < 0.35


def test_near_misses_only_on_small_targets_and_only_without_full_precision(config):
    small, large = {"box": {"x": 0, "y": 0, "w": 14, "h": 14}}, {"box": {"x": 0, "y": 0, "w": 120, "h": 36}}
    var = make(traits_of(3, {}, v3(), {"clickPrecision": "low"}), config, seed=2)
    assert all(var.miss_offset(large) is None for _ in range(500))
    rate = sum(var.miss_offset(small) is not None for _ in range(4000)) / 4000
    assert abs(rate - config["variability"]["click_miss"]["low"]) < 0.03
    sure = make(traits_of(3, {}, v3(), {"clickPrecision": "high"}), config, seed=2)
    assert all(sure.miss_offset(small) is None for _ in range(500))


def test_the_same_seed_gives_the_same_draws(config):
    def draws(seed):
        var = make(traits_of(3, {"detailCheck": {"score": 3}}, v3(distraction=6, warningAttention=5), {}), config, seed)
        return [(var.level("detailCheck"), var.notices_warnings(), bool(var.lapse([{"id": 1}, {"id": 2}], lambda e: 0)))
                for _ in range(50)]
    assert draws(4) == draws(4) and draws(4) != draws(5)


def test_text_too_small_to_read_turns_into_made_up_words():
    out = unreadable("Budget 80% alert")
    assert "Budget" not in out and "alert" not in out and "##%" in out


def test_colour_filter_keeps_a_valid_png():
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (4, 4), (220, 20, 20)).save(buf, format="PNG")
    out = Image.open(io.BytesIO(color_filter(buf.getvalue(), "no_color_cues"))).convert("RGB")
    r, g, b = out.getpixel((0, 0))
    assert r == g == b
    assert color_filter(buf.getvalue(), "typical") == buf.getvalue()
