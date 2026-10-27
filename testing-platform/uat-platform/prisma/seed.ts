import { config } from "dotenv";

config({ quiet: true });

// Creates one pilot human session for development and prints its link.
// Run it against production only when asked (see docs/DEPLOY.md).
async function main() {
  const { createSession } = await import("../lib/session");
  const { db } = await import("../lib/db");
  const session = await createSession({
    actorType: "human",
    variant: "A",
    datasetLabel: "pilot",
    familiarityBand: "medium",
  });
  const base = process.env.SEED_BASE_URL ?? "http://localhost:3000";
  console.log(`Pilot human session: ${base}/s/${session.token}`);
  await db.$disconnect();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
