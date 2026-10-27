"use client";

import { useState } from "react";
import { ChecklistDropdown, Select } from "@/components/console/Dropdown";
import type { BudgetConfig, Fixture } from "@/lib/domain/types";
import { Checkbox } from "./fields";
import type { Change } from "@/components/budget-shared/formStore";
import { PERIOD_OPTIONS, SAVINGS_OPTIONS, labelOptionText, projectsLabel, servicesLabel } from "./labels";

type Props = {
  config: BudgetConfig;
  data: Pick<Fixture, "projects" | "services" | "labels">;
  change: Change;
};

// Adds or removes one value, keeping the order of the full option list.
const toggled = (selected: string[], value: string, order: string[]) => {
  const next = selected.includes(value) ? selected.filter((v) => v !== value) : [...selected, value];
  return order.filter((v) => next.includes(v));
};

// Order and wording follow the reference capture. The account has no
// organization, so there is no Folders & organizations picker.
export function ScopeSection({ config, data, change }: Props) {
  const [labelsOpen, setLabelsOpen] = useState(false);
  const { scope } = config;
  const labelValues = data.labels.flatMap((label) => label.values.map((value) => `${label.key}:${value}`));

  return (
    <div className="space-y-4">
      <div data-setting="period">
        <Select
          label="Time range"
          value={config.period}
          options={PERIOD_OPTIONS}
          onChange={(period) => change([["period", period]])}
          className="w-full"
          kl="T11"
        />
        {/* TODO: the capture shows the helper for Monthly only. */}
        {config.period === "monthly" && (
          <p className="ml-4 mt-1 text-[12px] leading-4 text-muted">
            The month starts on the first of the month and resets at the beginning of each month.
          </p>
        )}
        {config.period === "custom" && (
          <div className="mt-4 flex gap-4">
            <input
              type="date"
              aria-label="From"
              value={config.customRange?.from ?? ""}
              onChange={(event) => change([["customRange.from", event.target.value]])}
              className="field h-11 w-48"
            />
            <input
              type="date"
              aria-label="To"
              value={config.customRange?.to ?? ""}
              onChange={(event) => change([["customRange.to", event.target.value || undefined]])}
              className="field h-11 w-48"
            />
          </div>
        )}
      </div>

      <Checkbox
        kl="T32"
        label="Read-only for project users (single-project budgets only)"
        checked={scope.readOnlyForProjectUsers}
        onChange={(checked) => change([["scope.readOnlyForProjectUsers", checked]])}
      />
      <p>
        Marking a budget read-only for project users restricts any inadvertent edits to important
        budgets tracked centrally.
      </p>
      <p>A budget can be scoped to focus on a specific set of resources.</p>

      {/* No project checked means every project, as in the capture. */}
      <div data-setting="scope">
        <ChecklistDropdown
          kl="T05"
          label="Projects"
          display={projectsLabel(scope, data.projects)}
          options={data.projects.map((project) => ({ value: project.id, label: project.name, detail: project.id }))}
          selected={scope.allProjects ? [] : scope.projectIds}
          onApply={(ids) =>
            change([
              ["scope.allProjects", ids.length === 0],
              ["scope.projectIds", ids],
            ])
          }
        />
      </div>

      <ChecklistDropdown
        kl="T12"
        label="Services"
        display={servicesLabel(scope.filters.services, data.services)}
        options={data.services.map((service) => ({ value: service, label: service }))}
        selected={scope.filters.services}
        onApply={(services) => change([["scope.filters.services", services]])}
      />

      <div>
        <button
          type="button"
          aria-expanded={labelsOpen}
          onClick={() => setLabelsOpen((value) => !value)}
          data-kl="T35"
          className="flex w-full items-center justify-between py-1 text-left"
        >
          <span className="text-[16px] font-medium">Labels</span>
          <Chevron up={labelsOpen} />
        </button>
        <p className="text-[12px] leading-4 text-muted">Select the key and value of the label you want to filter.</p>
        {/* TODO: the capture shows Labels collapsed only; its open contents are not captured. */}
        {labelsOpen && (
          <div className="mt-2">
            {labelValues.map((value) => (
              <Checkbox
                key={value}
                label={labelOptionText(value)}
                checked={scope.filters.labels.includes(value)}
                onChange={() =>
                  change([["scope.filters.labels", toggled(scope.filters.labels, value, labelValues)]])
                }
              />
            ))}
          </div>
        )}
      </div>

      <div data-kl="T34">
        <p className="text-[16px] font-medium">Savings</p>
        <p className="text-[12px] leading-4 text-muted">
          Selected credits are applied to the total cost. Budget tracks the total cost minus any
          applicable selected credits.
        </p>
        <div className="mt-1">
          {SAVINGS_OPTIONS.map((option) => (
            <Checkbox
              key={option.value}
              label={option.label}
              checked={scope.savings.includes(option.value)}
              onChange={() =>
                change([
                  ["scope.savings", toggled(scope.savings, option.value, SAVINGS_OPTIONS.map((o) => o.value))],
                ])
              }
            />
          ))}
        </div>
      </div>
    </div>
  );
}

export function Chevron({ up }: { up: boolean }) {
  return (
    <svg viewBox="0 0 24 24" className="size-6 text-muted" aria-hidden="true">
      <path
        d={up ? "M7 14l5-5 5 5" : "M7 10l5 5 5-5"}
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
