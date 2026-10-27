import { z } from "zod";
import type { BudgetConfig, Fixture, ReferenceDefaults } from "./types";

// Strict objects: an unknown key is an error, so a typo in a fixture or a
// stored config fails loudly instead of being ignored.

const person = z.strictObject({ id: z.string(), name: z.string(), email: z.string() });

const configSchemaWith = (percent: z.ZodType<number, unknown>) => z.strictObject({
  name: z.string(),
  kind: z.enum(["alerts_only", "spend_cap"]).nullable(),
  scope: z.strictObject({
    allProjects: z.boolean(),
    projectIds: z.array(z.string()),
    filters: z.strictObject({
      folders: z.array(z.string()),
      services: z.array(z.string()),
      labels: z.array(z.string()),
    }),
    savings: z.array(z.string()),
    readOnlyForProjectUsers: z.boolean(),
  }),
  period: z.enum(["monthly", "quarterly", "yearly", "custom"]),
  customRange: z.strictObject({ from: z.string(), to: z.string().optional() }).optional(),
  amount: z.strictObject({
    type: z.enum(["specified", "last_period"]),
    target: z.number().optional(),
  }),
  thresholds: z.array(z.strictObject({ percent, trigger: z.enum(["actual", "forecasted"]) })),
  recipients: z.strictObject({
    billingAdminsAndUsers: z.boolean(),
    projectOwners: z.boolean(),
    monitoring: z.strictObject({
      linked: z.boolean(),
      projectId: z.string().optional(),
      channelIds: z.array(z.string()),
    }),
    pubsubTopic: z.string().optional(),
  }),
});

// A saved budget always holds finite numbers.
export const budgetConfigSchema: z.ZodType<BudgetConfig> = configSchemaWith(z.number());

// A draft may hold a threshold whose percent text is not a number yet. JSON
// stores that as null, read back as NaN, which never passes validation.
export const draftConfigSchema: z.ZodType<BudgetConfig> = configSchemaWith(
  z
    .number()
    .nullable()
    .transform((value) => value ?? Number.NaN),
);

export const draftBodySchema = z.strictObject({
  config: draftConfigSchema,
  editingBudgetId: z.string().nullable(),
});

export const saveBodySchema = z.strictObject({
  config: budgetConfigSchema,
  editingBudgetId: z.string().nullable(),
});

export const fixtureSchema: z.ZodType<Fixture> = z.strictObject({
  fixtureVersion: z.string(),
  today: z.iso.date(),
  currency: z.string(),
  billingAccount: z.strictObject({ id: z.string(), name: z.string() }),
  projects: z.array(z.strictObject({ id: z.string(), name: z.string() })),
  billingMembers: z.array(
    z.strictObject({
      id: z.string(),
      name: z.string(),
      email: z.string(),
      role: z.string(),
      isYou: z.boolean(),
    }),
  ),
  projectOwners: z.record(z.string(), z.array(person)),
  folders: z.array(z.strictObject({ id: z.string(), name: z.string() })),
  services: z.array(z.string()),
  labels: z.array(z.strictObject({ key: z.string(), values: z.array(z.string()) })),
  monitoringChannels: z.record(
    z.string(),
    z.array(z.strictObject({ id: z.string(), email: z.string() })),
  ),
  pubsubTopics: z.array(z.string()),
  startingBudgets: z.array(budgetConfigSchema),
  monthlyCosts: z.record(
    z.string(),
    z.array(
      z.strictObject({
        month: z.string().regex(/^\d{4}-\d{2}$/),
        usd: z.number(),
        partial: z.boolean().optional(),
      }),
    ),
  ),
});

export const referenceDefaultsSchema: z.ZodType<ReferenceDefaults> = z.strictObject({
  defaultsVersion: z.string(),
  provisional: z.array(z.string()),
  config: budgetConfigSchema,
});
