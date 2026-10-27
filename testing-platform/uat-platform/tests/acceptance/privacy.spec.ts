import { expect, test, type Page } from "@playwright/test";
import { db } from "@/lib/db";
import { newHumanSession } from "./helpers";

// Only visible text and JSON keys are checked: library CSS and bundles can
// contain a word like "variant" without revealing anything.
const FORBIDDEN = /overall|criteria|variant|evaluation/i;

// The post-task question is specified wording (step 5). Its "Overall" is the
// everyday word and reveals no score, so that one sentence is taken out first.
const SURVEY_QUESTION = "Overall, how easy or difficult was this task?";

function collectKeys(value: unknown, keys: Set<string>) {
  if (Array.isArray(value)) value.forEach((item) => collectKeys(item, keys));
  else if (value && typeof value === "object") {
    for (const [key, inner] of Object.entries(value)) {
      keys.add(key);
      collectKeys(inner, keys);
    }
  }
}

async function expectClean(page: Page, path: string) {
  await page.goto(path);
  await page.waitForLoadState("networkidle");
  const text = (await page.locator("body").innerText()).replace(SURVEY_QUESTION, "");
  expect(text, path).not.toMatch(FORBIDDEN);
  expect(await page.locator('a[href*="/admin"]').count(), `${path} links to the console`).toBe(0);
}

test.afterAll(async () => {
  await db.$disconnect();
});

test("participant pages and participant API responses never show scoring or the variant", async ({ page }) => {
  const session = await newHumanSession();
  const base = `/s/${session.token}`;
  const keys = new Set<string>();
  page.on("response", async (response) => {
    if (!new URL(response.url()).pathname.startsWith("/api/s/")) return;
    collectKeys(await response.json().catch(() => undefined), keys);
  });

  // Save a budget, so Edit Budget and the list have something to show.
  await page.goto(`${base}/billing/budgets/create`);
  await page.getByRole("textbox", { name: "Name *" }).fill("Atlas monthly");
  await page.getByRole("button", { name: "Amount", exact: true }).click();
  await page.getByRole("textbox", { name: "Target amount *" }).fill("1000");
  await page.getByRole("button", { name: "Finish", exact: true }).click();
  await expect(page).toHaveURL(/\/billing\/budgets$/);
  const editHref = await page.getByRole("link", { name: "Atlas monthly", exact: true }).getAttribute("href");
  const budgetPath = editHref!.slice(base.length);

  const pages = [
    "",
    "/billing",
    "/billing/budgets",
    "/billing/budgets/create",
    budgetPath,
    "/billing/account",
    "/stub/reports",
    "/stub/notification-channels",
  ];
  for (const path of pages) await expectClean(page, `${base}${path}`);

  // Finish, answer the question, then visit everything again.
  await page.goto(`${base}/billing`);
  await page.getByRole("button", { name: "I'm finished" }).click();
  await expect(page).toHaveURL(/\/done$/);
  await expectClean(page, `${base}/done`);
  await page.getByRole("radio", { name: "4" }).check();
  await page.getByRole("button", { name: "Submit" }).click();
  await expect(page.getByText("Thank you. You can let the researcher know you are finished.")).toBeVisible();
  for (const path of [...pages, "/done"]) await expectClean(page, `${base}${path}`);

  expect([...keys].filter((key) => FORBIDDEN.test(key))).toEqual([]);
  expect(keys.has("budgetId")).toBe(true); // the save response was inspected
});

test("guided setup pages never show scoring or the variant", async ({ page }) => {
  const session = await newHumanSession("B");
  const base = `/s/${session.token}`;
  await expectClean(page, `${base}/billing/budgets/create`);
  await page.getByLabel("Budget name").fill("Atlas monthly");
  for (let screen = 2; screen <= 7; screen++) {
    if (screen === 5) await page.getByLabel("Amount in dollars").fill("1000");
    await page.getByRole("button", { name: /^Continue to/ }).click();
    const text = await page.locator("body").innerText();
    expect(text, `screen ${screen}`).not.toMatch(FORBIDDEN);
  }
});
