import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { TASK_TEXT, TASK_VERSION } from "@/lib/domain/task";
import { defaults, defaultsHash, fixture, fixtureHash, loadFixtureFiles } from "@/lib/fixtures";

describe("fixture files", () => {
  it("load and validate", () => {
    const loaded = loadFixtureFiles();
    expect(loaded.fixture.fixtureVersion).toBe("fixture-v1");
    expect(loaded.defaults.defaultsVersion).toBe("defaults-v2");
    expect(loaded.fixture).toEqual(fixture);
    expect(loaded.defaults).toEqual(defaults);
  });

  it("hash to the same value across two loads", () => {
    const first = loadFixtureFiles();
    const second = loadFixtureFiles();
    expect(first.fixtureHash).toMatch(/^[0-9a-f]{64}$/);
    expect(first.defaultsHash).toMatch(/^[0-9a-f]{64}$/);
    expect(second.fixtureHash).toBe(first.fixtureHash);
    expect(second.defaultsHash).toBe(first.defaultsHash);
    expect(fixtureHash).toBe(first.fixtureHash);
    expect(defaultsHash).toBe(first.defaultsHash);
  });

  // A failure here means a frozen file changed. Per CLAUDE.md, a change needs a
  // new version file and a CHANGELOG line, not an edit to v1.
  it("match the frozen bytes", () => {
    const hashOf = (file: string) =>
      createHash("sha256").update(readFileSync(new URL(`../../lib/fixtures/${file}`, import.meta.url))).digest("hex");
    expect(fixtureHash).toBe("40150d99fa7733a08b1580bea8cb577ef28f29e07401921ceacf6bf7ba11db68");
    expect(defaultsHash).toBe("080724e443e3b9384e8370d03fc5a98d9ebf15e86dcf7ec82f02e1125622e383");
    // defaults-v1 is no longer loaded but stays frozen for the sessions that used it.
    expect(hashOf("defaults-v1.json")).toBe("bf7e52fad12be1a3f6ece5faaa00319fbf0d2ea56cadf6f8184fadcd650e4bee");
  });

  it("never prefill the task answer in the defaults", () => {
    const { scope, amount, thresholds, recipients } = defaults.config;
    expect(scope.allProjects).toBe(true);
    expect(scope.projectIds).toEqual([]);
    expect(amount.target ?? 0).toBe(0); // the capture starts at $0, which Finish rejects
    expect(thresholds).not.toContainEqual({ percent: 80, trigger: "actual" });
    expect(recipients.projectOwners).toBe(false);
  });
});

describe("task text", () => {
  it("names the required recipient", () => {
    expect(TASK_TEXT).toContain("Only the Atlas project owner should receive this alert.");
  });

  it("matches the design guide Part 3 blockquote word for word", () => {
    const guide = readFileSync(new URL("../../docs/design-guide-v2.md", import.meta.url), "utf8");
    const part3 = guide.split("## 3. Task scenario")[1].split("\n## ")[0];
    const quote = part3
      .split(/\r?\n/)
      .filter((line) => line.startsWith(">"))
      .map((line) => line.replace(/^> ?/, ""))
      .join("\n");
    expect(TASK_TEXT).toBe(quote);
    expect(TASK_TEXT.split("\n\n")).toHaveLength(3);
    expect(TASK_VERSION).toBe("task-v1");
  });
});
