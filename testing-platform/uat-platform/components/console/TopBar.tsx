type Props = { accountName: string; userName: string };

export function TopBar({ accountName, userName }: Props) {
  return (
    <header className="flex h-12 items-center gap-6 border-b border-line bg-white px-6">
      <span className="text-[18px] text-muted">Cloud Console (prototype)</span>
      <span className="font-medium">{accountName}</span>
      <span className="ml-auto">{userName}</span>
    </header>
  );
}
