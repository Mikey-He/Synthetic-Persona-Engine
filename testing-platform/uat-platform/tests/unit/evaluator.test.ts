import { readdirSync, readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { resolveRecipients } from "@/lib/domain/resolveRecipients";
import type { BudgetConfig } from "@/lib/domain/types";
import { EVALUATOR_VERSION, evaluate } from "@/lib/evaluator/evaluate";
import { defaults, fixture } from "@/lib/fixtures";

// Every config starts from the current defaults file and changes only what the case describes.
const fromDefaults = (): BudgetConfig => structuredClone(defaults.config);

function correct(): BudgetConfig {
  const config = fromDefaults();
  config.scope.allProjects = false;
  config.scope.projectIds = ["atlas-demo"];
  config.amount = { type: "specified", target: 1000 };
  config.thresholds = [{ percent: 80, trigger: "actual" }];
  config.recipients.projectOwners = true;
  config.recipients.billingAdminsAndUsers = false;
  return config;
}

const ids = (config: BudgetConfig) =>
  resolveRecipients(config, fixture)
    .map((person) => person.id)
    .sort();

describe("evaluate", () => {
  it("passes overall for the correct saved config", () => {
    const result = evaluate(correct(), true, fixture);
    expect(result.criteria).toEqual({
      scope: true,
      period: true,
      amount: true,
      alert: true,
      recipients: true,
      persistence: true,
    });
    expect(result.overall).toBe(true);
    expect(result.version).toBe(EVALUATOR_VERSION);
    expect(EVALUATOR_VERSION).toBe("eval-v1");
  });

  it("fails recipients when billing admins and users stay checked, resolving three people", () => {
    const config = correct();
    config.recipients.billingAdminsAndUsers = true;
    const result = evaluate(config, true, fixture);
    expect(result.criteria.recipients).toBe(false);
    expect(result.overall).toBe(false);
    expect(result.people.map((person) => person.id).sort()).toEqual([
      "alex-kim",
      "jordan-lee",
      "sam-rivera",
    ]);
  });

  it("passes recipients with project owners checked and billing admins and users cleared", () => {
    const config = fromDefaults();
    config.scope.allProjects = false;
    config.scope.projectIds = ["atlas-demo"];
    config.recipients.projectOwners = true;
    config.recipients.billingAdminsAndUsers = false;
    const result = evaluate(config, true, fixture);
    expect(result.criteria.recipients).toBe(true);
    expect(result.people).toEqual([
      { id: "sam-rivera", name: "Sam Rivera", email: "atlas-owner@example.test", via: "project_owners" },
    ]);
  });

  it("fails scope for the entire account and resolves only billing members, even with project owners checked", () => {
    const config = fromDefaults();
    config.recipients.projectOwners = true;
    const result = evaluate(config, true, fixture);
    expect(config.scope.allProjects).toBe(true);
    expect(result.criteria.scope).toBe(false);
    expect(result.people.map((person) => [person.id, person.via])).toEqual([
      ["alex-kim", "billing_roles"],
      ["jordan-lee", "billing_roles"],
    ]);
  });

  it("fails scope for Beacon only", () => {
    const config = correct();
    config.scope.projectIds = ["beacon-demo"];
    expect(evaluate(config, true, fixture).criteria.scope).toBe(false);
  });

  it("fails scope for Atlas and Beacon together", () => {
    const config = correct();
    config.scope.projectIds = ["atlas-demo", "beacon-demo"];
    expect(evaluate(config, true, fixture).criteria.scope).toBe(false);
  });

  it("fails alert for only an 80% forecasted rule", () => {
    const config = correct();
    config.thresholds = [{ percent: 80, trigger: "forecasted" }];
    expect(evaluate(config, true, fixture).criteria.alert).toBe(false);
  });

  it("passes alert for 80% actual beside 50%, 90% and 100% actual", () => {
    const config = correct();
    config.thresholds = [...fromDefaults().thresholds, { percent: 80, trigger: "actual" }];
    const result = evaluate(config, true, fixture);
    expect(result.criteria.alert).toBe(true);
    expect(result.overall).toBe(true);
  });

  it("resolves nobody and fails recipients with zero thresholds", () => {
    const config = correct();
    config.thresholds = [];
    const result = evaluate(config, true, fixture);
    expect(result.people).toEqual([]);
    expect(result.criteria.recipients).toBe(false);
  });

  it("adds nobody for a linked Monitoring box with no channel", () => {
    const linked = correct();
    linked.recipients.monitoring.linked = true;
    expect(ids(linked)).toEqual(ids(correct()));
    expect(evaluate(linked, true, fixture).criteria.recipients).toBe(true);

    const onlyMonitoring = fromDefaults();
    onlyMonitoring.recipients.billingAdminsAndUsers = false;
    onlyMonitoring.recipients.monitoring.linked = true;
    expect(ids(onlyMonitoring)).toEqual([]);
  });

  it("fails amount for last period's spend", () => {
    const config = correct();
    config.amount = { type: "last_period" };
    expect(evaluate(config, true, fixture).criteria.amount).toBe(false);
  });

  it("passes amount for 1000.00 and fails it for 100", () => {
    const exact = correct();
    exact.amount = { type: "specified", target: 1000.0 };
    expect(evaluate(exact, true, fixture).criteria.amount).toBe(true);

    const tooLow = correct();
    tooLow.amount = { type: "specified", target: 100 };
    expect(evaluate(tooLow, true, fixture).criteria.amount).toBe(false);
  });

  it("fails period for quarterly", () => {
    const config = correct();
    config.period = "quarterly";
    expect(evaluate(config, true, fixture).criteria.period).toBe(false);
  });

  it("fails persistence only when not saved", () => {
    const result = evaluate(correct(), false, fixture);
    expect(result.criteria).toEqual({
      scope: true,
      period: true,
      amount: true,
      alert: true,
      recipients: true,
      persistence: false,
    });
    expect(result.overall).toBe(false);
  });

  it("returns the same result when called twice on the same input", () => {
    const config = correct();
    expect(evaluate(config, true, fixture)).toEqual(evaluate(config, true, fixture));
  });

  it("scores configs that are equal in value identically, whatever the click order", () => {
    // Scope first, then amount, alert and recipients.
    const first = fromDefaults();
    first.scope.allProjects = false;
    first.scope.projectIds = ["atlas-demo"];
    first.amount = { type: "specified", target: 1000 };
    first.thresholds = [{ percent: 80, trigger: "actual" }];
    first.recipients.projectOwners = true;
    first.recipients.billingAdminsAndUsers = false;

    // Recipients first, a detour through Beacon and quarterly, then the rest.
    const second = fromDefaults();
    second.recipients.billingAdminsAndUsers = false;
    second.thresholds = [{ percent: 50, trigger: "forecasted" }];
    second.period = "quarterly";
    second.scope.allProjects = false;
    second.scope.projectIds = ["beacon-demo"];
    second.scope.projectIds = ["atlas-demo"];
    second.recipients.projectOwners = true;
    second.period = "monthly";
    second.thresholds[0] = { trigger: "actual", percent: 80 };
    second.amount = { target: 1000, type: "specified" };

    expect(second).toEqual(first);
    expect(evaluate(second, true, fixture)).toEqual(evaluate(first, true, fixture));
  });
});

describe("evaluator purity", () => {
  it("uses no database, network, clock or randomness", () => {
    const dir = new URL("../../lib/evaluator/", import.meta.url);
    const sources = [
      ...readdirSync(dir)
        .filter((file) => file.endsWith(".ts"))
        .map((file) => readFileSync(new URL(file, dir), "utf8")),
      readFileSync(new URL("../../lib/domain/resolveRecipients.ts", import.meta.url), "utf8"),
    ];
    for (const source of sources) {
      expect(source).not.toMatch(/prisma/i);
      expect(source).not.toMatch(/\bfetch\b/);
      expect(source).not.toMatch(/\bDate\b/);
      expect(source).not.toMatch(/Math\.random/);
      expect(source).not.toMatch(/\bprocess\./);
      expect(source).not.toMatch(/from ["']node:/);
    }
  });
});
