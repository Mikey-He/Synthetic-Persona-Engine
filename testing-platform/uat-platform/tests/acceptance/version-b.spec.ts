import { expect, test } from "@playwright/test";
import { db } from "@/lib/db";
import { defaults } from "@/lib/fixtures";
import { sessionEvaluation } from "@/lib/scoring";
import { BudgetForm, newSessionThroughAdmin } from "./budgetForm";
import { GuidedFlow } from "./guidedFlow";
import { eventsOf, newHumanSession } from "./helpers";

// The guided setup, checked against guide Part 14.9.

test.afterAll(async () => {
  await db.$disconnect();
});

async function newFlow(page: import("@playwright/test").Page) {
  const session = await newHumanSession("B");
  const flow = new GuidedFlow(page, session.token);
  await flow.open();
  return { session, flow };
}

async function lastSaved(sessionId: string) {
  const budget = await db.budget.findFirstOrThrow({ where: { sessionId }, orderBy: { savedAt: "desc" } });
  return budget.config;
}

test("the same configuration entered through A and B saves identically and scores identically", async ({
  page,
}) => {
  const { session: b, flow } = await newFlow(page);
  await flow.enterAtlasBudget();
  await flow.create();

  const a = await newHumanSession("A");
  const form = new BudgetForm(page, a.token);
  await form.open();
  await form.fillRequired();
  await form.setRecipients({ billing: false, owners: true });
  await form.finishAndExpectSaved();

  expect(await lastSaved(b.id)).toEqual(await lastSaved(a.id));
  const [fromA, fromB] = await Promise.all([sessionEvaluation(a.id), sessionEvaluation(b.id)]);
  expect(fromB.evaluation?.criteria).toEqual(fromA.evaluation?.criteria);
  expect(fromB.evaluation?.overallSuccess).toBe(true);
  expect(fromB.evaluation?.resolvedRecipients).toEqual(fromA.evaluation?.resolvedRecipients);
});

test("each screen opens at the reference default", async ({ page }) => {
  const { flow } = await newFlow(page);
  await expect(flow.nameField).toHaveValue("");
  await flow.nameField.fill("Defaults");
  await flow.next();

  await flow.expectScreen("Which costs should this budget track?");
  await expect(page.getByRole("radio", { name: "All projects in Northstar Research" })).toBeChecked();
  await flow.next();

  await flow.expectScreen("How often should the budget start over?");
  await expect(page.getByRole("radio", { name: "Monthly" })).toBeChecked();
  await flow.next();

  await flow.expectScreen("How much should this budget allow each period?");
  await expect(page.getByRole("radio", { name: "A fixed amount" })).toBeChecked();
  await expect(flow.amountField).toHaveValue(String(defaults.config.amount.target ?? ""));
  await flow.next();
  await expect(page.getByText("Enter an amount greater than $0")).toBeVisible();
  await flow.amountField.fill("200");
  await flow.next();

  await flow.expectScreen("When should alert emails go out?");
  await expect(flow.percentFields).toHaveCount(3);
  for (const [i, percent] of ["50", "90", "100"].entries()) {
    await expect(flow.percentFields.nth(i)).toHaveValue(percent);
    await expect(page.getByRole("button", { name: new RegExp(`^Spend type ${i + 1}`) })).toContainText(
      "money already spent",
    );
  }
  await flow.next();

  await flow.expectScreen("Who should get alert emails?");
  await expect(flow.billingAdmins).toBeChecked();
  await expect(flow.main).toContainText("Alex Kim (you) · Billing Account Administrator");
  await expect(flow.main).toContainText("Jordan Lee · Billing Account User");
  await expect(flow.projectOwners).toHaveCount(0);
  await expect(page.getByText("Project owner emails are available when the budget covers one project.")).toBeVisible();
});

test("project owners appears for one project, then disappears and clears when the choice widens", async ({
  page,
}) => {
  const { session, flow } = await newFlow(page);
  await flow.nameField.fill("Owners");
  await flow.next();
  await page.getByRole("radio", { name: "Only specific projects" }).check();
  await flow.next();
  await expect(page.getByText("Choose at least one project")).toBeVisible();
  await flow.chooseProjects(["Atlas"]);
  await expect(page.getByText("Tracking · Atlas")).toBeVisible();
  await flow.next();
  await flow.next();
  await flow.amountField.fill("1000");
  await flow.next();
  await flow.next();
  await expect(flow.main).toContainText("Sam Rivera · Atlas owner");
  await flow.projectOwners.check();

  // Back keeps every earlier answer.
  for (let i = 0; i < 4; i++) await flow.back();
  await flow.expectScreen("Which costs should this budget track?");
  await expect(page.getByRole("checkbox", { name: /^Atlas · / })).toBeChecked();
  await flow.back();
  await expect(flow.nameField).toHaveValue("Owners");
  await flow.next();

  await flow.chooseProjects(["Atlas", "Beacon"]);
  for (let i = 0; i < 4; i++) await flow.next();
  await flow.expectScreen("Who should get alert emails?");
  await expect(flow.projectOwners).toHaveCount(0);
  await expect(page.getByText("Project owner emails are available when the budget covers one project.")).toBeVisible();

  // Events reach the server in batches, every 2 seconds.
  await expect
    .poll(async () => (await eventsOf(session.id)).filter((e) => e.type === "option_cleared_by_scope").map((e) => e.payload))
    .toEqual([{ option: "recipients.projectOwners", value: true }]);
});

test("removing every alert rule turns alert emails off on the recipients screen", async ({ page }) => {
  const { flow } = await newFlow(page);
  await flow.nameField.fill("No rules");
  await flow.next();
  await flow.next();
  await flow.next();
  await flow.amountField.fill("300");
  await flow.next();
  await flow.setRules([]);
  await flow.next();
  await expect(page.getByText("Alert emails are off because there are no alert rules.")).toBeVisible();
  await expect(flow.billingAdmins).toBeDisabled();
  await flow.next();
  await expect(flow.main).toContainText("No alert rules");
});

test("Edit on the review screen opens that screen and returns to review", async ({ page }) => {
  const { session, flow } = await newFlow(page);
  await flow.enterAtlasBudget();
  await page.getByRole("button", { name: "Edit amount" }).click();
  await flow.expectScreen("How much should this budget allow each period?");
  await flow.amountField.fill("1200");
  await expect(page.getByRole("button", { name: "Back to review" })).toBeVisible();
  await flow.next();
  await flow.expectScreen("Here is your budget");
  await expect(flow.main).toContainText("$1,200 each month");

  await expect
    .poll(async () => (await eventsOf(session.id)).filter((e) => e.type === "review_edit").map((e) => e.payload))
    .toEqual([{ setting: "amount", screen: "amount" }]);
});

test("a save from B keeps the reference defaults for the settings B does not ask about", async ({ page }) => {
  const { session, flow } = await newFlow(page);
  await flow.enterAtlasBudget();
  await flow.create();
  const saved = await lastSaved(session.id);
  const reference = defaults.config;
  expect(saved).toMatchObject({
    kind: reference.kind,
    scope: {
      filters: reference.scope.filters,
      savings: reference.scope.savings,
      readOnlyForProjectUsers: reference.scope.readOnlyForProjectUsers,
    },
    recipients: { monitoring: reference.recipients.monitoring },
  });
  expect((saved as { recipients: { pubsubTopic?: string } }).recipients.pubsubTopic).toBe(
    reference.recipients.pubsubTopic,
  );
});

test("B copy has no recommended label and no mention of the task, on any screen", async ({ page }) => {
  const { flow } = await newFlow(page);
  await flow.nameField.fill("Copy check");
  for (let screen = 1; screen <= 7; screen++) {
    const text = await flow.main.innerText();
    expect(text, `screen ${screen}`).not.toMatch(/recommend/i);
    expect(text, `screen ${screen}`).not.toMatch(/task|variant|Only the Atlas project owner/i);
    if (screen === 4) await flow.amountField.fill("100");
    if (screen < 7) await flow.next();
  }
});

test("a screen_viewed event fires for every screen in order, and a saved budget reopens on review", async ({
  page,
}) => {
  const { session, flow } = await newFlow(page);
  await flow.enterAtlasBudget();
  await flow.create();

  await page.getByRole("link", { name: "Atlas monthly", exact: true }).click();
  await flow.expectScreen("Here is your budget");
  await expect(flow.main).toContainText("Only Atlas");

  const screensViewed = async () =>
    (await eventsOf(session.id)).filter((e) => e.type === "screen_viewed").map((e) => e.target);
  await expect
    .poll(screensViewed)
    .toEqual(["name", "projects", "period", "amount", "alerts", "recipients", "review", "review"]);
  const events = await eventsOf(session.id);
  const reopened = events.findIndex((e) => e.type === "budget_reopened");
  expect(reopened).toBeGreaterThan(events.findIndex((e) => e.type === "save_succeeded"));
  const reached = events.filter((e) => e.type === "setting_reached").map((e) => e.target);
  expect(reached).toEqual(["name", "scope", "period", "amount", "alert", "recipients"]);
});

test("main-study sessions alternate variants in blocks of two within a band", async ({ request }) => {
  const count = () =>
    db.session.count({
      where: { datasetLabel: { in: ["evaluation_A", "evaluation_B"] }, participant: { familiarityBand: "low" } },
    });
  const create = async () => {
    await newSessionThroughAdmin(request); // signs in as the researcher
    const response = await request.post("/api/admin/sessions", {
      data: { actorType: "human", familiarityBand: "low", datasetLabel: "evaluation" },
    });
    expect(response.status()).toBe(201);
    const { id, variant } = (await response.json()) as { id: string; variant: "A" | "B" };
    const row = await db.session.findUniqueOrThrow({ where: { id } });
    expect(row.datasetLabel).toBe(`evaluation_${variant}`);
    return variant;
  };

  if ((await count()) % 2 === 1) await create(); // finish a block left open by an earlier run
  const first = await create();
  const second = await create();
  expect(new Set([first, second])).toEqual(new Set(["A", "B"]));

  const refused = await request.post("/api/admin/sessions", {
    data: { actorType: "human", familiarityBand: "low", datasetLabel: "calibration_A", variant: "B" },
  });
  expect(refused.status()).toBe(400);
});
