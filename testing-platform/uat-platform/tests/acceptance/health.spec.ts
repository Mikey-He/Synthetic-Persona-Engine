import { expect, test } from "@playwright/test";

test("/api/health reports the build and the frozen files", async ({ request }) => {
  const response = await request.get("/api/health");
  expect(response.status()).toBe(200);
  const body = await response.json();
  expect(body).toMatchObject({
    status: "ok",
    fixtureVersion: "fixture-v1",
    defaultsVersion: "defaults-v2",
    taskVersion: "task-v1",
    evaluatorVersion: "eval-v1",
  });
  expect(body.fixtureHash).toMatch(/^[0-9a-f]{64}$/);
  expect(body.defaultsHash).toMatch(/^[0-9a-f]{64}$/);
  expect(typeof body.buildVersion).toBe("string");
});
