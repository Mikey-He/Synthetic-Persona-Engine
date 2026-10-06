# Synthetic User Engine

A project of Cornell INFO 5900 with Google UX Insights (Synthetic Persona & UAT Platform). Mikey owns the data science part. This repo builds the synthetic user engine: an AI agent that sees only screenshots and operates Version A the way one specific person would.

## Read these first

- `docs/engine-design.md`: the full design. Read it before writing any code.
- `data/version-a/flow.json`: the workflow definition (task, screens, steps, key settings, experience questions, knowledge items). The questionnaire and the Persona Builder both read it; `tools/sync_flow.py` copies it into them.
- `tools/questionnaire.html`: the participant questionnaire. `tools/persona-builder.html`: turns an answer file into a persona card.
- `data/answers/*.json`: each participant's answers, with the researcher's worry mapping and any calibration adjustments.
- `data/personas/*.json`: the cards the engine runs. mikey, joy and aryan are people; blank-card and full-card are the self-test cards.
- `archive/`: the retired knowledge workbench and the original answer files. Do not build on them.

## Rules that must not be broken

1. The prompt carries no persona and no personality. The model sees only the processed screenshot, the visible element list, the items the person knows and the task, and only lists candidates with evidence.
2. Which action to take, whether a click misses, whether a turn is wrong, whether to stop and whether the task succeeded are all decided by code, by fixed rules.
3. The model's word does not count; evidence does. Evidence is checked against the knowledge list, and quoted text must really be on screen.
4. Do not change Version A's interface or behaviour. Word swapping and blurring are injected into the engine's own browser. Version A only gets marks, a status API and logs.
5. Fixed rules, no randomness. Every threshold and number lives in one config file and is marked as a placeholder.
6. Every step records which rule decided it.
7. Session memory is required: an action tried is not retried, and help understood during the test counts as learned.
8. "The most alike" is computed by code from literal word overlap and prominence, never judged by the model.
9. Only Google-approved Gemini models, only simulated data, no real personal or company information.

## How to work

- Reply to Mikey in Chinese, in plain words, conclusion first, with reverse thinking: how this could fail and what it assumes. Everything written into the repo (code, logs, docs, cards) is in English.
- No em-dashes. No "A, B and C" triple lists. Few colons introducing sentences.
- Discuss rule or design changes with Mikey first; once agreed, update `docs/engine-design.md` at the same time.
- After each phase, run the blank card and the full card first; only when both behave, run real personas.
- The development plan is section 8 of `docs/engine-design.md`.
