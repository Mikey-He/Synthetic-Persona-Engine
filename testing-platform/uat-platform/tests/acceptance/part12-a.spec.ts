import { expect, test } from "@playwright/test";
import { db } from "@/lib/db";
import { BudgetForm, newSessionThroughAdmin, storedEvaluation } from "./budgetForm";
import { eventsOf } from "./helpers";

// Guide Part 12, the version A cases. Each case starts a fresh session through
// the researcher console's API, works the form by clicking at 1440 x 900,
// saves, declares completion and checks the stored evaluation.

test.afterAll(async () => {
  await db.$disconnect();
});

const ALL_PASS = { scope: true, period: true, amount: true, alert: true, recipients: true, persistence: true };

test("required settings saved in A give overall success", async ({ page, request }) => {
  const session = await newSessionThroughAdmin(request);
  const form = new BudgetForm(page, session.token);
  await form.open();
  await form.fillRequired();
  await form.setRecipients({ billing: false, owners: true });
  await form.finishAndExpectSaved();
  await form.declareCompletion();

  const evaluation = await storedEvaluation(session.id);
  expect(evaluation.criteria).toEqual(ALL_PASS);
  expect(evaluation.overall).toBe(true);
  expect(evaluation.people).toEqual(["sam-rivera"]);
});

test("correct settings reopened show the same values", async ({ page, request }) => {
  const session = await newSessionThroughAdmin(request);
  const form = new BudgetForm(page, session.token);
  await form.open();
  await form.fillRequired();
  await form.setRecipients({ billing: false, owners: true });
  await form.finishAndExpectSaved();

  const row = page.getByRole("row", { name: /Atlas monthly/ });
  for (const text of ["Monthly", "Atlas", "80%", "$1,000.00"]) {
    await expect(row).toContainText(text);
  }
  await form.openSaved("Atlas monthly");
  await expect(form.nameField).toHaveValue("Atlas monthly");
  await form.openSection("Scope");
  await expect(page.getByRole("button", { name: /^Time range/ })).toContainText("Monthly");
  await expect(form.projectsDropdown).toContainText("Atlas");
  await form.openSection("Amount");
  await expect(page.getByRole("button", { name: /^Budget type/ })).toContainText("Specified amount");
  await expect(form.targetField).toHaveValue("1000");
  await form.openSection("Actions");
  await expect(form.percentFields).toHaveCount(1);
  await expect(form.percentFields.first()).toHaveValue("80");
  await expect(page.getByRole("button", { name: /^Trigger on/ })).toContainText("Actual");
  await expect(form.billingAdmins).not.toBeChecked();
  await expect(form.projectOwners).toBeChecked();
  await form.declareCompletion();

  expect((await storedEvaluation(session.id)).overall).toBe(true);
});

// The guide's "three people" only follows when project owners is checked too,
// so this is the correct budget with the billing admins default left on, as
// in the step 3 evaluator case.
test("default recipients saved unchanged fail recipients, with three people resolved", async ({
  page,
  request,
}) => {
  const session = await newSessionThroughAdmin(request);
  const form = new BudgetForm(page, session.token);
  await form.open();
  await form.fillRequired();
  await form.setRecipients({ owners: true });
  await expect(form.billingAdmins).toBeChecked();
  await form.finishAndExpectSaved();
  await form.declareCompletion();

  const evaluation = await storedEvaluation(session.id);
  expect(evaluation.criteria.recipients).toBe(false);
  expect(evaluation.overall).toBe(false);
  expect(evaluation.people).toEqual(["alex-kim", "jordan-lee", "sam-rivera"]);
});

test("project owners checked and billing admins and users cleared pass recipients", async ({
  page,
  request,
}) => {
  const session = await newSessionThroughAdmin(request);
  const form = new BudgetForm(page, session.token);
  await form.open();
  await form.setName("Owner only");
  await form.setProjects(["Atlas"]);
  await form.setTarget("250");
  await form.setRecipients({ billing: false, owners: true });
  await form.finishAndExpectSaved();
  await form.declareCompletion();

  const evaluation = await storedEvaluation(session.id);
  expect(evaluation.criteria.recipients).toBe(true);
  expect(evaluation.people).toEqual(["sam-rivera"]);
});

test("entire-account scope with account recipients is accepted by the product and fails the evaluation", async ({
  page,
  request,
}) => {
  const session = await newSessionThroughAdmin(request);
  const form = new BudgetForm(page, session.token);
  await form.open();
  await form.setName("Whole account");
  await form.openSection("Scope");
  await expect(form.projectsDropdown).toContainText("All projects (2)");
  await form.setTarget("1000");
  await form.addThreshold({ percent: "80", trigger: "Actual" });
  await form.finishAndExpectSaved();
  await form.declareCompletion();

  const evaluation = await storedEvaluation(session.id);
  expect(evaluation.saved).toBe(true);
  expect(evaluation.criteria.scope).toBe(false);
  expect(evaluation.criteria.recipients).toBe(false);
  expect(evaluation.overall).toBe(false);
  expect(evaluation.people).toEqual(["alex-kim", "jordan-lee"]);
});

test("only a forecast-based 80% rule fails the evaluation", async ({ page, request }) => {
  const session = await newSessionThroughAdmin(request);
  const form = new BudgetForm(page, session.token);
  await form.open();
  await form.setName("Forecast only");
  await form.setProjects(["Atlas"]);
  await form.setTarget("1000");
  await form.setThresholds([{ percent: "80", trigger: "Forecasted" }]);
  await form.setRecipients({ billing: false, owners: true });
  await form.finishAndExpectSaved();
  await form.declareCompletion();

  const evaluation = await storedEvaluation(session.id);
  expect(evaluation.criteria.alert).toBe(false);
  expect(evaluation.overall).toBe(false);
});

test("the required actual rule beside extra thresholds causes no failure", async ({ page, request }) => {
  const session = await newSessionThroughAdmin(request);
  const form = new BudgetForm(page, session.token);
  await form.open();
  await form.setName("Atlas monthly");
  await form.setProjects(["Atlas"]);
  await form.setTarget("1000");
  await form.addThreshold({ percent: "80", trigger: "Actual" });
  await expect(form.percentFields).toHaveCount(4); // 50, 90 and 100 stay
  await form.setRecipients({ billing: false, owners: true });
  await form.finishAndExpectSaved();
  await form.declareCompletion();

  const evaluation = await storedEvaluation(session.id);
  expect(evaluation.criteria).toEqual(ALL_PASS);
  expect(evaluation.overall).toBe(true);
});

test("widening the scope after project owners was checked disables and clears it, and logs the clearing", async ({
  page,
  request,
}) => {
  const session = await newSessionThroughAdmin(request);
  const form = new BudgetForm(page, session.token);
  await form.open();
  await form.fillRequired();
  await form.setRecipients({ owners: true });
  await expect(form.projectOwners).toBeChecked();

  await form.setProjects(["Atlas", "Beacon"]);
  await form.openSection("Actions");
  await expect(form.projectOwners).toBeDisabled();
  await expect(form.projectOwners).not.toBeChecked();

  await form.setProjects(["Atlas"]);
  await form.openSection("Actions");
  await expect(form.projectOwners).not.toBeChecked();
  await form.finishAndExpectSaved();
  await form.declareCompletion();

  const cleared = (await eventsOf(session.id)).filter((e) => e.type === "option_cleared_by_scope");
  expect(cleared.map((e) => e.payload)).toEqual([{ option: "recipients.projectOwners", value: true }]);
  const evaluation = await storedEvaluation(session.id);
  expect(evaluation.people).toEqual(["alex-kim", "jordan-lee"]);
});

test("a linked Monitoring box with no channel adds no recipient", async ({ page, request }) => {
  const session = await newSessionThroughAdmin(request);
  const form = new BudgetForm(page, session.token);
  await form.open();
  await form.fillRequired();
  await form.setRecipients({ billing: false });
  await form.monitoring.check();
  await page.getByRole("radio", { name: "Atlas" }).check();
  await expect(page.getByText("No notification channels").first()).toBeVisible();
  await form.finishAndExpectSaved(); // a linked box is a way to send alerts, so it saves
  await form.declareCompletion();

  const evaluation = await storedEvaluation(session.id);
  expect(evaluation.people).toEqual([]);
  expect(evaluation.criteria.recipients).toBe(false);
});

test("removing every threshold rule disables the email options", async ({ page, request }) => {
  const session = await newSessionThroughAdmin(request);
  const form = new BudgetForm(page, session.token);
  await form.open();
  await form.setName("No rules");
  await form.setProjects(["Atlas"]);
  await form.setTarget("1000");
  await form.setThresholds([]);
  await expect(page.getByText("Add a threshold rule to turn on email alerts.")).toBeVisible();
  await expect(form.billingAdmins).toBeDisabled();
  await expect(form.projectOwners).toBeDisabled();
  await expect(form.monitoring).toBeDisabled();
  await form.finishAndExpectSaved();
  await form.declareCompletion();

  const evaluation = await storedEvaluation(session.id);
  expect(evaluation.people).toEqual([]);
  expect(evaluation.criteria.alert).toBe(false);
});

test("an earlier mistake corrected before completion still passes, and the correction stays in the log", async ({
  page,
  request,
}) => {
  const session = await newSessionThroughAdmin(request);
  const form = new BudgetForm(page, session.token);
  await form.open();
  await form.setName("Atlas monthly");
  await form.setProjects(["Beacon"]); // the mistake
  await form.setTarget("1000");
  await form.setThresholds([{ percent: "80", trigger: "Actual" }]);
  await form.setRecipients({ billing: false, owners: true });
  await form.finishAndExpectSaved();

  await form.openSaved("Atlas monthly");
  await form.setProjects(["Atlas"]); // clears the Beacon owner, so check owners again
  await form.setRecipients({ owners: true });
  await form.save();
  await expect(page).toHaveURL(/\/billing\/budgets$/);
  await form.declareCompletion();

  const evaluation = await storedEvaluation(session.id);
  expect(evaluation.overall).toBe(true);

  const events = await eventsOf(session.id);
  const scopeChanges = events
    .filter((e) => e.type === "field_changed" && e.target === "scope.projectIds")
    .map((e) => (e.payload as { newValue: string[] }).newValue);
  expect(scopeChanges).toContainEqual(["beacon-demo"]);
  expect(scopeChanges.at(-1)).toEqual(["atlas-demo"]);
  expect(events.filter((e) => e.type === "save_succeeded")).toHaveLength(2);
  expect(await db.budget.count({ where: { sessionId: session.id } })).toBe(2);
});

test("a missing required value shows validation and the save does not complete", async ({ page, request }) => {
  const session = await newSessionThroughAdmin(request);
  const form = new BudgetForm(page, session.token);
  await form.open();
  await form.setProjects(["Atlas"]);
  await form.setTarget("1000");
  await form.finish();
  await expect(page.getByText("Enter a budget name.")).toBeVisible();
  await expect(page).toHaveURL(/\/billing\/budgets\/create$/);
  expect(await db.budget.count({ where: { sessionId: session.id } })).toBe(0);
  await form.declareCompletion();

  const evaluation = await storedEvaluation(session.id);
  expect(evaluation.saved).toBe(false);
  expect(evaluation.criteria.persistence).toBe(false);
  const events = await eventsOf(session.id);
  expect(events.some((e) => e.type === "validation_shown")).toBe(true);
  expect(events.some((e) => e.type === "save_succeeded")).toBe(false);
});

test("a new session starts from the defaults and leaves earlier session records unchanged", async ({
  page,
  request,
}) => {
  const first = await newSessionThroughAdmin(request);
  const firstForm = new BudgetForm(page, first.token);
  await firstForm.open();
  await firstForm.fillRequired();
  await firstForm.setRecipients({ billing: false, owners: true });
  await firstForm.finishAndExpectSaved();
  await firstForm.declareCompletion();
  const snapshot = async () => ({
    budgets: await db.budget.findMany({ where: { sessionId: first.id }, orderBy: { version: "asc" } }),
    evaluations: await db.evaluation.findMany({ where: { sessionId: first.id }, orderBy: { createdAt: "asc" } }),
    events: await eventsOf(first.id),
    session: await db.session.findUniqueOrThrow({ where: { id: first.id } }),
  });
  const before = await snapshot();

  const second = await newSessionThroughAdmin(request);
  const form = new BudgetForm(page, second.token);
  await form.open();
  await expect(form.nameField).toHaveValue("");
  await expect(page.getByRole("radio", { name: /Alerts only/ })).not.toBeChecked();
  await expect(page.getByRole("radio", { name: /Spend cap enforcement/ })).not.toBeChecked();
  await form.openSection("Scope");
  await expect(page.getByRole("button", { name: /^Time range/ })).toContainText("Monthly");
  await expect(form.projectsDropdown).toContainText("All projects (2)");
  await form.openSection("Amount");
  await expect(page.getByRole("button", { name: /^Budget type/ })).toContainText("Specified amount");
  await expect(form.targetField).toHaveValue("0");
  await form.openSection("Actions");
  await expect(form.percentFields).toHaveCount(3);
  for (const [i, percent] of ["50", "90", "100"].entries()) {
    await expect(form.percentFields.nth(i)).toHaveValue(percent);
  }
  await expect(form.billingAdmins).toBeChecked();
  await expect(form.projectOwners).toBeDisabled();
  await expect(form.monitoring).not.toBeChecked();
  await expect(form.checkbox("Connect a Pub/Sub topic to this budget")).not.toBeChecked();
  await form.declareCompletion();

  expect(await snapshot()).toEqual(before);
});

test("a click on empty space is logged as click_no_effect", async ({ page, request }) => {
  const session = await newSessionThroughAdmin(request);
  await page.goto(`/s/${session.token}/billing`);
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  await page.mouse.click(1300, 700); // blank console background
  const form = new BudgetForm(page, session.token);
  await form.open();
  await form.fillRequired();
  await form.finishAndExpectSaved();
  await form.declareCompletion();

  const noEffect = (await eventsOf(session.id)).filter((e) => e.type === "click_no_effect");
  expect(noEffect.map((e) => e.payload)).toContainEqual({ x: 1300, y: 700, route: "/billing" });
  expect((await storedEvaluation(session.id)).saved).toBe(true);
});
