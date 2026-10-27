// The billing navigation as the reference capture shows it (2026-09-30). Only
// Overview, Budgets & caps and Account management are part of the study; every
// other entry opens the out-of-study placeholder.

// kl: the knowledge item a link shows, for the AI engine (engine-design.md 7).
export type NavItem = { label: string; path: string; preview?: boolean; kl?: string };
export type NavGroup = { heading: string | null; items: NavItem[] };

const stub = (area: string) => `/stub/${area}`;

export const NAV_GROUPS: NavGroup[] = [
  { heading: null, items: [{ label: "Overview", path: "/billing" }] },
  {
    heading: "Cost management",
    items: [
      { label: "Reports", path: stub("reports") },
      { label: "Cost table", path: stub("cost-table") },
      { label: "Cost breakdown", path: stub("cost-breakdown") },
      { label: "Incentives", path: stub("incentives") },
      { label: "Billing export", path: stub("billing-export") },
    ],
  },
  {
    heading: "Cost control",
    items: [
      { label: "Budgets & caps", path: "/billing/budgets", preview: true, kl: "T09" },
      { label: "Anomalies", path: stub("anomalies") },
    ],
  },
  {
    heading: "Cost optimization",
    items: [
      { label: "FinOps hub", path: stub("finops-hub") },
      { label: "Committed use discounts", path: stub("committed-use-discounts") },
      { label: "CUD analysis", path: stub("cud-analysis") },
      { label: "Pricing", path: stub("pricing") },
      { label: "Cost estimation", path: stub("cost-estimation") },
      { label: "Credits", path: stub("credits"), kl: "T13" },
    ],
  },
  {
    heading: "Payments",
    items: [
      { label: "Invoices", path: stub("invoices") },
      { label: "Transactions", path: stub("transactions") },
      { label: "Payment settings", path: stub("payment-settings") },
      { label: "Payment method", path: stub("payment-method") },
    ],
  },
  {
    heading: "Billing management",
    items: [{ label: "Account management", path: "/billing/account" }],
  },
];

// Breadcrumb trail for a participant route (the path after /s/<token>).
// Edit Budget is the create route with ?edit=<id>.
export function breadcrumbsFor(route: string, editing = false): { label: string; path?: string }[] {
  const billing = { label: "Billing", path: "/billing" };
  const budgets = { label: "Budgets and alerts", path: "/billing/budgets" };
  if (route === "/billing") return [billing, { label: "Overview" }];
  if (route === "/billing/budgets") return [billing, { label: budgets.label }];
  if (route === "/billing/budgets/create")
    return [billing, budgets, { label: editing ? "Edit budget" : "Create budget" }];
  if (route === "/billing/account") return [billing, { label: "Account management" }];
  const item = NAV_GROUPS.flatMap((group) => group.items).find((entry) => entry.path === route);
  return [billing, { label: item?.label ?? "" }];
}
