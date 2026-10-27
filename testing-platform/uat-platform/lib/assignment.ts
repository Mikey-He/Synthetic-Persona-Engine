import { randomInt } from "node:crypto";
import type { FamiliarityBand, Variant } from "@/generated/prisma/client";
import { db } from "@/lib/db";

// Server only. Main-study human sessions get their variant in blocks of two
// within each familiarity band, in random order (guide Part 11): the first
// session of a block gets A or B at random, the second gets the other.
export async function nextEvaluationVariant(band: FamiliarityBand): Promise<Variant> {
  const earlier = await db.session.findMany({
    where: {
      actorType: "human",
      datasetLabel: { in: ["evaluation_A", "evaluation_B"] },
      participant: { familiarityBand: band },
    },
    orderBy: { createdAt: "asc" },
    select: { variant: true },
  });
  const last = earlier.at(-1);
  if (earlier.length % 2 === 1 && last) return last.variant === "A" ? "B" : "A";
  return randomInt(2) === 0 ? "A" : "B";
}
