"""Copies the workflow definition (data/version-a/flow.json, or the file given) into the two
pages that use it: the participant questionnaire gets the task and the experience
questions, the Persona Builder gets the whole flow. Run it after every change to the flow,
then republish the pages.

    python tools/sync_flow.py                    # rewrite both pages
    python tools/sync_flow.py --check            # only report whether they are in step
    python tools/sync_flow.py path/to/flow.json  # another workflow
    python tools/sync_flow.py path/to/flow.json --platform billing-config
        # a study page (testing-platform/<study>-study/): its own copy of the questionnaire and
        # study.js with the task. The two pages above stay as they are.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))
from sue.workflow import problems as engine_problems  # noqa: E402  the engine block (sue/workflow.py)
FLOW = ROOT / "data" / "version-a" / "flow.json"
QUESTIONNAIRE = ROOT / "tools" / "questionnaire.html"
BUILDER = ROOT / "tools" / "persona-builder.html"
STUDIES = ROOT.parent.parent / "testing-platform"  # the study pages, in this repository
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
    out += knowledge_group_problems(flow)
    out += engine_problems(flow)
    return out


def knowledge_group_problems(flow: dict) -> list[str]:
    """Persona Studio's knowledge groups (2026-10-19): every item that is not an alternative or a
    habit is in exactly one group; a word group holds only words, any other group none."""
    groups = flow.get("knowledgeGroups")
    if groups is None:
        return ["knowledgeGroups: missing; Persona Studio needs them to set knowledge"]
    out, keys, owner = [], set(), {}
    kinds = {i["id"]: i.get("kind") for i in flow.get("items", [])}
    for g in groups:
        key = g.get("key")
        if not key or key in keys:
            out.append(f"knowledge group {key!r}: needs a unique key")
        keys.add(key)
        if not g.get("title") or not g.get("description"):
            out.append(f"knowledge group {key}: needs a title and a description")
        if g.get("default") not in (0, 1, 2):
            out.append(f"knowledge group {key}: default must be 0, 1 or 2")
        if not g.get("items"):
            out.append(f"knowledge group {key}: has no items")
        for item in g.get("items", []):
            if item not in kinds:
                out.append(f"knowledge group {key}: unknown item {item}")
                continue
            if item in owner:
                out.append(f"item {item}: in knowledge groups {owner[item]} and {key}")
            owner[item] = key
            if (kinds[item] == "word") != bool(g.get("word")):
                out.append(f"knowledge group {key}: item {item} is a {kinds[item]}, but the group is "
                           + ("a word group" if g.get("word") else "not a word group"))
    for i in flow.get("items", []):
        if not i.get("altOf") and i.get("kind") != "habit" and i["id"] not in owner:
            out.append(f"item {i['id']}: in no knowledge group")
    return out


def questionnaire_data(flow: dict) -> dict:
    return {
        "flow": {"name": flow["name"], "task": flow["task"]},
        "sources": [{"id": s["id"], "legacy": s.get("legacy", "")} for s in flow["sources"]],
        "groups": [{"id": g["id"], "source": g["source"], "label": g["label"]} for g in flow["groups"]],
        "experiences": [{"id": e["id"], "group": e["group"], "question": e["question"]} for e in flow["experiences"]],
    }


def study_data(flow: dict, study: str) -> dict:
    """What the study page shows: the task as the task bar shows it. The success checks stay out of it,
    since participants can open the page's files; the engine grades the participant file."""
    return {"study": study, "flow": flow["name"], "task": flow["task"]}


def desktop_light(page: str) -> str:
    """The study page's copy is for a desktop browser in one light look (2026-10-27): without the
    questionnaire's dark theme and its narrow-screen rule."""
    for rule in (re.compile(r'@media \(prefers-color-scheme: dark\)\{\n  :root:not\(\[data-theme="light"\]\)\{.*?\n  \}\n\}\n', re.S),
                 re.compile(r':root\[data-theme="dark"\]\{.*?\n\}\n', re.S),
                 re.compile(r'@media \(max-width:520px\)\{[^\n]*\}\}\n')):
        page, n = rule.subn("", page, count=1)
        if n != 1:
            raise SystemExit("tools/questionnaire.html changed its theme rules; update desktop_light in sync_flow.py")
    return page


def put_platform(flow: dict, study: str, check: bool) -> list[str]:
    """Writes (or, with check, compares) the study page's questionnaire copy and study.js. Returns what changed."""
    page = QUESTIONNAIRE.read_text(encoding="utf-8")
    block = re.compile(r'(<script type="application/json" id="qdata">)(.*?)(</script>)', re.S)
    m = block.search(page)
    page = page[: m.start(2)] + dump(questionnaire_data(flow)) + page[m.end(2):]
    page = desktop_light(page)
    folder = STUDIES / f"{study}-study"
    if not (folder / "index.html").exists():
        raise SystemExit(f"no study page at {folder}")
    files = {
        folder / "questionnaire.html": page,
        folder / "study.js": "// Written by synthetic-user-engine/tools/sync_flow.py --platform from the workflow's flow.json; do not edit.\n"
                             "window.STUDY = " + json.dumps(study_data(flow, study), ensure_ascii=False, indent=2).replace("</", "<\\/") + ";\n",
    }
    changed = []
    for path, text in files.items():
        if path.exists() and path.read_text(encoding="utf-8") == text:
            continue
        changed.append(str(path.relative_to(STUDIES)))
        if not check:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
    return changed


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
    args = [a for i, a in enumerate(sys.argv[1:], 1) if not a.startswith("--") and sys.argv[i - 1] != "--platform"]
    check = "--check" in sys.argv
    path = Path(args[0]) if args else FLOW
    flow = json.loads(path.read_text(encoding="utf-8"))
    bad = problems(flow)
    if bad:
        print("The flow file has problems; fix them first:")
        print("\n".join("  " + x for x in bad))
        return 1
    if "--platform" in sys.argv:
        study = sys.argv[sys.argv.index("--platform") + 1]
        changed = put_platform(flow, study, check)
        print(("out of step: " if check else "updated: ") + ", ".join(changed) if changed else f"the platform's {study} files are in step")
        return 1 if changed and check else 0
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
