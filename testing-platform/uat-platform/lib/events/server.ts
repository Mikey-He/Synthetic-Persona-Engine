import { z } from "zod";
import type { Prisma } from "@/generated/prisma/client";
import { EVENT_TYPES } from "./types";

// Server only. Events are append only: rows are inserted, never updated or deleted.

export const eventBatchSchema = z.strictObject({
  events: z
    .array(
      z.strictObject({
        seq: z.number().int().positive(),
        clientTs: z.iso.datetime(),
        type: z.enum(EVENT_TYPES),
        target: z.string().max(500).nullable(),
        payload: z.unknown(),
      }),
    )
    .max(1000),
});

export type EventBatch = z.infer<typeof eventBatchSchema>;

const sessionStartedPayload = z.object({
  viewport: z.object({ width: z.number(), height: z.number() }),
  zoom: z.number(),
});

// Stores a batch with the server's own timestamp. The first session_started
// also records when the session started and at what viewport and zoom.
export async function insertEvents(
  tx: Prisma.TransactionClient,
  sessionId: string,
  events: EventBatch["events"],
) {
  if (events.length === 0) return;
  await tx.event.createMany({
    data: events.map((event) => ({
      sessionId,
      seq: event.seq,
      clientTs: new Date(event.clientTs),
      type: event.type,
      target: event.target,
      payload: (event.payload ?? undefined) as Prisma.InputJsonValue | undefined,
    })),
  });

  const started = events.find((event) => event.type === "session_started");
  const details = started && sessionStartedPayload.safeParse(started.payload);
  if (details?.success) {
    await tx.session.updateMany({
      where: { id: sessionId, startedAt: null },
      data: { startedAt: new Date(), viewport: details.data.viewport, zoom: details.data.zoom },
    });
  }
}
