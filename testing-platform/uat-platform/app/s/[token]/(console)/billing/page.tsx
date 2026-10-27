import { CostChart, projectColor } from "@/components/console/CostChart";
import { costMonths, currentMonth, projectCost, totalCost } from "@/lib/domain/costs";
import { fixture } from "@/lib/fixtures";
import { formatMoney, monthSpanLabel } from "@/lib/format";

export default function OverviewPage() {
  const projectIds = fixture.projects.map((project) => project.id);
  const months = costMonths(fixture);
  const soFar = totalCost(fixture, projectIds, currentMonth(fixture));

  return (
    <>
      <h1 className="page-title">Overview</h1>
      <dl className="mt-4 grid w-fit grid-cols-[max-content_1fr] gap-x-8 gap-y-1">
        <dt className="text-muted">Billing account</dt>
        <dd>{fixture.billingAccount.name}</dd>
        <dt className="text-muted">Billing account ID</dt>
        <dd>{fixture.billingAccount.id}</dd>
      </dl>

      <section className="mt-6 w-fit rounded-lg border border-line px-5 py-4">
        <h2 className="text-[16px] font-medium">Your total cost</h2>
        <p className="text-muted">{monthSpanLabel(currentMonth(fixture))}</p>
        <p className="mt-2 text-[28px] leading-9">{formatMoney(soFar, fixture.currency)}</p>
      </section>

      <section className="mt-6 w-fit rounded-lg border border-line px-5 py-4">
        {/* TODO: chart heading is not written in the docs. Confirm the wording. */}
        <h2 id="monthly-cost-title" className="mb-3 font-medium">
          Monthly cost by project
        </h2>
        <CostChart
          titleId="monthly-cost-title"
          months={months}
          currency={fixture.currency}
          series={fixture.projects.map((project) => ({
            id: project.id,
            name: project.name,
            color: projectColor(projectIds, project.id),
            values: months.map((month) => projectCost(fixture, project.id, month)),
          }))}
        />
      </section>
    </>
  );
}
