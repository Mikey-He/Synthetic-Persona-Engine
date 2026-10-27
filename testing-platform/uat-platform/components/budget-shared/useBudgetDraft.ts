"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { updateConfig, validateConfig, type ValidationIssue } from "@/lib/domain/rules";
import { useLogger } from "@/lib/events/EventLoggerProvider";
import { settingOfField } from "@/lib/events/types";
import { createFormStore, type Change, type FormState } from "./formStore";

// The draft, change and save plumbing shared by both create flows, so they
// write the same BudgetDraft, log the same events and save through the same
// function (build plan, Version B component).

const DRAFT_DELAY_MS = 500;

type Options = {
  token: string;
  initialState: FormState;
  editingBudgetId: string | null;
};

export type SubmitResult =
  | { status: "saved"; budgetId: string }
  | { status: "invalid"; issues: ValidationIssue[] }
  | { status: "error" };

export function useBudgetDraft({ token, initialState, editingBudgetId }: Options) {
  const logger = useLogger();
  const [store] = useState(() => createFormStore(initialState));
  const state = useSyncExternalStore(store.subscribe, store.get, store.get);
  const [saving, setSaving] = useState(false);
  const draftTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const draftWrite = useRef<Promise<unknown>>(Promise.resolve());
  const saved = useRef(false);

  const writeDraft = useCallback(
    (keepalive: boolean) => {
      draftTimer.current = null;
      if (saved.current) return;
      draftWrite.current = fetch(`/api/s/${token}/draft`, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ config: store.get().config, editingBudgetId }),
        keepalive,
      }).catch(() => undefined);
    },
    [store, token, editingBudgetId],
  );

  const flushDraft = useCallback(() => {
    if (draftTimer.current === null) return;
    clearTimeout(draftTimer.current);
    writeDraft(true);
  }, [writeDraft]);

  // Leaving the page, by any route, keeps the draft.
  useEffect(() => {
    const onVisibility = () => {
      if (document.visibilityState === "hidden") flushDraft();
    };
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("pagehide", flushDraft);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("pagehide", flushDraft);
      flushDraft();
    };
  }, [flushDraft]);

  // Every change updates local state at once, is logged with its old and new
  // value, and reaches the draft after 500 ms without further changes.
  const change: Change = (updates, patch = {}) => {
    const current = store.get();
    const result = updateConfig(current.config, updates);
    store.set({ ...current, ...patch, config: result.config });
    for (const c of result.changes) {
      logger?.log("field_changed", c.path, {
        field: c.path,
        setting: settingOfField(c.path),
        oldValue: c.oldValue ?? null, // an empty optional field is logged as null
        newValue: c.newValue ?? null,
      });
    }
    for (const cleared of result.cleared) {
      logger?.log("option_cleared_by_scope", cleared.option, cleared);
    }
    if (result.changes.length === 0 && result.cleared.length === 0) return;
    if (draftTimer.current !== null) clearTimeout(draftTimer.current);
    draftTimer.current = setTimeout(() => writeDraft(false), DRAFT_DELAY_MS);
  };

  // Finish in A, Create budget in B. Logs save_clicked and save_attempted,
  // then either the validation messages and save_failed, or the save outcome.
  async function submit(label: string, messageOf: (issue: ValidationIssue) => string): Promise<SubmitResult> {
    const config = store.get().config;
    const described = (issues: ValidationIssue[]) =>
      issues.map((issue) => ({ field: issue.field, message: messageOf(issue) }));
    const invalid = (issues: ValidationIssue[]): SubmitResult => {
      const shown = described(issues);
      for (const item of shown) logger?.log("validation_shown", item.field, item);
      logger?.log("save_failed", label, { reason: "validation", issues: shown });
      return { status: "invalid", issues };
    };

    logger?.log("save_clicked", label, { draft: config });
    const issues = validateConfig(config);
    logger?.log("save_attempted", label, { valid: issues.length === 0, issues: described(issues) });
    if (issues.length > 0) return invalid(issues);

    setSaving(true);
    if (draftTimer.current !== null) {
      clearTimeout(draftTimer.current);
      draftTimer.current = null;
    }
    await draftWrite.current; // an earlier draft write must land before the save clears it
    const response = await fetch(`/api/s/${token}/budgets`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ config, editingBudgetId }),
    }).catch(() => null);

    if (response?.ok) {
      saved.current = true;
      const { budgetId, version } = (await response.json()) as { budgetId: string; version: number };
      logger?.log("save_succeeded", budgetId, { budgetId, version });
      return { status: "saved", budgetId }; // saving stays true while the caller navigates away
    }
    setSaving(false);
    const body = response
      ? ((await response.json().catch(() => null)) as { issues?: ValidationIssue[] } | null)
      : null;
    if (body?.issues?.length) return invalid(body.issues);
    logger?.log("save_failed", label, { reason: "server", status: response?.status ?? null });
    return { status: "error" };
  }

  return { logger, store, state, change, submit, saving };
}
