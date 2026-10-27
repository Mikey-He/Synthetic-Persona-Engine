"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { NAV_GROUPS } from "@/lib/navigation";
import { Select } from "./Dropdown";

type Props = { token: string; accountName: string; stickyTop: number };

// The billing navigation of the reference capture: a Billing header, the
// billing account picker (this fixture has one account), then the groups.
export function LeftNav({ token, accountName, stickyTop }: Props) {
  const pathname = usePathname();
  const base = `/s/${token}`;
  const route = pathname.slice(base.length);
  const isActive = (path: string) =>
    path === "/billing" ? route === path : route === path || route.startsWith(`${path}/`);

  return (
    <nav
      aria-label="Billing"
      className="sticky w-64 shrink-0 self-start overflow-y-auto border-r border-line pb-4"
      style={{ top: stickyTop, height: `calc(100vh - ${stickyTop}px)` }}
    >
      <div data-kl="T06" className="px-6 pb-2 pt-4 text-[18px] leading-6">
        Billing
      </div>
      <div className="px-4 pb-2">
        <Select
          label="Billing account"
          value="account"
          options={[{ value: "account", label: accountName }]}
          onChange={() => undefined}
          className="w-full"
          kl="T07"
        />
      </div>
      {NAV_GROUPS.map((group) => (
        <div key={group.heading ?? "top"} className="pt-2">
          {group.heading && (
            <div className="px-6 pb-1 pt-2 text-[12px] font-medium uppercase tracking-wide text-muted">
              {group.heading}
            </div>
          )}
          <ul>
            {group.items.map((item) => (
              <li key={item.label}>
                <Link
                  href={`${base}${item.path}`}
                  data-kl={item.kl}
                  className={`mr-3 flex items-center gap-2 rounded-r-full py-1.5 pl-6 pr-4 ${
                    isActive(item.path) ? "bg-selected font-medium text-selected-ink" : "hover:bg-surface"
                  }`}
                >
                  {item.label}
                  {item.preview && <PreviewChip />}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  );
}

function PreviewChip() {
  return (
    <span className="rounded border border-line px-1.5 text-[11px] font-normal leading-4 text-muted">Preview</span>
  );
}
