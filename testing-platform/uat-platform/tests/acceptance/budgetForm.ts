import { expect, type APIRequestContext, type Page } from "@playwright/test";
import type { Recipient } from "@/lib/domain/types";
import { sessionEvaluation } from "@/lib/scoring";

// Drives the version A create form the way a participant does: by clicking
// and typing at 1440 x 900.

type Section = "Define" | "Scope" | "Amount" | "Actions";
type Rule = { percent: string; trigger: "Actual" | "Forecasted" };

export class BudgetForm {
  constructor(
    readonly page: Page,
    readonly token: string,
  ) {}

  async open() {
    await this.page.goto(`/s/${this.token}/billing/budgets`);
    await this.page.getByRole("link", { name: "Create new" }).click();
    await expect(this.page.getByRole("heading", { name: "Create Budget" })).toBeVisible();
  }

  // Edit Budget, from the budget's name on the list.
  async openSaved(name: string) {
    await this.page.goto(`/s/${this.token}/billing/budgets`);
    await this.page.getByRole("link", { name, exact: true }).click();
    await expect(this.page.getByRole("heading", { name: "Edit Budget" })).toBeVisible();
  }

  sectionHeader(section: Section) {
    return this.page.getByRole("button", { name: section, exact: true });
  }

  // Opens a step (Create) or unfolds a section (Edit), and leaves an open one alone.
  async openSection(section: Section) {
    const header = this.sectionHeader(section);
    if ((await header.getAttribute("aria-expanded")) !== "true") await header.click();
  }

  get nameField() {
    return this.page.getByRole("textbox", { name: "Name *" });
  }

  async setName(name: string) {
    await this.openSection("Define");
    await this.nameField.fill(name);
  }

  get projectsDropdown() {
    return this.page.getByRole("button", { name: /^Projects/ });
  }

  // "all" leaves every box unticked, which the console reads as All projects.
  async setProjects(choice: "all" | Array<"Atlas" | "Beacon">) {
    await this.openSection("Scope");
    await this.projectsDropdown.click();
    const wanted = choice === "all" ? [] : choice;
    for (const name of ["Atlas", "Beacon"] as const) {
      const box = this.page.getByRole("checkbox", { name: new RegExp(`^${name}`) });
      if ((await box.isChecked()) !== wanted.includes(name)) await box.click();
    }
    await this.page.getByRole("button", { name: "OK", exact: true }).click();
  }

  get targetField() {
    return this.page.getByRole("textbox", { name: "Target amount *" });
  }

  async setTarget(text: string) {
    await this.openSection("Amount");
    await this.targetField.fill(text);
  }

  get percentFields() {
    return this.page.getByRole("textbox", { name: /^Percent of budget/ });
  }

  // Replaces every threshold rule, through Delete item and Add threshold.
  async setThresholds(rules: Rule[]) {
    await this.openSection("Actions");
    const deletes = this.page.getByRole("button", { name: "Delete item" });
    while ((await deletes.count()) > 0) await deletes.first().click();
    for (const rule of rules) await this.addThreshold(rule);
  }

  async addThreshold(rule: Rule) {
    await this.openSection("Actions");
    await this.page.getByRole("button", { name: "Add threshold" }).click();
    const index = (await this.percentFields.count()) - 1;
    await this.percentFields.nth(index).fill(rule.percent);
    if (rule.trigger === "Forecasted") {
      await this.page.getByRole("button", { name: /^Trigger on/ }).nth(index).click();
      await this.page.getByRole("option", { name: "Forecasted" }).click();
    }
  }

  checkbox(label: RegExp | string) {
    return this.page.getByRole("checkbox", { name: label });
  }

  get billingAdmins() {
    return this.checkbox("Email alerts to billing admins and users");
  }

  get projectOwners() {
    return this.checkbox(/Email alerts to project owners/);
  }

  get monitoring() {
    return this.checkbox("Link Monitoring email notification channels to this budget");
  }

  async setRecipients({ billing, owners }: { billing?: boolean; owners?: boolean }) {
    await this.openSection("Actions");
    if (billing !== undefined) await this.billingAdmins.setChecked(billing);
    if (owners !== undefined) await this.projectOwners.setChecked(owners);
  }

  // Name, Atlas only, monthly (the default), $1,000 and one rule at 80% actual.
  async fillRequired() {
    await this.setName("Atlas monthly");
    await this.setProjects(["Atlas"]);
    await this.setTarget("1000");
    await this.setThresholds([{ percent: "80", trigger: "Actual" }]);
  }

  async finish() {
    await this.page.getByRole("button", { name: "Finish", exact: true }).click();
  }

  async save() {
    await this.page.getByRole("button", { name: "Save", exact: true }).click();
  }

  // A saved budget lands back on the list, as in the console.
  async finishAndExpectSaved() {
    await this.finish();
    await expect(this.page).toHaveURL(/\/billing\/budgets$/);
  }

  async declareCompletion() {
    await this.page.getByRole("button", { name: "I'm finished" }).click();
    await expect(this.page).toHaveURL(/\/done$/);
  }
}

// A fresh session through the researcher console's API, signed in with the
// console password.
export async function newSessionThroughAdmin(request: APIRequestContext) {
  const login = await request.post("/api/admin/login", {
    form: { password: process.env.ADMIN_PASSWORD ?? "" },
    maxRedirects: 0,
  });
  expect(login.status()).toBe(303);
  expect(login.headers().location).toMatch(/\/admin$/);
  const created = await request.post("/api/admin/sessions", {
    data: { actorType: "human", familiarityBand: "medium", datasetLabel: "pilot" },
  });
  expect(created.status()).toBe(201);
  return (await created.json()) as { id: string; token: string; link: string };
}

// The stored evaluation of the budget that scoring rule v1 picks.
export async function storedEvaluation(sessionId: string) {
  const { scored, evaluation } = await sessionEvaluation(sessionId);
  expect(evaluation, "a stored evaluation").not.toBeNull();
  return {
    saved: scored.saved,
    overall: evaluation!.overallSuccess,
    criteria: evaluation!.criteria as Record<string, boolean>,
    people: (evaluation!.resolvedRecipients as Recipient[]).map((person) => person.id).sort(),
  };
}
