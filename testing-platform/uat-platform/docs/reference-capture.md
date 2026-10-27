# Reference capture: Google Cloud Billing, 2026-09-30

Version A copies the Google Cloud Billing console. On 2026-09-30 the project owner took screenshots of a real billing account, and this file records what they showed and how version A follows them. The screenshots themselves are not in the repository because they contain personal account data.

## What version A now follows

### Left navigation

- A "Billing" header, a Billing account picker, and then these groups:
  - Overview.
  - Cost management: Reports, Cost table, Cost breakdown, Incentives, Billing export.
  - Cost control: Budgets & caps (with a Preview chip), Anomalies.
  - Cost optimization: FinOps hub, Committed use discounts, CUD analysis, Pricing, Cost estimation, Credits.
  - Payments: Invoices, Transactions, Payment settings, Payment method.
  - Billing management: Account management.
- Only Overview, Budgets & caps and Account management belong to the study. Every other entry opens the out-of-study page.
- The breadcrumb still says "Budgets and alerts", as it does in the console.

### Budgets list ("Budgets & caps")

- Actions: "+ Create new" and a Delete button that is never enabled.
- Columns:

  | Column | What it shows |
  |---|---|
  | Budget name | The name, which links to Edit Budget |
  | Budget period | The time range |
  | Budget type | The budget kind |
  | Applies to | "This billing account" |
  | Trigger alerts at | For example "50%, 90%, and 100%" |
  | Spend and budget amount | A bar with "$spend / $amount" and "No credits used" |
  | Spend cap status | "Not applicable" |

- Clicking a budget opens Edit Budget. The console has no read-only budget page, so the old saved-budget view is gone.
- After a successful Finish or Save, the participant returns to this list.

### Create Budget

- A numbered vertical stepper with four steps: 1 Define, 2 Scope, 3 Amount and 4 Actions. One step is open at a time.
- The open step has an outlined "Next" button.
- Step icons:
  - A step passed with Next shows a check mark.
  - After Finish, a step with an error shows a red "!".
- Finish and Cancel sit inline below the steps, so they are visible from the start.
- The cost trend panel is on the right.

### Edit Budget

- The saved budget's name is the heading, and all four sections open expanded.
- Each section has a chevron that folds it.
- Save and Cancel are pinned to the bottom of the page.

### Define

- Two radios, and neither is selected by default:
  - "Alerts only (available to all services)", with its (?) help text copied from the capture.
  - "Spend cap enforcement (available for limited services)", with a Preview tag and a description.
- Below them is "Name *".

### Scope

In order:

1. Time range, with the monthly helper text.
2. "Read-only for project users (single-project budgets only)".
3. The scoping explanation.
4. Projects, a checklist that applies on OK:
   - It has Select all, Deselect all, Cancel and OK.
   - With no box ticked, it reads "All projects (2)".
5. Services: "All services (N)".
6. Labels, which can be collapsed.
7. Savings: "Savings programs" and "Other savings", both ticked.

There is no Folders picker, because the account has no organization.

### Amount

- "Set a monthly budget amount".
- A Budget type dropdown with its helper text.
- "Target amount *" with a $ prefix, starting at $0.

### Actions

- Rows start at 50%, 90% and 100%, all Actual.
- Each row has three fields:
  - "Percent of budget N *" (%).
  - "Amount N", which is editable and in sync with the percent.
  - "Trigger on N".
- A "Delete item" button appears when the row is hovered or focused.
- "+ Add threshold" adds an empty row.
- "Email alerts to project owners":
  - It is always shown and has no Preview tag.
  - It works only when the budget covers exactly one project.
  - Otherwise it is disabled, and a (?) reads "This notification method is limited to budgets configured to monitor a single project."

### Cost trend

- One "Total cost" series.
- The budget amount as a red dashed line.
- A date-range subtitle, the forecast note, and "View report".

### Overview and Account management

- **Overview:** a "Your total cost" card for the current month.
- **Account management:** a table of the projects linked to the billing account, and a side panel of principals grouped by role.

## Starting values

`lib/fixtures/defaults-v2.json` holds the starting values from the capture. `defaults-v1.json` is unchanged and stays frozen for the sessions that used it.

| Setting | defaults-v1 | defaults-v2 |
|---|---|---|
| Budget kind | Alerts only | None selected |
| Savings | Not ticked | "Savings programs" and "Other savings" ticked |
| Target amount | Empty | $0, which Finish rejects |

None of them prefills the task answer.

## Deliberate simplifications

- The Filter box on the budgets list is left out, because a participant has at most a few budgets.
- Delete on the list is never enabled.
- Services and Labels are recorded but do not change the chart, because the fixture has costs per project only.

## Still to check against the console

- The full name error. The capture shows only "A budget n…", so the text is provisional.
- Whether Finish complains when no Define radio is chosen. For now it does not.
- Whether $0 is rejected at Next or only at Finish. For now it is only at Finish.
- What the list's "Budget type" column shows. For now it shows "Alerts only" or "Spend cap".
- The list's description paragraph.
- The Labels picker when it is open.
- The page after "Spend cap enforcement" is chosen.
