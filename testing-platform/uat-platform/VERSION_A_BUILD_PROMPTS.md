# Version A · Vibe Coding Prompts

## 怎么用这份文件（给 Mikey）

这份文件把 Version A 拆成 9 步。每一步是一段英文 prompt，直接复制进 VS Code 里的 AI 插件。一次只贴一步，做完、自己验收、commit 以后，再贴下一步。

开工前先做这几件事。

1. 在 GitHub 建一个 **private** 仓库，名字叫 `uat-platform`。谷歌合作协议里 NDA 和知识产权那两个附录还没确认，确认之前代码不要公开。
2. 把这个文件夹整个放进仓库根目录。里面有 `CLAUDE.md`、这份文件，还有 `docs/` 下的三份设计文档。
3. 如果你用的插件是 Claude Code，它会自动读 `CLAUDE.md`。如果是 GitHub Copilot，把 `CLAUDE.md` 复制一份到 `.github/copilot-instructions.md`。
4. 注册一个 Neon 账号（免费版够用），建一个 Postgres 数据库，拿到连接串。Step 0 会用到。

每一步的 "Done when" 是验收标准。AI 说做完了不算数，你自己按清单点一遍才算。最容易出问题的地方是 AI 自作主张加了文档里没有的按钮或文字，每一步结束都要看一眼 diff。

这份文件只覆盖 Version A 加上研究后台。Version B（引导版）和 AI 代理 runner 各自另有一份文件，等 A 稳定以后再做。

| Step | 内容 | 对应 build plan |
| --- | --- | --- |
| 0 | 项目搭建 | 准备 |
| 1 | 假数据和默认值文件、数据类型 | M0 的代码部分 |
| 2 | 外壳页面和任务栏 | M1 |
| 3 | 评分器，先写测试 | M3（提前做） |
| 4 | Version A 创建表单、草稿和保存 | M2 |
| 5 | Session 和事件记录 | M4 |
| 6 | 研究后台和导出 | M5 |
| 7 | 部署到 Vercel | 部署 |
| 8 | A 的验收测试 | M8 的 A 部分 |

评分器（Step 3）放在表单（Step 4）前面是故意的。先有一个测试过的评分器，做表单时每保存一次就能马上知道存进去的东西对不对。

---

## Step 0 · Project setup

```markdown
Read CLAUDE.md and the three files in docs/ first. Do not write feature code in this step.

Set up the project skeleton for the web app described in docs/build-plan.md.

Stack
- Next.js with the App Router and TypeScript in strict mode
- Tailwind CSS, with Roboto loaded through next/font/google
- Prisma with PostgreSQL. Use DATABASE_URL from .env for both local development and production. Do not set up SQLite.
- Vitest for unit tests and Playwright Test for browser tests
- ESLint with the Next.js config

Create this folder layout, with empty index files where needed.
- app/s/[token]/        participant routes
- app/admin/            researcher console
- app/api/              route handlers
- components/console/   console layout and form controls
- components/budget/    version A create form sections
- components/variant-b/ leave empty except a README saying it is built later
- components/taskbar/
- lib/fixtures/  lib/domain/  lib/evaluator/  lib/events/
- prisma/schema.prisma
- tests/unit/  tests/acceptance/
- agent-runner/  leave empty except a README saying it is built later

Add these npm scripts.
- "typecheck" runs tsc --noEmit
- "test" runs vitest run
- "test:e2e" runs playwright test
- "check" runs lint, then typecheck, then test, and stops on the first failure

Configure Playwright to use a 1440 x 900 viewport, deviceScaleFactor 1, and baseURL from PLAYWRIGHT_BASE_URL defaulting to http://localhost:3000.

Create .env.example with DATABASE_URL, ADMIN_PASSWORD and BUILD_VERSION, with placeholder values only. Make sure .gitignore excludes .env, .env.local, node_modules, .next, playwright-report and test-results.

Create docs/CHANGELOG.md with a single first line for this step.

Done when
- npm run dev serves a blank home page at localhost:3000
- npm run check passes
- No real secret appears in any committed file
```

**Done when（你自己验）** `npm run dev` 能打开，`npm run check` 全绿，`git status` 里看不到 `.env`。

---

## Step 1 · Fixture, defaults and domain types

```markdown
Read CLAUDE.md, docs/design-guide-v2.md Part 4, and the Data model section of docs/build-plan.md.

Create the frozen research data and the shared types. No pages in this step.

1. Create lib/fixtures/fixture-v1.json with exactly this content.

{
  "fixtureVersion": "fixture-v1",
  "today": "2026-09-20",
  "currency": "USD",
  "billingAccount": { "id": "billing-demo-001", "name": "Northstar Research" },
  "projects": [
    { "id": "atlas-demo", "name": "Atlas" },
    { "id": "beacon-demo", "name": "Beacon" }
  ],
  "billingMembers": [
    { "id": "alex-kim", "name": "Alex Kim", "email": "alex.kim@example.test", "role": "Billing Account Administrator", "isYou": true },
    { "id": "jordan-lee", "name": "Jordan Lee", "email": "jordan.lee@example.test", "role": "Billing Account User", "isYou": false }
  ],
  "projectOwners": {
    "atlas-demo": [ { "id": "sam-rivera", "name": "Sam Rivera", "email": "atlas-owner@example.test" } ],
    "beacon-demo": [ { "id": "priya-shah", "name": "Priya Shah", "email": "beacon-owner@example.test" } ]
  },
  "folders": [],
  "services": ["Compute Engine", "Cloud Storage", "BigQuery", "Cloud Run"],
  "labels": [ { "key": "env", "values": ["prod", "dev"] }, { "key": "team", "values": ["research"] } ],
  "monitoringChannels": { "atlas-demo": [], "beacon-demo": [] },
  "pubsubTopics": [],
  "startingBudgets": [],
  "monthlyCosts": {
    "atlas-demo": [
      { "month": "2026-04", "usd": 612.40 }, { "month": "2026-05", "usd": 688.15 },
      { "month": "2026-06", "usd": 731.02 }, { "month": "2026-07", "usd": 804.77 },
      { "month": "2026-08", "usd": 776.30 }, { "month": "2026-09", "usd": 523.40, "partial": true }
    ],
    "beacon-demo": [
      { "month": "2026-04", "usd": 1140.00 }, { "month": "2026-05", "usd": 1205.60 },
      { "month": "2026-06", "usd": 1188.25 }, { "month": "2026-07", "usd": 1262.90 },
      { "month": "2026-08", "usd": 1310.45 }, { "month": "2026-09", "usd": 902.15, "partial": true }
    ]
  }
}

2. Create lib/fixtures/defaults-v1.json with exactly this content. Items listed in "provisional" still need to be checked against the reference capture. Keep that list in the file.

{
  "defaultsVersion": "defaults-v1",
  "provisional": ["scope.allProjects", "scope.savings", "amount.type", "recipients.monitoring.linked", "recipients.pubsubTopic", "scope.readOnlyForProjectUsers"],
  "config": {
    "name": "",
    "kind": "alerts_only",
    "scope": {
      "allProjects": true,
      "projectIds": [],
      "filters": { "folders": [], "services": [], "labels": [] },
      "savings": ["discounts", "promotions_and_others"],
      "readOnlyForProjectUsers": false
    },
    "period": "monthly",
    "amount": { "type": "specified" },
    "thresholds": [
      { "percent": 50, "trigger": "actual" },
      { "percent": 90, "trigger": "actual" },
      { "percent": 100, "trigger": "actual" }
    ],
    "recipients": {
      "billingAdminsAndUsers": true,
      "projectOwners": false,
      "monitoring": { "linked": false, "channelIds": [] }
    }
  }
}

3. Create lib/domain/types.ts with the BudgetConfig type from docs/build-plan.md. Add one field that the build plan does not have yet, scope.filters with folders, services and labels as string arrays. These filters are not scored, but version A lets people change them and the study must record it. Add a line to docs/CHANGELOG.md saying this field was added.

Also define the Fixture, Recipient and Evaluation types to match the JSON above and the evaluator in docs/build-plan.md.

4. Create lib/fixtures/index.ts that loads both files, validates them with zod at import time, and exports them together with a SHA-256 hash of each file's exact bytes (fixtureHash, defaultsHash).

5. Create lib/domain/task.ts exporting TASK_VERSION = "task-v1" and TASK_TEXT, copied word for word from the blockquote in docs/design-guide-v2.md Part 3. Keep the three paragraphs.

6. Write unit tests in tests/unit/fixtures.test.ts that check the files load, the hashes are stable across two loads, and TASK_TEXT contains "Only the Atlas project owner should receive this alert."

Done when npm run check passes.
```

**Done when** 两个 JSON 文件里的内容和上面一字不差。任务文本和设计指南 Part 3 一字不差。`CHANGELOG.md` 里写了新增 `scope.filters` 字段。

---

## Step 2 · App shell and task bar

```markdown
Read CLAUDE.md, docs/prototype-design-a-b.md section "Shared shell", docs/design-guide-v2.md Part 5, and the Participant app section of docs/build-plan.md.

Build the participant shell. There is no database yet, so use a hard-coded dev token "dev-a" that behaves like a version A session. Step 5 replaces it with real sessions.

Routes to build
- /s/[token]                         consent and instructions page (humans only)
- /s/[token]/billing                 Billing overview
- /s/[token]/billing/budgets         Budgets & alerts list
- /s/[token]/billing/budgets/create  placeholder that says "Create form is built in step 4". This text is temporary and must be removed in Step 4.
- /s/[token]/billing/budgets/[id]    Saved budget view (empty state for now)
- /s/[token]/billing/account         Account management
- /s/[token]/stub/[area]             out-of-study placeholder
- /s/[token]/done                    post-task page (humans only)

Layout
- Task bar fixed at the very top of every page except the consent page and the done page. It shows TASK_TEXT from lib/domain/task.ts, a collapse toggle, and an "I'm finished" button on the right. Give it a fixed height when collapsed and when expanded. For now the button only navigates to /done.
- Below the task bar, the console frame. A top bar shows "Cloud Console (prototype)", the account name Northstar Research, and the user Alex Kim. A left menu shows Overview, Reports, Budgets & alerts and Account management, in that order.
- Reports goes to /stub/reports. Every other link a participant can reach must go to a real page or a stub. No dead links, no href="#".

Page content
- Billing overview. Account name and ID. This month's cost so far, which is the sum of the partial 2026-09 values in the fixture. A small bar chart of monthly cost split by project, drawn from fixture.monthlyCosts. Dates shown come from fixture.today, never the real clock.
- Budgets & alerts list. A "Create budget" button above a table with Name, Scope, Amount and Alerts columns. The fixture starts with no budgets, so show an empty-state row reading "No budgets yet".
- Account management. A read-only table of fixture.billingMembers with name, email and role. Mark Alex Kim as "(you)".
- Stub page. The text "This page is not part of the study." and a Back link. For area "notification-channels" the text is "Notification channels are outside this study." instead.
- Consent page. A heading "Before you start", a placeholder paragraph that reads "[Consent text goes here after ethics review]", and a "Start task" button that goes to /billing. Keep the placeholder visible so nobody forgets to replace it.
- Done page. The text "Thank you. You can let the researcher know you are finished." Nothing else yet.

Viewport gate
- On every participant page, if window.innerWidth < 1440 or window.innerHeight < 900, cover the page with a message: "Please make this window larger. It needs to be at least 1440 by 900. Current size is W by H." Show the live numbers. Remove the cover as soon as the window is large enough.

Style
- Dense console look. White background, grey borders, blue primary buttons, Roboto 14px body text. No Google logo or Google product marks anywhere.
- The page title is "Cloud Console (prototype)" on every participant page, in both variants.

Write a Playwright test in tests/acceptance/shell.spec.ts that visits every route with token dev-a at 1440 x 900, checks each renders without console errors, and checks every visible link leads to a page that returns 200.

Done when every route renders, every reachable link goes to a real page or a stub, and npm run check plus npm run test:e2e pass.
```

**Done when** 在 1440×900 下把每个页面、每个链接都点一遍。把浏览器窗口缩小，确认会弹出"请把窗口调大"的提示。

---

## Step 3 · Evaluator and recipient resolver, tests first

```markdown
Read CLAUDE.md, docs/design-guide-v2.md Part 7 and Part 12, and the Evaluator section of docs/build-plan.md.

Write the tests first. Then write the code until they pass. Do not touch any page in this step.

1. Create lib/domain/resolveRecipients.ts exactly as shown in docs/build-plan.md. Return each recipient with its id, name, email and the mechanism that produced it (billing_roles or project_owners).

2. Create lib/evaluator/evaluate.ts as shown in docs/build-plan.md, with EVALUATOR_VERSION = "eval-v1". Criteria are scope, period, amount, alert, recipients and persistence. overall is true only when every criterion is true. The function must be pure.

3. Create lib/evaluator/pickScoredBudget.ts. Rule v1, written here so it applies to humans and agents the same way: when a session saved more than one budget, score the most recently saved budget version before completion was declared. If nothing was saved, persistence is false and the other criteria are evaluated against the last draft. Put this rule in a comment at the top of the file.

4. Write tests/unit/evaluator.test.ts with one test per case below. Build every config by starting from defaults-v1.json and changing only what the case describes.

- Correct config (Atlas only, monthly, specified $1000, a rule at 80% actual, project owners checked, billing admins and users unchecked, saved) passes overall
- Same as correct but billing admins and users left checked fails recipients, and resolves exactly three people (alex-kim, jordan-lee, sam-rivera)
- Project owners checked with billing admins and users cleared passes recipients
- allProjects true with project owners checked fails scope and resolves only billing members
- Beacon only fails scope
- Atlas and Beacon both selected fails scope
- Only an 80% forecasted rule fails alert
- 80% actual beside 50%, 90% and 100% actual passes alert
- Zero thresholds resolves nobody and fails recipients
- Monitoring linked with no channel adds nobody
- amount type last_period fails amount
- target 1000.00 passes amount and target 100 fails it
- period quarterly fails period
- Not saved fails persistence only
- evaluate() returns the same result when called twice on the same input
- A config that was reached through different click orders but is equal in value scores identically

5. Write tests/unit/pickScoredBudget.test.ts covering zero saves, one save, and several saves with completion declared between them.

Done when every test passes and lib/evaluator has no import from Prisma, fetch, Date or Math.random.
```

**Done when** 所有测试通过。打开 `evaluate.ts` 看一眼，里面不能出现数据库、网络、`Date` 或者随机数。

---

## Step 4 · Version A create form, draft and save

```markdown
Read CLAUDE.md, docs/prototype-design-a-b.md section "Version A · the advanced form" and section "States and edge cases", docs/design-guide-v2.md Parts 4 to 6, and "Draft and save behavior" in docs/build-plan.md.

Replace the placeholder on /s/[token]/billing/budgets/create with ReferenceCreateForm in components/budget/. The create page must render ReferenceCreateForm through a single switch on the session variant. For now the variant always resolves to A. Leave a clear TODO where GuidedSetup will plug in later. That switch is the only place in the codebase allowed to read the variant.

Page layout
- Heading "Create budget" with a back arrow to the budgets list.
- Left column, about 60% wide, holds four numbered sections stacked vertically. Right column holds the cost trend chart.
- Each section has a header row with its number and name. Clicking a header opens that section. The open section shows its controls and a Next button that opens the section below. Closed sections show a one-line summary of their current values.
- Finish and Cancel buttons sit at the bottom of the page and are always visible. This is provisional until the capture confirms it. Add a TODO comment.
- There is no review page in version A. Do not add one.

Section 1 · Define
- "Name" text field, empty at start.
- A read-only line "Budget type · Alerts only".

Section 2 · Scope
- "Time range" dropdown with Monthly, Quarterly, Yearly and Custom range. Custom range shows From and To date fields.
- "Folders & organizations" picker. The fixture has none, so it opens a list that says "No folders in this account".
- "Projects" dropdown with a "Select all" checkbox and one checkbox per project. When Select all is checked, scope.allProjects is true and projectIds is empty. When the person unchecks Select all, the checked projects go to projectIds and allProjects is false. The closed dropdown shows "All projects", or the chosen project names separated by commas.
- "Services" picker listing fixture.services. "Labels" picker listing fixture.labels. Both write to scope.filters.
- "Savings" checkboxes for Discounts and Promotions and others, both checked at start.
- "Read-only for project users" checkbox, unchecked.

Section 3 · Amount
- "Budget type" radio group with "Specified amount" and "Last month's spend".
- "Target amount" number field with a $ prefix. Shown only for Specified amount. Empty at start.
- For Last month's spend, show the computed value from the fixture for the current scope as read-only text.

Section 4 · Actions
- "Set alert threshold rules" table with Percent of budget, Amount and Trigger on columns. Trigger on is a dropdown with Actual and Forecasted. Amount is computed from percent times the target. Each row has a delete icon. An "Add threshold" button adds a row at 100% Actual. Rows start from defaults-v1.json.
- "Manage notifications" group with these checkboxes, in this order.
  1. "Email alerts to billing admins and users", checked at start. No names next to it.
  2. "Email alerts to project owners" with a small "Preview" tag. Visible only when exactly one project is selected. Unchecked at start.
  3. "Link Monitoring email notification channels to this budget". Checking it reveals a project picker. Each project shows "No notification channels" and a "Manage notification channels" link that opens /stub/notification-channels.
  4. "Connect a Pub/Sub topic to this budget". Checking it reveals a picker that says "No topics available".

Cost trend chart
- A bar chart of monthly cost from fixture.monthlyCosts, filtered live by the current scope. Show all six months.

Product rules. Put them in lib/domain/rules.ts so version B can reuse them later.
- When the scope changes so that it no longer covers exactly one project, hide the project owners checkbox and set recipients.projectOwners to false. Report that it was cleared so Step 5 can log it.
- When every threshold rule is removed, disable all email checkboxes and show the line "Add a threshold rule to turn on email alerts."
- Every valid configuration can be saved even if it does not match the task. An entire-account budget saves. A forecast-only rule saves.

Validation on Finish. The wording is provisional until the capture. Add a TODO comment next to each message.
- Name empty: "Enter a budget name."
- Specified amount with empty, zero, negative or non-numeric target: "Enter an amount greater than $0."
- Projects with Select all unchecked and nothing chosen: "Select at least one project."
- Threshold rules exist but no email option is checked and monitoring is not linked: "Select at least one way to send alerts."
- Percent outside 1 to 1000 or not a number: "Enter a percent from 1 to 1000."
Show each message next to its field and open the section that holds the first error.

Draft and save
- Every change updates local state at once.
- The draft is saved with PUT /api/s/[token]/draft after 500 ms without further changes. For now store drafts in a Prisma table BudgetDraft keyed by token. Step 5 moves the key to the session.
- Finish validates. If valid, POST /api/s/[token]/budgets writes a new Budget row with the full config, then runs evaluate() and stores the result in an Evaluation row. Then go to the saved budget view.
- The saved budget view shows every saved value in the same section order, with an Edit button that reopens the create form loaded with the saved values. Saving again writes a new version row.
- The budgets list shows saved budgets for this token only.
- Cancel goes back to the list and keeps the draft.

Evaluation results must never appear on any participant page or in any participant API response.

Tests
- tests/unit/rules.test.ts for the scope-clears-owner rule and the zero-thresholds rule.
- tests/acceptance/version-a.spec.ts at 1440 x 900 that fills in the correct Atlas budget by clicking, clicks Finish, checks the saved view shows the values, reopens it, and checks the stored Evaluation row has overall true.

Done when a person can save the correct Atlas budget by hand and reopen it, and all tests pass.
```

**Done when** 你自己按任务手动做一遍，存进去，再打开看值对不对。然后故意做错几种（选全部项目、只选预测、收件人保持默认），存进去看数据库里的 Evaluation 行是不是判成失败。最后搜一遍页面源码，确认看不到 "variant"、"Version A" 或者评分结果。

---

## Step 5 · Sessions and event logging

```markdown
Read CLAUDE.md, the Data model and Event logging sections of docs/build-plan.md, and docs/design-guide-v2.md Part 9.

1. Prisma schema. Create the tables Participant, Session, BudgetDraft, Budget, Event, Evaluation, SurveyResponse and FixtureVersion with the fields listed in docs/build-plan.md. Also create AgentRun and AgentStep now so the schema is complete, even though nothing writes to them yet. Session.token is a random 21-character nanoid. Session stores variant, dataset_label, fixture_version, defaults_version, task_version, build_version, evaluator_version, viewport, zoom, started_at, ended_at and termination_reason. Move BudgetDraft, Budget and Evaluation to hang off session_id.

2. Replace the dev token. Every /s/[token] route loads the session on the server. An unknown token shows "This link is not valid." An ended session shows "This session has ended." Keep a seed script that creates one pilot human session for development and prints its link.

3. Client logger in lib/events/. Each event gets a per-session sequence number and a client timestamp. Batch and send every 2 seconds to POST /api/s/[token]/events, and flush with navigator.sendBeacon when the page is hidden. The server adds server_ts and stores events append-only. Never update or delete an Event row.

4. Log every event type in the Event types table of docs/build-plan.md that applies to version A. Use the names exactly. For version A that means
session_started, page_viewed, step_entered, setting_reached, field_changed, setting_returned, option_cleared_by_scope, control_clicked, click_no_effect, scroll, validation_shown, save_clicked, save_attempted, save_succeeded, save_failed, budget_reopened, completion_declared, session_ended, viewport_changed.
Leave screen_viewed and review_edit for version B.

Details
- setting names are name, scope, period, amount, alert and recipients. In version A, map them to the Name field, the Projects control, the Time range control, section 3, the threshold table and the Manage notifications group.
- setting_reached fires the first time a setting's control enters the viewport, using IntersectionObserver.
- setting_returned fires when a person comes back to a setting after having reached a different one. Record the route taken, such as "section_header_click" or "scroll".
- field_changed records field path, old value and new value. Unscored fields are logged too.
- click_no_effect comes from one global click listener. It fires when the click target has no interactive ancestor. Record x, y and route.
- scroll is throttled to one event per 500 ms and records scrollY.
- save_clicked stores the full draft snapshot.

5. I'm finished. Clicking it logs completion_declared, then session_ended with termination_reason "completion_declared", sets ended_at, and goes to /done for humans or to a plain "Session ended" page for synthetic sessions. Record completion even if nothing was saved.

6. Post-task question on /done for humans. One item, provisional until the team picks the instrument. "Overall, how easy or difficult was this task?" on a 1 to 7 scale from "Very difficult" to "Very easy", then a Submit button. Store it in SurveyResponse with instrument "seq-v1". Then show the thank-you text.

7. Write tests/acceptance/events.spec.ts. Run one full session that touches every version A event type at least once, then query the Event table and assert each type is present with increasing seq numbers.

Done when a test session's events include every version A event type in the table and all tests pass.
```

**Done when** 自己完整跑一次任务，然后打开数据库（Neon 网页上就能看表），确认 Event 表里每种事件都有，顺序号是递增的。

---

## Step 6 · Researcher console and exports

```markdown
Read CLAUDE.md, the Researcher console and Exports sections of docs/build-plan.md, and docs/design-guide-v2.md Part 11.

Build /admin behind a password. Use Next.js middleware that checks a signed HTTP-only cookie set after the password in ADMIN_PASSWORD is entered on /admin/login. No participant page may link to /admin. Add noindex to every admin page.

Pages
1. Session list. A table of sessions with created time, actor type, variant, dataset label, familiarity band, status and termination reason. Newest first.

2. New human session. Fields for familiarity band (low, medium, high) and dataset label (pilot, calibration_A, evaluation_A). Variant is fixed to A for now and shown read-only. Add a TODO saying version B and block assignment come in the B build. Creating a session makes a pseudonymous Participant with a random ID and returns the participant link in a copy box. Never ask for or store a name or email.

3. New synthetic session. Fields for model_id, prompt_version, persona_id and calibration_id (optional). Dataset label is fixed to synthetic. Returns the start link /s/[token]/billing. The runner is built later.

4. Session detail. The event timeline in order, with type, time since start, target and payload. Beside it, the final scored budget config and its Evaluation with each criterion, the resolved recipient names and how each was reached. A button "End session" that sets termination_reason "abandoned" for a session a participant left.

5. Assignment view. Counts of sessions by familiarity band and dataset label, split by variant.

6. Re-score. A button that runs the current evaluate() over every stored session and writes new Evaluation rows with the current evaluator_version. Never overwrite old Evaluation rows.

7. Exports. Three downloads.
- events.json, one object per event, grouped by session.
- sessions.csv with exactly the column order given in docs/build-plan.md. Leave B-only columns (review_edits) empty for version A sessions. Compute time_scope_ms and the other time columns from setting_reached and field_changed events, and document the formula in a comment.
- agent_steps.csv with its header row, empty for now.
Every file name carries the build version and the first 8 characters of the fixture hash, for example sessions_build-2026.10.02-a_fx-1a2b3c4d.csv.

8. Build info in the footer of every admin page. Build version, fixture hash, defaults hash, task version and evaluator version.

Tests
- tests/acceptance/admin.spec.ts. Wrong password is rejected. Creating a human session returns a working link. Completing that session shows it in the list with its evaluation. Each export downloads and sessions.csv has the exact header.
- A test that opens every participant page for a finished session and checks the visible page text never contains "overall", "criteria", "variant" or "evaluation". It also checks that no participant API response has a key with one of those names. Check visible text and JSON keys only, because library CSS can contain the word variant.

Done when sessions can be created and ended from the console, the detail view and all three exports work, and all tests pass.
```

**Done when** 从后台新建一个 session，用无痕窗口打开链接做完任务，回到后台看到这一条和它的评分，三个导出文件都能下载，`sessions.csv` 的表头和 build plan 一字不差。

---

## Step 7 · Deploy to Vercel and freeze a pilot build

```markdown
Read CLAUDE.md and the Privacy section of docs/build-plan.md.

Prepare the app for deployment on Vercel with the Neon database.

1. Make the Vercel build run prisma generate and prisma migrate deploy before next build.
2. Read BUILD_VERSION from the environment. If it is not set, fall back to the first 7 characters of VERCEL_GIT_COMMIT_SHA, then to "dev".
3. Add a /api/health route that returns 200 and the build info, without touching participant data.
4. Add a short docs/DEPLOY.md with the exact steps. Link the GitHub repo in Vercel, set DATABASE_URL, ADMIN_PASSWORD and BUILD_VERSION in Vercel project settings, deploy, run the seed script once against production only if asked, and open /api/health to confirm.
5. Add a script "freeze" that prints the current git commit, the fixture hash and the defaults hash, and reminds the user to create a git tag such as pilot-a-v1.

Do not add analytics, tracking scripts or third-party services.

Done when docs/DEPLOY.md exists, npm run build passes locally, and /api/health works.
```

**Done when** 你按 `docs/DEPLOY.md` 部署一次。线上打开 `/api/health` 能看到版本号。线上 `/admin` 要求输密码。打 git tag `pilot-a-v1`。

---

## Step 8 · Acceptance check for version A

```markdown
Read CLAUDE.md and docs/design-guide-v2.md Part 12.

Write tests/acceptance/part12-a.spec.ts. Each case below creates a fresh session through the admin API, drives the version A form by clicking at 1440 x 900, saves, declares completion, and checks the stored Evaluation.

- Required settings saved in A gives overall success
- Correct settings reopened show the same values
- Default recipients saved unchanged fails recipients, with three people resolved
- Project owners checked and billing admins and users cleared passes recipients
- Entire-account scope saved with account recipients is accepted by the product and fails the evaluation
- Only a forecast-based 80% rule fails the evaluation
- The required actual rule beside extra thresholds causes no failure
- Scope widened after project owners was checked hides and clears the option, and an option_cleared_by_scope event is stored
- Monitoring box checked with no channel adds no recipient
- Every threshold rule removed disables the email options
- An earlier mistake corrected before completion can still pass, and the correction stays in the event log
- A required value missing shows validation and the save does not complete
- A new session starts from the defaults, and earlier session records are unchanged
- A click on empty space is logged as click_no_effect

Run the suite against the local server and, if PLAYWRIGHT_BASE_URL is set, against the deployed URL.

Do not change product code to make a test pass without telling me which rule in the guide the change follows.

Done when all cases pass locally and on the deployed URL.
```

**Done when** 本地和线上都全绿。到这里 A 可以拿去做 Gate 1 预实验（6 到 8 个人）。

---

## 每一步做完都要检查

- [ ] `npm run check` 全绿
- [ ] 在 1440×900 下把 A 从头到尾点一遍
- [ ] 读一遍 diff，看有没有文档里没写的按钮或文字
- [ ] 页面源码和网址里看不到 variant 或评分结果
- [ ] `docs/CHANGELOG.md` 多了一行
- [ ] commit，信息里写上是第几步
