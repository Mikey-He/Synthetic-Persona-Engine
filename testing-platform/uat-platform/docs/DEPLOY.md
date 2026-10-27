# Deploy to Vercel

The app deploys to Vercel with a Neon Postgres database. Local development keeps using the Docker database in `.env`; nothing here touches it.

Keep the GitHub repository private until the NDA and IP appendices are confirmed.

## 1. Production database (Neon)

1. In Neon, create a project for the study.
2. Copy the **direct** connection string, the one whose host does not contain `-pooler`. `prisma migrate deploy` needs a direct connection. It looks like `postgresql://USER:PASSWORD@ep-example-123456.us-east-2.aws.neon.tech/neondb?sslmode=require`.
3. Also create a separate Neon branch named `acceptance`, and copy its direct connection string too. Section 6 uses it, so that test sessions never land in the study database.

## 2. Vercel project

1. Vercel → **Add New… → Project** → import the GitHub repository `synthetic-uat-platform`.
2. **Root Directory**: `uat-platform`.
3. Framework preset: Next.js, as detected. Leave the build and install commands at their defaults. Vercel runs `npm run vercel-build`, which runs `prisma generate`, then `prisma migrate deploy`, then `next build`.
4. Pick a function region close to the Neon region.

## 3. Environment variables

In **Project → Settings → Environment Variables**:

| Name | Production | Preview |
| --- | --- | --- |
| `DATABASE_URL` | Neon direct connection string of the study database | Neon direct connection string of the `acceptance` branch |
| `ADMIN_PASSWORD` | A long random password, for researchers only. Rotate it after the study. | A different password |
| `BUILD_VERSION` | The build name, for example `2026.10.02-a` | Leave empty. The first 7 characters of the commit are used. |

Never put these values in a committed file.

## 4. Deploy and check

1. Deploy from the Vercel dashboard, or push to `main`.
2. In the build log, confirm that `prisma migrate deploy` applied the migrations in `prisma/migrations`.
3. Open `https://<your-deployment>/api/health`. It must return `"status": "ok"`, the build version, `fixtureHash` starting `40150d99`, `defaultsHash` starting `bf7e52fa`, `taskVersion` `task-v1` and `evaluatorVersion` `eval-v1`. This route does not touch the database.
4. Open `https://<your-deployment>/admin`. It must ask for the password. After you sign in, the session list loads, which confirms the database connection.

## 5. Seed a pilot session (only if asked)

Normally, create sessions from **/admin → New human session**. Run the seed script against production only when you are asked to. It creates one pilot human session and prints its link.

PowerShell:

```powershell
$env:DATABASE_URL = "<production direct connection string>"
$env:SEED_BASE_URL = "https://<your-deployment>"
npm run seed
Remove-Item Env:DATABASE_URL, Env:SEED_BASE_URL
```

## 6. Acceptance run against a deployment

The Playwright suite creates sessions and reads the database directly. Point it at the **Preview** deployment, which uses the `acceptance` branch. Never point it at the study database.

```powershell
$env:PLAYWRIGHT_BASE_URL = "https://<preview-deployment>"
$env:DATABASE_URL = "<acceptance branch direct connection string>"
$env:ADMIN_PASSWORD = "<preview admin password>"
npm run test:e2e
```

When `PLAYWRIGHT_BASE_URL` is set, Playwright does not start a local server.

## 7. Freeze the pilot build

1. Commit everything. Then run `npm run freeze`. It prints the commit and the fixture and defaults hashes. Record them with the pilot notes.
2. Tag the commit and push the tag:

   ```powershell
   git tag -a pilot-a-v1 <commit> -m "Pilot A build"
   git push origin pilot-a-v1
   ```

3. A later change to the fixture, the defaults, the task text or the evaluator makes a new build. Never pool its sessions silently with this one.
