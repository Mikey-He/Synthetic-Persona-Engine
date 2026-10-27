import { NextResponse, type NextRequest } from "next/server";
import { ADMIN_COOKIE, isAdminCookie } from "@/lib/admin-auth";

// Next.js 16 renamed middleware to proxy. This one keeps the researcher
// console behind the password: pages redirect to the login page, the admin
// API answers 401. Admin routes also check the cookie themselves.
export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (pathname === "/admin/login" || pathname === "/api/admin/login") return NextResponse.next();
  if (isAdminCookie(request.cookies.get(ADMIN_COOKIE)?.value, Date.now())) return NextResponse.next();
  if (pathname.startsWith("/api/")) return new NextResponse(null, { status: 401 });
  return NextResponse.redirect(new URL("/admin/login", request.url));
}

export const config = {
  matcher: ["/admin/:path*", "/api/admin/:path*"],
};
