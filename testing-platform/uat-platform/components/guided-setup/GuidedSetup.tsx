"use client";

import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Select } from "@/components/console/Dropdown";
import { initialFormState } from "@/components/budget-shared/formStore";
import { addThreshold, removeThreshold, setPercent, setTarget, setTrigger } from "@/components/budget-shared/setters";
import { useBudgetDraft } from "@/components/budget-shared/useBudgetDraft";
import { budgetAmount, lastMonthSpend } from "@/lib/domain/costs";
import { coversOneProject, emailOptionsEnabled, parseNumber } from "@/lib/domain/rules";
import type { BudgetConfig, Fixture, Period, Trigger } from "@/lib/domain/types";
import { settingValue } from "@/lib/events/types";
import {
  B_MESSAGES,
  PERIOD_CHOICES,
  SCREENS,
  TRIGGER_CHOICES,
  alertsSummary,
  amountSummary,
  money,
  periodSummary,
  recipientsSummary,
  screenIssues,
  tracksSummary,
  type ScreenKey,
} from "./copy";

// The guided setup (guide Part 14): the AWS simplified-template pattern of one
// question per screen, with Google Cloud's settings, defaults and product
// rules. It writes the same BudgetDraft through the same setters and saves
// through the same function as the advanced form.

export type GuidedData = Pick<
  Fixture,
  "currency" | "today" | "projects" | "monthlyCosts" | "billingAccount" | "billingMembers" | "projectOwners"
>;

type Props = {
  token: string;
  data: GuidedData;
  initialConfig: BudgetConfig;
  editingBudgetId: string | null; // set when a saved budget was opened, which lands on review
};

// How a person arrived on a screen, recorded with setting_returned.
type Arrival = "page_load" | "continue_button" | "back_button" | "review_edit" | "validation";

const LAST = SCREENS.length - 1;

export function GuidedSetup({ token, data, initialConfig, editingBudgetId }: Props) {
  const router = useRouter();
  const { logger, store, state, change, submit, saving } = useBudgetDraft({
    token,
    initialState: initialFormState(initialConfig, "create"),
    editingBudgetId,
  });
  const [index, setIndex] = useState(editingBudgetId ? LAST : 0);
  const [returnToReview, setReturnToReview] = useState(false);
  const [error, setError] = useState<{ field: string; message: string } | null>(null);
  const [saveFailed, setSaveFailed] = useState(false);
  const mounted = useRef(false);
  const listHref = `/s/${token}/billing/budgets`;
  const screen = SCREENS[index];
  const { config } = state;

  const enter = (to: number, arrival: Arrival) => {
    if (!logger) return;
    const next = SCREENS[to];
    logger.log("screen_viewed", next.key, { screen: next.key, number: to + 1 });
    if (next.setting) logger.settingEntered(next.setting, settingValue(store.get().config, next.setting), arrival);
  };

  // The first screen shown on arrival.
  useEffect(() => {
    if (mounted.current || !logger) return;
    mounted.current = true;
    if (editingBudgetId) logger.log("budget_reopened", editingBudgetId, { budgetId: editingBudgetId });
    enter(index, "page_load");
  });

  const go = (to: number, arrival: Arrival) => {
    if (screen.setting) logger?.settingLeft(screen.setting);
    setError(null);
    setIndex(to);
    enter(to, arrival);
    window.scrollTo(0, 0);
  };

  const showIssue = (issue: { field: string; message: string }) => {
    logger?.log("validation_shown", issue.field, issue);
    setError(issue);
  };

  const onContinue = () => {
    const issue = screenIssues(screen.key, store.get().config)[0];
    if (issue) return showIssue(issue);
    if (returnToReview) {
      setReturnToReview(false);
      go(LAST, "continue_button");
    } else go(index + 1, "continue_button");
  };

  const onEdit = (key: ScreenKey) => {
    const to = SCREENS.findIndex((s) => s.key === key);
    logger?.log("review_edit", SCREENS[to].setting, { setting: SCREENS[to].setting, screen: key });
    setReturnToReview(true);
    go(to, "review_edit");
  };

  async function create() {
    setSaveFailed(false);
    const result = await submit("Create budget", (issue) => B_MESSAGES[issue.code]);
    if (result.status === "saved") router.push(listHref);
    else if (result.status === "invalid") {
      const first = result.issues[0];
      const to = SCREENS.findIndex((s) => screenIssues(s.key, store.get().config).length > 0);
      setReturnToReview(true);
      go(to === -1 ? 0 : to, "validation");
      setError({ field: first.field, message: B_MESSAGES[first.code] });
    } else setSaveFailed(true);
  }

  const mainLabel = returnToReview ? "Back to review" : `Continue to ${SCREENS[index + 1]?.name.toLowerCase()}`;

  return (
    <div className="max-w-[720px]">
      <Progress index={index} />
      <h1 className="mt-6 text-[26px] leading-9">{screen.question}</h1>
      <p className="mt-1 text-muted">{screen.reason}</p>

      <div className="mt-6">
        {screen.key === "name" && <NameScreen config={config} change={change} invalid={error?.field === "name"} />}
        {screen.key === "projects" && <ProjectsScreen config={config} data={data} change={change} />}
        {screen.key === "period" && <PeriodScreen config={config} change={change} />}
        {screen.key === "amount" && (
          <AmountScreen config={config} data={data} targetText={state.targetText} change={change} />
        )}
        {screen.key === "alerts" && (
          <AlertsScreen config={config} data={data} percentTexts={state.percentTexts} change={change} />
        )}
        {screen.key === "recipients" && <RecipientsScreen config={config} data={data} change={change} />}
        {screen.key === "review" && <ReviewScreen config={config} data={data} onEdit={onEdit} />}
      </div>

      {error && (
        <p role="alert" className="mt-4 text-error">
          {error.message}
        </p>
      )}
      {/* TODO: save-failure wording is not in the docs. Same text as the advanced form. */}
      {saveFailed && <p className="mt-4 text-error">The budget could not be saved. Try again.</p>}

      <div className="mt-8 flex items-center justify-between">
        {index > 0 ? (
          <button type="button" className="btn-secondary" onClick={() => go(index - 1, "back_button")}>
            Back
          </button>
        ) : (
          <span />
        )}
        {index === LAST ? (
          <button type="button" className="btn-primary" disabled={saving} onClick={create}>
            Create budget
          </button>
        ) : (
          <button type="button" className="btn-primary" onClick={onContinue}>
            {mainLabel}
          </button>
        )}
      </div>
    </div>
  );
}

function Progress({ index }: { index: number }) {
  return (
    <div>
      <ol className="grid grid-cols-7 gap-1.5" aria-label="Progress">
        {SCREENS.map((s, i) => (
          <li key={s.key} aria-current={i === index ? "step" : undefined}>
            <div className={`h-1.5 rounded-full ${i <= index ? "bg-primary" : "bg-grid"}`} />
            <span className={`mt-1.5 block text-[12px] ${i === index ? "font-medium text-primary" : "text-muted"}`}>
              {s.name}
            </span>
          </li>
        ))}
      </ol>
      <p className="mt-3 text-[13px] text-muted">
        {SCREENS[index].name} · step {index + 1} of {SCREENS.length}
      </p>
    </div>
  );
}

type Change = ReturnType<typeof useBudgetDraft>["change"];

function Card({ children, selected = false }: { children: ReactNode; selected?: boolean }) {
  return (
    <div className={`rounded-lg border px-4 py-3 ${selected ? "border-primary" : "border-line"}`}>{children}</div>
  );
}

function Radio({ name, label, checked, onChange }: { name: string; label: string; checked: boolean; onChange: () => void }) {
  return (
    <label className="flex cursor-pointer items-center gap-3 font-medium">
      <input type="radio" name={name} checked={checked} onChange={onChange} className="size-4" />
      {label}
    </label>
  );
}

function NameScreen({ config, change, invalid }: { config: BudgetConfig; change: Change; invalid: boolean }) {
  const id = useId();
  return (
    <div>
      <label htmlFor={id} className="block font-medium">
        Budget name
      </label>
      <input
        id={id}
        value={config.name}
        onChange={(event) => change([["name", event.target.value]])}
        className={`field mt-1.5 h-11 w-full ${invalid ? "border-error" : ""}`}
      />
    </div>
  );
}

function ProjectsScreen({ config, data, change }: { config: BudgetConfig; data: GuidedData; change: Change }) {
  const name = useId();
  const { scope } = config;
  const chosen = data.projects.filter((p) => scope.projectIds.includes(p.id));
  const toggle = (id: string) => {
    const next = scope.projectIds.includes(id) ? scope.projectIds.filter((p) => p !== id) : [...scope.projectIds, id];
    change([["scope.projectIds", data.projects.map((p) => p.id).filter((p) => next.includes(p))]]);
  };

  return (
    <div className="space-y-3">
      {!scope.allProjects && chosen.length > 0 && (
        <div className="flex flex-wrap gap-2" aria-label="Tracked projects">
          {chosen.map((p) => (
            <span key={p.id} className="rounded-full bg-selected px-3 py-1 text-[13px] text-selected-ink">
              Tracking · {p.name}
            </span>
          ))}
        </div>
      )}
      <Card selected={scope.allProjects}>
        <Radio
          name={name}
          label={`All projects in ${data.billingAccount.name}`}
          checked={scope.allProjects}
          onChange={() => change([["scope.allProjects", true], ["scope.projectIds", []]])}
        />
      </Card>
      <Card selected={!scope.allProjects}>
        <Radio
          name={name}
          label="Only specific projects"
          checked={!scope.allProjects}
          onChange={() => change([["scope.allProjects", false]])}
        />
        {!scope.allProjects && (
          <div className="ml-7 mt-2 space-y-2">
            {data.projects.map((p) => (
              <label key={p.id} className="flex cursor-pointer items-center gap-3">
                <input
                  type="checkbox"
                  className="size-4"
                  checked={scope.projectIds.includes(p.id)}
                  onChange={() => toggle(p.id)}
                />
                {p.name} · {p.id}
              </label>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

function PeriodScreen({ config, change }: { config: BudgetConfig; change: Change }) {
  const name = useId();
  return (
    <div className="space-y-3">
      {PERIOD_CHOICES.map((choice) => (
        <Card key={choice.value} selected={config.period === choice.value}>
          <Radio
            name={name}
            label={choice.label}
            checked={config.period === choice.value}
            onChange={() => change([["period", choice.value satisfies Period]])}
          />
          {choice.value === "custom" && config.period === "custom" && (
            <div className="ml-7 mt-3 flex gap-4">
              <label className="block">
                <span className="block text-[13px] text-muted">From</span>
                <input
                  type="date"
                  value={config.customRange?.from ?? ""}
                  onChange={(event) => change([["customRange.from", event.target.value]])}
                  className="field mt-1 h-10 w-48"
                />
              </label>
              <label className="block">
                <span className="block text-[13px] text-muted">To</span>
                <input
                  type="date"
                  value={config.customRange?.to ?? ""}
                  onChange={(event) => change([["customRange.to", event.target.value || undefined]])}
                  className="field mt-1 h-10 w-48"
                />
              </label>
            </div>
          )}
        </Card>
      ))}
    </div>
  );
}

type AmountProps = { config: BudgetConfig; data: GuidedData; targetText: string; change: Change };

function AmountScreen({ config, data, targetText, change }: AmountProps) {
  const name = useId();
  const fieldId = useId();
  const fixed = config.amount.type === "specified";
  return (
    <div className="space-y-3">
      <Card selected={fixed}>
        <Radio name={name} label="A fixed amount" checked={fixed} onChange={() => change([["amount.type", "specified"]])} />
        {fixed && (
          <div className="ml-7 mt-3">
            <label htmlFor={fieldId} className="block text-[13px] text-muted">
              Amount in dollars
            </label>
            <div className="mt-1 flex h-11 w-60 items-center rounded border border-line px-3 focus-within:border-primary">
              <span className="text-muted">$</span>
              <input
                id={fieldId}
                inputMode="decimal"
                value={targetText}
                onChange={(event) => setTarget(change, event.target.value)}
                className="ml-1 h-full min-w-0 flex-1 outline-none"
              />
            </div>
          </div>
        )}
      </Card>
      <Card selected={!fixed}>
        <Radio
          name={name}
          label="Match last period's spend"
          checked={!fixed}
          onChange={() => change([["amount.type", "last_period"]])}
        />
        {!fixed && (
          <p className="ml-7 mt-2 text-muted">
            Last month: {money(lastMonthSpend(data, config.scope), data.currency)}
          </p>
        )}
      </Card>
    </div>
  );
}

type AlertsProps = { config: BudgetConfig; data: GuidedData; percentTexts: string[]; change: Change };

function AlertsScreen({ config, data, percentTexts, change }: AlertsProps) {
  const texts = { targetText: "", percentTexts };
  const base = budgetAmount(data, config);
  return (
    <div className="space-y-3">
      {config.thresholds.map((rule, i) => (
        <Card key={i}>
          <div className="flex flex-wrap items-center gap-x-2 gap-y-2">
            <span>Email when</span>
            <Select
              label={`Spend type ${i + 1}`}
              value={rule.trigger}
              options={TRIGGER_CHOICES}
              onChange={(trigger: Trigger) => setTrigger(change, i, trigger)}
              className="w-80"
            />
            <span>reaches</span>
            <input
              aria-label={`Percent ${i + 1}`}
              inputMode="decimal"
              value={percentTexts[i] ?? ""}
              onChange={(event) =>
                setPercent(change, texts, i, parseNumber(event.target.value) ?? Number.NaN, event.target.value)
              }
              className="field h-11 w-20 text-right"
            />
            <span>%</span>
            {base !== undefined && Number.isFinite(rule.percent) && (
              <span className="text-muted">({money((base * rule.percent) / 100, data.currency)})</span>
            )}
            <button
              type="button"
              aria-label={`Remove rule ${i + 1}`}
              onClick={() => removeThreshold(change, config, texts, i)}
              className="ml-auto flex size-8 items-center justify-center rounded-full text-muted hover:bg-surface"
            >
              <svg viewBox="0 0 24 24" className="size-5" aria-hidden="true">
                <path
                  fill="currentColor"
                  d="M6 19a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V7H6zm3.5-9h1v8h-1zm4 0h1v8h-1zM15.5 4l-1-1h-5l-1 1H5v2h14V4z"
                />
              </svg>
            </button>
          </div>
        </Card>
      ))}
      <button type="button" className="link font-medium" onClick={() => addThreshold(change, config, texts)}>
        Add another rule
      </button>
    </div>
  );
}

function RecipientsScreen({ config, data, change }: { config: BudgetConfig; data: GuidedData; change: Change }) {
  const enabled = emailOptionsEnabled(config);
  const single = coversOneProject(config);
  const project = single ? data.projects.find((p) => p.id === config.scope.projectIds[0]) : undefined;
  const owners = project ? (data.projectOwners[project.id] ?? []) : [];
  const { recipients } = config;

  return (
    <div className="space-y-3">
      {!enabled && <p className="text-muted">Alert emails are off because there are no alert rules.</p>}
      <Card selected={enabled && recipients.billingAdminsAndUsers}>
        <label className={`flex items-center gap-3 font-medium ${enabled ? "cursor-pointer" : "text-muted"}`}>
          <input
            type="checkbox"
            className="size-4"
            checked={recipients.billingAdminsAndUsers}
            disabled={!enabled}
            onChange={(event) => change([["recipients.billingAdminsAndUsers", event.target.checked]])}
          />
          Billing account admins and users
        </label>
        <ul className="ml-7 mt-1.5 text-[13px] text-muted">
          {data.billingMembers.map((member) => (
            <li key={member.id}>
              {member.name}
              {member.isYou ? " (you)" : ""} · {member.role}
            </li>
          ))}
        </ul>
      </Card>
      {single ? (
        <Card selected={enabled && recipients.projectOwners}>
          <label className={`flex items-center gap-3 font-medium ${enabled ? "cursor-pointer" : "text-muted"}`}>
            <input
              type="checkbox"
              className="size-4"
              checked={recipients.projectOwners}
              disabled={!enabled}
              onChange={(event) => change([["recipients.projectOwners", event.target.checked]])}
            />
            Project owners
          </label>
          <ul className="ml-7 mt-1.5 text-[13px] text-muted">
            {owners.map((owner) => (
              <li key={owner.id}>
                {owner.name} · {project?.name} owner
              </li>
            ))}
          </ul>
        </Card>
      ) : (
        <p className="text-muted">Project owner emails are available when the budget covers one project.</p>
      )}
    </div>
  );
}

type ReviewProps = { config: BudgetConfig; data: GuidedData; onEdit: (key: ScreenKey) => void };

function ReviewScreen({ config, data, onEdit }: ReviewProps) {
  const rows: { item: string; answer: string; key: ScreenKey }[] = [
    { item: "Name", answer: config.name, key: "name" },
    { item: "Tracks", answer: tracksSummary(config, data), key: "projects" },
    { item: "Starts over", answer: periodSummary(config), key: "period" },
    { item: "Amount", answer: amountSummary(config, data), key: "amount" },
    { item: "Alerts", answer: alertsSummary(config, data), key: "alerts" },
    { item: "Recipients", answer: recipientsSummary(config, data), key: "recipients" },
  ];
  return (
    <table className="w-full border-collapse text-left">
      <tbody>
        {rows.map((row) => (
          <tr key={row.key} className="border-b border-line align-top">
            <th scope="row" className="w-36 py-3 pr-4 font-medium">
              {row.item}
            </th>
            <td className="py-3 pr-4">{row.answer}</td>
            <td className="w-16 py-3 text-right">
              <button
                type="button"
                className="link font-medium"
                aria-label={`Edit ${row.item.toLowerCase()}`}
                onClick={() => onEdit(row.key)}
              >
                Edit
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
