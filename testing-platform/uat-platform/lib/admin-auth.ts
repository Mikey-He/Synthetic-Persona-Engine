import { createHash, createHmac, timingSafeEqual } from "node:crypto";

// The researcher console is behind ADMIN_PASSWORD. Signing in sets an
// HTTP-only cookie holding the time it was issued and an HMAC of that time,
// keyed by the password, so rotating the password signs everyone out.

export const ADMIN_COOKIE = "uat_admin";
export const ADMIN_COOKIE_MAX_AGE_S = 12 * 60 * 60;

function sign(issuedAt: string, secret: string) {
  return createHmac("sha256", secret).update(`admin:${issuedAt}`).digest("base64url");
}

export function passwordMatches(input: string) {
  const secret = process.env.ADMIN_PASSWORD;
  if (!secret) return false;
  // Compare digests, so the comparison takes the same time whatever was typed.
  const typed = createHash("sha256").update(input).digest();
  const expected = createHash("sha256").update(secret).digest();
  return timingSafeEqual(typed, expected);
}

export function newAdminCookie(now: number) {
  const secret = process.env.ADMIN_PASSWORD;
  if (!secret) throw new Error("ADMIN_PASSWORD is not set.");
  const issuedAt = String(now);
  return `${issuedAt}.${sign(issuedAt, secret)}`;
}

export function isAdminCookie(value: string | undefined, now: number) {
  const secret = process.env.ADMIN_PASSWORD;
  if (!value || !secret) return false;
  const [issuedAt, mac] = value.split(".");
  if (!issuedAt || !mac) return false;
  const age = now - Number(issuedAt);
  if (!(age >= 0 && age < ADMIN_COOKIE_MAX_AGE_S * 1000)) return false;
  const expected = Buffer.from(sign(issuedAt, secret));
  const given = Buffer.from(mac);
  return expected.length === given.length && timingSafeEqual(expected, given);
}
