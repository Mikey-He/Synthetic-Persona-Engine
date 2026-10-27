import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { SESSION_COLUMNS, toCsv } from "@/lib/exports";
import { settingTimes } from "@/lib/metrics";

const at = (ms: number) => new Date(Date.UTC(2026, 8, 30, 12, 0, 0, ms));

describe("sessions.csv columns", () => {
  it("match docs/build-plan.md exactly, in order", () => {
    const plan = readFileSync(new URL("../../docs/build-plan.md", import.meta.url), "utf8");
    const header = plan.split("```csv")[1].split("```")[0].trim();
    expect(SESSION_COLUMNS.join(",")).toBe(header);
  });
});

describe("toCsv", () => {
  it("writes the header, leaves missing values empty and quotes when needed", () => {
    const csv = toCsv(["a", "b", "c"], [{ a: 'say "hi", then', b: null, c: true }]);
    expect(csv).toBe('a,b,c\n"say ""hi"", then",,true\n');
  });
});

describe("settingTimes", () => {
  it("measures from setting_reached to the last field_changed of each setting", () => {
    const times = settingTimes([
      { type: "setting_reached", clientTs: at(0), payload: { setting: "scope" } },
      { type: "field_changed", clientTs: at(400), payload: { setting: "scope" } },
      { type: "field_changed", clientTs: at(900), payload: { setting: "scope" } },
      { type: "setting_reached", clientTs: at(500), payload: { setting: "period" } },
      { type: "field_changed", clientTs: at(600), payload: { setting: null } },
      { type: "setting_reached", clientTs: at(700), payload: { setting: "amount" } },
      { type: "field_changed", clientTs: at(650), payload: { setting: "amount" } },
    ]);
    expect(times).toEqual({ scope: 900, period: 0, amount: 0, alert: null, recipients: null });
  });
});
