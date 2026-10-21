# Synthetic User Engine · code

The design is `../docs/engine-design.md`; its rules win over anything here. Every number lives in `config.toml` and is a placeholder.

## Setup

```sh
cd engine
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
cp .env.example .env   # fill in ADMIN_PASSWORD (the local platform's researcher password) and GEMINI_API_KEY
```

Playwright is 1.63.0, the same version as the platform, so both share the installed browsers.

## From questionnaire to run

1. The participant fills in `tools/questionnaire.html` (English, with a 中文 switch) and sends back the answer file.
2. Save it as `data/answers/<code name>.json`.
3. Open `tools/persona-builder.html`, load the answer file, map the participant's worry to at most two key settings, and download the card into `data/personas/`. Or build every card at once with `node tools/build_cards.js`, which runs the same page (it reads the mapping from the answer file's `researcher` block).
4. Run the engine on the card, at the participant's window size: `python -m sue.run --card <code name> --like-session <their session id>`.
5. Compare with the participant's own session: `python -m sue.compare --person <their session id> --engine <run folder>`.

Both pages read the workflow definition `data/version-a/flow.json`. After changing it, run `python tools/sync_flow.py` and rebuild the cards.

## A new workflow

Nothing in the engine's code or `config.toml` names Version A, and the product does not have to be ours. A workflow is one folder with its `flow.json`; its `engine.target` says where it runs:

- **`uat`** (or no target): our UAT platform, which keeps the engine's contract (below). Version A runs here.
- **`web`**: any web product, as it is. The engine opens `start` in a fresh browser, signs in as the test account named by `login` (the user and password live in `engine/.env`; flow.json only names the variables), calls `reset` first so earlier runs leave nothing behind, draws the task bar with its I'm finished button **below** the page instead of inside it (`screen.Strip`: the page's window is shorter by the bar, as on our platform, so nothing of the product is covered), puts the item marks on the page itself from each item's `locate` and `explainedBy`, keeps the steps in its own log, and grades the run with the flow's `success` checks: a field in a JSON answer the product gives (`json`), words on a page (`text`), or the final address (`url`). Use a test environment, never the live product: the engine really clicks Save.

**What a product may be made of** (each has a test page in `tests/fixtures/apps` and a whole run in `tests/test_capabilities.py`):

| The product has | What the engine does |
|---|---|
| A native dropdown (`<select>`) | Its options are listed for the model; action `choose` sets it the way the browser does |
| Enter, Escape, arrow keys | Action `press` |
| A menu that opens under the mouse | Action `hover` |
| Drag and drop | Action `drag` (value: the element it is dropped on) |
| A file to upload | The file picker gets the task's sample file (`engine.files`, else a small sample of each kind) |
| A file to download | Saved in the run folder; a `download` check can match it |
| Web components (shadow DOM, closed too) | Read and rewritten like the page; closed roots are opened as they are created |
| Embedded frames (payment forms, widgets) | Read and rewritten like the page; clicks land in them |
| A link that opens a new tab | He follows it; Back from its first page closes it |
| A panel that scrolls inside the page | Scrolling happens over the panel |
| Text drawn on a canvas (Figma prototype, map, editor) | OCR reads the screenshot (`sue/vision.py`), paints made-up words over unknown ones, and offers the text as places to click |
| A Chinese interface | Chinese words are segmented and masked by the persona's level of Chinese (`persona.lang.chinese`, `top_n_zh`) |
| Single sign-on, a second sign-in step | `login: {"mode": "session"}`: the researcher signs in once while recording; runs reuse it and say when it has expired |
| No reset address | `setup` and `cleanup` steps the engine replays before and after each run, and `{run}`: a value of each run's own in the task, the path and the checks |
| A CAPTCHA | Cannot be passed: turn it off in the test environment (the capability check says so) |

The extra actions are offered only to a workflow that uses them (`engine.actions`; a web product gets them all), so Version A's prompt is unchanged word for word.

**What the task leaves behind** (`engine.outcome`): `change` (something saved, checked in what was saved), `answer` (he finds something out and reports it; an `answer` check compares it), or `place` (he reaches a page). For an answer or a place he stops when he sees it himself: code checks the model's quote is on screen and readable to him.

**The easy way: the platform.** `server.py` (below) has a Workflows page: give the start page, the task and the test account; a browser window opens and you do the task once (`sue.record`); Gemini drafts the flow from the recording (`sue.draft`); you review every part (steps with their screenshots and the control each item is on, knowledge groups, questionnaire, success checks); then the checks run (`sue.check`). Only a workflow whose current flow passed its checks can be tested. The same from the command line:

```sh
.venv/Scripts/python -m sue.record --start https://staging.example.com/home --out ../data/workflows/x/recording --login-url /login --user X_USER --password X_PASSWORD --reset /api/reset
.venv/Scripts/python -m sue.draft --recording ../data/workflows/x/recording/recording.json --basics ../data/workflows/x/basics.json --out ../data/workflows/x/flow.json
.venv/Scripts/python -m sue.check --flow ../data/workflows/x/flow.json [--with-model]
```

What can be read off the recording is never left to the model: screens and routes, the order of actions, the scripted success path, which control each item is on and its locator (the simplest one that finds that control alone, `sue/locate.py`), the start page and the sign-in. The model drafts what needs judgement: step names, the knowledge items, experiences and their questions in English and Chinese, knowledge groups, which buttons commit, data words and the success checks (it sees the requests the product made, so it can check what was saved).

**The checks** (`sue.check`): the flow can drive the engine; runs cannot see each other's data (a reset, a clean-up, or values of the run's own); the blank card on the scripted path is not graded a pass (else the items block nothing; it runs first, so it cannot find what the full card saved); the full card is; every locator found its control where the path goes, once, word for word; and, with `--with-model`, the full card passes with the model. `--card full` and `--card blank` are each workflow's own self-test cards, built from its flow (`sue/selfcards.py`; for Version A they are the Persona Builder's).

**Item locators.** `"locate": {"text": "Invite people"}` finds the control by what a person reads; add `role`, `region` (nav, main, aside, header, footer, dialog), `group` (the heading of its menu group or fieldset), `label` (an icon's name), `match` (exact, contains, starts), `nth`, `route`, or a CSS `selector` as a last resort. A locator applies on its step's screen route unless it names its own. A looser match counts only when it finds one control. Every run reports locators that found nothing, found more than one control or only matched loosely (`summary.json`, `marks`).

**By hand.** Copy a flow.json as a template:

| Part | What it says |
|---|---|
| task, screens (with `route`), steps, items (with `locate`), experiences, groups | The workflow itself: what the person must know at each step |
| `knowledgeGroups` | How Persona Studio sets knowledge (see below) |
| `engine.target` | Where it runs: `uat`, or `web` with start, login, reset and success |
| `engine.created` | What the task makes, as the list shows it (Version A: `budget`); the model is asked whether the list has one. `engine.createdArticle` when the first letter misleads (`a user`) |
| `engine.routes.path` / `.list` | The pages on the success path (any other page is a wrong turn), and the page that lists what was made |
| `engine.labels.consequential` / `.advancing` | Buttons that commit (Finish, Save, Cancel) and buttons that move on (Next) |
| `engine.items.entry` / `.help` / `.review` | The items that say where the entry is, that a help icon explains, and that open a saved item to check it |
| `engine.words.dataTerms` / `.forceFake` | Data always shown as it is (names, ids), and jargon always swapped |
| `engine.compare.fieldLabels` | Field names, cut off the platform log for comparing (UAT only) |
| `engine.grading` | Readable names for the UAT platform's grading checks, for the results page |
| `engine.plumbing` | The success path for `sue.plumbing` and the checks |

Then `python tools/sync_flow.py path/to/flow.json`: it refuses a flow the engine or Persona Studio cannot use. Every command takes `--flow path/to/flow.json` (or set `SUE_FLOW`); a card built for another workflow is refused.

**Our UAT platform's contract** (a fork of it keeps it): elements the task depends on carry `data-kl="<item id>"`, help text carries `data-kl-explains`, the test's own bar carries `data-kl-harness` with an "I'm finished" button, session URLs start `/s/<token>` (`platform.session_path`), and the researcher API (`/api/admin/login`, `sessions`, `agent-steps`, `result`, `end`, `exports/events.json`) returns what was saved under `saved` (or `budgets`) with its evaluation. Comparing with a person's own session (`sue.compare`, `--like-session`) needs this platform, which logs both the same way.

## The platform

`tools/persona-studio/server.py` is the platform: Tests, in four steps (what to test; do it once; tick what must be right at the end, read from what the product saved; the engine gets it ready, with the task step by step and what a person needs to know, which a sentence can correct), the full review under Advanced settings, Personas (describe one in plain words; Gemini drafts the settings, you fine-tune them, and the Persona Builder builds the card for the workflow being tested), Run test (several personas, several seeded runs each, with a live view) and Results (what went wrong, how often, for whom, and every run's report). It listens on 127.0.0.1 only and keeps every key in `engine/.env`.

```sh
.venv/Scripts/python ../tools/persona-studio/server.py    # opens http://127.0.0.1:8765/
```

## Persona Studio: personas without a participant

`tools/persona-studio/` (built by Joy, merged 2026-10-19) makes persona cards per role instead of per participant: pick a role, set the traits as 0-10 scores, the states (fatigue, distraction, time pressure) and perception, or let AI propose varied personas from participant references. It saves sue-persona v3 cards into `data/personas/studio-*.json` and **Save & run 5 times** runs a card with five seeds through `sue.batch`, then shows what the runs add up to.

```sh
Its full editor is at `/studio` on the same server.

It uses the keys in `engine/.env` (GEMINI_API_KEY, ADMIN_PASSWORD). Its AI features call Gemini through its OpenAI-compatible endpoint unless `AI_*` settings say otherwise.

The knowledge groups (which items move together when you set "Billing terminology" or "Concepts") come from the workflow's `flow.json` (`knowledgeGroups`), not the Studio's code. For another workflow: write its flow.json with its groups, run `python tools/sync_flow.py path/to/flow.json` (it refuses groups that miss or repeat an item), then start the Studio with `--flow path/to/flow.json`.

## Running

```sh
.venv/Scripts/python -m pytest                          # unit tests; no network (test_page_marks.py uses the browser)
.venv/Scripts/python -m sue.run --card full --watch     # a real run with the watch window; calls Gemini (GEMINI_API_KEY in .env)
.venv/Scripts/python -m sue.plumbing --card full --watch
.venv/Scripts/python -m sue.smoke --cards blank full mikey --path "Budgets & caps" "Create new"
.venv/Scripts/python -m sue.compare --person <the person's session id> --engine <folder under runs>
.venv/Scripts/python -m sue.run --card <card> --seed 3           # slips and in-between scores drawn from seed 3 (v3 cards)
.venv/Scripts/python -m sue.batch --card <card> --runs 5 --like-session <session id>   # seeds 1-5, counted together
```

**Watch mode `--watch`.** One window with two columns. The left column streams the engine's browser live (the engine's own browser has no window), with a line above it saying what the engine is doing (reading the screen and swapping words, waiting for the model, checking evidence and choosing, acting). The pointer is drawn in this column, moves to its target and then clicks, leaving an orange ripple. The right column is the live log: each step's time, page, the model's candidates and reasons, how code rated each piece of evidence (sure, half or void), which rule decided, and what was done. Click any step on the right to see the screenshot they saw at that step; "Back to live" returns. When the run ends, the bottom of the right column shows why it stopped, the platform's grading, the missed defaults and where the files are; close the window to finish. The pointer is only ever drawn in the watch window, never in the screenshots the model gets. Without `--watch` there is no window and the files are the same.

After each run, `runs/<time>-<card>/` holds `report.html` (the whole run; open it in a browser, same as the right column), `steps.jsonl` (one line per step), `summary.json` (the result), `run.json` (the card, model and config) and a screenshot per step from `step_001.png`.

The last three commands need the local platform running (`npm run open:a` in the platform repo starts it). Each run opens a new synthetic session on the platform and keeps its screenshots and logs in `runs/`.

- `sue.run`: one full run. One line per step in `steps.jsonl`; `summary.json` holds why it stopped, the platform's grading, how often each rule fired, the items learned during the test, the missed defaults (error events) and any items seen on screen that the platform did not mark.
- `sue.plumbing`: no model. A script that finds buttons by their text walks Version A's success path; everything else is real. It proves the pipeline works, not that the engine behaves like a person. The full card should pass the platform's grading and the blank card should be stopped.
- `sue.smoke`: shows how each card sees each screen, without choosing or clicking.
- `sue.compare`: lines up the engine's run and the person's session from the platform event logs, prints them side by side, computes content (recall, precision), order, first-touch order and saved settings, and writes `compare.json` into the run folder. Pilot sessions: Mikey `cmut8m8290000pk7stzauis43`.

## Modules

| File | What it does | Design doc |
|---|---|---|
| `sue/config.py` | Reads `config.toml` and `.env` | 2 |
| `sue/persona.py` | Reads a card built by the Persona Builder | 3, 6 |
| `sue/words.py` | What each word looks like to them: made-up words, items, off-list words, data | 4.1 |
| `sue/page_script.js` | Injected into the page: collects text, writes the swapped words back, grays icons, reads clickable elements | 4.1 |
| `sue/screen.py` | Reads the screen, swaps words, takes screenshots, checks the swap, acts | 4 steps 1 to 3 and 7 |
| `sue/evidence.py` | Turns evidence into sure, half or void; checks quotes | 4.3 |
| `sue/memory.py` | Session memory: actions tried, items learned during the test, dead ends | 4.5 |
| `sue/attention.py` | Field of view: one piece at a time, in reading order | 4.8 |
| `sue/similarity.py` | "Most alike": how many words an element shares with the task | 4.3 |
| `sue/completion.py` | Done yet: checking the list, reviewing after saving, the expectation missed | 4.6 |
| `sue/compare.py` | Comparison with the person's own session | 5 |
| `sue/viewer.py`, `viewer.html` | Watch window and report | 8 |
| `sue/choose.py` | Drops candidates, picks an action, records which rule decided | 4.3 |
| `sue/prompt.py` | The model's input (no persona) and its fixed output format | 4.2 |
| `sue/model.py` | Calls Gemini; also a script model for tests | 4.2 |
| `sue/run.py` | The main loop that ties the steps together, and the stopping rules | 4 |
| `sue/platform.py` | The platform's researcher API, including the final result | 7 |
| `sue/runlog.py` | One log line per step | 5 |
| `sue/variability.py` | Traits as 0-10 scores, fatigue, time pressure, distraction, unnoticed warnings, perception; all seeded | 4.9 |
| `sue/batch.py` | Several seeded runs of the same cards, counted together | 4.9 |
| `sue/workflow.py` | Reads a flow.json into the engine's settings; refuses one that cannot drive it | 6 |
| `sue/target.py` | Where a run happens: our UAT platform or any web product; sign-in, reset, grading | 6.3 |
| `sue/locate.py` | Item locators, built and checked on a recorded screen | 6.3 |
| `sue/selfcards.py` | Each workflow's full and blank self-test cards, from its flow | 6.3 |
| `sue/record.py` | Records a researcher doing the task once | 6.3 |
| `sue/draft.py` | A draft flow.json from a recording | 6.3 |
| `sue/check.py` | The checks a workflow passes before it is used | 6.3 |
| `sue/vision.py` | Text read off a canvas with OCR, and painted over | 6.3 |

Phase 1 wired the knowledge list and session memory. Phase 2 wired the tendencies (risk, detail split into finding and checking a form, patience), "most alike", the field of view, reviewing after saving, the expectation missed and missed defaults. Phase 3 (2026-10-19) made the tendencies scores and added the states, slips and perception, seeded; questionnaire (v2) cards run exactly as before.

## Never

The model gets only the processed screenshot and the element list code picked; it never reads the DOM. Code reads the DOM only to change the screen and to judge. The element list holds only text a person can see; invisible text such as `aria-label` and `title` never reaches the model. The one exception is a button with an icon and no text: it is named by what it shows (its `aria-label`), then swapped through their vocabulary like any other word (design doc 4.1).
