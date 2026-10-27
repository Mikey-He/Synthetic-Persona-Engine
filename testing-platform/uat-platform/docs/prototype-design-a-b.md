# Prototype Design · Version A and Version B

Sep 29, 2026 · @HCF

## At a glance

Version A is the advanced form copied from Google Cloud. Version B is a simplified guided setup modeled on AWS's template workflow tailored for Google Cloud. Both create the same budget and are scored the same way.

|  | Version A · advanced form | Version B · guided setup |
| --- | --- | --- |
| Modeled on | Google Cloud Budgets & alerts | AWS Budgets simplified template workflow, rebuilt with Google Cloud's settings and defaults |
| Shape | Four sections on one long create page | Seven screens, one question each |
| Hidden settings | None | Extra scope filters and advanced notification options, left at defaults |
| Role in the study | Calibration data for synthetic users | Held-out test of calibrated synthetic users |
| Expected errors | More, which gives calibration something to learn | Fewer, which is the design's hypothesis |

> Diagram (see the online doc). A goes Budgets list, then one create page with four sections. B goes Budgets list, then seven screens (Name, Projects, Period, Amount, Alerts, Recipients, Review). Both end in the same saved budget scored by the same evaluator.

The Design and Build Guide (v2) sets the rules. This document shows what each screen looks like and says. When they disagree, the guide wins.

## Shared shell

Everything outside the create flow is the same page in both versions. Build it once and switch only the create flow by variant. The study viewport is 1440 by 900. Use Roboto and a neutral product name such as Cloud Console (prototype), with no Google logo.

| Area | What it shows | Notes |
| --- | --- | --- |
| Task bar | The task text from guide Part 3, word for word, with an I'm finished button on the right | Fixed above the console frame on every page, stubs included. Fixed height so screenshots line up across sessions. |
| Console frame | A top bar with the product name, the account Northstar Research and the signed-in user Alex Kim. A left menu with Overview, Reports, Budgets & alerts and Account management. | Reports opens the neutral placeholder page. |
| Billing overview | The start page. It shows the account name with its ID. Below that sit this month's cost so far and a small cost chart split by project. | All numbers come from the frozen fixture. |
| Budgets & alerts list | A table of budgets with Name, Scope, Amount and Alerts columns. A Create budget button sits above the table. | Starting contents follow the Part 13 decision in the guide. |
| Saved budget view | The saved values in the reference layout, with an Edit button | Edit reopens the variant's own create flow with saved values loaded. In B it opens the review screen. |
| Account management | A read-only table of billing account members. Alex Kim (you) is Billing Account Administrator. Jordan Lee is Billing Account User. | Matches the fixture exactly, since B lists these same names. |
| Notification channels stub | "Notification channels are outside this study." plus a back link | Reached from Manage notification channels in A. |
| Other links | "This page is not part of the study." plus a back link | Every visit is logged. |

The create flow is the only part that changes. Pressing Create budget in the list opens the A form or the B guided setup depending on the session's variant.

## Version A · the advanced form

A copies the Google Cloud create budget page. It is one long page with four numbered sections stacked on the left and a cost trend chart on the right. Each section has a Next button that opens the one below it. A section heading can be clicked at any time to reopen it. Finish and Cancel sit at the bottom of the page.

### Section by section

| Section | Controls | Starts at |
| --- | --- | --- |
| 1 Define | Budget name text field. Budget kind shown as Alerts only. | Name empty |
| 2 Scope | Time range dropdown with Monthly, Quarterly, Yearly and Custom range. Folders & organizations picker. Projects multi-select listing Atlas and Beacon. Services picker. Labels picker. Savings checkboxes. Read-only for project users checkbox. | Monthly. Projects from the capture. All savings types checked. Read-only unchecked. |
| 3 Amount | Budget type choice between Specified amount and Last month's spend. Target amount field in dollars. | Specified amount, field empty |
| 4 Actions | Threshold table with Percent of budget, Amount and Trigger on columns. Trigger on is a dropdown with Actual and Forecasted. Add threshold button and a delete icon per row. Below it, Manage notifications. | Three rows at 50%, 90% and 100% of Actual |

### Manage notifications in section 4

- **Email alerts to billing admins and users.** Checked at start. No names are shown next to it, which is the gap B tries to close.
- **Email alerts to project owners.** Marked Preview. Appears only when Projects holds exactly one project. Unchecked at start.
- **Link Monitoring email notification channels to this budget.** Unchecked. Checking it reveals a project picker, and both projects list zero channels. The Manage notification channels link opens the stub.
- **Connect a Pub/Sub topic to this budget.** Unchecked. Checking it reveals a topic picker with no topics.

### Cost trend chart

The chart follows the Scope filters, so choosing Atlas alone changes the bars. It shows fixture numbers only. Where it sits when the user reaches section 4 at 1440 by 900 is still to be confirmed in the capture.

### What A does not have

No review page before saving and no names next to recipient options. There is also no one-question-at-a-time flow. These are exactly the things B adds, so A must not borrow any of them.

## Version B · the guided setup

B asks one question per screen, in the style of the AWS simplified template workflow tailored for Google Cloud. AWS supplies only the one-question-per-screen pattern. Every setting and default comes from Google Cloud, and so does every product rule. Only the path through them changes. Every screen has the same layout. A progress bar at the top lists all seven screen names with the current one marked. Under it sit the question in large type and a one-line reason in grey. The controls come next, with Back and Continue at the bottom. Continue names the next screen.

Every screen starts at the reference default. Nothing is prefilled from the task answer, and no option is labeled recommended.

| Screen | Question | Reason line | Controls | Starts at | Main button |
| --- | --- | --- | --- | --- | --- |
| 1 Name | What should this budget be called? | A clear name helps you find it later. | Text field | Empty | Continue to projects |
| 2 Projects | Which costs should this budget track? | Costs from projects you leave out will not count toward this budget. | All projects in Northstar Research, or Only specific projects | Reference default from the capture | Continue to period |
| 3 Period | How often should the budget start over? | Spending resets to $0 at the start of each period. | Monthly, Quarterly, Yearly or Custom dates | Monthly | Continue to amount |
| 4 Amount | How much should this budget allow each period? | Alerts are measured against this amount. | A fixed amount with a dollar field, or Match last period's spend | Fixed amount, field empty | Continue to alerts |
| 5 Alerts | When should alert emails go out? | Each rule sends an email when spending reaches a share of the amount. | One sentence per rule | 50%, 90% and 100% of money already spent | Continue to recipients |
| 6 Recipients | Who should get alert emails? | These people get an email whenever an alert rule is reached. | One checkbox per group, with names listed under each | Billing account admins and users checked | Continue to review |
| 7 Review | Here is your budget | Check each answer before you create the budget. | Summary lines with Edit links | Not applicable | Create budget |

### Screen 2 · Projects

Two radio options. Choosing Only specific projects reveals a checklist.

- Atlas · atlas-demo
- Beacon · beacon-demo

Each chosen project shows as a chip under the question, for example "Tracking · Atlas". The chip row stays visible as long as the user is on this screen. If Only specific projects is chosen with nothing checked, Continue shows "Choose at least one project".

### Screen 5 · Alerts

Each rule is one editable sentence.

> Email when **money already spent** ▾ reaches **50** % ($500)

The bold parts are controls. The dropdown switches between money already spent and money expected by the end of the period. The dollar figure in brackets updates from the screen 4 amount. Each row has a remove icon, and an Add another rule link sits below the list. Removing every rule is allowed.

### Screen 6 · Recipients

- [x] **Billing account admins and users**
  - Alex Kim (you) · Billing Account Administrator
  - Jordan Lee · Billing Account User
- [ ] **Project owners**
  - Sam Rivera · Atlas owner

The Project owners option appears only when screen 2 holds exactly one project. The name under it is that project's owner, so Priya Shah would appear for Beacon. When the option is hidden, one grey line says "Project owner emails are available when the budget covers one project." When there are no alert rules, both options are disabled and the screen says "Alert emails are off because there are no alert rules." When rules exist and nothing is checked, Continue shows "Choose at least one recipient".

### Screen 7 · Review

One line per earlier screen, each with an Edit link on the right. Example with a filled-in budget:

| Item | Your answer |
| --- | --- |
| Name | Atlas monthly |
| Tracks | Only Atlas |
| Starts over | Every month |
| Amount | $1,000 each month |
| Alerts | Email when money already spent reaches 50% ($500). Also at 80% ($800). |
| Recipients | Project owners · Sam Rivera |

Edit opens that screen, and its main button then reads Back to review. Create budget saves and opens the saved budget view. B offers no switch to the advanced form.

## Wireframes

The two drawings show the same decision point in each version, choosing who gets the alert. They are layout sketches. Final spacing and styling follow the reference capture.

> Wireframe (see the online doc). Left, A with section 4 open, showing the threshold table and four notification checkboxes named by role group only. Right, B screen 6, showing the question, a reason line, and two options with the real people listed under each.

In A the recipient choice is four checkboxes near the bottom of a long page, named by role group only. In B it is the whole screen, and each choice lists the real people it would email. It is one of the clearest places where the two paths differ.

## States and edge cases

Both versions run on the same product rules, so each case below behaves the same way underneath. Only what the user sees differs.

| Case | Version A | Version B | Logged as |
| --- | --- | --- | --- |
| Owner option checked, then a second project is added | The project owners checkbox disappears and clears | The Project owners option disappears and clears. The grey note appears. | Cleared value as its own event |
| Every alert rule removed | Email settings turn disabled | Screen 6 says alert emails are off, with both options disabled | Rule removals |
| Rules exist but no recipient is chosen | Reference error copy from the capture, shown on Finish | "Choose at least one recipient" on Continue | Validation event |
| Only specific projects with nothing checked | Reference error copy from the capture | "Choose at least one project" on Continue | Validation event |
| Amount empty or not a number | Reference error copy from the capture | "Enter an amount greater than $0" on Continue | Validation event |
| Going back | Reopening a section keeps its values | Back keeps every earlier answer | Section or screen view |
| Edit from review | Not applicable | Opens that screen, then returns to review | Review edit |
| Leaving the flow through the menu | Follows the capture | Same rule as A | Navigation event |
| I'm finished pressed before saving | The attempt ends with no saved budget | Same | Completion declared |
| Saved budget reopened and changed | Scored by the rules in guide Part 7 | Same | Save event |

Every valid configuration can be saved, including ones that fail the task. An entire-account budget saves normally. So does a forecast rule. The evaluator judges task accuracy later and never shows it to the participant.

## Items to confirm before building

These come from the reference capture or from a team decision. Settle each one before the A baseline is frozen, because B copies A's defaults.

- [ ] The project owners option exists in the account context used, with its exact label and Preview tag.
- [ ] The default project selection on a new budget. Both A and B screen 2 start from it.
- [ ] Whether Finish in A is always visible or appears only after section 4.
- [ ] Where the cost trend chart sits at 1440 by 900 when section 4 is open.
- [ ] Exact label text and order in section 4.
- [ ] A's own error copy for missing recipients, missing projects and a bad amount.
- [ ] What a checked project owners option does when the scope widens. The current rule hides and clears it.
- [ ] Whether the budget list starts empty (guide Part 13).
- [ ] Team decision on the screen 6 grey note. It explains a real product rule, but A has no matching text. Keep it as part of B's design or remove it to keep B closer to A.
- [ ] Team decision on where Edit in the saved budget view lands in B. The current choice is the review screen.
