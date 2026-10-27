import { afterEach, describe, expect, it, vi } from "vitest";
import { buildVersion } from "@/lib/build";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("buildVersion", () => {
  it("prefers BUILD_VERSION, then the first 7 characters of the Vercel commit, then dev", () => {
    vi.stubEnv("VERCEL_GIT_COMMIT_SHA", "0123456789abcdef");
    vi.stubEnv("BUILD_VERSION", "2026.10.02-a");
    expect(buildVersion()).toBe("2026.10.02-a");
    vi.stubEnv("BUILD_VERSION", "");
    expect(buildVersion()).toBe("0123456");
    vi.stubEnv("VERCEL_GIT_COMMIT_SHA", "");
    expect(buildVersion()).toBe("dev");
  });
});
