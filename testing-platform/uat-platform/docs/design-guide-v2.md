# Cloud Billing Prototype Design and Build Guide (v2)

Sep 29, 2026 · @HCF

## What changed in v2

Version B is now a guided setup that asks one question per screen, modeled on the simplified and advanced workflows in AWS Budgets. Earlier single-change options were dropped as too small to measure with the planned sample.

| Area | v1 | v2 |
| --- | --- | --- |
| Version B | Read-only scope summary during alert configuration | Guided one-question-per-screen setup that saves the same configuration (Part 14) |
| Fixtures | Atlas Project Owner only | Named billing account members plus a named owner for each project |
| Recipient scoring | Checkbox states | The set of people who would actually receive email |
| Notification channel route | Not addressed | Closed in the fixture and recorded as a deliberate simplification |
| Unscored fields | Budget name only | Budget name and savings settings |
| Friction comparison | By page | By setting, because A and B have different pages |
| Pilot | One pilot | Gate 1 checks A is a fair test. Gate 2 checks B before freezing. |
| Task text | Two slightly different versions across project documents | One exact version, used everywhere |

A stays faithful to the Google Cloud reference. B is a deliberate, larger design alternative, so the study compares an expert-style form with a novice-style guided flow.

## 1. Purpose and build scope

Build an interactive research prototype of a cloud billing budget task in two interface variants. Human participants and screenshot-based synthetic users work in the same interface.

The platform compares task completion between humans and synthetic users. It also compares where usability difficulties occur. Satisfaction is collected as a separate, secondary measure.

Use Google Cloud Billing as the interface reference. Reproduce the relevant budget workflow with high visual fidelity and working interactions. Use fictional account data throughout. Use Google logos and product marks only with sponsor approval, and use neutral placeholders otherwise.

The prototype stores saved budget configurations in a test database. It never connects to a production billing service. Email delivery stays simulated because the task ends when the settings are saved.

Build the test interface first. Provide a separate researcher view for session management and result export. The companion document, Synthetic User UAT Platform Build Plan, describes the technical architecture.

## 2. Reference fidelity

Use one documented Google Cloud interface version as the baseline. Do not combine interface conventions from different cloud providers.

Before the main study, create a reference record with the source URL and capture date. Record the account permission context separately. Attach a public or approved screenshot for each relevant interface state when one is available.

Public documentation confirms the workflow rules. It does not establish the exact current layout of every screen. Mark visual details that still need confirmation, and document every deliberate simplification.

| Area | Implementation guidance |
| --- | --- |
| Navigation | Preserve the location of the budget entry point and the surrounding navigation structure. |
| Visual presentation | Match the reference typography and spacing. Preserve its information density at the study viewport. |
| Workflow structure | Follow the observed creation flow. A configuration section does not automatically need a separate page. |
| Controls | Reproduce the relevant field labels and choices. Preserve dependencies between controls. |
| Defaults | Record the initial value of every task-relevant field. Use the same defaults in both variants. |
| Feedback | Reproduce relevant validation and save feedback. Display the values the user actually saved. |
| Peripheral interface | Keep surrounding content consistent with the reference. Every visible control a user can reach needs a defined response. |

Use the account-level budget-management context. Some project-level interfaces lock the budget to the current project, which would remove the scope decision from this task. \[1\]

### Items to confirm in the reference capture

The items below decide how A behaves. Confirm each one against the captured interface before freezing the baseline.

| Item to confirm | Why it matters | What the documentation says |
| --- | --- | --- |
| The Project Owner email option exists in the account context used | The required recipient depends on it | Available only for single-project budgets and labeled Preview \[2\] |
| The billing admins and users option starts checked | Version B targets this default | It is the default role-based option \[1\] |
| What happens to a checked Project Owner option when the scope later widens | Defines the scope dependency in both variants | Not documented |
| Where the cost trend chart sits at the study viewport during the alert step | Shows how much scope information A already gives | The chart appears on create and edit pages and follows the scope filters \[1\] |
| Default project selection for a new budget | Sets the starting scope state | Not documented |
| Default threshold rules | Recorded in the defaults table | Three rules at 50% / 90% / 100% of actual spend \[1\] |
| Notification channel controls | Defines the alternative recipient route | Up to five Cloud Monitoring email channels per budget \[2\] |
| Label text and order in the alert step | Visual fidelity | Capture only |

## 3. Task scenario

Every session starts at the same Billing overview state for its assigned variant. Humans and synthetic users receive the same task text, word for word.

The simulated account contains two projects, Atlas and Beacon. The user can manage budgets across the whole account. Each project has one fictional Project Owner whose role is already configured.

Use exactly the participant-facing text below in every project document and in the platform.

> You manage your team's cloud spending. Create a fixed monthly budget of $1,000 for the Atlas project. The budget should reset at the start of each calendar month. Include all Atlas project costs and exclude costs from other projects.
>
> Configure an email alert for when the project's actual spending during the month exceeds 80% of the budget. Only the Atlas project owner should receive this alert.
>
> Save your settings and indicate when you have finished.

The research questions document currently uses a shorter wording for the scope sentence. Replace it with the text above so both documents match.

The task states the business goal. It does not prescribe a click sequence. Budget names are free.

Other alert thresholds may remain, and users do not have to remove existing rules. If the study later requires exactly one rule, update the task text and the scoring rules together.

The task text stays visible in a task bar above the console frame for both actor types. The bar also holds an I'm finished button, which is how every attempt declares completion.

## 4. Mock environment

The values below are research fixtures, not claims about Google Cloud defaults. Freeze them as one fixture version and store its hash with every session.

| Item | Fixture |
| --- | --- |
| Billing account | Northstar Research, identifier billing-demo-001 |
| Target project | Atlas, identifier atlas-demo |
| Other project | Beacon, identifier beacon-demo |
| Participant identity | Alex Kim, shown as "you", Billing Account Administrator, alex.kim@example.test |
| Billing account user | Jordan Lee, Billing Account User, jordan.lee@example.test |
| Atlas Project Owner | Sam Rivera, atlas-owner@example.test |
| Beacon Project Owner | Priya Shah, beacon-owner@example.test |
| Monitoring email channels | None configured in either project |
| Session permissions | Account-level budget management |
| Currency and language | USD, English |
| Starting budgets | No existing Atlas budget. Decide whether the list starts empty (see Part 13). |
| Cost history | Fixed synthetic values, used consistently wherever charts or totals appear |
| Notification behavior | Store the selected recipient options and the resolved recipient set. No email is sent. |

The named people exist for two reasons. Version B lists recipients by name, and A's Account management page must show the same members.

Budget scope means the costs being monitored. Recipient settings mean who receives notifications. Keep these two concepts separate in the data model.

### Reference defaults record

Store reference defaults in their own record, separate from the fixture. Never prefill the task answer to simplify implementation.

| Field | Default to reproduce | Status |
| --- | --- | --- |
| Budget kind | Alerts only | Documented \[1\] |
| Time range | Monthly | Documented \[1\] |
| Project selection | Take from the capture | Not documented |
| Savings | All savings types selected | Documented \[1\] |
| Amount type | Specified amount, target left empty | Confirm in capture |
| Threshold rules | 50% / 90% / 100% of actual spend | Documented \[1\] |
| Email alerts to billing admins and users | Checked | Documented \[1\] |
| Email alerts to project owners | Unchecked, shown only for single-project scope | Documented \[2\], confirm label |
| Link Monitoring email notification channels | Unchecked | Confirm in capture |
| Connect a Pub/Sub topic | Unchecked | Confirm in capture |
| Read-only for project users | Unchecked | Confirm in capture |

## 5. Interface structure

The table defines functional areas. Final screen boundaries follow the selected reference.

| Functional area | Required behavior |
| --- | --- |
| Task bar | Sits above the console frame in both variants. Shows the task text and the I'm finished button. |
| Billing overview | Shows the fictional account context. Provides the reference navigation into Budgets & alerts. |
| Budget list | Shows saved budgets. Supports creating a new budget and reopening an existing one. |
| Budget creation | Follows the reference order. Budget definition comes first, then scope, then amount, then actions. |
| Saved budget view | Shows persisted values in the reference presentation. Allows reopening for editing. |
| Account management | Read-only list of billing account members and their roles, matching the fixture. |
| Notification channel management | A stub page saying the tool is outside this study, with a back link. |
| Other reachable links | A neutral placeholder page with a back link. Every visit is logged. |

Version B replaces the Budget creation area with the guided setup in Part 14. Every other area in this table is identical in both variants.

Do not add a compulsory review page to version A unless it appears in the captured reference. The review screen belongs to B only.

## 6. Interaction rules

Every task-relevant field updates real prototype state. Back navigation keeps the draft unless the reference explicitly discards it. Saving persists the current configuration.

Users can correct any earlier selection. Reopening a budget shows its saved values.

Allow every valid product configuration to be saved, even when it fails the task. An entire-account budget is valid. A forecast-based alert is valid too. Task accuracy is judged separately by the evaluator.

### Recipient rules

- The billing admins and users option starts checked. \[1\]
- The project owners option appears only when the budget covers exactly one project. \[2\]
- When the scope changes, update the available recipient controls at once.
- Until the capture shows otherwise, a checked project owners option is hidden and cleared when the scope widens. Log the cleared value as its own event.
- When threshold rules exist, at least one email option must be selected before saving. \[1\]
- Removing every threshold rule disables the email settings. \[1\]

### Notification channel route

Cloud Monitoring channels are a real second route to a chosen recipient. \[2\] The fixture closes this route in both variants.

- The Link Monitoring email notification channels checkbox works and reveals its project picker.
- Both projects list zero channels.
- Manage notification channels opens the stub page from Part 5.
- Checking the box without a channel adds no recipient.

Record the closed route as a deliberate simplification in the reference record.

### Validation and feedback

Validate missing required values and invalid numbers. Never reject a configuration because it differs from the task answer. Product validation stays separate from research scoring.

Show normal product feedback in the participant interface. Keep every evaluator result in the researcher view.

## 7. Completion and scoring

Score the saved budget that the attempt submits. If a user creates several budgets, identify the intended one with a written rule before scoring, and apply the same rule to synthetic users.

| Criterion | Passing condition |
| --- | --- |
| Project scope | The budget covers Atlas alone. An entire-account scope fails. Beacon alone or both projects also fail. |
| Budget period | Recurring monthly |
| Budget amount | Specified amount of USD 1,000 |
| Required alert | At least one rule at 80% of actual spend |
| Recipients | The resolved recipient set is exactly Sam Rivera, the Atlas Project Owner |
| Persistence | The configuration was saved successfully |

Overall success requires every criterion to pass. Keep a separate result for each criterion.

### Resolved recipient set

Score recipients by who would actually receive email, not by which box is checked. The set is built from three sources.

1. Every billing account member, when the billing admins and users option is checked.
2. The owner of the scoped project, when the project owners option is checked and the scope is one project.
3. Every linked Monitoring channel address. The fixture has none.

Record the mechanism that produced each recipient as a separate field. Two users can reach the same set by different routes.

### What is not scored

- Budget name
- Savings settings
- Extra threshold rules beside the required one
- The Read-only for project users setting
- The navigation path

The monthly period is the default, so almost everyone will pass it. Do not treat that pass as evidence of task skill.

A user who corrects an earlier mistake and saves the required configuration still succeeds. Keep the earlier actions in the session record.

Declaring completion ends the attempt but says nothing about correctness. Record the termination reason separately from configuration accuracy.

## 8. Human and synthetic interaction

Give both groups the same starting state and the same task text. Fix the study viewport at 1440 × 900 with 100% browser zoom, and record any deviation.

Run human sessions on a lab machine wherever possible. Remote participants cannot be held to one screen size, so enforce a minimum window size and record the actual viewport.

Synthetic users see rendered screenshots only. They act through coordinate clicks and text entry. They can also press keys and scroll. Set the device scale factor to 1 so screenshot pixels match click coordinates.

The agent must never inspect the DOM or the accessibility tree. It must never query stored configuration through an API. It never receives evaluator labels or researcher notes.

The application may use internal state for logging and scoring. That state belongs to the research system and is never an observation channel for the agent.

Log the agent's stated reason for each action, when the model gives one. The reason is research data only and never appears in the interface.

Capture every action attempt, including attempts that change nothing. Record technical execution failures separately. A click with no effect is not automatically evidence of usability friction.

Use public or approved models under the project agreement. All visible scenario data is fictional or explicitly approved.

## 9. Research records

Each attempt needs a session record and an ordered event history. Use pseudonymous participant identifiers only.

| Record | Minimum content |
| --- | --- |
| Session identity | Session ID and actor type |
| Experimental condition | Variant / fixture version / dataset label |
| Reference identity | Reference capture ID and prototype build version |
| Task identity | Task version and exact task text |
| Display conditions | Viewport size and browser zoom |
| Synthetic configuration | Model ID and prompt version. Calibration ID recorded separately. |
| Event history | Timestamped actions with the resulting interface state |
| Saved result | Submitted budget ID and its final configuration |
| Evaluation | Field-level results / overall success / resolved recipient set |
| Termination | One explicit reason for ending the attempt |
| Post-task answers | Humans only. Satisfaction, plus any probes the protocol adds. |

Keep declared completion apart from abandonment. A time limit and a technical interruption are separate termination reasons.

For each event, record the action type and its target. When a value changes, keep the previous value and the new value. Link screenshots to the matching events.

Log navigation even when users return to an earlier area. Record every validation message shown. Keep save attempts distinct from successful saves.

### Setting-level events

A and B have different pages, so friction is compared by setting. Log these events in both variants unless marked otherwise.

| Event | When it fires | Content |
| --- | --- | --- |
| Setting first reached | A setting's control first enters the viewport in A, or its screen opens in B | Setting name and current value |
| Setting value change | Any task-relevant value changes | Setting / old value / new value |
| Return to setting | The user comes back to a setting already visited | Setting name and the route taken |
| Option cleared by scope change | A scope change removes a checked option | The cleared option |
| Screen viewed | B only. A guided screen opens | Screen number and name |
| Review edit | B only. Edit is used on the review screen | The setting edited |
| Save clicked | Finish in A or Create budget in B | Full snapshot before saving |
| Reopen after save | A saved budget is opened for editing | Budget ID |
| Agent action reason | Synthetic only, each step | The model's stated reason |

Keep raw observations apart from later friction coding. A return visit can be deliberate checking and is not automatically a problem. Review unclear cases against the screen record.

Export the event history as JSON. Export session-level results as CSV.

## 10. A/B support

Version A reproduces the reference workflow. Version B replaces the create form with the guided setup in Part 14. Everything before and after the create flow is identical.

| Element | Version A | Version B |
| --- | --- | --- |
| Create flow | Reference multi-section form | Guided setup, one question per screen |
| Starting values | Reference defaults | Same defaults |
| Product rules and validation | Reference | Same as A |
| Fixture data | Frozen fixture | Same fixture version |
| Task text and scoring | Parts 3 and 7 | Same as A |
| Pages before and after the create flow | Reference | Same as A |
| Review screen | None | Present |

B never states which answer the task requires. Its one-line reasons explain settings, not the task.

This is the planned experimental change. Gate 1 in Part 13 checks that A is a fair baseline before the main study. The effect of B on people remains an empirical question.

Store the variant with every session. Keep human B outcomes out of everything used for calibration on A. Dataset labels in Part 11 enforce this separation.

## 11. Researcher controls and assignment

The researcher view starts isolated sessions and resets them to the baseline fixture. A reset never erases a completed session record.

The researcher picks the variant before the task starts. Variant labels never appear in the participant's interface or URL. The researcher view stays unreachable for the synthetic agent.

The researcher can inspect each final saved configuration with its evaluation, and can export session records.

### Screening and familiarity bands

Screening records prior Google Cloud use. It measures cloud billing familiarity separately from general programming experience.

Define the familiarity bands before the pilot and keep them fixed. A simple start is three bands, from no cloud console use to regular budget or billing work.

### Assignment

Each human participant sees one variant only. Repeating the task in both interfaces would add learning effects.

Assign variants in blocks of two within each familiarity band, in random order. This keeps the familiarity mix similar across A and B, which matters with small groups.

### Dataset labels

Every session carries exactly one label. A participant never appears under two labels.

| Label | Used for |
| --- | --- |
| pilot | Gate 1 and Gate 2 in Part 13. Never pooled with main data. |
| calibration\_A | Human A sessions used to calibrate synthetic users |
| evaluation\_A | Human A sessions for the design comparison |
| evaluation\_B | Held-out human B sessions. Never used for calibration. |
| synthetic | All synthetic sessions, with model and calibration IDs |

## 12. Build sequence and acceptance checks

Build in the order below. Each stage finishes before the next begins.

| Build stage | Required output |
| --- | --- |
| Reference preparation | Reference record with screenshots. Completed defaults record. |
| Baseline implementation | Working version A with persistent configuration state |
| Research instrumentation | Session isolation and event export. Separate evaluator. |
| Variant implementation | The Part 14 guided setup, built after the reference checks and sharing A's business rules |
| Pilot preparation | Critical paths verified, then the pilot build frozen |

Verify every case below before any pilot. These are implementation checks. They do not establish synthetic-human agreement.

| Case | Expected result |
| --- | --- |
| Required settings saved in A | Overall success |
| Required settings saved in B | Overall success |
| Same configuration entered through A and through B | Identical saved configuration and evaluation |
| Correct settings reopened | Reopened values match the saved result |
| Default recipients saved unchanged | Recipient criterion fails. Resolved set holds three people. |
| Project owners checked and billing admins and users cleared | Recipient criterion passes |
| Entire-account scope saved with account recipients | Product accepts it. Task evaluation fails. |
| Only a forecast-based 80% rule | Task evaluation fails |
| Required actual rule beside extra thresholds | Extra thresholds cause no failure |
| Scope widened after project owners was checked | Option handled as the reference shows, in both variants |
| Monitoring box checked with no channel | No recipient added |
| Every threshold rule removed | Email options disabled in both variants |
| Each B screen opened fresh | Starts at the reference default |
| Edit used on the B review screen | Opens that screen, then returns to review |
| Earlier mistake corrected before completion | Final configuration can pass. The correction stays in the record. |
| A required value is missing | Validation appears and the save does not complete |
| New session starts | Baseline data restored. Earlier session records intact. |
| Synthetic click has no effect | The attempt is kept for review |

## 13. Pilot gates and open items

Two gates stand between the build and formal data collection. Neither gate estimates the effect of B.

### Gate 1 · A pilot

Run 6 to 8 human participants on A, spread across familiarity bands. Also run the synthetic agent on A, which costs little. Gate 1 checks that A is a fair baseline. It no longer chooses the B design.

- **Saved errors exist.** If almost everyone succeeds in A, B has nothing to improve. Revisit the task before the main study.
- **Errors vary with familiarity.** If behavior shows no difference across bands, RQ1 has nothing to reproduce.
- **Agent failures are recorded.** Where the agent fails in A gives the first view of the human-agent gap before any calibration.

Zero errors in a small pilot does not prove a low error rate. With 0 of 8, the one-sided 95% upper bound is still about 31%.

### Gate 2 · B check

Run 2 to 3 people on B. Check only that each screen is understood and that the flow completes without technical faults. Do not judge the effect of B from this gate.

Do not tune B toward a preferred result. Freeze B after this gate. Any later change becomes a new prototype version and is never pooled silently with earlier B sessions.

### Sample size

The human A/B comparison will likely be underpowered. A larger effect needs fewer people, which is one reason B changes the whole flow. Plan the design check around direction and intervals, not significance.

| Task failure in A | Task failure in B | People per variant for 80% power |
| --- | --- | --- |
| 40% | 15% | about 49 |
| 50% | 15% | about 27 |
| 40% | 20% | about 81 |

Figures use the normal approximation with two-sided α = 0.05. With 12 to 15 people per variant and 40% against 15%, simulated power with Fisher's exact test is only 15% to 19%. An unclear difference stays inconclusive.

### Items to settle before the main study

- [ ] Freeze the reference capture and the defaults record
- [ ] Confirm the Project Owner option in the capture
- [ ] Decide whether the budget list starts empty. An existing account-wide budget adds realism but opens an edit-the-wrong-budget path.
- [ ] Set session stopping rules for time and for agent steps
- [ ] Define friction coding before any main data arrives
- [ ] Choose the satisfaction instrument
- [ ] Get sponsor approval for any Google marks
- [ ] Ask course staff whether Cornell IRB review or an exemption determination is needed before recruiting

## 14. Version B · guided setup

### 14.1 Decision and hypotheses

Version B replaces the multi-section create form with a guided setup that asks one question per screen. The design follows the split AWS Budgets offers between a simplified template workflow and a customized advanced workflow. \[11\]

Version A stays the expert-style reference form. Version B is the novice-style alternative. Both save the same configuration shape, and one evaluator scores both.

- **H1.** Overall success is higher in B than in A.
- **H2.** The gain from B is larger for low-familiarity participants than for high-familiarity participants.

A useful B creates a real design comparison. It does not need to win.

### 14.2 Why this change

- **A difference large enough to measure.** B changes how the whole task is done, not one hint. With the planned sample, a small change would likely show no difference (Part 13).
- **A direct target for RQ1.** H2 is a familiarity-by-variant pattern that novice and expert synthetic profiles can try to reproduce.
- **A harder and more convincing RQ2 test.** Calibration learned on A must predict behavior on a structurally different design. This resembles the counterfactual validation used for ConvApparel. \[9\]
- **A real precedent.** AWS Budgets offers a single-page simplified workflow beside a five-step advanced one, and a template budget can be edited later. \[11\]
- **It answers doubts raised in the team walkthrough.** Walkers were unsure what each button would open. Showing one question with its purpose before the user acts is feedforward. \[12\] They were also unsure whether the right project was selected. Keeping the current selection visible addresses that. \[13\] Mis-scoping is a common cloud configuration problem. \[14\]

### 14.3 What stays identical

B changes the path through the task. It never changes the defaults, which would make the comparison about defaults instead of design.

| Element | Rule in B |
| --- | --- |
| Task text and scoring | Identical to Parts 3 and 7 |
| Saved configuration | Same shape. The evaluator never branches on variant. |
| Starting values | Every question starts at the reference default. Nothing is prefilled from the task answer. |
| Product rules | Same recipient dependency and same validation as Part 6 |
| Fixture | Same fixture version |
| Before and after the flow | Same Billing overview start and task bar. Same budget list and saved budget view. |

Settings that B does not ask about keep their reference defaults when saved. These include the extra scope filters and the savings options. Notification channels and the other advanced options also stay at their defaults. None of them is scored.

### 14.4 Flow specification

Each screen shows one question with a one-line reason. Back and Continue buttons sit below the controls. A progress bar lists all seven screen names with the current one marked.

| Screen | Question | Controls | Starts at |
| --- | --- | --- | --- |
| 1 Name | What should this budget be called? | Text field | Empty |
| 2 Projects | Which costs should this budget track? | All projects in Northstar Research, or Only specific projects with a checklist of Atlas and Beacon. Chosen projects show as chips. | Reference default from the capture |
| 3 Period | How often should the budget start over? | Monthly / Quarterly / Yearly / Custom dates | Monthly |
| 4 Amount | How much should this budget allow each period? | A fixed amount with a dollar field, or Match last period's spend | Fixed amount, field empty |
| 5 Alerts | When should alert emails go out? | One sentence per rule, such as "Email when money already spent reaches 50% ($500)". The spend type is a dropdown between money already spent and money expected by the end of the period. Rules can be added and removed. | 50% / 90% / 100% of money already spent |
| 6 Recipients | Who should get alert emails? | Billing account admins and users, with their names listed below. Project owners, with the owner's name listed below, shown only when one project is chosen. | Billing admins and users checked |
| 7 Review | Here is your budget | Plain-language summary of screens 1 to 6 with an Edit link on each line. A Create budget button below. | Not applicable |

Continue buttons name the next screen, for example "Continue to amount". Edit on the review screen opens that screen and then returns to review.

B offers no switch to the advanced form. AWS allows one, but a switch would let participants choose their own variant and blur the comparison. Record this as a deliberate difference from the precedent.

### 14.5 Copy rules

- One question per screen, in plain words.
- The one-line reason explains the setting, never the task. For screen 2, write "Costs from projects you leave out will not count toward this budget."
- No option carries "recommended" or a similar label. A label like that would add an endorsement effect.
- No warning colors. No sign of which answer is right.

### 14.6 Reverse review

| Potential failure | Signal | Response |
| --- | --- | --- |
| B is so easy that almost everyone succeeds | B success near 100% at Gate 2 | Keep B. Put more analytic weight on where humans and agents fail in A. |
| B wins partly because it hides settings | A participants change hidden filters by mistake | Report hiding as part of the design. Log hidden-field changes in A. |
| Friction cannot be compared page to page | Different screens in A and B | Compare by setting, using the map in 14.7 |
| Agents gain from simpler screenshots, not better design | Agent technical errors drop sharply in B | Label perception failures separately from behavior |
| B takes longer because it has more screens | Time on task higher in B | Report time as secondary. Accuracy is primary. |
| B departs from the Google reference | Reviewers question realism | A stays faithful to Google. B is the intervention, and AWS shows the pattern ships. |

### 14.7 Measurement

Overall success from Part 7 stays the primary outcome. Report per-criterion success for each variant beside it.

Compare friction by setting, not by page.

| Setting | Where it lives in A | Where it lives in B |
| --- | --- | --- |
| Scope | Project filter in the Scope section | Screen 2 |
| Period | Time range in the Scope section | Screen 3 |
| Amount | Amount section | Screen 4 |
| Alert rule | Threshold rules in the Actions section | Screen 5 |
| Recipients | Email options in the Actions section | Screen 6 |
| Final check | None | Screen 7 |

For each setting, record time spent and value changes. Also record returns to the setting and whether it was wrong at save. Record edits made from the review screen as their own measure.

Test H2 as a familiarity-by-variant comparison. With small groups, report direction and intervals rather than significance.

### 14.8 Link to the research questions

For RQ1, first examine familiarity differences in human behavior within each variant. Then check whether synthetic profiles reproduce the direction, including whether the novice-expert gap narrows in B.

Expect weak persona effects. Detailed personas barely changed simulated clicks in one large study. \[7\] ADK's NOVICE and EXPERT personas describe conversation, not interface actions. \[10\] Familiarity profiles here need their own observable interface behaviors.

For the design comparison, use independent human groups per variant, as set in Part 11.

For RQ2, calibrate on calibration\_A only. Freeze the calibration before any human B outcome is seen, including B pilot data. Compare uncalibrated and calibrated synthetic results against the held-out evaluation\_B sessions.

Because B is structurally different, only calibration that captures behavior can transfer. A correction tied to A's page layout cannot. Report whether synthetic testing picks the same better variant and ranks settings by friction in the same order as humans.

### 14.9 Implementation checks

| Check | Expected result |
| --- | --- |
| Enter the same configuration through A and through B | Identical saved configuration and evaluation |
| Open each B screen fresh | It starts at the reference default |
| Choose exactly one project, then widen the choice | The project owners option appears, then disappears and clears |
| Remove every alert rule | The recipients screen says alert emails are off |
| Go back one screen | Earlier answers are kept |
| Edit from the review screen | Opens that screen, then returns to review |
| Save from B | Settings B does not ask about carry their reference defaults |
| Search all B copy | No "recommended" label and no mention of the task |
| Inspect event order | A screen-view event fires for every screen in order |

## References

All pages below were opened and reviewed on 29 September 2026.

1. Google Cloud. [Create, edit, or delete budgets and budget alerts](https://docs.cloud.google.com/billing/docs/how-to/budgets)
2. Google Cloud. [Customize budget alert email recipients](https://docs.cloud.google.com/billing/docs/how-to/budgets-notification-recipients)
3. Jachimowicz, Duncan, Weber and Johnson (2019). [When and why defaults influence decisions](https://business.columbia.edu/faculty/research/when-and-why-defaults-influence-decisions-meta-analysis-default-effects). Behavioural Public Policy.
4. Nielsen Norman Group. [Confirmation Dialogs Can Prevent User Errors](https://www.nngroup.com/articles/confirmation-dialog/)
5. Slack Help Center. [Notify a channel or workspace](https://slack.com/help/articles/202009646-Notify-a-channel-or-workspace)
6. Zhou, Sun et al. (2026). [Mind the Sim2Real Gap in User Simulation for Agentic Tasks](https://arxiv.org/html/2603.11245v1). arXiv 2603.11245.
7. Kuric, Demcak and Krajcovic (2026). [What Would GPT Click](https://arxiv.org/pdf/2605.18302v1). arXiv 2605.18302.
8. Kuo, Cai, Morris and Terry (2026). [Synthetic TLX](https://arxiv.org/html/2609.12273v1). arXiv 2609.12273.
9. Google Research (2026). [ConvApparel](https://research.google/blog/convapparel-measuring-and-bridging-the-realism-gap-in-user-simulators/)
10. Agent Development Kit. [User simulation](https://adk.dev/evaluate/user-sim/)
11. AWS. [Using budget templates](https://docs.aws.amazon.com/cost-management/latest/userguide/budget-templates.html)
12. Vermeulen et al. (2013). [Crossing the Bridge over Norman's Gulf of Execution](http://jovermeulen.com/Research/FeedforwardCHI2013). CHI 2013.
13. UX Patterns. [Multi-select Input Pattern](https://uxpatterns.dev/patterns/forms/multi-select-input)
14. NDSS 2026. [A Mixed-Methods Study of Cloud Security and Privacy](https://www.ndss-symposium.org/wp-content/uploads/2026-f1302-paper.pdf)
