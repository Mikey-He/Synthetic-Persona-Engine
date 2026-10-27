import { expect, test } from "@playwright/test";
import { db } from "@/lib/db";
import { VERSION_A_EVENT_TYPES } from "@/lib/events/types";
import { eventsOf, newHumanSession } from "./helpers";

test.afterAll(async () => {
  await db.$disconnect();
});

test("one full version A session records every version A event type in sequence", async ({ page }) => {
  const session = await newHumanSession();
  const token = session.token;

  // session_started and page_viewed on the consent page, control_clicked on Start task
  await page.goto(`/s/${token}`);
  await page.getByRole("link", { name: "Start task" }).click();
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();

  // click_no_effect on plain text, viewport_changed on a resize
  await page.getByRole("heading", { name: "Overview" }).click();
  await page.setViewportSize({ width: 1500, height: 950 });
  await page.waitForTimeout(500);
  await page.setViewportSize({ width: 1440, height: 900 });

  // step_entered, setting_reached and field_changed through the four sections
  await page.getByRole("link", { name: /^Budgets & caps/ }).click();
  await page.getByRole("link", { name: "Create new" }).click();
  await page.getByRole("textbox", { name: "Name *" }).fill("Atlas monthly");
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.getByRole("button", { name: /^Projects/ }).click();
  await page.getByRole("checkbox", { name: /^Atlas/ }).check();
  await page.getByRole("button", { name: "OK", exact: true }).click();
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.getByRole("textbox", { name: "Target amount *" }).fill("1000");
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.getByRole("textbox", { name: /^Percent of budget/ }).first().fill("80");
  await page.getByRole("checkbox", { name: "Email alerts to billing admins and users" }).uncheck();
  await page.getByRole("checkbox", { name: /Email alerts to project owners/ }).check();

  // setting_returned by reopening Scope, option_cleared_by_scope by adding Beacon
  await page.getByRole("button", { name: "Scope", exact: true }).click();
  const projects = page.getByRole("button", { name: /^Projects/ });
  await projects.click();
  await page.getByRole("checkbox", { name: /^Beacon/ }).check();
  await page.getByRole("button", { name: "OK", exact: true }).click();
  await projects.click();
  await page.getByRole("checkbox", { name: /^Beacon/ }).uncheck();
  await page.getByRole("button", { name: "OK", exact: true }).click();

  // scroll
  await page.mouse.wheel(0, 300);
  await page.waitForTimeout(800);

  // save_clicked, save_attempted, validation_shown and save_failed: the owner
  // option was cleared, so no way to send alerts is left
  await page.getByRole("button", { name: "Finish", exact: true }).click();
  await expect(page.getByText("Select at least one way to send alerts.")).toBeVisible();

  // save_succeeded once fixed
  await page.getByRole("button", { name: "Actions", exact: true }).click();
  await page.getByRole("checkbox", { name: /Email alerts to project owners/ }).check();
  await page.getByRole("button", { name: "Finish", exact: true }).click();
  await expect(page).toHaveURL(/\/billing\/budgets$/);

  // budget_reopened
  await page.getByRole("link", { name: "Atlas monthly", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Edit Budget" })).toBeVisible();

  // completion_declared and session_ended
  await page.getByRole("button", { name: "I'm finished" }).click();
  await expect(page).toHaveURL(new RegExp(`/s/${token}/done$`));

  const events = await eventsOf(session.id);
  const types = new Set(events.map((event) => event.type));
  for (const type of VERSION_A_EVENT_TYPES) expect(types.has(type), `${type} was logged`).toBe(true);

  // 1, 2, 3 ... with no gap and no repeat, so no event went missing
  expect(events.map((event) => event.seq)).toEqual(events.map((_, i) => i + 1));
  expect(events.slice(-2).map((event) => event.type)).toEqual(["completion_declared", "session_ended"]);

  // A page is announced before anything that happens on it.
  const createViewed = events.findIndex(
    (event) => event.type === "page_viewed" && event.target === "/billing/budgets/create",
  );
  expect(createViewed).toBeGreaterThan(-1);
  expect(createViewed).toBeLessThan(events.findIndex((event) => event.type === "step_entered"));

  const returned = events.find((event) => event.type === "setting_returned");
  expect(returned?.payload).toMatchObject({ route: "section_header_click" });
  const cleared = events.find((event) => event.type === "option_cleared_by_scope");
  expect(cleared?.payload).toEqual({ option: "recipients.projectOwners", value: true });

  const started = await db.session.findUniqueOrThrow({ where: { id: session.id } });
  expect(started.startedAt).not.toBeNull();
  expect(started.viewport).toEqual({ width: 1440, height: 900 });
});
