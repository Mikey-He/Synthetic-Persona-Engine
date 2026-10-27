import type { Setting } from "@/lib/events/types";

// Pure per-session measures for sessions.csv, computed from the event log.

type LoggedEvent = { type: string; clientTs: Date; payload: unknown };

const settingOf = (payload: unknown) =>
  typeof payload === "object" && payload !== null && "setting" in payload
    ? ((payload as { setting: unknown }).setting as Setting | null)
    : null;

export type TimedSetting = "scope" | "period" | "amount" | "alert" | "recipients";
const TIMED: TimedSetting[] = ["scope", "period", "amount", "alert", "recipients"];

/*
 * time_<setting>_ms, on the participant's clock:
 *
 *   client_ts of the last field_changed for the setting
 *   minus client_ts of its setting_reached
 *
 * 0 when the setting was reached but never changed, empty (null) when it was
 * never reached, and never below 0.
 */
export function settingTimes(events: LoggedEvent[]): Record<TimedSetting, number | null> {
  const reachedAt = new Map<Setting, number>();
  const lastChangeAt = new Map<Setting, number>();
  for (const event of events) {
    const setting = settingOf(event.payload);
    if (!setting) continue;
    const at = event.clientTs.getTime();
    if (event.type === "setting_reached" && !reachedAt.has(setting)) reachedAt.set(setting, at);
    if (event.type === "field_changed") lastChangeAt.set(setting, at);
  }
  const times = {} as Record<TimedSetting, number | null>;
  for (const setting of TIMED) {
    const reached = reachedAt.get(setting);
    const changed = lastChangeAt.get(setting);
    times[setting] = reached === undefined ? null : Math.max(0, (changed ?? reached) - reached);
  }
  return times;
}

export const countOf = (events: LoggedEvent[], type: string) =>
  events.filter((event) => event.type === type).length;
