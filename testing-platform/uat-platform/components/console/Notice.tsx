// A whole-page message outside the console frame.
export function Notice({ text }: { text: string }) {
  return (
    <main className="mx-auto max-w-2xl px-8 py-16">
      <p>{text}</p>
    </main>
  );
}
