import { describe, expect, it } from "vitest";
import type { BudgetConfig } from "@/lib/domain/types";
import { pickScoredBudget, type SavedVersion } from "@/lib/evaluator/pickScoredBudget";
import { defaults } from "@/lib/fixtures";

const named = (name: string): BudgetConfig => ({ ...structuredClone(defaults.config), name });

const save = (budgetId: string, version: number, savedAt: number): SavedVersion => ({
  budgetId,
  version,
  savedAt,
  config: named(`${budgetId} v${version}`),
});

describe("pickScoredBudget (rule v1)", () => {
  it("scores the last draft as unsaved when nothing was saved", () => {
    const draft = named("draft");
    expect(pickScoredBudget({ saves: [], completionDeclaredAt: 500, lastDraft: draft })).toEqual({
      saved: false,
      config: draft,
    });
  });

  it("scores the only save", () => {
    const only = save("b1", 1, 100);
    expect(
      pickScoredBudget({ saves: [only], completionDeclaredAt: 500, lastDraft: named("draft") }),
    ).toEqual({ saved: true, budgetId: "b1", version: 1, config: only.config });
  });

  it("scores the latest save when completion was never declared", () => {
    const result = pickScoredBudget({
      saves: [save("b1", 1, 100), save("b1", 2, 300)],
      completionDeclaredAt: null,
      lastDraft: named("draft"),
    });
    expect(result).toMatchObject({ saved: true, budgetId: "b1", version: 2 });
  });

  it("scores the most recent save before completion across several budgets and versions", () => {
    const saves = [save("b2", 1, 250), save("b1", 1, 100), save("b1", 2, 200), save("b1", 3, 900)];
    const result = pickScoredBudget({ saves, completionDeclaredAt: 500, lastDraft: named("draft") });
    expect(result).toEqual({ saved: true, budgetId: "b2", version: 1, config: saves[0].config });
  });

  it("treats saves made only after completion as nothing saved", () => {
    const draft = named("draft");
    const result = pickScoredBudget({
      saves: [save("b1", 1, 900)],
      completionDeclaredAt: 500,
      lastDraft: draft,
    });
    expect(result).toEqual({ saved: false, config: draft });
  });
});
