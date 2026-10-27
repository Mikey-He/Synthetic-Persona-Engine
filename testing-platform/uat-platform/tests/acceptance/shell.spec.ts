import { expect, test } from "@playwright/test";
import { db } from "@/lib/db";
import { newHumanSession, newSyntheticSession } from "./helpers";

const ROUTES = [
  "",
  "/billing",
  "/billing/budgets",
  "/billing/budgets/create",
  "/billing/account",
  "/stub/reports",
  "/stub/notification-channels",
  "/done",
];

let token: string;

test.beforeEach(async () => {
  token = (await newHumanSession()).token;
});

for (const route of ROUTES) {
  test(`/s/<token>${route} renders cleanly and every visible link works`, async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (message) => {
      if (message.type() === "error") errors.push(message.text());
    });
    page.on("pageerror", (error) => errors.push(error.message));

    const response = await page.goto(`/s/${token}${route}`);
    expect(response?.status()).toBe(200);
    await page.waitForLoadState("networkidle");
    await expect(page).toHaveTitle("Cloud Console (prototype)");

    // Light DOM only, so framework dev tooling inside shadow roots is not counted.
    const hrefs = await page.evaluate(() =>
      Array.from(document.querySelectorAll("a"))
        .filter((a) => a.checkVisibility())
        .map((a) => a.getAttribute("href") ?? ""),
    );
    for (const href of hrefs) {
      expect(href, "a link needs a real target").not.toMatch(/^(#.*)?$/);
      const linked = await page.request.get(href);
      expect(linked.status(), href).toBe(200);
    }
    expect(errors).toEqual([]);
  });
}

test("task bar always shows the whole task at a fixed height", async ({ page }) => {
  await page.goto(`/s/${token}/billing/budgets/create`);
  const bar = page.getByRole("button", { name: "I'm finished" }).locator("xpath=..");

  expect((await bar.boundingBox())?.height).toBe(136);
  const lastParagraph = await page
    .getByText("Save your settings and indicate when you have finished.")
    .boundingBox();
  expect(lastParagraph!.y + lastParagraph!.height).toBeLessThanOrEqual(136);
  await expect(page.getByRole("button", { name: /collapse|expand/i })).toHaveCount(0);

  await page.mouse.wheel(0, 800);
  await expect(page.getByText("Only the Atlas project owner should receive this alert.")).toBeInViewport();
});

test("viewport gate covers small windows and lifts once the window is large enough", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1200, height: 800 });
  await page.goto(`/s/${token}/billing`);
  await expect(
    page.getByText(
      "Please make this window larger. It needs to be at least 1440 by 900. Current size is 1200 by 800.",
    ),
  ).toBeVisible();

  await page.setViewportSize({ width: 1440, height: 800 });
  await expect(page.getByText("Current size is 1440 by 800.")).toBeVisible();

  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(page.getByText("Please make this window larger.")).toHaveCount(0);
});

test("an unknown token shows that the link is not valid", async ({ page }) => {
  await page.goto("/s/not-a-real-token/billing");
  await expect(page.getByText("This link is not valid.")).toBeVisible();
});

test("I'm finished ends the session, asks the post-task question once, and closes the pages", async ({
  page,
}) => {
  await page.goto(`/s/${token}/billing`);
  await page.getByRole("button", { name: "I'm finished" }).click();
  await expect(page).toHaveURL(new RegExp(`/s/${token}/done$`));

  const session = await db.session.findUniqueOrThrow({ where: { token } });
  expect(session.endedAt).not.toBeNull();
  expect(session.terminationReason).toBe("completion_declared");

  await expect(page.getByText("Overall, how easy or difficult was this task?")).toBeVisible();
  const submit = page.getByRole("button", { name: "Submit" });
  await expect(submit).toBeDisabled();
  await page.getByRole("radio", { name: "6" }).check();
  await submit.click();
  await expect(page.getByText("Thank you. You can let the researcher know you are finished.")).toBeVisible();

  const answers = await db.surveyResponse.findMany({ where: { sessionId: session.id } });
  expect(answers.map((a) => [a.instrument, a.answers])).toEqual([["seq-v1", { ease: 6 }]]);

  for (const route of ["", "/billing", "/billing/budgets/create"]) {
    await page.goto(`/s/${token}${route}`);
    await expect(page.getByText("This session has ended.")).toBeVisible();
  }
  await page.goto(`/s/${token}/done`);
  await expect(page.getByText("Thank you. You can let the researcher know you are finished.")).toBeVisible();
});

test("a synthetic session skips consent and ends on a plain page", async ({ page }) => {
  const synthetic = await newSyntheticSession();
  await page.goto(`/s/${synthetic.token}`);
  await expect(page).toHaveURL(new RegExp(`/s/${synthetic.token}/billing$`));
  await page.getByRole("button", { name: "I'm finished" }).click();
  await expect(page.getByText("Session ended", { exact: true })).toBeVisible();
  await expect(page.getByText("Overall, how easy or difficult was this task?")).toHaveCount(0);
});

test.afterAll(async () => {
  await db.$disconnect();
});
