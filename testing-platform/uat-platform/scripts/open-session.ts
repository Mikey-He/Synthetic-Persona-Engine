import { spawn, spawnSync, type ChildProcess } from "node:child_process";
import { existsSync } from "node:fs";
import { config } from "dotenv";

config({ quiet: true });

// npm run open:a / npm run open:b
//
// Opens a fresh local test session of version A or B in the browser:
//   1. starts the local Docker database if it is not running;
//   2. starts the dev server if nothing answers on the port;
//   3. creates a pilot human session with the chosen variant;
//   4. opens its link in a study window: a Chromium window whose page is
//      exactly 1440 x 900 at scale factor 1, the same as the engine's
//      screenshots, whatever the computer's display scaling (guide Part 8).
//      Add --system-browser to open the default browser instead.
// The variant is chosen here because it never appears in a participant URL.
// Local development only: it refuses to run against a remote database.

const PORT = Number(process.env.PORT ?? 3000);
const STUDY_VIEWPORT = { width: 1440, height: 900 };
const BASE = `http://localhost:${PORT}`;
const CONTAINER = "uat-platform-db";
const DOCKER_DESKTOP = "C:\\Program Files\\Docker\\Docker\\Docker Desktop.exe";

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

async function until(what: string, seconds: number, check: () => Promise<boolean> | boolean) {
  for (let waited = 0; waited < seconds; waited += 2) {
    if (await check()) return;
    await sleep(2000);
  }
  throw new Error(`Gave up waiting for ${what} after ${seconds} seconds.`);
}

function assertLocalDatabase() {
  const url = process.env.DATABASE_URL ?? "";
  const host = url.match(/@([^:/?]+)/)?.[1] ?? "";
  if (!["localhost", "127.0.0.1", "::1"].includes(host)) {
    throw new Error("DATABASE_URL does not point at a local database. This script is for local testing only.");
  }
}

const docker = (...args: string[]) => spawnSync("docker", args, { stdio: "ignore" }).status === 0;

async function ensureDatabase(ping: () => Promise<boolean>) {
  if (await ping()) return;
  if (!docker("info")) {
    if (process.platform === "win32" && existsSync(DOCKER_DESKTOP)) {
      console.log("Starting Docker Desktop…");
      spawn(DOCKER_DESKTOP, [], { detached: true, stdio: "ignore" }).unref();
    } else {
      throw new Error("Docker is not running. Start Docker, then run this again.");
    }
    await until("Docker", 180, () => docker("info"));
  }
  console.log(`Starting the ${CONTAINER} database container…`);
  if (!docker("start", CONTAINER)) throw new Error(`Could not start the ${CONTAINER} container.`);
  await until("the database", 60, ping);
}

const serverUp = async () => {
  try {
    return (await fetch(`${BASE}/api/health`)).ok;
  } catch {
    return false;
  }
};

function openInBrowser(url: string) {
  const [command, args] =
    process.platform === "win32"
      ? ["cmd", ["/c", "start", "", url]]
      : process.platform === "darwin"
        ? ["open", [url]]
        : ["xdg-open", [url]];
  spawn(command, args, { detached: true, stdio: "ignore" }).unref();
}

// A fresh profile each time, so no cookies or zoom carry over between sessions.
// Resolves when the window is closed.
async function openStudyWindow(url: string) {
  const { chromium } = await import("@playwright/test");
  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext({ viewport: STUDY_VIEWPORT, deviceScaleFactor: 1 });
  const page = await context.newPage();
  const closed = new Promise<void>((resolve) => browser.on("disconnected", () => resolve()));
  page.on("close", () => void browser.close());
  await page.goto(url);
  return closed;
}

async function main() {
  const variant = process.argv[2]?.toUpperCase();
  if (variant !== "A" && variant !== "B") {
    console.error("Usage: npm run open:a  or  npm run open:b");
    process.exit(2);
  }
  assertLocalDatabase();

  const { db } = await import("../lib/db");
  const { createSession } = await import("../lib/session");
  const ping = () =>
    db.$queryRaw`SELECT 1`.then(
      () => true,
      () => false,
    );

  await ensureDatabase(ping);

  let server: ChildProcess | null = null;
  if (!(await serverUp())) {
    console.log(`Starting the dev server on ${BASE}…`);
    // One command string: npx is a .cmd file on Windows, which needs a shell.
    server = spawn(`npx next dev --port ${PORT}`, { stdio: "inherit", shell: true });
    server.on("exit", (code) => process.exit(code ?? 0));
    await until("the dev server", 120, serverUp);
  }

  const session = await createSession({ actorType: "human", variant, datasetLabel: "pilot", familiarityBand: "medium" });
  await db.$disconnect();
  const link = `${BASE}/s/${session.token}`;
  // Load the page once so the first visit in the browser is not a cold compile.
  await fetch(link).catch(() => undefined);

  console.log("");
  console.log(`Version ${variant} test session: ${link}`);
  // The id is what the researcher console and the engine's comparison (sue.compare) use.
  console.log(`Session id: ${session.id}`);
  if (process.argv.includes("--system-browser")) {
    openInBrowser(link);
    console.log("Use the browser in full screen at 100% zoom (at least 1440 x 900).");
  } else {
    console.log("Opening a study window at 1440 x 900. Close the window when the session is over.");
    await openStudyWindow(link);
    console.log("Study window closed.");
  }
  if (server) console.log("The dev server keeps running here. Press Ctrl+C to stop it.");
}

main().catch((error: Error) => {
  console.error(error.message);
  process.exit(1);
});
