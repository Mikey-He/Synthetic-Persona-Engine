import { db } from "@/lib/db";
import { createSession } from "@/lib/session";

// Each test runs on a session of its own, created the same way the seed script
// and the researcher console create them.

export function newHumanSession(variant: "A" | "B" = "A") {
  return createSession({ actorType: "human", variant, datasetLabel: "pilot", familiarityBand: "low" });
}

export function newSyntheticSession() {
  return createSession({
    actorType: "synthetic",
    variant: "A",
    agentRun: { modelId: "test-model", promptVersion: "test", personaId: "test" },
  });
}

export async function eventsOf(sessionId: string) {
  return db.event.findMany({ where: { sessionId }, orderBy: { seq: "asc" } });
}
