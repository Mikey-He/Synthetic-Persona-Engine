"use client";

import { useId } from "react";
import { Select } from "@/components/console/Dropdown";
import { lastMonthSpend, type CostData } from "@/lib/domain/costs";
import type { BudgetConfig, Period } from "@/lib/domain/types";
import { FieldError, OutlinedInput } from "./fields";
import type { Change } from "@/components/budget-shared/formStore";
import { AMOUNT_TYPE_OPTIONS } from "./labels";
import { setTarget } from "@/components/budget-shared/setters";

type Props = {
  config: BudgetConfig;
  targetText: string;
  data: CostData;
  errors: Map<string, string>;
  change: Change;
};

// TODO: the capture shows "Set a monthly budget amount" only; the other periods follow its pattern.
const PERIOD_WORD: Record<Period, string> = { monthly: "monthly ", quarterly: "quarterly ", yearly: "yearly ", custom: "" };

export function AmountSection({ config, targetText, data, errors, change }: Props) {
  const targetId = useId();
  const error = errors.get("amount.target");
  const specified = config.amount.type === "specified";

  return (
    <div data-setting="amount" className="space-y-4">
      <p>Set a {PERIOD_WORD[config.period]}budget amount</p>
      <div>
        <Select
          label="Budget type"
          value={config.amount.type}
          options={AMOUNT_TYPE_OPTIONS}
          onChange={(type) => change([["amount.type", type]])}
          className="w-full"
          kl="T16"
        />
        {specified && (
          <p className="ml-4 mt-1 text-[12px] leading-4 text-muted">
            A fixed amount that your spend will be compared against.
          </p>
        )}
      </div>
      {specified ? (
        <div>
          <OutlinedInput
            id={targetId}
            kl="T36"
            label="Target amount *"
            prefix="$"
            inputMode="decimal"
            value={targetText}
            invalid={Boolean(error)}
            onChange={(text) => setTarget(change, text)}
          />
          <FieldError message={error} />
        </div>
      ) : (
        <OutlinedInput
          id={targetId}
          kl="T36"
          label="Target amount"
          prefix="$"
          value={lastMonthSpend(data, config.scope).toFixed(2)}
          disabled
        />
      )}
    </div>
  );
}
