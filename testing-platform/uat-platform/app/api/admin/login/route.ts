import { ADMIN_COOKIE, ADMIN_COOKIE_MAX_AGE_S, newAdminCookie, passwordMatches } from "@/lib/admin-auth";

// The login form posts here. A wrong password goes back to the form.
export async function POST(request: Request) {
  const form = await request.formData().catch(() => null);
  const password = form?.get("password");
  const url = new URL(request.url);

  if (typeof password !== "string" || !passwordMatches(password)) {
    return Response.redirect(new URL("/admin/login?error=1", url), 303);
  }

  const response = Response.redirect(new URL("/admin", url), 303);
  const headers = new Headers(response.headers);
  const secure = url.protocol === "https:" ? "; Secure" : "";
  headers.append(
    "Set-Cookie",
    `${ADMIN_COOKIE}=${newAdminCookie(Date.now())}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${ADMIN_COOKIE_MAX_AGE_S}${secure}`,
  );
  return new Response(null, { status: 303, headers });
}
