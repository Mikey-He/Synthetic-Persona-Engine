"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Fragment } from "react";
import { breadcrumbsFor } from "@/lib/navigation";

export function Breadcrumbs({ token }: { token: string }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const base = `/s/${token}`;
  const trail = breadcrumbsFor(pathname.slice(base.length), searchParams.has("edit"));

  return (
    <nav aria-label="Breadcrumb" className="mb-4 text-[13px] text-muted">
      {trail.map((crumb, i) => (
        <Fragment key={i}>
          {i > 0 && <span className="mx-1.5">/</span>}
          {crumb.path ? (
            <Link href={`${base}${crumb.path}`} className="hover:underline">
              {crumb.label}
            </Link>
          ) : (
            <span>{crumb.label}</span>
          )}
        </Fragment>
      ))}
    </nav>
  );
}
