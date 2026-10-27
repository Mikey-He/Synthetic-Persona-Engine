import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Keep `next dev` from appending its own block to CLAUDE.md.
  agentRules: false,
  // No dev-only button on screen, so local screenshots match what participants see.
  devIndicators: false,
  // The fixture files are read from disk at run time (their hashes cover the
  // exact bytes), so every server function must ship with them.
  outputFileTracingIncludes: {
    "/*": ["./lib/fixtures/*.json"],
  },
};

export default nextConfig;
