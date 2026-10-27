import { expect, type Page } from "@playwright/test";

// Drives the guided setup the way a participant does: by clicking and typing
// at 1440 x 900, one screen at a time.

type Rule = { percent: string; spend?: "already spent" | "expected" };

export class GuidedFlow {
  constructor(
    readonly page: Page,
    readonly token: string,
  ) {}

  async open() {
    await this.page.goto(`/s/${this.token}/billing/budgets`);
    await this.page.getByRole("link", { name: "Create new" }).click();
    await this.expectScreen("What should this budget be called?");
  }

  async expectScreen(question: string) {
    await expect(this.page.getByRole("heading", { level: 1, name: question })).toBeVisible();
  }

  get main() {
    return this.page.locator("main");
  }

  get continueButton() {
    return this.page.getByRole("button", { name: /^(Continue to \w+|Back to review)$/ });
  }

  async next() {
    await this.continueButton.click();
  }

  async back() {
    await this.page.getByRole("button", { name: "Back", exact: true }).click();
  }

  get nameField() {
    return this.page.getByLabel("Budget name");
  }

  get amountField() {
    return this.page.getByLabel("Amount in dollars");
  }

  get percentFields() {
    return this.page.getByRole("textbox", { name: /^Percent \d+$/ });
  }

  get billingAdmins() {
    return this.page.getByRole("checkbox", { name: "Billing account admins and users" });
  }

  get projectOwners() {
    return this.page.getByRole("checkbox", { name: "Project owners" });
  }

  async chooseProjects(names: Array<"Atlas" | "Beacon">) {
    await this.page.getByRole("radio", { name: "Only specific projects" }).check();
    for (const name of ["Atlas", "Beacon"] as const) {
      const box = this.page.getByRole("checkbox", { name: new RegExp(`^${name} · `) });
      if ((await box.isChecked()) !== names.includes(name)) await box.click();
    }
  }

  // Replaces every rule through Remove rule and Add another rule.
  async setRules(rules: Rule[]) {
    const removes = this.page.getByRole("button", { name: /^Remove rule/ });
    while ((await removes.count()) > 0) await removes.first().click();
    for (const [i, rule] of rules.entries()) {
      await this.page.getByRole("button", { name: "Add another rule" }).click();
      await this.percentFields.nth(i).fill(rule.percent);
      if (rule.spend === "expected") {
        await this.page.getByRole("button", { name: new RegExp(`^Spend type ${i + 1}`) }).click();
        await this.page.getByRole("option", { name: "money expected by the end of the period" }).click();
      }
    }
  }

  // Name, Atlas only, monthly, $1,000, one rule at 80% of money already spent,
  // project owners only.
  async enterAtlasBudget() {
    await this.nameField.fill("Atlas monthly");
    await this.next();
    await this.chooseProjects(["Atlas"]);
    await this.next();
    await this.next(); // Monthly stays
    await this.amountField.fill("1000");
    await this.next();
    await this.setRules([{ percent: "80" }]);
    await this.next();
    await this.billingAdmins.uncheck();
    await this.projectOwners.check();
    await this.next();
    await this.expectScreen("Here is your budget");
  }

  async create() {
    await this.page.getByRole("button", { name: "Create budget", exact: true }).click();
    await expect(this.page).toHaveURL(/\/billing\/budgets$/);
  }
}
