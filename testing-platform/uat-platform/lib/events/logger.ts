import type { ClientEvent, EventType, Setting } from "./types";

// Client side. One logger per open participant page, shared across in-app
// navigation. Each event gets a per-session sequence number and a client
// timestamp; batches go to the server every 2 seconds and through
// navigator.sendBeacon when the page is hidden.

const FLUSH_MS = 2000;

function readStored<T>(key: string): T | null {
  try {
    const raw = window.sessionStorage.getItem(key);
    return raw === null ? null : (JSON.parse(raw) as T);
  } catch {
    return null;
  }
}

function writeStored(key: string, value: unknown) {
  try {
    window.sessionStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Storage can be unavailable. The server's last seq still seeds the next page.
  }
}

export class EventLogger {
  route: string | null = null; // the participant route on screen, without /s/<token>; set by pageViewed
  private seq: number;
  private queue: ClientEvent[] = [];
  private stopped = false;
  private timer: ReturnType<typeof setInterval> | null = null;
  private inFlight: Promise<void> = Promise.resolve();
  private readonly url: string;
  // Settings that were reached and then left the viewport, and those among
  // them that saw a different setting arrive since. See settingEntered.
  private readonly leftSettings = new Set<Setting>();
  private readonly returnable = new Set<Setting>();

  constructor(
    private readonly token: string,
    lastSeq: number,
  ) {
    this.url = `/api/s/${token}/events`;
    this.seq = Math.max(lastSeq, readStored<number>(`uat:seq:${token}`) ?? 0);
  }

  log(type: EventType, target: string | null = null, payload: unknown = null) {
    if (this.stopped) return;
    this.seq += 1;
    writeStored(`uat:seq:${this.token}`, this.seq);
    this.queue.push({ seq: this.seq, clientTs: new Date().toISOString(), type, target, payload });
  }

  // page_viewed carries the route and the in-app route it came from.
  pageViewed(route: string) {
    if (route === this.route) return; // same page, rendered again
    this.log("page_viewed", route, { route, referrer: this.route });
    this.route = route;
  }

  // True only the first time this session sees kind:id, even across reloads.
  firstTime(kind: string, id: string) {
    const key = `uat:${kind}:${this.token}`;
    const seen = new Set(readStored<string[]>(key) ?? []);
    if (seen.has(id)) return false;
    seen.add(id);
    writeStored(key, [...seen]);
    return true;
  }

  // setting_reached fires the first time a setting's control enters the
  // viewport. setting_returned fires when a setting enters again after it had
  // left and a different setting arrived in the meantime.
  settingEntered(setting: Setting, value: unknown, route: string) {
    for (const other of this.leftSettings) if (other !== setting) this.returnable.add(other);
    if (this.firstTime("reached", setting)) this.log("setting_reached", setting, { setting, value });
    else if (this.returnable.has(setting)) this.log("setting_returned", setting, { setting, route });
    this.leftSettings.delete(setting);
    this.returnable.delete(setting);
  }

  settingLeft(setting: Setting) {
    this.leftSettings.add(setting);
    this.returnable.delete(setting);
  }

  start() {
    if (this.timer !== null || this.stopped) return;
    this.timer = setInterval(() => void this.flush(), FLUSH_MS);
    document.addEventListener("visibilitychange", this.onVisibilityChange);
    window.addEventListener("pagehide", this.beacon);
  }

  dispose() {
    if (this.timer !== null) clearInterval(this.timer);
    this.timer = null;
    document.removeEventListener("visibilitychange", this.onVisibilityChange);
    window.removeEventListener("pagehide", this.beacon);
    this.beacon();
  }

  // Batches are sent one after another, so they reach the server in order.
  flush(): Promise<void> {
    if (this.queue.length === 0) return this.inFlight;
    const batch = this.queue.splice(0);
    this.inFlight = this.inFlight.then(() => this.post(batch));
    return this.inFlight;
  }

  // Waits until every batch already sent has landed.
  settle() {
    return this.inFlight;
  }

  // Hands over every pending event, for a request that carries them itself.
  drain() {
    return this.queue.splice(0);
  }

  // After session_ended nothing more is recorded or sent on the timer.
  stop() {
    this.stopped = true;
    if (this.timer !== null) clearInterval(this.timer);
    this.timer = null;
  }

  private async post(batch: ClientEvent[]) {
    try {
      const response = await fetch(this.url, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ events: batch }),
        keepalive: true,
      });
      if (response.status >= 500) this.queue.unshift(...batch); // retry on the next tick
    } catch {
      this.queue.unshift(...batch);
    }
  }

  private beacon = () => {
    if (this.queue.length === 0) return;
    const body = JSON.stringify({ events: this.queue.splice(0) });
    const sent = navigator.sendBeacon(this.url, new Blob([body], { type: "application/json" }));
    if (!sent) {
      void fetch(this.url, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body,
        keepalive: true,
      }).catch(() => undefined);
    }
  };

  private onVisibilityChange = () => {
    if (document.visibilityState === "hidden") this.beacon();
  };
}
