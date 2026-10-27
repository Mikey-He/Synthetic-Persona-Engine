"use client";

import Link from "next/link";
import { useId, useState } from "react";
import { Dropdown, Select } from "@/components/console/Dropdown";
import { HelpPopover } from "@/components/console/HelpPopover";
import { budgetAmount, type CostData } from "@/lib/domain/costs";
import { emailOptionsEnabled, parseNumber, projectOwnersAvailable } from "@/lib/domain/rules";
import type { BudgetConfig } from "@/lib/domain/types";
import { Checkbox, FieldError, OutlinedInput } from "./fields";
import type { Change } from "@/components/budget-shared/formStore";
import { TRIGGER_OPTIONS } from "./labels";
import { addThreshold, removeThreshold, setPercent, setTrigger } from "@/components/budget-shared/setters";

type Props = {
  token: string;
  config: BudgetConfig;
  percentTexts: string[];
  data: CostData;
  errors: Map<string, string>;
  change: Change;
};

// "5" for 5.00, "12.5" for 12.50.
const plain = (value: number) => String(Math.round(value * 100) / 100);

export function ActionsSection({ token, config, percentTexts, data, errors, change }: Props) {
  const idPrefix = useId();
  const monitoringGroup = useId();
  const { thresholds, recipients } = config;
  const base = budgetAmount(data, config);
  const emailEnabled = emailOptionsEnabled(config);
  const ownersAvailable = projectOwnersAvailable(config);

  const texts = { targetText: "", percentTexts };
  const onPercent = (index: number, percent: number, text: string) =>
    setPercent(change, texts, index, percent, text);

  return (
    <>
      <div data-setting="alert">
        <p className="text-[16px] font-medium">Set alert threshold rules</p>
        <p className="mt-1">
          Send email alert notifications after the actual or forecasted spend exceeds a percent of the
          budget or a specified amount.
        </p>
        <div className="mt-5 space-y-5">
          {thresholds.map((threshold, index) => {
            const error = errors.get(`thresholds.${index}.percent`);
            const n = index + 1;
            return (
              <div key={index} className="group flex items-start gap-3">
                <div className="w-44 shrink-0">
                  <OutlinedInput
                    id={`${idPrefix}-percent-${index}`}
                    kl="T19"
                    label={`Percent of budget ${n} *`}
                    suffix="%"
                    inputMode="decimal"
                    value={percentTexts[index] ?? ""}
                    invalid={Boolean(error)}
                    onChange={(text) => onPercent(index, parseNumber(text) ?? Number.NaN, text)}
                  />
                  <FieldError message={error} />
                </div>
                <AmountField
                  id={`${idPrefix}-amount-${index}`}
                  label={`Amount ${n}`}
                  base={base}
                  percent={threshold.percent}
                  onPercent={(percent) => onPercent(index, percent, Number.isNaN(percent) ? "" : plain(percent))}
                />
                <Select
                  label={`Trigger on ${n}`}
                  value={threshold.trigger}
                  options={TRIGGER_OPTIONS}
                  onChange={(trigger) => setTrigger(change, index, trigger)}
                  kl="T37"
                  className="w-44 shrink-0"
                />
                {/* Shown on hover or focus, as in the capture ("Delete item"). */}
                <button
                  type="button"
                  aria-label="Delete item"
                  title="Delete item"
                  onClick={() => removeThreshold(change, config, texts, index)}
                  className="mt-1.5 flex size-8 shrink-0 items-center justify-center rounded-full text-muted opacity-0 hover:bg-surface focus:opacity-100 group-hover:opacity-100 group-focus-within:opacity-100"
                >
                  <svg viewBox="0 0 24 24" className="size-5" aria-hidden="true">
                    <path
                      fill="currentColor"
                      d="M6 19a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V7H6zm3.5-9h1v8h-1zm4 0h1v8h-1zM15.5 4l-1-1h-5l-1 1H5v2h14V4z"
                    />
                  </svg>
                </button>
              </div>
            );
          })}
        </div>
        <button type="button" className="btn-secondary mt-5 gap-1" onClick={() => addThreshold(change, config, texts)}>
          <span aria-hidden="true" className="text-[18px] leading-none">
            +
          </span>
          Add threshold
        </button>
      </div>

      <div className="mt-8" data-setting="recipients">
        <p className="text-[16px] font-medium">Manage notifications</p>
        {!emailEnabled && <p className="mt-1 text-muted">Add a threshold rule to turn on email alerts.</p>}
        <div className="mt-1">
          <Checkbox
            kl="T23"
            label="Email alerts to billing admins and users"
            checked={recipients.billingAdminsAndUsers}
            disabled={!emailEnabled}
            onChange={(checked) => change([["recipients.billingAdminsAndUsers", checked]])}
          />
          {/* Always shown. With one project it works and the (?) goes away; otherwise
              the (?) explains the limit, as the participant's screenshots showed. */}
          <Checkbox
            kl="T38"
            label="Email alerts to project owners"
            checked={recipients.projectOwners}
            disabled={!emailEnabled || !ownersAvailable}
            onChange={(checked) => change([["recipients.projectOwners", checked]])}
            help={
              ownersAvailable ? undefined : (
                <HelpPopover kl="T25" explains="T39">
                  This notification method is limited to budgets configured to monitor a single project.
                </HelpPopover>
              )
            }
          />
          <Checkbox
            kl="T22"
            label="Link Monitoring email notification channels to this budget"
            checked={recipients.monitoring.linked}
            disabled={!emailEnabled}
            onChange={(checked) => change([["recipients.monitoring.linked", checked]])}
            description="Select a project and a maximum of 5 Monitoring email notification channels."
          />
          {recipients.monitoring.linked && (
            <div className="mb-2 ml-7 mt-1 space-y-3">
              {data.projects.map((project) => (
                <div key={project.id}>
                  <label className="flex cursor-pointer items-center gap-3">
                    <input
                      type="radio"
                      name={monitoringGroup}
                      className="size-4"
                      checked={recipients.monitoring.projectId === project.id}
                      disabled={!emailEnabled}
                      onChange={() => change([["recipients.monitoring.projectId", project.id]])}
                    />
                    {project.name}
                  </label>
                  <div className="ml-7">
                    <p className="text-muted">No notification channels</p>
                    <Link href={`/s/${token}/stub/notification-channels`} className="link">
                      Manage notification channels
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          )}
          <Checkbox
            kl="T21"
            label="Connect a Pub/Sub topic to this budget"
            checked={recipients.pubsubTopic !== undefined}
            onChange={(checked) => change([["recipients.pubsubTopic", checked ? "" : undefined]])}
            description="Select a project and Pub/Sub topic. Anyone who can view this budget will also be able to view the project ID and the topic name. It may not be possible to add a Pub/Sub topic if it belongs to an organization that has domain restricted sharing enabled."
          />
          {recipients.pubsubTopic !== undefined && (
            <Dropdown display="No topics available" disabled className="mb-2 ml-7 mt-1 w-72">
              {() => null}
            </Dropdown>
          )}
        </div>
        <FieldError message={errors.get("recipients")} />
      </div>
    </>
  );
}

type AmountFieldProps = {
  id: string;
  label: string;
  base: number | undefined;
  percent: number;
  onPercent: (percent: number) => void;
};

// The dollar value of a rule. It can be typed too, which sets the percent, and
// it stays greyed out until the budget has an amount, as in the capture.
function AmountField({ id, label, base, percent, onPercent }: AmountFieldProps) {
  const [typing, setTyping] = useState<string | null>(null);
  const usable = base !== undefined && base > 0;
  const shown = usable && Number.isFinite(percent) ? plain((base * percent) / 100) : "0";

  return (
    <div className="w-44 shrink-0">
      <OutlinedInput
        id={id}
        label={usable ? `${label} *` : label}
        prefix="$"
        inputMode="decimal"
        value={typing ?? shown}
        disabled={!usable}
        onFocus={() => setTyping(shown)}
        onBlur={() => setTyping(null)}
        onChange={(text) => {
          setTyping(text);
          const amount = parseNumber(text);
          if (usable) onPercent(amount === undefined ? Number.NaN : Math.round((amount / base) * 10000) / 100);
        }}
      />
    </div>
  );
}
