import { nanoid } from "nanoid";
import type { DatasetLabel, FamiliarityBand, Prisma, TerminationReason, Variant } from "@/generated/prisma/client";
import { buildVersion } from "@/lib/build";
import { db } from "@/lib/db";
import { TASK_VERSION } from "@/lib/domain/task";
import { EVALUATOR_VERSION } from "@/lib/evaluator/evaluate";
import { defaults, defaultsHash, fixture, fixtureHash } from "@/lib/fixtures";
import { scoreEndedSession } from "@/lib/scoring";

// Server only. A session is one attempt by one actor, human or synthetic.

export async function getParticipantSession(token: string) {
  return db.session.findUnique({
    where: { token },
    // The variant is deliberately not selected here. See readVariant.
    select: { id: true, token: true, actorType: true, startedAt: true, endedAt: true },
  });
}

export type ParticipantSession = NonNullable<Awaited<ReturnType<typeof getParticipantSession>>>;

// Only the create route may call this: it holds the single switch on variant.
export async function readVariant(sessionId: string): Promise<Variant> {
  const session = await db.session.findUniqueOrThrow({ where: { id: sessionId }, select: { variant: true } });
  return session.variant;
}

export async function lastEventSeq(sessionId: string) {
  const result = await db.event.aggregate({ where: { sessionId }, _max: { seq: true } });
  return result._max.seq ?? 0;
}

// Freezes the fixture and defaults files in the database the first time, and
// refuses to go on if a frozen file has changed since.
export async function ensureFixtureVersions() {
  const files = [
    { id: fixture.fixtureVersion, content: fixture, hash: fixtureHash },
    { id: defaults.defaultsVersion, content: defaults, hash: defaultsHash },
  ];
  for (const file of files) {
    const row = await db.fixtureVersion.upsert({
      where: { id: file.id },
      create: { id: file.id, content: file.content as Prisma.InputJsonValue, contentHash: file.hash },
      update: {},
    });
    if (row.contentHash !== file.hash) {
      throw new Error(`${file.id} changed after it was frozen. Add a new version file instead.`);
    }
  }
}

export type NewSession =
  | {
      actorType: "human";
      variant: Variant;
      datasetLabel: Exclude<DatasetLabel, "synthetic">;
      familiarityBand: FamiliarityBand;
    }
  | {
      actorType: "synthetic";
      variant: Variant;
      agentRun: {
        modelId: string;
        promptVersion: string;
        personaId: string;
        calibrationId?: string | null;
        temperature?: number | null;
      };
    };

export async function createSession(input: NewSession) {
  await ensureFixtureVersions();
  const base = {
    token: nanoid(), // 21 random URL-safe characters, independent of the variant
    variant: input.variant,
    fixture: { connect: { id: fixture.fixtureVersion } },
    defaults: { connect: { id: defaults.defaultsVersion } },
    taskVersion: TASK_VERSION,
    buildVersion: buildVersion(),
    evaluatorVersion: EVALUATOR_VERSION,
  };
  if (input.actorType === "human") {
    return db.session.create({
      data: {
        ...base,
        actorType: "human",
        datasetLabel: input.datasetLabel,
        // Pseudonymous: a random id and a familiarity band, never a name or an email.
        participant: { create: { id: nanoid(), familiarityBand: input.familiarityBand } },
      },
    });
  }
  return db.session.create({
    data: { ...base, actorType: "synthetic", datasetLabel: "synthetic", agentRun: { create: input.agentRun } },
  });
}

// Termination reasons the research side can record. completion_declared only
// ever comes from the participant's own I'm finished.
export type EndReason = Exclude<TerminationReason, "completion_declared">;

// The researcher ends a session the participant left (abandoned), or the agent
// runner ends a synthetic session by one of its stop rules. The server writes
// the session_ended event itself, numbered after the last event the session sent.
export async function abandonSession(sessionId: string) {
  return endSessionAs(sessionId, "abandoned", "researcher");
}

export async function endSessionAs(sessionId: string, reason: EndReason, endedBy: "researcher" | "agent_runner") {
  return db.$transaction(async (tx) => {
    const session = await tx.session.findUniqueOrThrow({ where: { id: sessionId } });
    if (session.endedAt) return false;
    const now = new Date();
    const last = await tx.event.aggregate({ where: { sessionId }, _max: { seq: true } });
    await tx.event.create({
      data: {
        sessionId,
        seq: (last._max.seq ?? 0) + 1,
        clientTs: now,
        type: "session_ended",
        payload: { terminationReason: reason, endedBy },
      },
    });
    await tx.session.update({ where: { id: sessionId }, data: { endedAt: now, terminationReason: reason } });
    await scoreEndedSession(tx, sessionId);
    return true;
  });
}
