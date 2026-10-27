// Shared shapes for the draft, the saved budget, the fixture and the evaluator.
// BudgetConfig follows docs/build-plan.md (Data model).

export type Period = "monthly" | "quarterly" | "yearly" | "custom";
// The two Define choices in the reference capture. Neither is chosen at the start.
export type BudgetKind = "alerts_only" | "spend_cap";
export type AmountType = "specified" | "last_period";
export type Trigger = "actual" | "forecasted";

export type Threshold = { percent: number; trigger: Trigger };

export type BudgetConfig = {
  name: string;
  kind: BudgetKind | null; // null until one of the Define options is chosen
  scope: {
    allProjects: boolean; // true = entire account, shown as no project checked
    projectIds: string[]; // explicit selection
    // Not in build-plan.md yet. Unscored, but version A lets people change
    // these filters and the study records it. Labels are stored as "key:value".
    filters: {
      folders: string[];
      services: string[];
      labels: string[];
    };
    savings: string[]; // savings types included
    readOnlyForProjectUsers: boolean;
  };
  period: Period;
  customRange?: { from: string; to?: string };
  amount: { type: AmountType; target?: number };
  thresholds: Threshold[];
  recipients: {
    billingAdminsAndUsers: boolean;
    projectOwners: boolean; // only offered for single-project scope
    monitoring: { linked: boolean; projectId?: string; channelIds: string[] };
    // Absent while "Connect a Pub/Sub topic" is unchecked. "" means checked
    // with no topic chosen, which is all the fixture allows.
    pubsubTopic?: string;
  };
};

export type Person = { id: string; name: string; email: string };
export type BillingMember = Person & { role: string; isYou: boolean };
export type Project = { id: string; name: string };
export type MonthlyCost = { month: string; usd: number; partial?: boolean };

export type Fixture = {
  fixtureVersion: string;
  today: string; // YYYY-MM-DD. The only "today" a participant ever sees.
  currency: string;
  billingAccount: { id: string; name: string };
  projects: Project[];
  billingMembers: BillingMember[];
  projectOwners: Record<string, Person[]>;
  folders: { id: string; name: string }[];
  services: string[];
  labels: { key: string; values: string[] }[];
  monitoringChannels: Record<string, { id: string; email: string }[]>;
  pubsubTopics: string[];
  startingBudgets: BudgetConfig[];
  monthlyCosts: Record<string, MonthlyCost[]>;
};

export type ReferenceDefaults = {
  defaultsVersion: string;
  provisional: string[];
  config: BudgetConfig;
};

export type RecipientMechanism = "billing_roles" | "project_owners";
export type Recipient = Person & { via: RecipientMechanism };

export type Criterion =
  | "scope"
  | "period"
  | "amount"
  | "alert"
  | "recipients"
  | "persistence";

export type Evaluation = {
  criteria: Record<Criterion, boolean>;
  overall: boolean;
  people: Recipient[];
  version: string;
};
