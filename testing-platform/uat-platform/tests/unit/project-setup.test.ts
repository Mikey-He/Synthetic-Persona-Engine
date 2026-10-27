import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const root = fileURLToPath(new URL("../../", import.meta.url));

// Exit code 0 means git ignores the path. A tracked file never counts as ignored.
const ignoredByGit = (path: string) =>
  spawnSync("git", ["check-ignore", "--quiet", path], { cwd: root }).status === 0;

describe("project setup", () => {
  it("keeps secrets, dependencies and build output out of git", () => {
    for (const path of [
      ".env",
      ".env.local",
      "node_modules/x",
      ".next/x",
      "playwright-report/x",
      "test-results/x",
    ]) {
      expect(ignoredByGit(path), path).toBe(true);
    }
    expect(ignoredByGit(".env.example")).toBe(false);
  });

  it("lists exactly the required variables in .env.example", () => {
    const keys = readFileSync(new URL("../../.env.example", import.meta.url), "utf8")
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter((line) => line !== "" && !line.startsWith("#"))
      .map((line) => line.split("=")[0]);
    expect(keys).toEqual(["DATABASE_URL", "ADMIN_PASSWORD", "BUILD_VERSION"]);
  });
});
