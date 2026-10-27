import { notFound } from "next/navigation";
import { ReferenceCreateForm } from "@/components/advanced-form/ReferenceCreateForm";
import { GuidedSetup } from "@/components/guided-setup/GuidedSetup";
import { getBudget, getDraft, type Draft } from "@/lib/budgets";
import { defaults, fixture } from "@/lib/fixtures";
import { getParticipantSession, readVariant } from "@/lib/session";

type Props = {
  params: Promise<{ token: string }>;
  searchParams: Promise<{ edit?: string | string[] }>;
};

export default async function CreateBudgetPage({ params, searchParams }: Props) {
  const { token } = await params;
  const { edit } = await searchParams;
  const session = await getParticipantSession(token);
  if (!session) notFound();

  // A budget name on the list opens this page with ?edit=<id> (Edit Budget).
  // A draft already editing that budget wins, so changes survive a reload.
  // Create Budget resumes only a draft of a new budget.
  const draft = await getDraft(session.id);
  let start: Draft;
  let savedName: string | undefined;
  if (typeof edit === "string") {
    const budget = await getBudget(session.id, edit);
    if (!budget) notFound();
    savedName = budget.config.name;
    start = draft?.editingBudgetId === edit ? draft : { config: budget.config, editingBudgetId: budget.id };
  } else {
    start = draft && draft.editingBudgetId === null ? draft : { config: defaults.config, editingBudgetId: null };
  }

  const data = {
    currency: fixture.currency,
    today: fixture.today,
    projects: fixture.projects,
    folders: fixture.folders,
    services: fixture.services,
    labels: fixture.labels,
    monthlyCosts: fixture.monthlyCosts,
  };

  // The only place in the codebase that reads the variant.
  switch (await readVariant(session.id)) {
    case "A":
      return (
        <ReferenceCreateForm
          key={crypto.randomUUID()} // a fresh form, loaded from the server, on every visit
          token={token}
          mode={savedName === undefined ? "create" : "edit"}
          savedName={savedName}
          data={data}
          initialConfig={start.config}
          editingBudgetId={start.editingBudgetId}
        />
      );
    case "B":
      // A saved budget opened from the list lands on the review screen.
      return (
        <GuidedSetup
          key={crypto.randomUUID()}
          token={token}
          data={{
            ...data,
            billingAccount: fixture.billingAccount,
            billingMembers: fixture.billingMembers,
            projectOwners: fixture.projectOwners,
          }}
          initialConfig={start.config}
          editingBudgetId={start.editingBudgetId}
        />
      );
  }
}
