"use client";

import { useId } from "react";
import { HelpPopover } from "@/components/console/HelpPopover";
import type { BudgetConfig, BudgetKind } from "@/lib/domain/types";
import { FieldError, OutlinedInput, PreviewTag } from "./fields";
import type { Change } from "@/components/budget-shared/formStore";

type Props = { config: BudgetConfig; errors: Map<string, string>; change: Change };

export function DefineSection({ config, errors, change }: Props) {
  const nameId = useId();
  const group = useId();
  const error = errors.get("name");

  const radio = (kind: BudgetKind, label: string, kl: string) => (
    <label className="flex cursor-pointer items-center gap-3" data-kl={kl}>
      <input
        type="radio"
        name={group}
        className="size-4"
        checked={config.kind === kind}
        onChange={() => change([["kind", kind]])}
      />
      {label}
    </label>
  );

  return (
    <>
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          {radio("alerts_only", "Alerts only (available to all services)", "T28")}
          <HelpPopover kl="T25" explains="T18">
            <span className="block">
              Budget alerts track your actual spend relative to your planned budget. Unlike spend
              caps, budget alerts don&apos;t pause your services.
            </span>
            <span className="mt-2 block">
              Cost recording typically takes up to 24 hours. Consider setting a slightly lower
              budget amount to compensate for this reporting delay.
            </span>
          </HelpPopover>
        </div>
        <div>
          <div className="flex items-center gap-2">
            {radio("spend_cap", "Spend cap enforcement (available for limited services)", "T29")}
            <PreviewTag />
          </div>
          <p className="ml-7 text-[12px] leading-4 text-muted">
            Enforced spend caps will pause your usage, including commitments such as CUDs and
            provisioned throughput, on specified services until lifted.
          </p>
        </div>
      </div>
      <div data-setting="name" className="mt-6">
        <OutlinedInput
          id={nameId}
          label="Name *"
          value={config.name}
          onChange={(value) => change([["name", value]])}
          invalid={Boolean(error)}
          floating
        />
        <FieldError message={error} />
      </div>
    </>
  );
}
