"use client";

import Link from "next/link";
import { useId } from "react";
import { CostChart } from "@/components/console/CostChart";
import { budgetAmount, costMonths, scopeProjectIds, totalCost, type CostData } from "@/lib/domain/costs";
import type { BudgetConfig } from "@/lib/domain/types";
import { monthRangeLabel } from "@/lib/format";

type Props = { token: string; config: BudgetConfig; data: CostData & { currency: string } };

// Total cost for the budget's scope, month by month, with the budget amount
// as a dashed line, as in the reference capture. The fixture has no
// per-service or per-label costs, so only the Projects scope changes the bars.
export function CostTrend({ token, config, data }: Props) {
  const titleId = useId();
  const months = costMonths(data);
  const inScope = scopeProjectIds(data, config.scope);

  return (
    <>
      <div className="px-5 pt-4">
        <h2 id={titleId} className="text-[18px] leading-6">
          Cost trend
        </h2>
        <p className="text-muted">{monthRangeLabel(months[0], months[months.length - 1])}</p>
        <div className="mt-3">
          <CostChart
            titleId={titleId}
            months={months}
            currency={data.currency}
            width={400}
            height={230}
            shortMonths
            budgetLine={budgetAmount(data, config)}
            series={[
              {
                id: "total",
                name: "Total cost",
                color: "var(--color-series-1)",
                values: months.map((month) => totalCost(data, inScope, month)),
              },
            ]}
          />
        </div>
        <p className="mt-2 text-[13px] leading-5">
          Note: Forecasts are calculated using actual costs. However, spend caps are triggered by
          gross estimated costs for faster reporting.
        </p>
      </div>
      <Link
        href={`/s/${token}/stub/reports`}
        className="mt-4 flex items-center gap-2 border-t border-line px-5 py-3 hover:bg-surface"
      >
        <svg viewBox="0 0 24 24" className="size-5" aria-hidden="true">
          <path d="M4 12h14M13 6l6 6-6 6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
        View report
      </Link>
    </>
  );
}
