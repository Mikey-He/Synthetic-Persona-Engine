// Researcher console formatting. The console may show real times; only
// participant pages are limited to fixture dates.

export const formatTime = (date: Date | null) =>
  date ? `${date.toISOString().replace("T", " ").slice(0, 19)} UTC` : "—";

export const statusOf = (session: { startedAt: Date | null; endedAt: Date | null }) =>
  session.endedAt ? "Ended" : session.startedAt ? "In progress" : "Not started";

export const passFail = (value: boolean | undefined) =>
  value === undefined ? "—" : value ? "Pass" : "Fail";

// "+01:02.345" since the first event, on the participant's clock.
export function sinceStart(ms: number) {
  const minutes = Math.floor(ms / 60000);
  const seconds = ((ms % 60000) / 1000).toFixed(3).padStart(6, "0");
  return `+${String(minutes).padStart(2, "0")}:${seconds}`;
}
