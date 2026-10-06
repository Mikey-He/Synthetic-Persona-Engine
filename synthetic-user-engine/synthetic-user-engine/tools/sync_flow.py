"""Copies the workflow definition (data/version-a/flow.json, or the file given) into the two
pages that use it: the participant questionnaire gets the task and the experience
questions, the Persona Builder gets the whole flow. Run it after every change to the flow,
then republish the pages.

    python tools/sync_flow.py                    # rewrite both pages
    python tools/sync_flow.py --check            # only report whether they are in step
    python tools/sync_flow.py path/to/flow.json  # another workflow
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FLOW = ROOT / "data" / "version-a" / "flow.json"
QUESTIONNAIRE = ROOT / "tools" / "questionnaire.html"
BUILDER = ROOT / "tools" / "persona-builder.html"
SOURCES = ("product", "work", "study", "life")


def problems(flow: dict) -> list[str]:
    """What would break the pages or the rules: unknown ids, missing English or Chinese lines."""
    out = []
    groups = {g["id"]: g for g in flow.get("groups", [])}
    exps = {e["id"] for e in flow.get("experiences", [])}
    steps = {s["id"] for s in flow.get("steps", [])}
    screens = {s["id"] for s in flow.get("screens", [])}
    items = {i["id"] for i in flow.get("items", [])}
    for s in flow.get("sources", []):
        if s["id"] not in SOURCES:
            out.append(f"source {s['id']}: the questionnaire only asks about {', '.join(SOURCES)}")
    for g in groups.values():
        if g.get("source") not in SOURCES:
            out.append(f"group {g['id']}: unknown source {g.get('source')}")
        if not (g.get("label") or {}).get("en") or not (g.get("label") or {}).get("zh"):
            out.append(f"group {g['id']}: needs an English and a Chinese label")
    for e in flow.get("experiences", []):
        if e.get("group") not in groups:
            out.append(f"experience {e['id']}: unknown group {e.get('group')}")
        if not (e.get("question") or {}).get("en") or not (e.get("question") or {}).get("zh"):
            out.append(f"experience {e['id']}: needs the question in English and Chinese")
    for s in flow.get("steps", []):
        if s.get("screen") not in screens:
            out.append(f"step {s['id']}: unknown screen {s.get('screen')}")
    kinds = {"word", "icon", "location", "concept", "strategy", "habit"}
    for i in flow.get("items", []):
        if i.get("step") not in steps:
            out.append(f"item {i['id']}: unknown step {i.get('step')}")
        if i.get("kind") not in kinds:
            out.append(f"item {i['id']}: kind must be one of {', '.join(sorted(kinds))}")
        if i.get("altOf") and i["altOf"] not in items:
            out.append(f"item {i['id']}: altOf points to unknown item {i['altOf']}")
        for x in i.get("exps", []):
            if x not in exps:
                out.append(f"item {i['id']}: unknown experience {x}")
        if i.get("kind") == "word" and i.get("common") not in ("common", "rare", "none"):
            out.append(f"item {i['id']}: common must be common, rare or none")
    return out


def questionnaire_data(flow: dict) -> dict:
    return {
        "flow": {"name": flow["name"], "task": flow["task"]},
        "sources": [{"id": s["id"], "legacy": s.get("legacy", "")} for s in flow["sources"]],
        "groups": [{"id": g["id"], "source": g["source"], "label": g["label"]} for g in flow["groups"]],
        "experiences": [{"id": e["id"], "group": e["group"], "question": e["question"]} for e in flow["experiences"]],
    }


def dump(data: dict) -> str:
    # One record per line keeps diffs readable; "</" is escaped so text can never close the tag.
    lines = ["{"]
    keys = list(data)
    for n, k in enumerate(keys):
        v = data[k]
        tail = "," if n < len(keys) - 1 else ""
        if isinstance(v, list) and v and isinstance(v[0], dict):
            rows = ",\n".join("  " + json.dumps(x, ensure_ascii=False) for x in v)
            lines.append(f'"{k}": [\n{rows}\n]{tail}')
        else:
            lines.append(f'"{k}": {json.dumps(v, ensure_ascii=False)}{tail}')
    lines.append("}")
    return "\n".join(lines).replace("</", "<\\/")


def put(page: Path, block_id: str, data: dict, check: bool) -> bool | None:
    """Returns True when the page changed (or would change), False when in step, None on error."""
    text = page.read_text(encoding="utf-8")
    block = re.compile(r'(<script type="application/json" id="' + block_id + r'">)(.*?)(</script>)', re.S)
    m = block.search(text)
    if not m:
        print(f"{page.name}: no {block_id} block")
        return None
    new = dump(data)
    if m.group(2) == new:
        return False
    if not check:
        page.write_text(text[: m.start(2)] + new + text[m.end(2):], encoding="utf-8")
    return True


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    check = "--check" in sys.argv
    path = Path(args[0]) if args else FLOW
    flow = json.loads(path.read_text(encoding="utf-8"))
    bad = problems(flow)
    if bad:
        print("The flow file has problems; fix them first:")
        print("\n".join("  " + x for x in bad))
        return 1
    changed = []
    for page, block, data in ((QUESTIONNAIRE, "qdata", questionnaire_data(flow)), (BUILDER, "flow", flow)):
        r = put(page, block, data, check)
        if r is None:
            return 1
        if r:
            changed.append(page.name)
    if not changed:
        print("both pages are in step with " + path.name)
        return 0
    print(("out of step: " if check else "updated: ") + ", ".join(changed))
    return 1 if check else 0


if __name__ == "__main__":
    sys.exit(main())
