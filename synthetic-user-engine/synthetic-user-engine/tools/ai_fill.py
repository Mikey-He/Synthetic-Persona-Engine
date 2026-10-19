"""Lets Gemini fill in the questionnaire as a role described in Google's persona fields
(data/roles/*.json), and saves the result as an ordinary answer file. The file then goes
through the same Persona Builder as a real participant's answers:

    engine/.venv/Scripts/python tools/ai_fill.py data/roles/role-p3.json
    node tools/build_cards.js data/answers/ai-p3.json

The model sees only the role description and the questions, never anyone's answers. The
vocabulary test is left out (a model knows every word); the card then uses the English
level the model picks. Rules for the behaviour fields of a role, so they are not set by
judgment: risk tolerance follows years in cloud (under 1 year cautious, 1 to 4 moderate,
5 or more confident).
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))
from sue.config import load_config, load_env, require_env  # noqa: E402

FLOW = json.loads((ROOT / "data" / "version-a" / "flow.json").read_text(encoding="utf-8"))

# Same wording and option order as tools/questionnaire.html.
SOURCES = {
    "product": "What software, websites and devices do you use, and what have you done with them?",
    "work": "What jobs have you had, and what were you responsible for? (Students can include course projects, internships and TA work.)",
    "study": "What courses, certificates or self-study have you done? (Training at work counts too.)",
    "life": "Outside work, what have you done to manage money, such as tracking spending or budgeting?",
}
LEVELS = [
    "0 Never: haven't done or studied it",
    "1 Studied, but forgot: learned it once, can barely remember it",
    "2 Studied it: learned it in a class, a certificate or docs, never done it",
    "3 Done it: a few times myself; following an AI or a tutorial counts",
    "4 Expert: I do it often without thinking",
]
TEND = [
    ("R1", "Last time you didn't understand a button on a website you hadn't used before, what did you do? (Answer as if you couldn't search online or ask an AI.)",
     ["Didn't click it; looked for an explanation or asked someone", "Looked for an explanation first, then clicked to see", "Just clicked it to see"]),
    ("R2", "Before confirming a money-related setting, like a payment, subscription or budget, what do you do?",
     ["Make sure I understand every item", "Confirm once I roughly understand", "Confirm once it looks about right; fix it later if needed"]),
    ("P1", "Last time you couldn't find a feature on a website, how long did you keep trying?",
     ["Gave up after two or three tries, or asked someone", "Looked everywhere I could think of", "Kept trying different ways until I found it"]),
    ("P2", "When something fails a few times in a row, what do you usually do?",
     ["Stop", "Try one or two other ways", "Keep trying until it works"]),
    ("D1", "When you open a new page for the first time, how do you usually look at it?",
     ["Click the first thing that looks right", "Skim the main parts, then click", "Read the whole page first"]),
    ("D2", "In a form with many options, do you check the defaults you weren't asked to change?",
     ["No", "I glance at the obvious ones", "I check every one"]),
    ("D3", "Last time you filled in a form and met an option you didn't understand, what did you do?",
     ["Left it as it was", "Read the explanation next to it, but didn't change it", "Tried changing it to see what happened, then changed it back"]),
    ("H", "When you look for a feature on a new website, what do you try first?",
     ["Search", "Look through the menus", "It depends"]),
]
PERC = [
    ("V", "Is small text on a computer, like the hints under a form field, hard for you to read?", ["Not hard", "Only when it's small and faint", "Anything smaller than normal text"]),
    ("C", "Can you tell red from green?", ["Yes", "Not easily"]),
    ("M", "When you click very small things, like checkboxes, do you miss?", ["Rarely", "Only very small ones", "Often"]),
    ("S", "Compared with people around you, do you read on-screen explanations faster or slower? (For the language the screen is in.)", ["Faster", "About the same", "Slower"]),
]
DONE = {"action": "Once I click the last button", "toast": "I see a success message", "list": "I check the list or details page",
        "external": "I wait for an email or notification", "test": "I make it actually trigger once"}
MISS = ["Let it go", "Go back and check", "Do it all again", "Something else"]
ENGLISH = {"fluent": "Native or fluent: I understand almost everything in English software",
           "intermediate": "Intermediate: I know common words but not rarer ones",
           "beginner": "Beginner: I don't understand English words I haven't studied"}

SYSTEM = (
    "You are role-playing one research participant, described in the persona fields a Google UX team uses. "
    "Fill in the questionnaire exactly as this person would: honestly and in their own words, including what they "
    "have never done, what they only half remember, and their everyday habits. Do not answer as a helpful expert, and "
    "do not give them knowledge or carefulness their background does not support. Reply with JSON only."
)


def questionnaire_text(role: dict) -> str:
    fields = "\n".join(f"- {k}: {v}" for k, v in role.items() if k not in ("kind", "version", "id", "note"))
    out = ["THE PERSON YOU ARE\n" + fields,
           "THE TASK THEY WILL LATER DO (they have not seen the product yet)\n" + FLOW["task"],
           "1. BACKGROUND, free text, a few sentences each:\n" + "\n".join(f"- {k}: {q}" for k, q in SOURCES.items()),
           "2. EXPERIENCE. For each item give a number on this scale:\n" + "\n".join(LEVELS) + "\n"
           + "\n".join(f"- {e['id']}: {e['question']['en']}" for e in FLOW["experiences"]),
           "3. LANGUAGE. ui: what language are your phone and computer set to (English, Chinese, Spanish, Other). "
           "english, one of:\n" + "\n".join(f"- {k}: {v}" for k, v in ENGLISH.items()),
           "4. HABITS. For each, the index of the option (0, 1 or 2):\n" + "\n".join(
               f"- {i}: {q} " + " / ".join(f"{n}) {o}" for n, o in enumerate(opts)) for i, q, opts in TEND),
           "5. SEEING AND CLICKING. Index of the option:\n" + "\n".join(
               f"- {i}: {q} " + " / ".join(f"{n}) {o}" for n, o in enumerate(opts)) for i, q, opts in PERC),
           "6. careText: For this task, what would you most worry about getting wrong? A sentence or two.\n"
           "done: After you set something up, how do you usually make sure it really worked? All that apply, from: "
           + "; ".join(f"{k} = {v}" for k, v in DONE.items()) + ".\n"
           "doneMiss: If the confirmation you're waiting for never comes, what do you do? Index: "
           + " / ".join(f"{n}) {o}" for n, o in enumerate(MISS))]
    return "\n\n".join(out)


def schema() -> dict:
    idx = lambda n: {"type": "integer", "minimum": 0, "maximum": n - 1}  # noqa: E731
    return {
        "type": "object",
        "properties": {
            "background": {"type": "object", "properties": {k: {"type": "string"} for k in SOURCES}, "required": list(SOURCES)},
            "experience": {"type": "object", "properties": {e["id"]: idx(5) for e in FLOW["experiences"]},
                           "required": [e["id"] for e in FLOW["experiences"]]},
            "ui": {"type": "string", "enum": ["English", "Chinese", "Spanish", "Other"]},
            "english": {"type": "string", "enum": list(ENGLISH)},
            "tend": {"type": "object", "properties": {i: idx(len(o)) for i, _, o in TEND}, "required": [i for i, _, _ in TEND]},
            "perc": {"type": "object", "properties": {i: idx(len(o)) for i, _, o in PERC}, "required": [i for i, _, _ in PERC]},
            "careText": {"type": "string"},
            "done": {"type": "array", "items": {"type": "string", "enum": list(DONE)}},
            "doneMiss": idx(len(MISS)),
        },
        "required": ["background", "experience", "ui", "english", "tend", "perc", "careText", "done", "doneMiss"],
    }


def answer_file(role: dict, reply: dict, model_id: str) -> dict:
    group_of = {e["id"]: e["group"] for e in FLOW["experiences"]}
    source_of = {g["id"]: g["source"] for g in FLOW["groups"]}
    exp = {k: v for k, v in reply["experience"].items() if v}
    screen = {s["id"]: [] for s in FLOW["sources"]}
    for eid in exp:
        g = group_of[eid]
        if g not in screen[source_of[g]]:
            screen[source_of[g]].append(g)
    return {
        "kind": "sue-questionnaire", "version": 2, "flow": FLOW["name"],
        "filledAt": datetime.now(timezone.utc).isoformat(timespec="seconds"), "pageLanguage": "en",
        "answers": {
            "name": "AI " + role["id"].replace("role-", "").upper() + " · " + role["title"],
            "background": reply["background"], "screen": screen, "screenOther": {}, "answers": exp, "expNotes": {},
            "lang": {"ui": reply["ui"], "english": reply["english"]}, "vocab": {},
            "tendStory": "", "tendFollow": "", "tend": reply["tend"], "perc": reply["perc"],
            "careText": reply["careText"], "done": reply["done"], "doneMiss": reply["doneMiss"], "doneMissOther": "",
        },
        "researcher": {"care": []},
        "note": f"Filled by {model_id} role-playing {role['id']} (from data/roles/"
                f"{role['id'].rsplit('-', 1)[0] if role.get('individual') else role['id']}.json) with tools/ai_fill.py. "
                "No participant's answers were shown to the model.",
    }


# Asking for "this role" gets the role's average, and an average answers the middle option
# to almost every habit question (2026-10-08, both roles). So --people N first makes N
# specific individuals inside the role, who differ the way people in that role really
# differ, each with concrete "last time" episodes; each then answers from their episodes.
PEOPLE_SYSTEM = (
    "You write realistic individuals for user research. Real people in the same job differ: some rush and skip "
    "defaults, some check every field, some give up fast, some never stop, and many sit in between on some traits. "
    "Never describe the role's average; describe real individuals, in-between ones included as often as they really "
    "occur. Reply with JSON only."
)
# The first wording ("middle only when the episodes show it") swung to the ends: none of
# the five students was in-between on risk, though P2 is in-between on everything.
INDIVIDUAL_RULE = (
    "Answer as THIS individual, from their portrait and episodes: pick the option their episodes show, an end or the "
    "middle. Do not pick the middle just to be safe, and do not avoid it when it is what they do."
)


def people_text(role: dict, n: int) -> str:
    fields = "\n".join(f"- {k}: {v}" for k, v in role.items() if k not in ("kind", "version", "id", "note"))
    return (f"THE ROLE\n{fields}\n\nTHE TASK THEY WILL LATER DO\n{FLOW['task']}\n\n"
            f"Write {n} different individuals who all fit this role. Keep the role facts, but let them differ the way people "
            "in this role really do: how carefully they read pages and check form defaults, how patient they are, how much "
            "risk they take with unfamiliar buttons, and how they make sure a setup worked. Make the mix realistic for this "
            "role (say which traits are common in it and which are rare), not evenly spread; a person can be at an end on "
            "one trait and in between on another. For each give a short portrait "
            "(work pressures, habits) and three concrete episodes from the last time they: met a button they didn't understand "
            "on a new website; couldn't find a feature; met a form option they didn't understand.")


def people_schema(n: int) -> dict:
    person = {"type": "object", "properties": {"label": {"type": "string"}, "portrait": {"type": "string"},
                                               "episodes": {"type": "array", "items": {"type": "string"}}},
              "required": ["label", "portrait", "episodes"]}
    return {"type": "object", "properties": {"roleTraits": {"type": "string"},
                                             "people": {"type": "array", "items": person, "minItems": n, "maxItems": n}},
            "required": ["roleTraits", "people"]}


def main(path: str, people: int = 0) -> None:
    from google import genai
    from google.genai import types

    role = json.loads(Path(path).read_text(encoding="utf-8"))
    load_env()
    config = load_config()
    model_id = config["model"]["id"]
    client = genai.Client(api_key=require_env("GEMINI_API_KEY"))

    def ask(system: str, text: str, shape: dict) -> dict:
        reply = client.models.generate_content(
            model=model_id, contents=text,
            config=types.GenerateContentConfig(system_instruction=system, temperature=0.0, response_mime_type="application/json",
                                               response_json_schema=shape))
        return json.loads(reply.text)

    base = role["id"].replace("role-", "ai-")
    if not people:
        out = ROOT / "data" / "answers" / (base + ".json")
        out.write_text(json.dumps(answer_file(role, ask(SYSTEM, questionnaire_text(role), schema()), model_id),
                                  ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(out.relative_to(ROOT))
        return
    made = ask(PEOPLE_SYSTEM, people_text(role, people), people_schema(people))
    (ROOT / "data" / "roles" / (role["id"] + "-people.json")).write_text(json.dumps(made, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for i, p in enumerate(made["people"], 1):
        who = {**role, "id": f"{role['id']}-{i}", "title": f"{role['title']} ({p['label']})",
               "individual": p["portrait"], "lastTimeEpisodes": " | ".join(p["episodes"])}
        reply = ask(SYSTEM + " " + INDIVIDUAL_RULE, questionnaire_text(who), schema())
        out = ROOT / "data" / "answers" / f"{base}-{i}.json"
        out.write_text(json.dumps(answer_file(who, reply, model_id), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(out.relative_to(ROOT), "·", p["label"])


if __name__ == "__main__":
    args = sys.argv[1:]
    n = 0
    if "--people" in args:
        i = args.index("--people")
        n = int(args[i + 1])
        args = args[:i] + args[i + 2:]
    for p in args:
        main(p, n)
