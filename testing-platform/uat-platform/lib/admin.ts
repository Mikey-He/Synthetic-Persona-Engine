import { cookies } from "next/headers";
import { ADMIN_COOKIE, isAdminCookie } from "@/lib/admin-auth";

// Server only. Every admin page and admin API route checks the cookie itself
// as well, so the console stays closed even if the proxy matcher changes.
export async function isAdmin() {
  const jar = await cookies();
  return isAdminCookie(jar.get(ADMIN_COOKIE)?.value, Date.now());
}

export const unauthorized = () => new Response(null, { status: 401 });
