import { execSync } from "node:child_process";
import { defaultsHash, fixtureHash } from "../lib/fixtures";

// Prints what identifies a frozen pilot build. Tag the commit afterwards.
const git = (command: string) => execSync(`git ${command}`, { encoding: "utf8" }).trim();

const commit = git("rev-parse HEAD");
const dirty = git("status --porcelain") !== "";

console.log(`Commit        ${commit}${dirty ? "  (the working tree has uncommitted changes)" : ""}`);
console.log(`Fixture hash  ${fixtureHash}`);
console.log(`Defaults hash ${defaultsHash}`);
console.log("");
console.log("Create a git tag for this build, for example:");
console.log(`  git tag -a pilot-a-v1 ${commit.slice(0, 7)} -m "Pilot A build"`);
console.log("  git push origin pilot-a-v1");
