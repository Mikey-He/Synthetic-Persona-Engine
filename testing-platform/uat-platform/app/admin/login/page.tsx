type Props = { searchParams: Promise<{ error?: string }> };

export default async function AdminLoginPage({ searchParams }: Props) {
  const { error } = await searchParams;
  return (
    <main className="mx-auto max-w-sm px-8 py-16">
      <h1 className="page-title">Researcher console</h1>
      <form method="post" action="/api/admin/login" className="mt-6">
        <label htmlFor="password" className="block font-medium">
          Password
        </label>
        <input
          id="password"
          name="password"
          type="password"
          required
          autoComplete="current-password"
          className="field mt-1.5 w-full"
        />
        {error && <p className="mt-2 text-error">Wrong password.</p>}
        <button type="submit" className="btn-primary mt-4">
          Sign in
        </button>
      </form>
    </main>
  );
}
