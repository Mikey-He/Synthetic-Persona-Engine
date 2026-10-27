# Billing Config study page

One browser tab for a whole session with the UX team's Billing Config prototype. No server, no login:
the page ends with the participant's file, which the moderator downloads and sends to the data science
team. Persona Studio imports that file as it is.

## A session

1. **Start.** The moderator enters the participant ID (such as 001, never a name) and the participant
   confirms the consent form was gone through with them.
2. **Questionnaire**, about 5 minutes, English only. Every question sets something the engine reads:

   | Questions | Engine setting |
   | --- | --- |
   | Which of these have you used / done / studied, then how much for each (X01 to X07) | What they know: each knowledge item of the task, through the experiences that teach it (flow.json) |
   | Is English your first language? If not, their English level and the 50-word test | English level and vocabulary size (a first language skips both: fluent) |
   | R1, and R2 after the task | Willingness to try unfamiliar things (risk) |
   | P1, P2 | Patience |
   | D1 | Care when finding (detailFind) |
   | D3, and D2 after the task | Care when checking (detailCheck) |
   | W, after the task | Attention to warnings |
   | E | How pressure builds after setbacks, and stress tolerance |
   | V, C, M, S | Reading small text, colour, clicking small targets, reading speed |
   | How they make sure it worked, and what they do if no confirmation comes (after the task) | confirmBy, ifConfirmMissing |

   How an answer becomes a number is `synthetic-user-engine/synthetic-user-engine/engine/config.toml`
   (`[persona]`, `[persona.answers]`) and `tools/persona-builder.html`.
3. **The task.** The task bar with "I'm finished" on top, the prototype below (`app/`, see its
   `SOURCE.md`). `harness.js` logs pages, screens, clicks, field changes, saves and pop-up messages.
4. **A few last questions.** About the task just done, 1 to 5: how tired, how rushed, how focused (fatigue,
   time pressure, distraction). Then, about other apps in general, the five questions that would cue what
   the study observes if asked first (Shining, 2026-10-28): checking before confirming (R2), checking defaults
   (D2), noticing warnings (W), how they make sure it worked and what they do without a confirmation. Their
   answers go where the questionnaire keeps them, so the Persona Builder reads them as before.

   Rule for any question: if it measures a behaviour the study observes in the task (navigation errors,
   hesitation, double checking, attention to warnings, deciding it is done), ask it after the task.
5. **The file.** Download file (or Copy) gives `participant-<ID>.json`: the session, the questionnaire
   answers, the three answers, every event in order and what the prototype saved. "Start the next
   participant" clears the page for the next person.

The engine grades the file's saved state with the success checks in the workflow's flow.json (the UX
team's Test Procedure, section 10); the page itself does not grade, so participants cannot read the
criteria in its files.

## Running it

Published at **https://mikey-he.github.io/billing-config-study/** (GitHub Pages, repository
Mikey-He/billing-config-study, a copy of this folder). Open it in Chrome, full screen at 100% zoom. Each
participant's progress is kept in that browser only, so a reload continues where it was; nothing is sent
anywhere except by the prototype's own Clarity script.

To try it locally instead, serve this folder over http (opened as a file, the browser keeps the frames
apart), for example `python -m http.server 4200`, then open http://localhost:4200.

## Changing it

`questionnaire.html` and `study.js` (the task text) are written from the workflow's flow.json; never edit
them by hand. This folder is the source; after a change, copy it over the billing-config-study repository
and push, and GitHub Pages republishes in a minute or two. After changing the flow or `tools/questionnaire.html`, from
`synthetic-user-engine/synthetic-user-engine` run:

```
python tools/sync_flow.py data/workflows/billing-config-atlas-budget-ux-team/flow.json --platform billing-config
```
