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

Nothing in the engine's code or `config.toml` names Version A. A new workflow needs two things.

**1. Its own `flow.json`** (copy `data/version-a/flow.json` as a template):

| Part | What it says |
|---|---|
| task, screens, steps, items, experiences, groups | The workflow itself, as before: what the person must know at each step |
| `knowledgeGroups` | How Persona Studio sets knowledge (see below) |
| `engine.created` | What the task makes, as the list shows it (Version A: `budget`); the model is asked whether the list has one. `engine.createdArticle` when the first letter misleads (`a user`) |
| `engine.routes.path` / `.list` | The pages on the success path (any other page is a wrong turn), and the page that lists what was made |
| `engine.labels.consequential` / `.advancing` | Buttons that commit (Finish, Save, Cancel) and buttons that move on (Next) |
| `engine.items.entry` / `.help` / `.review` | The items that say where the entry is, that a help icon explains, and that open a saved item to check it |
| `engine.words.dataTerms` / `.forceFake` | Data always shown as it is (names, ids), and jargon always swapped |
| `engine.compare.fieldLabels` | Field names, cut off the platform log for comparing |
| `engine.plumbing` | The success path for `sue.plumbing` (optional) |

Then `python tools/sync_flow.py path/to/flow.json`: it refuses a flow the engine or Persona Studio cannot use, and copies it into the questionnaire and the Persona Builder. Every command takes `--flow path/to/flow.json` (or set `SUE_FLOW`); a card built for another workflow is refused.

**2. A platform that keeps the engine's contract** (a fork of the UAT platform keeps it): elements the task depends on carry `data-kl="<item id>"`, help text carries `data-kl-explains`, the test's own bar carries `data-kl-harness` with an "I'm finished" button, session URLs start `/s/<token>` (`platform.session_path`), and the researcher API (`/api/admin/login`, `sessions`, `agent-steps`, `result`, `end`, `exports/events.json`) returns what was saved under `saved` (or `budgets`) with its evaluation.

## Persona Studio: personas without a participant

`tools/persona-studio/` (built by Joy, merged 2026-10-19) makes persona cards per role instead of per participant: pick a role, set the traits as 0-10 scores, the states (fatigue, distraction, time pressure) and perception, or let AI propose varied personas from participant references. It saves sue-persona v3 cards into `data/personas/studio-*.json` and **Save & run 5 times** runs a card with five seeds through `sue.batch`, then shows what the runs add up to.

```sh
.venv/Scripts/python ../tools/persona-studio/server.py    # opens http://127.0.0.1:8765/; needs the platform running for Save & run
```

It uses the keys in `engine/.env` (GEMINI_API_KEY, ADMIN_PASSWORD). Its AI features call Gemini through its OpenAI-compatible endpoint unless `AI_*` settings say otherwise.

The knowledge groups (which items move together when you set "Billing terminology" or "Concepts") come from the workflow's `flow.json` (`knowledgeGroups`), not the Studio's code. For another workflow: write its flow.json with its groups, run `python tools/sync_flow.py path/to/flow.json` (it refuses groups that miss or repeat an item), then start the Studio with `--flow path/to/flow.json`.

## Running

```sh
.venv/Scripts/python -m pytest                          # unit tests; no network, no browser
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

Phase 1 wired the knowledge list and session memory. Phase 2 wired the tendencies (risk, detail split into finding and checking a form, patience), "most alike", the field of view, reviewing after saving, the expectation missed and missed defaults. Phase 3 (2026-10-19) made the tendencies scores and added the states, slips and perception, seeded; questionnaire (v2) cards run exactly as before.

## Never

The model gets only the processed screenshot and the element list code picked; it never reads the DOM. Code reads the DOM only to change the screen and to judge. The element list holds only text a person can see; invisible text such as `aria-label` and `title` never reaches the model. The one exception is a button with an icon and no text: it is named by what it shows (its `aria-label`), then swapped through their vocabulary like any other word (design doc 4.1).
