# Synthetic UAT Platform

This is a research prototype of a cloud billing budget task. It looks and works like Google Cloud Billing, with fictional data. Human participants and screenshot-based AI agents do the same task in it, and the platform records what they do.

There are two versions of the create-budget flow. Everything before and after that flow is the same in both.

| Version | What it is | Code |
| --- | --- | --- |
| **A** | The advanced form, modelled on Google Cloud's Create Budget page | `components/advanced-form/` |
| **B** | A guided setup that asks one question per screen, in the style of AWS's simplified template workflow, with Google Cloud's settings | `components/guided-setup/` |

Both versions save the same configuration shape through `components/budget-shared/`, and one evaluator scores both.

The version is stored on the session. It never appears in a URL, the page or its code, and the create route is the only place that reads it.

The AI engine (the synthetic agent) is built outside this repository. See [Connecting an AI engine](#connecting-an-ai-engine).

## Run it locally

You need Node.js 24 and Docker.

```sh
cd uat-platform
npm install
cp .env.example .env        # then set DATABASE_URL to the local database below, and ADMIN_PASSWORD
docker run -d --name uat-platform-db --restart unless-stopped \
  -e POSTGRES_USER=uat -e POSTGRES_PASSWORD=<local-password> -e POSTGRES_DB=uat_platform \
  -p 127.0.0.1:5433:5432 -v uat-platform-db-data:/var/lib/postgresql/data postgres:17
npx prisma migrate deploy
```

For this container, the local `DATABASE_URL` is `postgresql://uat:<local-password>@localhost:5433/uat_platform`.

Then open a fresh test session of either version:

```sh
npm run open:a
npm run open:b
```

On Windows you can also double-click `launch/Open version A.cmd` or `launch/Open version B.cmd`.

Each run does four things:

1. starts Docker and the database if they are not running;
2. starts the dev server if it is not running;
3. creates a new pilot session of that version;
4. opens the session in a study window: a Chromium window whose page is exactly 1440 × 900 at scale factor 1, the same as the AI engine's screenshots, whatever the computer's display scaling. Close the window when the session is over.

The script refuses any database that is not local. To open the default browser instead, run `npm run open:a -- --system-browser`; then use the browser in full screen at 100% zoom, with the window at least 1440 × 900.

The researcher console is at `http://localhost:3000/admin`, with the `ADMIN_PASSWORD` from `.env`. From there you can:

- create human and synthetic sessions;
- inspect each session's events and evaluation;
- re-score sessions;
- export the research records.

## Tests

```sh
npm run check       # lint, typecheck, unit tests
npm run test:e2e    # Playwright acceptance tests (uses the local database)
```

## Documents

| File | What it is for |
| --- | --- |
| `docs/design-guide-v2.md` | The source of truth for behaviour |
| `docs/build-plan.md` | Architecture, data model, event names and milestones |
| `docs/prototype-design-a-b.md` | What each screen of A and B looks like and says |
| `docs/reference-capture.md` | How version A follows the real console |
| `docs/DEPLOY.md` | Deployment to Vercel with Neon |
| `docs/CHANGELOG.md` | One line per change |

## Connecting an AI engine

An external agent uses the platform the way a person does. It opens the session link in a real browser at 1440 × 900 (scale factor 1), looks only at screenshots, and acts with the mouse and keyboard. It ends the task by clicking **I'm finished**. The build plan's section "Synthetic agent runner" is its specification.

The engine reports its steps through the researcher console API. That API is for the engine's own HTTP client, never the agent's browser.

To sign in, send `POST /api/admin/login` with the form field `password`. The response is a redirect (303) that sets the console cookie. Then:

| Request | Body | Result |
| --- | --- | --- |
| `POST /api/admin/sessions` | `{"actorType": "synthetic", "modelId", "promptVersion", "personaId", "calibrationId" (or null), "temperature" (optional), "variant": "A" or "B"}` | `201` with `{id, token, link, variant}`. The `link` opens the billing overview. |
| `POST /api/admin/sessions/{id}/agent-steps` | `{"stepNo", "screenshotPath" (or null), "action" (any JSON object), "reason" (or null), "executed", "errorLabel" (one of `invalid_json`, `out_of_bounds`, `model_timeout`, `browser_error`, `no_visible_change`, or null), "latencyMs" (or null)}` | `201`. Synthetic sessions only. |
| `GET /api/admin/sessions/{id}` | – | `{ended, terminationReason}`. The session ends by itself when the agent clicks I'm finished. |
| `POST /api/admin/sessions/{id}/end` | `{"terminationReason": "abandoned" or "step_limit" or "time_limit" or "loop" or "technical_error"}` | `204`, or `409` if the session had already ended |
| `GET /api/admin/sessions/{id}/result` | – | `{ended, terminationReason, saves, budgets, scored, evaluation}`: every saved budget at its latest version, the number of saved versions, which one scoring rule v1 picks, and its evaluation (or `null` while nothing has been scored) |

Version A also carries marks for the engine's own browser. They are invisible attributes and change nothing a person sees: `data-kl="T09"` names the knowledge item an element shows, `data-kl-explains="T18"` names the item a help text explains, and `data-kl-harness` marks the task bar, which the engine leaves as it is. The item IDs are the engine's (its knowledge workbench); they say nothing about the variant.

Steps appear in the `agent_steps.csv` export beside the sessions and events.
