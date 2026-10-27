import Link from "next/link";
import { alertsAt, amountTypeLabel, appliesTo, kindLabel, periodLabel } from "@/components/advanced-form/labels";
import { listBudgets } from "@/lib/budgets";
import { budgetAmount, currentMonth, scopeProjectIds, totalCost } from "@/lib/domain/costs";
import { fixture } from "@/lib/fixtures";
import { formatMoney } from "@/lib/format";
import { getParticipantSession } from "@/lib/session";

type Props = { params: Promise<{ token: string }> };

// The budgets list as the reference capture shows it. A budget name opens Edit
// Budget; there is no read-only view. Delete is shown but never enabled, and
// the capture's Filter box is left out (a participant has at most a few rows).
export default async function BudgetsPage({ params }: Props) {
  const { token } = await params;
  const session = await getParticipantSession(token);
  const budgets = session ? await listBudgets(session.id) : [];
  const month = currentMonth(fixture);

  return (
    <>
      <div className="flex items-center gap-6">
        <h1 className="page-title">Budgets &amp; caps</h1>
        <Link
          href={`/s/${token}/billing/budgets/create`}
          data-kl="T10"
          className="inline-flex h-9 items-center gap-1 rounded px-3 font-medium text-primary hover:bg-selected"
        >
          <span aria-hidden="true" className="text-[20px] leading-none">
            +
          </span>
          Create new
        </Link>
        <button type="button" disabled className="h-9 rounded px-3 font-medium text-muted opacity-60">
          Delete
        </button>
      </div>
      {/* TODO: the capture's description paragraph was not legible. Minimal neutral text until it is. */}
      <p className="mt-3 max-w-[760px] text-muted">
        Budgets track your spend against a planned amount and send alerts when spend reaches the thresholds you set.
      </p>
      <table className="data-table mt-4">
        <thead>
          <tr>
            <th>Budget name</th>
            <th>Budget period</th>
            <th>Budget type</th>
            <th>Applies to</th>
            <th>Trigger alerts at</th>
            <th>Spend and budget amount</th>
            <th>Spend cap status</th>
          </tr>
        </thead>
        <tbody>
          {budgets.length === 0 ? (
            <tr>
              <td colSpan={7} className="text-muted">
                No budgets yet
              </td>
            </tr>
          ) : (
            budgets.map(({ id, config }) => {
              const amount = budgetAmount(fixture, config) ?? 0;
              const spend = totalCost(fixture, scopeProjectIds(fixture, config.scope), month);
              const share = amount > 0 ? Math.min(1, spend / amount) : 0;
              return (
                <tr key={id}>
                  <td>
                    <Link href={`/s/${token}/billing/budgets/create?edit=${id}`} className="link" data-kl="T43">
                      {config.name}
                    </Link>
                  </td>
                  <td>{periodLabel(config.period)}</td>
                  <td>{config.kind ? kindLabel(config.kind) : amountTypeLabel(config.amount.type)}</td>
                  <td>{appliesTo(config.scope, fixture.projects)}</td>
                  <td>{alertsAt(config.thresholds)}</td>
                  <td className="min-w-44">
                    <div className="h-1.5 w-40 rounded-full bg-grid">
                      <div className="h-full rounded-full bg-primary" style={{ width: `${share * 100}%` }} />
                    </div>
                    <div className="mt-1">
                      {formatMoney(spend, fixture.currency)} / {formatMoney(amount, fixture.currency)}
                    </div>
                    <div className="text-[12px] text-muted">No credits used</div>
                  </td>
                  <td>{config.kind === "spend_cap" ? "—" : "Not applicable"}</td>
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </>
  );
}
