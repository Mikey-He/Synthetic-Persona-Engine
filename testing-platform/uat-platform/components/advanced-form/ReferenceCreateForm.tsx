"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { TASK_BAR_HEIGHT } from "@/components/taskbar/TaskBar";
import { validateConfig, type ValidationIssue } from "@/lib/domain/rules";
import type { BudgetConfig, Fixture } from "@/lib/domain/types";
import { settingValue, type Setting } from "@/lib/events/types";
import { ActionsSection } from "./ActionsSection";
import { AmountSection } from "./AmountSection";
import { CostTrend } from "./CostTrend";
import { DefineSection } from "./DefineSection";
import { initialFormState, sectionOf, type FormMode, type SectionNumber } from "@/components/budget-shared/formStore";
import { SECTION_NAMES, VALIDATION_MESSAGES } from "./labels";
import { Chevron, ScopeSection } from "./ScopeSection";
import { useBudgetDraft } from "@/components/budget-shared/useBudgetDraft";

export type CreateFormData = Pick<
  Fixture,
  "currency" | "today" | "projects" | "services" | "labels" | "monthlyCosts"
>;

type Props = {
  token: string;
  mode: FormMode;
  data: CreateFormData;
  initialConfig: BudgetConfig;
  editingBudgetId: string | null;
  savedName?: string; // Edit shows the saved budget's name as its heading
};

// Layout per the reference capture: Create Budget is a numbered stepper with
// Next, and Finish and Cancel right under the steps; Edit Budget opens every
// section with Save and Cancel pinned to the bottom of the page.

const FOOTER_HEIGHT = 64;
const SECTIONS: SectionNumber[] = [1, 2, 3, 4];
const SECTION_KEYS = { 1: "define", 2: "scope", 3: "amount", 4: "actions" } as const;

// How a person came back to a setting. For this long after a section opens, a
// return is credited to what opened it; any other return is a scroll.
type NavCause = "section_header_click" | "next_button" | "validation" | "page_load";
const CAUSE_WINDOW_MS = 1500;

export function ReferenceCreateForm({ token, mode, data, initialConfig, editingBudgetId, savedName }: Props) {
  const router = useRouter();
  const { logger, store, state, change, submit, saving } = useBudgetDraft({
    token,
    initialState: initialFormState(initialConfig, mode),
    editingBudgetId,
  });
  const [saveFailed, setSaveFailed] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const visible = useRef(new Set<Setting>());
  const navCause = useRef<NavCause | null>(null);
  const causeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mounted = useRef(false);
  const listHref = `/s/${token}/billing/budgets`;

  const markCause = useCallback((cause: NavCause) => {
    navCause.current = cause;
    if (causeTimer.current !== null) clearTimeout(causeTimer.current);
    causeTimer.current = setTimeout(() => {
      navCause.current = null;
    }, CAUSE_WINDOW_MS);
  }, []);

  const logStep = useCallback(
    (section: SectionNumber) => {
      if (!logger) return;
      const key = SECTION_KEYS[section];
      const entry = logger.firstTime("step", key) ? "first" : "return";
      logger.log("step_entered", key, { section: key, number: section, entry });
    },
    [logger],
  );

  // ---- events on arrival --------------------------------------------------

  useEffect(() => {
    if (mounted.current || !logger) return;
    mounted.current = true;
    markCause("page_load");
    if (editingBudgetId) logger.log("budget_reopened", editingBudgetId, { budgetId: editingBudgetId });
    for (const section of store.get().open) logStep(section);
  }, [logger, logStep, markCause, editingBudgetId, store]);

  // setting_reached and setting_returned: which setting controls are on screen.
  // The fixed task bar and the pinned Save bar are not counted as viewport.
  useEffect(() => {
    const form = root.current;
    if (!logger || !form) return;
    const shown = visible.current;
    const elements = Array.from(form.querySelectorAll<HTMLElement>("[data-setting]"));
    const present = new Set(elements.map((element) => element.dataset.setting as Setting));
    for (const setting of [...shown]) {
      if (!present.has(setting)) {
        shown.delete(setting); // its section closed
        logger.settingLeft(setting);
      }
    }
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const setting = (entry.target as HTMLElement).dataset.setting as Setting;
          if (entry.isIntersecting && !shown.has(setting)) {
            shown.add(setting);
            logger.settingEntered(setting, settingValue(store.get().config, setting), navCause.current ?? "scroll");
          } else if (!entry.isIntersecting && shown.has(setting)) {
            shown.delete(setting);
            logger.settingLeft(setting);
          }
        }
      },
      { rootMargin: `-${TASK_BAR_HEIGHT}px 0px -${FOOTER_HEIGHT}px 0px` },
    );
    elements.forEach((element) => observer.observe(element));
    return () => observer.disconnect();
  }, [logger, store, state.open]);

  // Leaving the page takes every setting out of view.
  useEffect(() => {
    const shown = visible.current;
    return () => {
      for (const setting of shown) logger?.settingLeft(setting);
      shown.clear();
    };
  }, [logger]);

  // Create: one step open at a time. Next marks the step it leaves as done.
  const openStep = (section: SectionNumber, cause: NavCause) => {
    const current = store.get();
    if (current.open.length === 1 && current.open[0] === section) return;
    const visited =
      cause === "next_button"
        ? [...new Set([...current.visited, ...current.open])]
        : current.visited;
    markCause(cause);
    store.set({ ...current, open: [section], visited });
    logStep(section);
  };

  // Edit: every section folds on its own.
  const toggleSection = (section: SectionNumber) => {
    const current = store.get();
    const isOpen = current.open.includes(section);
    store.set({
      ...current,
      open: isOpen ? current.open.filter((s) => s !== section) : [...current.open, section].sort(),
    });
    if (!isOpen) {
      markCause("section_header_click");
      logStep(section);
    }
  };

  // ---- finish ---------------------------------------------------------------

  const saveLabel = mode === "edit" ? "Save" : "Finish";

  const showIssues = (issues: ValidationIssue[]) => {
    const first = sectionOf(issues[0].field);
    const current = store.get();
    store.set({ ...current, reported: issues, visited: SECTIONS });
    if (mode === "create") openStep(first, "validation");
    else if (!current.open.includes(first)) toggleSection(first);
  };

  async function finish() {
    setSaveFailed(false);
    const result = await submit(saveLabel, (issue) => VALIDATION_MESSAGES[issue.code]);
    if (result.status === "saved") router.push(listHref); // back to the budgets list, as the console does
    else if (result.status === "invalid") showIssues(result.issues);
    else setSaveFailed(true);
  }

  // ---- render -------------------------------------------------------------

  const { config } = state;
  // A message from the last Finish stays until its problem is fixed.
  const open = validateConfig(config);
  const errors = new Map(
    state.reported
      .filter((issue) => open.some((o) => o.field === issue.field && o.code === issue.code))
      .map((issue) => [issue.field, VALIDATION_MESSAGES[issue.code]]),
  );
  const sectionHasError = (section: SectionNumber) => [...errors.keys()].some((field) => sectionOf(field) === section);

  const body: Record<SectionNumber, ReactNode> = {
    1: <DefineSection config={config} errors={errors} change={change} />,
    2: <ScopeSection config={config} data={data} change={change} />,
    3: <AmountSection config={config} targetText={state.targetText} data={data} errors={errors} change={change} />,
    4: (
      <ActionsSection
        token={token}
        config={config}
        percentTexts={state.percentTexts}
        data={data}
        errors={errors}
        change={change}
      />
    ),
  };

  const saveButton = (
    <button type="button" className="btn-primary" disabled={saving} onClick={finish} data-kl="T24">
      {saveLabel}
    </button>
  );
  const cancelButton = (
    <button
      type="button"
      className="h-9 rounded px-4 font-medium text-primary hover:bg-selected"
      onClick={() => router.push(listHref)}
    >
      Cancel
    </button>
  );
  // TODO: save-failure wording is not in the docs or the capture. Confirm.
  const saveError = saveFailed && <p className="text-error">The budget could not be saved. Try again.</p>;

  return (
    <>
      <div className="flex items-center gap-4">
        <Link
          href={listHref}
          aria-label="Back"
          className="-ml-2 flex size-9 items-center justify-center rounded-full text-primary hover:bg-selected"
        >
          <svg viewBox="0 0 24 24" className="size-5" aria-hidden="true">
            <path fill="currentColor" d="M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20z" />
          </svg>
        </Link>
        <h1 className="page-title">{mode === "edit" ? "Edit Budget" : "Create Budget"}</h1>
      </div>

      <div className="mt-6 flex items-start gap-10">
        <div ref={root} className="w-[600px] shrink-0">
          {mode === "create" ? (
            <>
              {SECTIONS.map((section) => (
                <Step
                  key={section}
                  number={section}
                  status={
                    sectionHasError(section)
                      ? "error"
                      : state.open.includes(section)
                        ? "active"
                        : state.visited.includes(section)
                          ? "done"
                          : "idle"
                  }
                  open={state.open.includes(section)}
                  last={section === 4}
                  onOpen={() => openStep(section, "section_header_click")}
                  onNext={section < 4 ? () => openStep((section + 1) as SectionNumber, "next_button") : undefined}
                >
                  {body[section]}
                </Step>
              ))}
              <div className="mt-6 flex items-center gap-2">
                {saveButton}
                {cancelButton}
                {saveError}
              </div>
            </>
          ) : (
            <>
              <h2 className="text-[24px] leading-8">{savedName}</h2>
              {SECTIONS.map((section) => (
                <EditSection
                  key={section}
                  name={SECTION_NAMES[section]}
                  open={state.open.includes(section)}
                  onToggle={() => toggleSection(section)}
                >
                  {body[section]}
                </EditSection>
              ))}
            </>
          )}
        </div>
        {/* TODO: where the chart sits at 1440 x 900 with Actions open is provisional until the capture. */}
        <aside className="min-w-0 flex-1 rounded-lg border border-line">
          <CostTrend token={token} config={config} data={data} />
        </aside>
      </div>

      {mode === "edit" && (
        <div className="sticky bottom-0 z-20 -mx-8 mt-8 flex items-center gap-2 border-t border-line bg-white px-8 py-3">
          {saveButton}
          {cancelButton}
          {saveError}
        </div>
      )}
    </>
  );
}

type StepStatus = "active" | "done" | "error" | "idle";

function StepIcon({ number, status }: { number: SectionNumber; status: StepStatus }) {
  const base = "flex size-6 shrink-0 items-center justify-center rounded-full text-[12px] font-medium text-white";
  if (status === "error")
    return (
      <span className={`${base} bg-error`} aria-hidden="true">
        !
      </span>
    );
  if (status === "done")
    return (
      <span className={`${base} bg-primary`} aria-hidden="true">
        <svg viewBox="0 0 24 24" className="size-4">
          <path d="M5 12.5l4.5 4.5L19 7.5" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" />
        </svg>
      </span>
    );
  return (
    <span className={`${base} ${status === "active" ? "bg-primary" : "bg-muted/60"}`} aria-hidden="true">
      {number}
    </span>
  );
}

type StepProps = {
  number: SectionNumber;
  status: StepStatus;
  open: boolean;
  last: boolean;
  onOpen: () => void;
  onNext?: () => void;
  children: ReactNode;
};

function Step({ number, status, open, last, onOpen, onNext, children }: StepProps) {
  return (
    <section>
      <button
        type="button"
        onClick={onOpen}
        aria-expanded={open}
        className="flex items-center gap-4 py-1 text-left"
        data-kl="T15"
      >
        <StepIcon number={number} status={status} />
        <span className="text-[22px] leading-9">{SECTION_NAMES[number]}</span>
      </button>
      <div className={`ml-3 pl-7 ${last ? "" : "border-l border-line"} ${open ? "pb-6 pt-3" : "h-5"}`}>
        {open && (
          <>
            {children}
            {onNext && (
              <button type="button" className="btn-secondary mt-6" onClick={onNext} data-kl="T15">
                Next
              </button>
            )}
          </>
        )}
      </div>
    </section>
  );
}

type EditSectionProps = { name: string; open: boolean; onToggle: () => void; children: ReactNode };

function EditSection({ name, open, onToggle, children }: EditSectionProps) {
  return (
    <section className="border-t border-line py-4">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex w-full items-center justify-between text-left"
      >
        <span className="text-[22px] leading-9">{name}</span>
        <Chevron up={open} />
      </button>
      {open && <div className="pt-3">{children}</div>}
    </section>
  );
}
