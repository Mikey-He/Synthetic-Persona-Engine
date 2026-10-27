import { describe, expect, it } from "vitest";
import { resolveRecipients } from "@/lib/domain/resolveRecipients";
import {
  emailOptionsEnabled,
  parseNumber,
  projectOwnersAvailable,
  updateConfig,
  validateConfig,
} from "@/lib/domain/rules";
import type { BudgetConfig } from "@/lib/domain/types";
import { defaults, fixture } from "@/lib/fixtures";

const fromDefaults = (): BudgetConfig => structuredClone(defaults.config);

function atlasWithOwners(): BudgetConfig {
  return updateConfig(fromDefaults(), [
    ["scope.allProjects", false],
    ["scope.projectIds", ["atlas-demo"]],
    ["recipients.projectOwners", true],
  ]).config;
}

describe("scope clears the project owners option", () => {
  it("offers project owners only for exactly one project", () => {
    expect(projectOwnersAvailable(fromDefaults())).toBe(false);
    expect(projectOwnersAvailable(atlasWithOwners())).toBe(true);
  });

  it("clears a checked option when a second project is added, and reports it", () => {
    const result = updateConfig(atlasWithOwners(), [["scope.projectIds", ["atlas-demo", "beacon-demo"]]]);
    expect(result.config.recipients.projectOwners).toBe(false);
    expect(result.cleared).toEqual([{ option: "recipients.projectOwners", value: true }]);
    expect(result.changes).toEqual([
      { path: "scope.projectIds", oldValue: ["atlas-demo"], newValue: ["atlas-demo", "beacon-demo"] },
    ]);
  });

  it("clears it when Select all turns the scope into the entire account", () => {
    const result = updateConfig(atlasWithOwners(), [
      ["scope.allProjects", true],
      ["scope.projectIds", []],
    ]);
    expect(result.config.recipients.projectOwners).toBe(false);
    expect(result.cleared).toHaveLength(1);
  });

  it("clears it when the only project is removed", () => {
    const result = updateConfig(atlasWithOwners(), [["scope.projectIds", []]]);
    expect(result.cleared).toHaveLength(1);
  });

  it("reports nothing when the option was not checked or the scope stays on one project", () => {
    const unchecked = updateConfig(fromDefaults(), [["scope.projectIds", ["atlas-demo", "beacon-demo"]]]);
    expect(unchecked.cleared).toEqual([]);
    const unrelated = updateConfig(atlasWithOwners(), [["amount.target", 1000]]);
    expect(unrelated.cleared).toEqual([]);
    expect(unrelated.config.recipients.projectOwners).toBe(true);
  });
});

describe("zero thresholds", () => {
  it("disable the email options and resolve nobody", () => {
    const none = updateConfig(fromDefaults(), [["thresholds", []]]).config;
    expect(emailOptionsEnabled(fromDefaults())).toBe(true);
    expect(emailOptionsEnabled(none)).toBe(false);
    expect(resolveRecipients(none, fixture)).toEqual([]);
  });

  it("need no email option before saving", () => {
    const none = updateConfig(fromDefaults(), [
      ["name", "No alerts"],
      ["amount.target", 500],
      ["thresholds", []],
      ["recipients.billingAdminsAndUsers", false],
    ]).config;
    expect(validateConfig(none)).toEqual([]);
  });
});

describe("validation", () => {
  const valid = () =>
    updateConfig(fromDefaults(), [
      ["name", "Budget"],
      ["amount.target", 1000],
    ]).config;

  it("accepts every valid configuration, including ones that fail the task", () => {
    expect(validateConfig(valid())).toEqual([]);
    const forecastOnly = updateConfig(valid(), [["thresholds", [{ percent: 80, trigger: "forecasted" }]]]);
    expect(validateConfig(forecastOnly.config)).toEqual([]);
  });

  it("reports each problem in page order", () => {
    const broken = updateConfig(fromDefaults(), [
      ["scope.allProjects", false],
      ["thresholds.1.percent", 0],
      ["recipients.billingAdminsAndUsers", false],
    ]).config;
    expect(validateConfig(broken)).toEqual([
      { field: "name", code: "name_required" },
      { field: "amount.target", code: "amount_invalid" },
      { field: "thresholds.1.percent", code: "percent_invalid" },
      { field: "recipients", code: "recipient_required" },
    ]);
  });

  it("rejects a blank name, and a zero, negative or missing specified amount", () => {
    for (const target of [0, -5, undefined]) {
      const config = updateConfig(valid(), [["amount.target", target]]).config;
      expect(validateConfig(config)).toEqual([{ field: "amount.target", code: "amount_invalid" }]);
    }
    const blank = updateConfig(valid(), [["name", "   "]]).config;
    expect(validateConfig(blank)).toEqual([{ field: "name", code: "name_required" }]);
  });

  it("needs no target for last month's spend", () => {
    const config = updateConfig(valid(), [
      ["amount.type", "last_period"],
      ["amount.target", undefined],
    ]).config;
    expect(validateConfig(config)).toEqual([]);
  });

  it("accepts percents from 1 to 1000 only", () => {
    for (const [percent, ok] of [[1, true], [1000, true], [0.5, false], [1001, false], [Number.NaN, false]] as const) {
      const config = updateConfig(valid(), [["thresholds.0.percent", percent]]).config;
      expect(validateConfig(config).length === 0, String(percent)).toBe(ok);
    }
  });

  it("counts a linked Monitoring box as a way to send alerts", () => {
    const config = updateConfig(valid(), [
      ["recipients.billingAdminsAndUsers", false],
      ["recipients.monitoring.linked", true],
    ]).config;
    expect(validateConfig(config)).toEqual([]);
  });
});

describe("updateConfig", () => {
  it("records old and new values and skips values that did not change", () => {
    const result = updateConfig(fromDefaults(), [
      ["name", "Atlas"],
      ["period", "monthly"],
    ]);
    expect(result.changes).toEqual([{ path: "name", oldValue: "", newValue: "Atlas" }]);
  });

  it("never mutates the config it was given", () => {
    const before = fromDefaults();
    const copy = structuredClone(before);
    updateConfig(before, [["scope.projectIds", ["beacon-demo"]], ["recipients.pubsubTopic", ""]]);
    expect(before).toEqual(copy);
  });
});

describe("parseNumber", () => {
  it("reads plain numbers only", () => {
    expect(parseNumber("1000")).toBe(1000);
    expect(parseNumber(" 80 ")).toBe(80);
    expect(parseNumber("1000.00")).toBe(1000);
    expect(parseNumber("-5")).toBe(-5);
    for (const text of ["", "abc", "1,000", "$1000", "1e3"]) expect(parseNumber(text)).toBeUndefined();
  });
});
