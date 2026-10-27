import { Suspense, type ReactNode } from "react";
import { TASK_BAR_HEIGHT, TaskBar } from "@/components/taskbar/TaskBar";
import { Breadcrumbs } from "./Breadcrumbs";
import { LeftNav } from "./LeftNav";
import { TopBar } from "./TopBar";

type Props = {
  token: string;
  accountName: string;
  userName: string;
  children: ReactNode;
};

export function ParticipantShell({ token, accountName, userName, children }: Props) {
  return (
    <>
      <TaskBar token={token} />
      <div style={{ paddingTop: TASK_BAR_HEIGHT }}>
        <TopBar accountName={accountName} userName={userName} />
        <div className="flex">
          <LeftNav token={token} accountName={accountName} stickyTop={TASK_BAR_HEIGHT} />
          <main className="min-w-0 flex-1 px-8 py-4">
            <Suspense>
              <Breadcrumbs token={token} />
            </Suspense>
            {children}
          </main>
        </div>
      </div>
    </>
  );
}
