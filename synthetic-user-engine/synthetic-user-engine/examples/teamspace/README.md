# Teamspace (demo product)

A small, self-contained admin console for a fictional team workspace. It stands in for
"someone else's product" when testing the usability engine. The company (Lumen Labs) and
every person in it are made up, and all data is simulated and kept in memory.

## Run

```
python examples/teamspace/server.py --port 4100
```

Python 3 standard library only. Default port 4100, bound to 127.0.0.1. Open
http://127.0.0.1:4100/login. Add `--quiet` to stop request logging.

## Test account

| Email | Password |
|---|---|
| admin@lumenlabs.example | teamspace-demo |

The session is an HttpOnly cookie (`ts_session`). When you are not signed in, every page
redirects to `/login?next=<page>`, and every `/api/*` call except `/api/reset` returns 401.

## Pages

| Path | What it is |
|---|---|
| `/login` | Sign-in form (Email address, Password, Sign in) |
| `/home` | Overview dashboard |
| `/projects` | Project list |
| `/members` | Member table with an "Invite people" button |
| `/members/invite` | Two-step invite form (1 Details, 2 Access) with a confirmation dialog |
| `/groups`, `/settings`, `/billing` | Placeholder pages |
| `POST /logout` | Sign out (the button in the top bar) |

## API (same origin, cookie auth)

| Method and path | Description |
|---|---|
| `GET /api/me` | The signed-in user |
| `GET /api/members` | `{"members": [...]}`, including invited people (status `Invited`) |
| `GET /api/projects` | `{"projects": [...]}` |
| `GET /api/invites` | `{"invites": [...]}` with every field: id, email, name, role, roleLabel, projects, welcomeEmail, status, invitedBy, createdAt |
| `POST /api/invites` | Body `{"email", "name", "role", "projects": [], "welcomeEmail"}`. `role` is `viewer`, `contributor` or `admin` (or the label). Returns 201 `{"invite": {...}}`, 422 on validation errors, 409 if the email is already a member |
| `POST /api/reset` | No auth, only from 127.0.0.1. Restores the seed members and projects, clears invites, returns `{"ok": true}`. Sessions stay signed in |

## End-to-end check

`check_flow.py` uses Playwright (Chromium). It signs in, invites Priya Shah
(priya.shah@lumenlabs.example) as Viewer with only Lyra access, confirms, checks the toast,
the table and `/api/invites`, then checks that `/api/reset` clears the invite.

```
python examples/teamspace/check_flow.py --base-url http://127.0.0.1:4100
python examples/teamspace/check_flow.py --start-server        # starts and stops its own server
python examples/teamspace/check_flow.py --screenshots out/    # also saves a screenshot per step
```
