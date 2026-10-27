import { expect, test } from "@playwright/test";
import { db } from "@/lib/db";
import { BudgetForm } from "./budgetForm";
import { newHumanSession } from "./helpers";

let token: string;
let sessionId: string;

test.beforeEach(async () => {
  const session = await newHumanSession();
  token = session.token;
  sessionId = session.id;
});

test.afterAll(async () => {
  await db.$disconnect();
});

test("a person saves the correct Atlas budget by clicking, and reopens it", async ({ page }) => {
  const form = new BudgetForm(page, token);
  await form.open();
  const next = page.getByRole("button", { name: "Next", exact: true });

  // 1 Define: neither kind is chosen at first, as in the capture
  await expect(page.getByRole("radio", { name: /Alerts only/ })).not.toBeChecked();
  await page.getByRole("radio", { name: /Alerts only/ }).check();
  await form.nameField.fill("Atlas monthly");
  await next.click();

  // 2 Scope: the time range stays Monthly; the projects go from all to Atlas only
  await expect(form.projectsDropdown).toContainText("All projects (2)");
  await form.projectsDropdown.click();
  await page.getByRole("checkbox", { name: /^Atlas/ }).check();
  await page.getByRole("button", { name: "OK", exact: true }).click();
  await expect(form.projectsDropdown).toContainText("Atlas");
  await next.click();

  // 3 Amount
  await form.targetField.fill("1000");
  await next.click();

  // 4 Actions: first rule to 80% actual, alert only the project owner
  await form.percentFields.first().fill("80");
  await form.billingAdmins.uncheck();
  await form.projectOwners.check();

  await form.finishAndExpectSaved();

  // The list shows the saved budget
  const row = page.getByRole("row", { name: /Atlas monthly/ });
  for (const text of ["Monthly", "Alerts only", "Atlas", "80%, 90%, and 100%", "$1,000.00"]) {
    await expect(row).toContainText(text);
  }

  // The stored evaluation passes every criterion
  const evaluation = await db.evaluation.findFirst({
    where: { sessionId },
    orderBy: { createdAt: "desc" },
  });
  expect(evaluation?.overallSuccess).toBe(true);
  expect(evaluation?.criteria).toEqual({
    scope: true,
    period: true,
    amount: true,
    alert: true,
    recipients: true,
    persistence: true,
  });

  // Reopen: Edit Budget shows every section with the saved values
  await form.openSaved("Atlas monthly");
  await expect(form.nameField).toHaveValue("Atlas monthly");
  await expect(form.projectsDropdown).toContainText("Atlas");
  await expect(form.targetField).toHaveValue("1000");
  await expect(form.percentFields.first()).toHaveValue("80");
  await expect(form.projectOwners).toBeChecked();

  // Saving again writes a new version of the same budget
  await form.save();
  await expect(page).toHaveURL(/\/billing\/budgets$/);
  const versions = await db.budget.findMany({ where: { sessionId }, orderBy: { version: "asc" } });
  expect(versions.map((row) => row.version)).toEqual([1, 2]);
  expect(new Set(versions.map((row) => row.id)).size).toBe(1);
});

test("the draft survives a reload", async ({ page }) => {
  const form = new BudgetForm(page, token);
  await form.open();
  await form.nameField.fill("Draft only");
  await expect
    .poll(async () => (await db.budgetDraft.findUnique({ where: { sessionId } }))?.draft)
    .toMatchObject({ config: { name: "Draft only" } });
  await page.reload();
  await expect(form.nameField).toHaveValue("Draft only");
});

test("a missing name shows validation and nothing is saved", async ({ page }) => {
  const form = new BudgetForm(page, token);
  await form.open();
  await form.openSection("Actions");
  await form.finish();
  await expect(page.getByText("Enter a budget name.")).toBeVisible();
  await expect(form.nameField).toBeVisible();
  expect(await db.budget.count({ where: { sessionId } })).toBe(0);
});
