"""Cards for a sensitivity sweep (engine-design.md 4.9): one participant's card as v3, with one
trait set to each score in turn and everything else unchanged.

    python tools/sweep_cards.py aryan detailCheck 0 2.5 5 7.5 10

writes data/personas/sweep-aryan-detailCheck-<score>.json. Every state is off and perception
normal, so the only thing that differs between the cards is that one score.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEVELS = {"low": 0, "medium": 5, "high": 10}
NO_STATE = {"fatigue": 0, "distraction": 0, "timePressure": {"score": 0, "pattern": "steady"},
            "stressTolerance": 5, "warningAttention": 10}
NO_PERCEPTION = {"vision": "normal", "colorVision": "typical", "clickPrecision": "high", "readingSpeed": "average"}


def name_of(score: float) -> str:
    return str(score).rstrip("0").rstrip(".") if "." in str(score) else str(score)


def main(card: str, trait: str, scores: list[float]) -> None:
    base = json.loads((ROOT / "data" / "personas" / f"{card}.json").read_text(encoding="utf-8"))
    if trait not in base["tendency"]:
        raise SystemExit(f"{card} has no trait {trait}")
    for score in scores:
        c = json.loads(json.dumps(base))
        c["version"] = 3
        for key, t in c["tendency"].items():
            if isinstance(t, dict) and t.get("level") in LEVELS:
                t["score"] = LEVELS[t["level"]]
        t = c["tendency"][trait]
        t["score"] = score
        t["level"] = "low" if score < 2.5 else "medium" if score < 7.5 else "high"
        t["source"] = f"Sweep: {trait} set to {score}"
        c["state"], c["perception"] = dict(NO_STATE), dict(NO_PERCEPTION)
        out = ROOT / "data" / "personas" / f"sweep-{card}-{trait}-{name_of(score)}.json"
        c["persona"]["id"] = out.stem
        c["persona"]["name"] = f"{c['persona']['name']} · {trait} {score}"
        out.write_text(json.dumps(c, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(out.relative_to(ROOT))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], [float(x) for x in sys.argv[3:]])
