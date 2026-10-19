"""Human variability (engine-design.md 4.9, 2026-10-19): traits as 0-10 scores, states that
change during the task, and slips, all drawn from one seeded random generator.

A trait score picks the level the existing rules use, step by step: 0 is always low, 5 always
medium, 10 always high, and a score in between mixes the two levels around it (2.5 is low
half the time and medium half the time). The rules themselves stay three-level. A card
built from a questionnaire (format v2) has only levels; they become 0, 5 and 10, and every
state and slip below is off, so such a card makes exactly the decisions it made before.

States, from a card of format v3:
- fatigue: carefulness and patience fall as reading effort builds up over the task;
- time pressure: reads less, dares more, gives up sooner; steady, or rising after setbacks
  or over time (stress tolerance slows the rise after setbacks);
- distraction: each step, a chance of missing one less prominent element of the piece he
  is looking at;
- attention to warnings: each step, a chance of not noticing error and warning text.

Perception, also from v3: small text he cannot read, a colour filter, near-miss clicks on
small targets, and reading speed (how much effort reading a piece costs).

How strong each effect is per point lives in config.toml [variability]. Those numbers are
placeholders until calibrated against people; the code only says in which direction a
trait pushes."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Callable

LEVELS = ("low", "medium", "high")
SCORE_OF = {"low": 0.0, "medium": 5.0, "high": 10.0}
TRAITS = ("risk", "patience", "detailFind", "detailCheck")
PATTERNS = ("steady", "rises_after_setbacks", "rises_over_time")
VISION = ("normal", "mild", "reduced")
COLOR = ("typical", "reduced", "no_color_cues")
CLICK = ("high", "medium", "low")
READING = ("slow", "average", "fast")


def _clamp(x: float, lo: float = 0.0, hi: float = 10.0) -> float:
    return max(lo, min(hi, x))


def _score(entry: Any, fallback: str = "medium") -> float:
    """A card's tendency entry as a score: its score when it has one, else its level."""
    if isinstance(entry, dict):
        if isinstance(entry.get("score"), (int, float)):
            return _clamp(float(entry["score"]))
        return SCORE_OF.get(entry.get("level") or fallback, 5.0)
    return SCORE_OF.get(fallback, 5.0)


@dataclass(frozen=True)
class Traits:
    risk: float = 5.0
    patience: float = 5.0
    find: float = 5.0  # detail when finding things
    check: float = 5.0  # detail when checking a form
    fatigue: float = 0.0
    distraction: float = 0.0
    pressure: float = 0.0
    pattern: str = "steady"
    stress_tolerance: float = 5.0
    warnings: float = 10.0  # attention to warnings
    vision: str = "normal"
    color: str = "typical"
    click: str = "high"
    reading: str = "average"

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def traits_of(card_version: int, tendency: dict[str, Any], state: dict[str, Any] | None,
              perception: dict[str, Any] | None) -> Traits:
    """The card's traits. A v2 card's perception answers are not used: v2 runs stay as they were."""
    t = tendency or {}
    base = dict(
        risk=_score(t.get("risk")),
        patience=_score(t.get("patience")),
        find=_score(t.get("detailFind") or t.get("detail")),
        check=_score(t.get("detailCheck") or t.get("detail")),
    )
    if card_version < 3:
        return Traits(**base)
    s, p = state or {}, perception or {}
    tp = s.get("timePressure") or {}
    pick = lambda value, allowed, default: value if value in allowed else default  # noqa: E731
    num = lambda value, default: _clamp(float(value)) if isinstance(value, (int, float)) else default  # noqa: E731
    return Traits(
        **base,
        fatigue=num(s.get("fatigue"), 0.0),
        distraction=num(s.get("distraction"), 0.0),
        pressure=num(tp.get("score"), 0.0),
        pattern=pick(tp.get("pattern"), PATTERNS, "steady"),
        stress_tolerance=num(s.get("stressTolerance"), 5.0),
        warnings=num(s.get("warningAttention"), 10.0),
        vision=pick(p.get("vision"), VISION, "normal"),
        color=pick(p.get("colorVision"), COLOR, "typical"),
        click=pick(p.get("clickPrecision"), CLICK, "high"),
        reading=pick(p.get("readingSpeed"), READING, "average"),
    )


def level_from(score: float, rng: random.Random) -> str:
    """The level the rules use this time. Draws only when the score is between two levels,
    so a score of 0, 5 or 10 never uses the random generator."""
    s = _clamp(score)
    if s in (0.0, 5.0, 10.0):
        return LEVELS[int(s // 5)]
    lower = 0 if s < 5 else 1
    upper_share = (s - 5 * lower) / 5
    return LEVELS[lower + 1] if rng.random() < upper_share else LEVELS[lower]


@dataclass
class Variability:
    traits: Traits
    cfg: dict[str, Any]
    rng: random.Random
    limits: dict[str, float]  # patience limits for low, medium and high (config.toml [patience])
    effort: float = 0.0  # reading effort so far: pieces read, weighted by reading speed
    setbacks: int = 0
    log: dict[str, Any] = field(default_factory=dict)  # what this step drew, for the step record
    held: dict[tuple[str, str], str] = field(default_factory=dict)  # levels kept for a screen part

    # ---- states -----------------------------------------------------------------

    def pressure(self) -> float:
        t, c = self.traits, self.cfg
        p = t.pressure
        if t.pattern == "rises_after_setbacks":
            p += self.setbacks * c["pressure_setback_gain"] * (1 - t.stress_tolerance / 10)
        elif t.pattern == "rises_over_time":
            p += self.effort * c["pressure_time_gain"]
        return _clamp(p)

    def tiredness(self) -> float:
        """0 to 1: how far fatigue has set in."""
        if self.traits.fatigue <= 0:
            return 0.0
        return (self.traits.fatigue / 10) * min(1.0, self.effort / self.cfg["fatigue_horizon"])

    def score(self, name: str) -> float:
        """A trait's score now, after fatigue and time pressure."""
        t, c = self.traits, self.cfg
        base = {"risk": t.risk, "patience": t.patience, "detailFind": t.find, "detailCheck": t.check}[name]
        tired, press = self.tiredness(), self.pressure() / 10
        if name in ("detailFind", "detailCheck"):
            key = "pressure_find_drop" if name == "detailFind" else "pressure_check_drop"
            return _clamp(base - tired * c["fatigue_max_drop"] - press * c[key])
        if name == "patience":
            return _clamp(base - tired * c["fatigue_max_drop"])
        return _clamp(base + press * c["pressure_risk_gain"])  # risk

    def level(self, name: str, held_for: str | None = None) -> str:
        """The level the rules use now. held_for: a screen part (route and open sections).
        How carefully he goes over a part is decided when he first looks at it and kept while he
        stays there (2026-10-19): drawn afresh every step, a default he skimmed past was nearly
        always caught a step later, so a score of 2.5 almost never missed one (sweep on P3)."""
        s = self.score(name)
        key = (name, held_for) if held_for is not None else None
        if key in self.held:
            lv = self.held[key]
        else:
            lv = level_from(s, self.rng)
            if key is not None:
                self.held[key] = lv
        self.log.setdefault("levels", {})[name] = lv
        self.log.setdefault("scores", {})[name] = round(s, 2)
        return lv

    def patience_limit(self) -> int:
        """Wrong turns and backs he puts up with now: the config's limits at 0, 5 and 10,
        in between for scores between, then cut by time pressure."""
        s = self.score("patience")
        lo, mid, hi = self.limits["low"], self.limits["medium"], self.limits["high"]
        limit = lo + (mid - lo) * s / 5 if s <= 5 else mid + (hi - mid) * (s - 5) / 5
        limit *= 1 - (self.pressure() / 10) * self.cfg["pressure_patience_cut"]
        return max(1, round(limit))

    def read(self, pieces: int) -> None:
        """He read this many pieces of screen this step."""
        self.effort += max(1, pieces) * self.cfg["reading_effort"][self.traits.reading]

    # ---- slips --------------------------------------------------------------------

    def lapse(self, seen: list[dict[str, Any]], prominence: Callable[[dict[str, Any]], float]) -> dict[str, Any] | None:
        """Distracted for a moment: misses one of the less prominent elements of the piece he
        is reading. Drawn once per piece read; None most of the time, always at distraction 0."""
        chance = (self.traits.distraction / 10) * self.cfg["distraction_max_lapse"]
        pool = [e for e in seen if not e.get("harness")]
        if chance <= 0 or len(pool) < 2 or self.rng.random() >= chance:
            return None
        quiet = sorted(pool, key=prominence)[: max(1, len(pool) // 2)]  # the less prominent half
        missed = quiet[self.rng.randrange(len(quiet))]
        self.log.setdefault("lapses", []).append(missed.get("original") or missed.get("text"))
        return missed

    def notices_warnings(self) -> bool:
        if self.traits.warnings >= 10:
            return True
        noticed = self.rng.random() < self.traits.warnings / 10
        self.log["warnings_noticed"] = noticed
        return noticed

    def miss_offset(self, element: dict[str, Any] | None) -> tuple[float, float] | None:
        """A near miss on a small target: where the click lands off the element, or None."""
        chance = self.cfg["click_miss"][self.traits.click]
        box = (element or {}).get("box")
        if chance <= 0 or not box or min(box["w"], box["h"]) > self.cfg["small_target_px"]:
            return None
        if self.rng.random() >= chance:
            return None
        side = self.rng.choice(((1, 0), (-1, 0), (0, 1), (0, -1)))
        gap = self.cfg["miss_gap_px"]
        offset = (side[0] * (box["w"] / 2 + gap), side[1] * (box["h"] / 2 + gap))
        self.log["misclick"] = {"aimed_at": element.get("original"), "offset": offset}
        return offset

    def vision_px(self) -> float:
        """Text smaller than this he cannot read (0: he reads every size)."""
        return self.cfg["vision_px"].get(self.traits.vision, 0)

    def take_log(self) -> dict[str, Any]:
        out, self.log = self.log, {}
        if out:
            out["tiredness"] = round(self.tiredness(), 2)
            out["pressure"] = round(self.pressure(), 2)
        return out


def make(traits: Traits, config: dict[str, Any], seed: int) -> Variability:
    return Variability(traits, config["variability"], random.Random(seed), dict(config["patience"]["limit"]))
