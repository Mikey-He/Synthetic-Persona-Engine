import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fixtureSchema, referenceDefaultsSchema } from "@/lib/domain/schemas";

// Server only: reads the frozen research files from disk so the hashes cover
// their exact bytes. Client components receive fixture values as props.

const FIXTURE_FILE = path.join(process.cwd(), "lib", "fixtures", "fixture-v1.json");
// defaults-v2 follows the reference capture of 2026-09-30. defaults-v1 stays
// frozen for the sessions that used it.
const DEFAULTS_FILE = path.join(process.cwd(), "lib", "fixtures", "defaults-v2.json");

const sha256 = (bytes: Buffer) => createHash("sha256").update(bytes).digest("hex");

export function loadFixtureFiles() {
  const fixtureBytes = readFileSync(FIXTURE_FILE);
  const defaultsBytes = readFileSync(DEFAULTS_FILE);
  return {
    fixture: fixtureSchema.parse(JSON.parse(fixtureBytes.toString("utf8"))),
    defaults: referenceDefaultsSchema.parse(JSON.parse(defaultsBytes.toString("utf8"))),
    fixtureHash: sha256(fixtureBytes),
    defaultsHash: sha256(defaultsBytes),
  };
}

export const { fixture, defaults, fixtureHash, defaultsHash } = loadFixtureFiles();
