import type { Metadata } from "next";
import type { ReactNode } from "react";
import { buildVersion } from "@/lib/build";
import { TASK_VERSION } from "@/lib/domain/task";
import { EVALUATOR_VERSION } from "@/lib/evaluator/evaluate";
import { defaultsHash, fixtureHash } from "@/lib/fixtures";

export const metadata: Metadata = {
  title: "Researcher console",
  robots: { index: false, follow: false },
};

export default function AdminLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col">
      <div className="flex-1">{children}</div>
      <footer className="border-t border-line px-8 py-3 text-[12px] text-muted">
        Build {buildVersion()} · Fixture hash {fixtureHash} · Defaults hash {defaultsHash} · Task{" "}
        {TASK_VERSION} · Evaluator {EVALUATOR_VERSION}
      </footer>
    </div>
  );
}
