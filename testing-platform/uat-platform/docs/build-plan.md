# Synthetic User UAT Platform Build Plan

Sep 29, 2026 · @HCF

## What we are building

We are building one web platform with two sides. The participant side is the cloud billing prototype in variants A and B. The research side runs sessions and scores results, and it also drives synthetic users and exports data.

The Design and Build Guide (v2) defines what the prototype must do. This plan defines how to build it. When the two disagree, the guide wins.

| Actor | What they do | What they must never see |
| --- | --- | --- |
| Human participant | Completes the budget task in A or B | Variant labels and evaluator results |
| Synthetic agent | Completes the same task from screenshots with mouse and keyboard | Page code or the accessibility tree. Stored state and researcher pages are off limits too. |
| Researcher | Creates sessions and assigns variants. Reviews sessions and exports data. | Nothing is hidden |

The platform is built with vibe coding. Every section below is written so a coding agent can build it one milestone at a time.

## System overview

The participant app is the only thing both humans and the agent touch. The agent reaches it through a real browser, so it can never read page code or stored state.

> Diagram (see the online doc). The participant app is the only surface humans and the agent touch. The researcher console and the evaluator sit behind the API. The Python agent runner reaches the app only through a real browser and writes its step log to the API.

The agent runner writes its own step log straight to the API, beside the events the app records. The evaluator runs inside the API and reads saved budgets only.

## Recommended tech stack

Use one TypeScript web app for everything people touch, and one Python runner for synthetic users. This split keeps the agent physically unable to read page code.

| Layer | Choice | Why |
| --- | --- | --- |
| Web app | Next.js (App Router) with TypeScript | Participant pages and researcher pages share one codebase with the API routes. Coding agents handle this stack well. |
| Styling | Tailwind CSS with Roboto from Google Fonts | Fast to match dense console layouts. Roboto is openly licensed. |
| Database | Postgres through Prisma, hosted on Neon or Supabase. SQLite for local development. | Typed schema and migrations. Simple exports. |
| Hosting | Vercel | Remote participants need a public URL. Researcher pages sit behind a password. |
| Agent runner | Python 3.11 with Playwright | Screenshot capture and coordinate control with no page-code access |
| Model access | A small adapter per approved model | Swap models without touching the loop |
| Human session replay | rrweb, optional | Researchers can replay a human session beside its event log |
| Tests | Vitest for scoring logic. Playwright Test for critical paths. | A scoring bug is the most expensive bug in this project. |

Set the study viewport to 1440 × 900 at 100% zoom everywhere. The agent runner uses the same size with a device scale factor of 1.

## Repository structure

This repository holds the web app only. The agent runner is built in a separate project (decision of 2026-10-02) and never imports app code.

```
uat-platform/
  docs/
    design-guide-v2.md        source of truth for behavior
    build-plan.md             this document
    CHANGELOG.md              one line per build version
  app/
    s/[token]/                participant routes (task bar + console)
    admin/                    researcher console (password protected)
    api/                      route handlers
  components/
    console/                  console-style layout, stepper, form controls
    advanced-form/            version A: ReferenceCreateForm with Define, Scope, Amount, Actions
    guided-setup/             version B: GuidedSetup and its screens
    budget-shared/            draft, setters and save shared by both flows
                              (no "variant-a"/"variant-b" names: dev chunk names would carry the variant)
    taskbar/                  task text and I'm finished button
  lib/
    fixtures/                 fixture-v1.json, defaults-v1.json, defaults-v2.json
    domain/                   budget types, validation, resolveRecipients
    evaluator/                evaluate() and its tests
    events/                   client logger and event type list
  prisma/
    schema.prisma
  tests/
    acceptance/               Playwright tests for Part 12 cases
  scripts/
    open-session.ts           npm run open:a / open:b, a local test session in the browser
  launch/                     double-click versions of open:a and open:b (Windows)
```

Put both project documents in `docs/` as Markdown. Tell the coding agent to read them before every milestone.

## Data model

Every row hangs off a session. A session is one attempt by one actor, human or synthetic.

| Table | Key fields | Notes |
| --- | --- | --- |
| Participant | id, familiarity\_band, screening (json), consented\_at | Pseudonymous. No names or emails. |
| Session | id, token, actor\_type, participant\_id or agent\_run\_id, variant, dataset\_label, fixture\_version, build\_version, task\_version, reference\_capture\_id, viewport, zoom, started\_at, ended\_at, termination\_reason | The token is opaque and never reveals the variant |
| BudgetDraft | session\_id, draft (json), updated\_at | One live draft per session |
| Budget | id, session\_id, version, config (json), saved\_at | A new version row on every save keeps edit history |
| Event | id, session\_id, seq, client\_ts, server\_ts, type, target, payload (json), screenshot\_ref | Append only |
| AgentRun | id, model\_id, prompt\_version, persona\_id, calibration\_id, temperature, started\_at | One per synthetic session |
| AgentStep | id, session\_id, step\_no, screenshot\_path, action (json), reason, executed, error\_label, latency\_ms | Includes attempts that changed nothing |
| CalibrationConfig | id, source\_label, content (json), content\_hash, frozen\_at | Frozen before any evaluation\_B data is viewed |
| Evaluation | session\_id, budget\_id, criteria (json), overall\_success, resolved\_recipients (json), recipient\_mechanisms (json), evaluator\_version | Researcher view only |
| SurveyResponse | session\_id, instrument, answers (json) | Humans only |
| FixtureVersion | id, content (json), content\_hash, frozen\_at | Also stores the defaults record |

The draft and the saved budget share one configuration shape. The evaluator reads that same shape.

```ts
type BudgetConfig = {
  name: string;
  kind: 'alerts_only';
  scope: {
    allProjects: boolean;          // true = entire account
    projectIds: string[];          // explicit selection
    savings: string[];             // savings types included
    readOnlyForProjectUsers: boolean;
  };
  period: 'monthly' | 'quarterly' | 'yearly' | 'custom';
  customRange?: { from: string; to?: string };
  amount: { type: 'specified' | 'last_period'; target?: number };
  thresholds: { percent: number; trigger: 'actual' | 'forecasted' }[];
  recipients: {
    billingAdminsAndUsers: boolean;
    projectOwners: boolean;        // only offered for single-project scope
    monitoring: { linked: boolean; projectId?: string; channelIds: string[] };
    pubsubTopic?: string;
  };
};
```

## Participant app

Every participant route sits under an opaque session token. The server reads the variant from the session record, so nothing in the URL or on screen reveals it.

| Route | Screen | Notes |
| --- | --- | --- |
| /s/\[token\] | Consent and instructions | Humans only. Agent sessions start at the overview. |
| /s/\[token\]/billing | Billing overview | Starting state for every attempt |
| /s/\[token\]/billing/budgets | Budgets & alerts list | Create budget entry point |
| /s/\[token\]/billing/budgets/create | Create budget | A shows Define → Scope → Amount → Actions → Finish. B shows the seven guided screens. |
| /s/\[token\]/billing/budgets/\[id\] | Saved budget | View and edit |
| /s/\[token\]/billing/account | Account management | Read-only member list from the fixture |
| /s/\[token\]/stub/\[area\] | Out-of-study placeholder | For notification channels and any other reachable link |
| /s/\[token\]/done | Post-task questions | Humans only |

### Task bar

A fixed bar sits above the console frame on every participant page. It shows the whole task text at all times, with no collapse toggle, because the guide requires the task text to stay visible. Its I'm finished button records completion and ends the attempt for both actor types.

### Draft and save behavior

1. Every field change updates local state at once.
2. The change is logged as an event with its old value and new value.
3. The draft is saved to the server after 500 ms without further changes.
4. Back navigation inside the create flow keeps the draft.
5. Finish validates, then writes a new Budget version and a save event.
6. A failed save logs a save attempt with the validation messages shown.

### Variant switch

The create route renders `GuidedSetup` instead of `ReferenceCreateForm` when the session variant is B. Nothing else branches on the variant. Keep that single branch point so reviewers can confirm A and B differ in one place.

### Viewport gate

If the window is smaller than 1440 × 900, show a message asking the participant to enlarge it. Log the actual viewport at session start and on every resize.

## Version B component

`GuidedSetup` is a seven-screen flow that writes into the same BudgetDraft as the A form. It reuses A's field setters and validation, so both variants save the same configuration shape. Guide Part 14.4 defines every screen.

```tsx
// components/guided-setup/GuidedSetup.tsx
const SCREENS = ['name', 'projects', 'period', 'amount', 'alerts', 'recipients', 'review'] as const;

export function GuidedSetup({ draft, setField, save, log }: Props) {
  const [step, setStep] = useState(0);
  useEffect(() => { log('screen_viewed', { screen: SCREENS[step], index: step + 1 }); }, [step]);
  // Screens 1 to 6 edit draft fields through the same setField() the A form uses.
  // Screen 7 shows a plain-language summary with an Edit link per line.
  // Edit jumps to that screen, and Continue then returns to review.
  // Create budget calls the same save() as Finish in A.
}
```

| Screen | Writes to | Starts at |
| --- | --- | --- |
| 1 Name | name | Empty |
| 2 Projects | scope.allProjects, scope.projectIds | Reference default |
| 3 Period | period, customRange | Monthly |
| 4 Amount | amount | Specified, target empty |
| 5 Alerts | thresholds | 50% / 90% / 100% actual |
| 6 Recipients | recipients.billingAdminsAndUsers, recipients.projectOwners | Billing admins and users checked |
| 7 Review | Nothing. Read-only summary. | Not applicable |

### Rules for the coding agent

- Every screen starts from the reference defaults record, never from the task answer.
- Reuse A's field setters and validation. Saving goes through the same function as A.
- Settings B does not ask about keep their reference defaults on save.
- No "recommended" labels and no warning colors. No copy mentions the task.
- Continue buttons name the next screen, such as "Continue to amount".
- There is no switch to the advanced form.
- The recipients screen lists names under each option, taken from the fixture.

Write a test that enters the correct Atlas configuration through the A form and through `GuidedSetup`. Both saved configurations and both evaluations must be identical.

## Event logging

The web app logs the same events for humans and agents. The agent runner adds its own step log on top, joined by session ID.

### How the client logger works

1. Each event gets a per-session sequence number and a client timestamp.
2. Events are batched and sent every 2 seconds, and with `navigator.sendBeacon` when the page hides.
3. The server adds its own timestamp and stores events append-only.
4. A global click listener logs clicks that land on no interactive element as `click_no_effect`.
5. Scroll events are throttled to one per 500 ms and store the scroll position.

### Event types

| Type | Fires when | Payload |
| --- | --- | --- |
| session\_started | The first participant page loads | Viewport / zoom / user agent |
| page\_viewed | Any route renders | Route and referrer route |
| step\_entered | A only. A create-form section opens | Section name, first entry or return |
| screen\_viewed | B only. A guided screen opens | Screen number and name |
| setting\_reached | A setting first enters the viewport in A, or its screen opens in B | Setting name and current value |
| field\_changed | Any form value changes | Field / old value / new value |
| setting\_returned | The user comes back to a setting already visited | Setting name and route taken |
| option\_cleared\_by\_scope | A scope change removes a checked option | The cleared option |
| review\_edit | B only. Edit is used on the review screen | The setting edited |
| control\_clicked | Any button or link is clicked | Control label and route |
| click\_no\_effect | A click hits no interactive element | Coordinates and route |
| scroll | The page scrolls | Scroll position |
| validation\_shown | A validation message appears | Field and message text |
| save\_clicked | Finish in A or Create budget in B | Full draft snapshot |
| save\_attempted / save\_succeeded / save\_failed | A save runs | Budget ID or validation errors |
| budget\_reopened | A saved budget opens for editing | Budget ID |
| completion\_declared | I'm finished is clicked | None |
| session\_ended | Any termination | Termination reason |
| viewport\_changed | The window resizes | New size |

Keep event names exactly as written. Analysis code matches on them.

Agent steps live in the AgentStep table, not in Event. Each step stores its screenshot path and action JSON. The model's stated reason sits beside them.

## Evaluator

The evaluator is a pure function with no database or network access. It takes a saved budget plus the fixture and returns per-criterion results. It runs on every save and again on demand from the researcher console.

```ts
// lib/domain/resolveRecipients.ts, shared by the evaluator and both create flows
export function resolveRecipients(b: BudgetConfig, fx: Fixture): Recipient[] {
  if (b.thresholds.length === 0) return [];            // email settings disabled
  const out = new Map<string, Recipient>();
  if (b.recipients.billingAdminsAndUsers)
    fx.billingMembers.forEach(p => out.set(p.id, { ...p, via: 'billing_roles' }));
  const single = !b.scope.allProjects && b.scope.projectIds.length === 1;
  if (single && b.recipients.projectOwners)
    fx.projectOwners[b.scope.projectIds[0]].forEach(p => out.set(p.id, { ...p, via: 'project_owners' }));
  if (b.recipients.monitoring.linked)
    b.recipients.monitoring.channelIds.forEach(id => { /* fixture has no channels */ });
  return [...out.values()];
}
```

```ts
// lib/evaluator/evaluate.ts
export function evaluate(b: BudgetConfig, saved: boolean, fx: Fixture): Evaluation {
  const people = resolveRecipients(b, fx);
  const criteria = {
    scope: !b.scope.allProjects && same(b.scope.projectIds, ['atlas-demo']),
    period: b.period === 'monthly',
    amount: b.amount.type === 'specified' && b.amount.target === 1000,
    alert: b.thresholds.some(t => t.percent === 80 && t.trigger === 'actual'),
    recipients: people.length === 1 && people[0].id === 'sam-rivera',
    persistence: saved,
  };
  return { criteria, overall: Object.values(criteria).every(Boolean), people, version: EVALUATOR_VERSION };
}
```

### Tests to write before the evaluator

Each case from Part 12 of the guide becomes one Vitest test. Write the tests first and have the coding agent make them pass.

- [ ] Required settings pass overall
- [ ] Default recipients left checked fail the recipient criterion with three people resolved
- [ ] Owners checked with billing roles cleared pass
- [ ] Entire-account scope fails scope
- [ ] A forecast-only 80% rule fails the alert criterion
- [ ] Extra thresholds beside the required rule still pass
- [ ] Zero thresholds resolve nobody
- [ ] Monitoring linked with no channel adds nobody
- [ ] The same configuration scores the same regardless of variant

Bump `EVALUATOR_VERSION` on any change and re-score stored sessions from the console.

## Researcher console

The console lives under `/admin` behind a password set in an environment variable. No participant page links to it, and the agent runner never receives its URL.

| Feature | What it does |
| --- | --- |
| New human session | Records screening answers and the familiarity band. Suggests the next variant from the assignment blocks. Returns the participant link. |
| New synthetic session | Picks model / prompt version / persona. Attaches a frozen calibration ID or none. Returns the token for the runner. |
| Assignment view | Counts of sessions per familiarity band and variant, per dataset label |
| Session list | Status / actor type / variant / termination reason |
| Session detail | Event timeline with screenshots or replay. Final configuration beside its evaluation. |
| Reset | Restores the baseline fixture for a new session. Completed records stay intact. |
| Re-score | Runs the current evaluator over stored sessions |
| Calibration freeze | Locks a calibration config and records its hash and time |
| Exports | Event JSON / session CSV / agent step CSV |
| Build info | Build version / fixture hash / evaluator version, shown on every page |

The console never shows evaluation results inside participant routes. It also blocks viewing evaluation\_B outcomes until a calibration freeze exists, which enforces the RQ2 hold-out.

## Synthetic agent runner

> Built outside this repository since 2026-10-02. This section stays as the specification for that project. The platform provides the interface it needs, documented in `README.md`:
>
> - synthetic sessions with model, prompt, persona, calibration and temperature recorded;
> - an API to record each step;
> - session status;
> - ending a session by a stop rule;
> - the `agent_steps.csv` export.

The runner is a Python loop. Each turn it shows the model a screenshot and performs the one action the model returns. It sees exactly what a person would see and nothing more.

### The loop

1. Open the participant link for the session at 1440 × 900, scale factor 1.
2. Wait for the page to settle, then take a screenshot.
3. Send the model the task text and the persona, plus any frozen calibration text. Add the last five actions with their reasons and the current screenshot.
4. Parse one action from the reply and perform it.
5. Save the step to AgentStep, including attempts that change nothing.
6. Repeat until the agent clicks I'm finished or gives up. A stop rule can also end the run.

### Action format

```json
{"action": "click", "x": 612, "y": 344, "reason": "Open Budgets & alerts"}
{"action": "double_click", "x": 612, "y": 344, "reason": "..."}
{"action": "type", "text": "1000", "reason": "..."}
{"action": "key", "key": "Tab", "reason": "..."}
{"action": "scroll", "dy": 400, "reason": "..."}
{"action": "wait", "ms": 1000, "reason": "..."}
{"action": "give_up", "reason": "..."}
```

There is no finish action. The agent ends a task the way a person does, by clicking I'm finished in the task bar.

### Allowed and forbidden browser calls

| Allowed | Forbidden |
| --- | --- |
| `page.goto` for the start link only | `page.content`, `page.evaluate` |
| `page.screenshot` | Locators and query selectors |
| `page.mouse` and `page.keyboard` | Accessibility snapshots |
| `page.wait_for_timeout` | Reading network responses |

Add a test that fails the build if any forbidden call appears in `agent-runner/`.

### Stop rules and labels

| Rule | Termination reason |
| --- | --- |
| Agent clicks I'm finished | completion\_declared |
| Agent returns give\_up | abandoned |
| 80 steps reached | step\_limit |
| 20 minutes reached | time\_limit |
| Six identical actions in a row | loop |
| Model or browser failure after two retries | technical\_error |

Label each technical failure with one code from invalid\_json / out\_of\_bounds / model\_timeout / browser\_error. A click that changes nothing is flagged as no\_visible\_change, which is not a technical failure.

### Personas

Write each familiarity profile as knowledge and habits someone could observe, never as instructions to make mistakes. Store each profile as a versioned text file.

- **Low familiarity.** Uses everyday web apps. Has never opened a cloud console and does not know what billing roles include.
- **Medium familiarity.** Has used a cloud console for small projects. Knows budgets exist but has rarely set alerts.
- **High familiarity.** Manages cloud costs regularly. Knows the difference between account roles and project roles.

Match the profile boundaries to the human familiarity bands in the guide.

### Calibration slot

A calibration config is text or examples derived from calibration\_A human sessions only. The runner loads it by ID and records that ID on the session. Freeze it in the console before any evaluation\_B outcome is viewed.

Outcome-level corrections, such as adjusting predicted success rates, happen in analysis code, not in the runner. Record them separately so the two kinds of calibration can be compared.

## Exports and analysis handoff

The console produces three files per export. Analysis happens outside the platform, in Python or R.

| File | Grain | Used for |
| --- | --- | --- |
| events.json | One object per event, grouped by session | Friction location and recovery analysis |
| sessions.csv | One row per session | Success rates and A/B comparison |
| agent\_steps.csv | One row per agent step | Separating technical failures from behavior |

The session CSV uses the column order below.

```csv
session_id,actor_type,variant,dataset_label,familiarity_band,model_id,prompt_version,persona_id,calibration_id,fixture_version,build_version,evaluator_version,termination_reason,overall_success,crit_scope,crit_period,crit_amount,crit_alert,crit_recipients,crit_persistence,resolved_recipient_ids,recipient_mechanisms,time_scope_ms,time_period_ms,time_amount_ms,time_alert_ms,time_recipients_ms,setting_returns,review_edits,n_events,n_saves,reopened_after_save,survey_satisfaction
```

Every export carries the build version and fixture hash in its file name. Two exports from different builds are never merged without an explicit note.

## Build milestones

Build in nine milestones, each small enough for one or two vibe coding sessions. Do not start a milestone until the previous one meets its done condition.

| # | Milestone | Done when |
| --- | --- | --- |
| M0 | Reference capture and fixture freeze. No code. | The guide's defaults record is complete and the fixture file has a hash |
| M1 | App shell with fixtures and the task bar | Every route renders. Every reachable link leads to a real page or a stub. |
| M2 | Version A create flow with draft and save | A person can save the correct budget by hand and reopen it |
| M3 | Evaluator and resolver, tests first | All evaluator tests pass |
| M4 | Event logging and sessions | A test session export contains every event type in the table |
| M5 | Researcher console | Sessions can be created and reset. Detail view and exports work. |
| M6 | Version B guided setup | Guide Part 14.9 checks pass. A and B save identical configurations. |
| M7 | Agent runner | One full agent run finishes with a complete step log. The forbidden-call test passes. |
| M8 | Acceptance run and pilot freeze | Every Part 12 case passes. Build version tagged and fixture hash recorded. |

The evaluator comes before logging on purpose. Scoring errors are the costliest mistake, and a tested evaluator catches flaws in the create flow early.

## Vibe coding playbook

The coding agent will build what you ask, and it will also add things you did not ask for. Most risk in this project comes from those additions, so every session starts from the documents and ends with a review.

### Session prompt template

```markdown
Read docs/design-guide-v2.md and docs/build-plan.md before writing code.
The design guide is the source of truth. If anything conflicts, stop and ask me.

This session builds milestone {M#}, {milestone name}.
It is done when {done condition from the milestones table}.

Follow these rules.
- Change only files needed for this milestone.
- Do not change fixtures or defaults. Do not change the task text.
- Do not add features or UI text that the guide does not specify.
- Every interactive control must emit the events listed in build-plan.md.
- Keep the evaluator pure, with no database or network calls inside it.
- Write or update tests first, then code until they pass.
- At the end, list every file you changed and add one line to docs/CHANGELOG.md.
```

Fill the braces from the milestones table and paste the whole block into the coding tool.

### Guardrails

- One milestone per session. Commit after each one with the build version in the message.
- Fixture or defaults changes create a new fixture version and a CHANGELOG line.
- The variant never appears in the DOM or the URL. The page title stays the same in both variants.
- The agent runner imports nothing from the web app.
- Any change to task text or scoring updates both project documents first.

### Review after every session

- [ ] Run the tests and the forbidden-call check
- [ ] Click through A and B at 1440 × 900 and compare them side by side
- [ ] Export one test session and confirm the new events appear
- [ ] Read the diff for added UI text that the guide does not specify
- [ ] Confirm the variant switch still lives in one place

### Example prompt for M2

```markdown
Build milestone M2, the version A create-budget flow.
Follow guide Parts 4 to 6 and the reference defaults record.
Sections run Define → Scope → Amount → Actions → Finish.
Prefill defaults exactly as the record says. The billing admins and users
email option starts checked. The project owners option appears only when
one project is selected, and it is cleared if the scope widens.
Save drafts after 500 ms of inactivity. Finish validates, then writes a new
Budget version. Reopening shows saved values.
It is done when a person can save the correct Atlas budget by hand and reopen it.
```

## Privacy and open decisions

The platform holds research data about real people, so treat it as sensitive even though every scenario value is fictional.

- Participants are stored under pseudonymous IDs. Names and emails never enter the database.
- Model API keys live in server or runner environment variables, never in client code or the repository.
- The researcher console sits behind a password. Rotate it after the study.
- Session replay, if used, masks every text input.
- Delete raw data on the schedule the study protocol sets.

### Open decisions

| Decision | Options | Needed before |
| --- | --- | --- |
| Database host | Neon or Supabase | M1 |
| Where human sessions run | Lab machine or remote with a size gate | Gate 1 pilot |
| Budget list at start | Empty, or one existing account-wide budget | M0 |
| Model for synthetic users | Any model the project agreement approves | M7 |
| Satisfaction instrument | One post-task ease item, or a short standard scale | Gate 1 pilot |
| Google marks in the prototype | Sponsor-approved marks or neutral placeholders | M1 |
| Ethics review | Confirm with course staff whether Cornell IRB review or an exemption determination applies | Before recruiting |
