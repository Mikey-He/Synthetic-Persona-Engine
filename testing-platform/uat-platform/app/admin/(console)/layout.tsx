import Link from "next/link";
import { redirect } from "next/navigation";
import { connection } from "next/server";
import type { ReactNode } from "react";
import { isAdmin } from "@/lib/admin";

const NAV = [
  { href: "/admin", label: "Sessions" },
  { href: "/admin/sessions/new-human", label: "New human session" },
  { href: "/admin/sessions/new-synthetic", label: "New synthetic session" },
  { href: "/admin/assignment", label: "Assignment" },
  { href: "/admin/exports", label: "Exports" },
];

export default async function ConsoleLayout({ children }: { children: ReactNode }) {
  await connection();
  if (!(await isAdmin())) redirect("/admin/login");

  return (
    <>
      <header className="flex h-12 items-center gap-6 border-b border-line px-8">
        <span className="text-[18px] text-muted">Researcher console</span>
        <nav className="flex gap-5">
          {NAV.map((item) => (
            <Link key={item.href} href={item.href} className="link">
              {item.label}
            </Link>
          ))}
        </nav>
      </header>
      <main className="px-8 py-6">{children}</main>
    </>
  );
}
