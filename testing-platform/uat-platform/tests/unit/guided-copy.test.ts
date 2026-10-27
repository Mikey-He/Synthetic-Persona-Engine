import { describe, expect, it } from "vitest";
import {
  SCREENS,
  alertsSummary,
  amountSummary,
  periodSummary,
  recipientsSummary,
  screenIssues,
  tracksSummary,
} from "@/components/guided-setup/copy";
import { updateConfig } from "@/lib/domain/rules";
import type { BudgetConfig } from "@/lib/domain/types";
import { defaults, fixture } from "@/lib/fixtures";

const fromDefaults = (): BudgetConfig => structuredClone(defaults.config);
const atlas = () =>
  updateConfig(fromDefaults(), [
    ["name", "Atlas monthly"],
    ["scope.allProjects", false],
    ["scope.projectIds", ["atlas-demo"]],
    ["amount.target", 1000],
    ["thresholds", [{ percent: 50, trigger: "actual" }, { percent: 80, trigger: "actual" }]],
    ["recipients.billingAdminsAndUsers", false],
    ["recipients.projectOwners", true],
  ]).config;

describe("review summary", () => {
  it("reads like the design doc example", () => {
    const config = atlas();
    expect(tracksSummary(config, fixture)).toBe("Only Atlas");
    expect(periodSummary(config)).toBe("Every month");
    expect(amountSummary(config, fixture)).toBe("$1,000 each month");
    expect(alertsSummary(config, fixture)).toBe(
      "Email when money already spent reaches 50% ($500). Also at 80% ($800).",
    );
    expect(recipientsSummary(config, fixture)).toBe("Project owners · Sam Rivera");
  });

  it("names a change of spend type and the defaults' recipients", () => {
    const config = updateConfig(fromDefaults(), [
      ["amount.target", 200],
      ["thresholds", [{ percent: 50, trigger: "actual" }, { percent: 90, trigger: "forecasted" }]],
    ]).config;
    expect(tracksSummary(config, fixture)).toBe("All projects in Northstar Research");
    expect(alertsSummary(config, fixture)).toBe(
      "Email when money already spent reaches 50% ($100). Also when money expected by the end of the period reaches 90% ($180).",
    );
    expect(recipientsSummary(config, fixture)).toBe("Billing account admins and users · Alex Kim, Jordan Lee");
  });

  it("says alert emails are off without rules", () => {
    const config = updateConfig(fromDefaults(), [["thresholds", []]]).config;
    expect(alertsSummary(config, fixture)).toBe("No alert rules");
    expect(recipientsSummary(config, fixture)).toBe("Alert emails are off");
  });
});

describe("Continue checks", () => {
  it("need a project when only specific projects are tracked", () => {
    const config = updateConfig(fromDefaults(), [["scope.allProjects", false]]).config;
    expect(screenIssues("projects", config)).toEqual([
      { field: "scope.projectIds", message: "Choose at least one project" },
    ]);
    expect(screenIssues("projects", fromDefaults())).toEqual([]);
  });

  it("check only the fields of their own screen, with B's wording", () => {
    const config = updateConfig(fromDefaults(), [["recipients.billingAdminsAndUsers", false]]).config;
    expect(screenIssues("name", config)).toEqual([{ field: "name", message: "Enter a budget name." }]);
    expect(screenIssues("amount", config)).toEqual([
      { field: "amount.target", message: "Enter an amount greater than $0" },
    ]);
    expect(screenIssues("recipients", config)).toEqual([
      { field: "recipients", message: "Choose at least one recipient" },
    ]);
    expect(screenIssues("period", config)).toEqual([]);
  });
});

describe("guided copy", () => {
  it("never recommends an option or mentions the task", () => {
    const text = JSON.stringify(SCREENS);
    expect(text).not.toMatch(/recommend/i);
    expect(text).not.toMatch(/task|Atlas|\$1,000|80%/);
  });
});
