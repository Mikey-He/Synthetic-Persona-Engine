import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";
import { db } from "@/lib/db";
import { newHumanSession } from "./helpers";

const PASSWORD = process.env.ADMIN_PASSWORD ?? "";

// Copied from docs/build-plan.md, not from the code, so a drift in either shows up.
const SESSIONS_HEADER =
  "session_id,actor_type,variant,dataset_label,familiarity_band,model_id,prompt_version,persona_id,calibration_id,fixture_version,build_version,evaluator_version,termination_reason,overall_success,crit_scope,crit_period,crit_amount,crit_alert,crit_recipients,crit_persistence,resolved_recipient_ids,recipient_mechanisms,time_scope_ms,time_period_ms,time_amount_ms,time_alert_ms,time_recipients_ms,setting_returns,review_edits,n_events,n_saves,reopened_after_save,survey_satisfaction";

async function signIn(page: Page) {
  await page.goto("/admin/login");
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Sessions" })).toBeVisible();
}

test.afterAll(async () => {
  await db.$disconnect();
});

test("the console needs the password", async ({ page, request }) => {
  expect(PASSWORD, "ADMIN_PASSWORD must be set for these tests").not.toBe("");
  await page.goto("/admin");
  await expect(page).toHaveURL(/\/admin\/login$/);
  await page.getByLabel("Password").fill("not-the-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("Wrong password.")).toBeVisible();
  await page.goto("/admin/exports");
  await expect(page).toHaveURL(/\/admin\/login$/);

  expect((await request.get("/api/admin/exports/sessions.csv")).status()).toBe(401);
  const create = await request.post("/api/admin/sessions", {
    data: { actorType: "human", familiarityBand: "low", datasetLabel: "pilot" },
  });
  expect(create.status()).toBe(401);
});

test("every admin page is marked noindex and shows the build info", async ({ page }) => {
  await signIn(page);
  for (const path of ["/admin", "/admin/sessions/new-human", "/admin/assignment", "/admin/exports"]) {
    await page.goto(path);
    await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", /noindex/);
    await expect(page.locator("footer")).toContainText(/Fixture hash [0-9a-f]{64}/);
    await expect(page.locator("footer")).toContainText("Evaluator eval-v1");
  }
});

test("a human session is created, completed and listed with its evaluation", async ({ page, browser }) => {
  await signIn(page);
  await page.getByRole("link", { name: "New human session" }).click();
  await page.getByLabel("Familiarity band").selectOption("high");
  await page.getByLabel("Dataset label").selectOption("calibration_A");
  await page.getByRole("button", { name: "Create session" }).click();
  const link = await page.getByLabel("Participant link").inputValue();
  expect(link).toMatch(/\/s\/[A-Za-z0-9_-]{21}$/);
  const session = await db.session.findUniqueOrThrow({
    where: { token: link.split("/s/")[1] },
    include: { participant: true },
  });
  expect(session.participant?.familiarityBand).toBe("high");

  // The participant uses the link in a browser of their own.
  const participantContext = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const participant = await participantContext.newPage();
  await participant.goto(link);
  await expect(participant.getByRole("heading", { name: "Before you start" })).toBeVisible();
  await participant.getByRole("link", { name: "Start task" }).click();
  await participant.getByRole("button", { name: "I'm finished" }).click();
  await expect(participant).toHaveURL(/\/done$/);
  await participantContext.close();

  await page.goto("/admin");
  const row = page.getByRole("row", { name: new RegExp(session.id) });
  for (const text of ["human", "calibration_A", "high", "Ended", "completion_declared", "Failure (eval-v1)"]) {
    await expect(row).toContainText(text);
  }
  await row.getByRole("link", { name: session.id }).click();
  await expect(page.getByText("Nothing saved: the last draft")).toBeVisible();
  await expect(page.getByRole("row", { name: "persistence Fail" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "completion_declared", exact: true }).first()).toBeVisible();
});

test("End session records a session the participant left as abandoned", async ({ page }) => {
  const session = await newHumanSession();
  await signIn(page);
  await page.goto(`/admin/sessions/${session.id}`);
  await page.getByRole("button", { name: "End session" }).click();
  await expect(page.getByRole("button", { name: "End session" })).toHaveCount(0);

  const ended = await db.session.findUniqueOrThrow({ where: { id: session.id } });
  expect(ended.terminationReason).toBe("abandoned");
  const last = await db.event.findFirst({ where: { sessionId: session.id }, orderBy: { seq: "desc" } });
  expect(last?.type).toBe("session_ended");
  expect(await db.evaluation.count({ where: { sessionId: session.id } })).toBe(1);
});

test("Re-score adds evaluation rows and keeps the earlier ones", async ({ page }) => {
  test.setTimeout(90_000);
  await newHumanSession();
  const before = await db.evaluation.findMany({ select: { id: true } });
  const sessions = await db.session.count();
  await signIn(page);
  // The session list grows with the test database; the button works once the page has hydrated.
  await page.waitForLoadState("networkidle");
  await page.getByRole("button", { name: "Re-score" }).click();
  // Re-scoring walks every stored session, so it also slows as the database grows.
  await expect(page.getByText(`Re-scored ${sessions} sessions with eval-v1.`)).toBeVisible({ timeout: 60_000 });

  const after = await db.evaluation.findMany({ select: { id: true } });
  expect(after.length).toBe(before.length + sessions);
  const afterIds = new Set(after.map((row) => row.id));
  expect(before.every((row) => afterIds.has(row.id))).toBe(true);
});

test("the three exports download under build and fixture names", async ({ page }) => {
  await signIn(page);
  await page.getByRole("link", { name: "Exports" }).click();

  const download = async (kind: string) => {
    const [file] = await Promise.all([
      page.waitForEvent("download"),
      page.getByRole("link", { name: new RegExp(`^${kind}_build-`) }).click(),
    ]);
    return { name: file.suggestedFilename(), text: readFileSync(await file.path(), "utf8") };
  };

  const events = await download("events");
  expect(events.name).toMatch(/^events_build-.+_fx-[0-9a-f]{8}\.json$/);
  expect(Array.isArray(JSON.parse(events.text).sessions)).toBe(true);

  const sessions = await download("sessions");
  expect(sessions.name).toMatch(/^sessions_build-.+_fx-[0-9a-f]{8}\.csv$/);
  expect(sessions.text.split("\n")[0]).toBe(SESSIONS_HEADER);

  const steps = await download("agent_steps");
  expect(steps.name).toMatch(/^agent_steps_build-.+_fx-[0-9a-f]{8}\.csv$/);
  // Rows appear once the agent runner has recorded steps.
  expect(steps.text.split("\n")[0]).toBe("session_id,step_no,screenshot_path,action,reason,executed,error_label,latency_ms");
});

test("the agent runner records steps, reads status and ends a synthetic session by a stop rule", async ({
  request,
}) => {
  const login = await request.post("/api/admin/login", { form: { password: PASSWORD }, maxRedirects: 0 });
  expect(login.status()).toBe(303);
  const created = await request.post("/api/admin/sessions", {
    data: {
      actorType: "synthetic",
      modelId: "gemini-3.8-flash",
      promptVersion: "system-v1",
      personaId: "low-v1",
      calibrationId: null,
      temperature: 0.4,
      variant: "B",
    },
  });
  expect(created.status()).toBe(201);
  const { id, variant } = (await created.json()) as { id: string; variant: string };
  expect(variant).toBe("B");

  const step = {
    stepNo: 1,
    screenshotPath: "runs/x/step-001.png",
    action: { action: "click", x: 10, y: 20, reason: "look" },
    reason: "look",
    executed: true,
    errorLabel: "no_visible_change",
    latencyMs: 1200,
  };
  expect((await request.post(`/api/admin/sessions/${id}/agent-steps`, { data: step })).status()).toBe(201);
  expect(
    (await request.post(`/api/admin/sessions/${id}/agent-steps`, { data: { ...step, errorLabel: "made_up" } })).status(),
  ).toBe(400);
  expect(await (await request.get(`/api/admin/sessions/${id}`)).json()).toEqual({ ended: false, terminationReason: null });

  expect((await request.post(`/api/admin/sessions/${id}/end`, { data: { terminationReason: "loop" } })).status()).toBe(204);
  expect(await (await request.get(`/api/admin/sessions/${id}`)).json()).toEqual({ ended: true, terminationReason: "loop" });
  expect(
    (await request.post(`/api/admin/sessions/${id}/end`, { data: { terminationReason: "completion_declared" } })).status(),
  ).toBe(400); // only the participant's own I'm finished records completion

  const session = await db.session.findUniqueOrThrow({ where: { id }, include: { agentRun: true, agentSteps: true } });
  expect(session.agentRun?.temperature).toBe(0.4);
  expect(session.agentRun?.startedAt).not.toBeNull();
  expect(session.agentSteps.map((s) => [s.stepNo, s.errorLabel])).toEqual([[1, "no_visible_change"]]);
  const ended = await db.event.findFirst({ where: { sessionId: id, type: "session_ended" } });
  expect(ended?.payload).toEqual({ terminationReason: "loop", endedBy: "agent_runner" });

  // Steps belong to synthetic sessions only.
  const human = await newHumanSession();
  expect((await request.post(`/api/admin/sessions/${human.id}/agent-steps`, { data: step })).status()).toBe(409);
});
