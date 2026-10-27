// The build version recorded on every session and every export: BUILD_VERSION
// when set, else the first 7 characters of the Vercel commit, else "dev".
export const buildVersion = () =>
  process.env.BUILD_VERSION || process.env.VERCEL_GIT_COMMIT_SHA?.slice(0, 7) || "dev";
