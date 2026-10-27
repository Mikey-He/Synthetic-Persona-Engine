"use client";

import { useId, useState } from "react";
import { THANK_YOU } from "@/lib/survey";

const SCALE = [1, 2, 3, 4, 5, 6, 7];

// Post-task question for humans. Provisional until the team picks the
// instrument (guide Part 13).
export function SurveyForm({ token }: { token: string }) {
  const questionId = useId();
  const [ease, setEase] = useState<number | null>(null);
  const [sending, setSending] = useState(false);
  const [done, setDone] = useState(false);

  async function submit() {
    if (ease === null) return;
    setSending(true);
    const response = await fetch(`/api/s/${token}/survey`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ ease }),
    }).catch(() => null);
    setSending(false);
    if (response?.ok || response?.status === 409) setDone(true);
  }

  if (done) return <p>{THANK_YOU}</p>;

  return (
    <fieldset>
      <legend id={questionId} className="text-[16px] leading-6">
        Overall, how easy or difficult was this task?
      </legend>
      <div className="mt-6 flex items-end gap-4">
        <span className="pb-1 text-muted">Very difficult</span>
        {SCALE.map((value) => (
          <label key={value} className="flex cursor-pointer flex-col items-center gap-1">
            <span>{value}</span>
            <input
              type="radio"
              name={questionId}
              className="size-5"
              checked={ease === value}
              onChange={() => setEase(value)}
            />
          </label>
        ))}
        <span className="pb-1 text-muted">Very easy</span>
      </div>
      <button
        type="button"
        className="btn-primary mt-8"
        disabled={ease === null || sending}
        onClick={submit}
      >
        Submit
      </button>
    </fieldset>
  );
}
