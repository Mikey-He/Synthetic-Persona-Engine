# Project rules for the coding agent

This repository builds a research prototype of a cloud billing budget task. Humans and screenshot-based AI agents complete the same task, and the platform records what they do. Accuracy of the recorded data matters more than polish.

## Read before every task

- `docs/design-guide-v2.md` is the source of truth for behavior.
- `docs/build-plan.md` defines architecture, data model, event names and milestones.
- `docs/prototype-design-a-b.md` defines what each screen looks like and says.
- `VERSION_A_BUILD_PROMPTS.md` holds the step you are asked to build.

If two documents disagree, the design guide wins. If the guide is silent or unclear, stop and ask. Do not guess.

## Hard rules

1. Build only the step you were given. Do not start the next one.
2. Do not add features, pages, buttons or UI text that the documents or the prompt do not specify. If a screen needs text that is not written anywhere, stop and ask.
3. Starting values come only from `lib/fixtures/defaults-v2.json` (defaults-v1 stays frozen for earlier sessions). Never prefill the task answer (Atlas only, $1,000, 80% actual, project owner only).
4. The variant (A or B) must never appear in the URL, the DOM, the page title, CSS class names or client-side bundles sent to participants. The server reads it from the session record.
5. The create route is the only place that branches on variant. Nothing else may branch on it.
6. The evaluator in `lib/evaluator/` is a pure function. No database, network, clock or randomness inside it.
7. Event names must match the table in `docs/build-plan.md` exactly.
8. Never change `lib/fixtures/*.json` or the task text without being asked. A fixture change means a new version file and a line in `docs/CHANGELOG.md`.
9. No Google logos or product marks. The product name shown is "Cloud Console (prototype)".
10. No personal data. Participants are stored under random IDs. Never store a participant's name or email.
11. Secrets live in environment variables. Never commit `.env` files, API keys or passwords.
12. All displayed dates and costs come from the fixture. Never use the real current date in anything a participant sees.
13. The synthetic agent (AI engine) is built outside this repository (decision of 2026-10-02). Do not add an agent runner here. This repository is the platform only: versions A and B, the researcher console, the evaluator and the research records. Synthetic sessions connect through the researcher console API described in `README.md`.

## Finish every task the same way

1. Run `npm run check` (set up in Step 0). Fix every failure before reporting.
2. List every file you created or changed.
3. Add one line to `docs/CHANGELOG.md` in the form `YYYY-MM-DD · step N · what changed`.
4. Say plainly anything you could not do or had to assume.
