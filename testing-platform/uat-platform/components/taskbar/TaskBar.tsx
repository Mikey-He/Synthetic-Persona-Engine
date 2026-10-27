"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { TASK_TEXT } from "@/lib/domain/task";
import { useLogger } from "@/lib/events/EventLoggerProvider";

// Fixed height so screenshots line up across sessions. The whole task stays
// visible at all times (guide Part 3), so the bar cannot be collapsed.
export const TASK_BAR_HEIGHT = 136;

const PARAGRAPHS = TASK_TEXT.split("\n\n");

export function TaskBar({ token }: { token: string }) {
  const router = useRouter();
  const logger = useLogger();
  const [finishing, setFinishing] = useState(false);

  // I'm finished ends the attempt for both actor types, saved or not. The last
  // events travel with the request that records the end of the session.
  async function finish() {
    if (finishing) return;
    setFinishing(true);
    logger?.log("completion_declared", "I'm finished");
    logger?.log("session_ended", null, { terminationReason: "completion_declared" });
    logger?.stop();
    await logger?.settle();
    await fetch(`/api/s/${token}/complete`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ events: logger?.drain() ?? [] }),
    }).catch(() => undefined);
    router.push(`/s/${token}/done`);
  }

  return (
    <div
      data-kl-harness=""
      className="fixed inset-x-0 top-0 z-40 flex items-start gap-4 overflow-hidden border-b border-note-line bg-note px-6 py-3"
      style={{ height: TASK_BAR_HEIGHT }}
    >
      <div className="min-w-0 flex-1 space-y-2">
        {PARAGRAPHS.map((paragraph) => (
          <p key={paragraph}>{paragraph}</p>
        ))}
      </div>
      <button type="button" className="btn-primary -my-2 shrink-0" disabled={finishing} onClick={finish}>
        I&apos;m finished
      </button>
    </div>
  );
}
