/*
 * Scoring rule v1. It applies to humans and agents the same way.
 *
 * When a session saved more than one budget, score the most recently saved
 * budget version before completion was declared. If nothing was saved,
 * persistence is false and the other criteria are evaluated against the last
 * draft.
 *
 * Times are plain numbers (milliseconds) supplied by the caller, so this stays
 * pure. With no completion declared (abandoned, time limit), every save counts.
 */
import type { BudgetConfig } from "@/lib/domain/types";

export type SavedVersion = {
  budgetId: string;
  version: number;
  savedAt: number;
  config: BudgetConfig;
};

export type ScoredBudget =
  | { saved: true; budgetId: string; version: number; config: BudgetConfig }
  | { saved: false; config: BudgetConfig };

type Input = {
  saves: SavedVersion[];
  completionDeclaredAt: number | null;
  lastDraft: BudgetConfig; // the defaults when no draft was ever written
};

export function pickScoredBudget({ saves, completionDeclaredAt, lastDraft }: Input): ScoredBudget {
  const eligible = saves.filter(
    (save) => completionDeclaredAt === null || save.savedAt <= completionDeclaredAt,
  );
  if (eligible.length === 0) return { saved: false, config: lastDraft };

  const latest = eligible.reduce((best, save) =>
    save.savedAt > best.savedAt || (save.savedAt === best.savedAt && save.version > best.version)
      ? save
      : best,
  );
  return { saved: true, budgetId: latest.budgetId, version: latest.version, config: latest.config };
}
