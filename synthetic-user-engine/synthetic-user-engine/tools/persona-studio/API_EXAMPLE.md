# Connect your own API — no desktop AI login required

Persona Studio uses your configured HTTP API for both interview extraction and
AI batch planning. Other users do not need a desktop AI account, CLI installation,
or this project's author's credentials.

## 1. Configure the API

In the project folder:

```sh
cp .env.example .env
```

Edit `.env` (not `.env.example`):

```dotenv
AI_API_KEY=API_KEY_PLACEHOLDER
AI_API_URL=https://YOUR_API_HOST/v1/chat/completions
AI_MODEL=YOUR_MODEL
AI_JSON_MODE=json_object
```

Replace all three placeholders:

| Setting | What to enter |
| --- | --- |
| `AI_API_KEY` | Your provider's real API key |
| `AI_API_URL` | The full compatible Chat Completions endpoint, including its path |
| `AI_MODEL` | A model ID available to that key/provider |

The sample host and model are placeholders, not a working service. A key alone
is insufficient without the matching endpoint and model. Never commit real keys.

The API must accept `Authorization: Bearer ...`, `model`, `messages`, and
`response_format: {"type":"json_object"}`. It must return JSON text in
`choices[0].message.content`. Providers with a different API contract need an
adapter change. Set `AI_JSON_MODE=json_schema` only if the provider supports strict
structured outputs. Remote endpoints must use HTTPS.

## 2. Test the connection

```sh
python3 examples/api_example.py
```

This sends one small request through the exact adapter used by the platform.
A successful result looks like:

```json
{"message": "Persona Studio API connected"}
```

It never prints your key. Placeholders are rejected without making a request.
HTTP 401/403 usually requires checking credentials/permissions; other HTTP errors
may require checking endpoint, model, quota, or provider support. See the provider's
response/status and documentation when diagnosing your account setup.

## 3. Start the platform

```sh
python3 server.py
```

Open the printed localhost URL. Select a role, then paste an interview and click
**Extract persona settings**, or add/select participant references and click
**Generate batch with AI**. Both features now call your API directly. There is no
CLI fallback. Only information used by the chosen AI action is sent to the provider.

Example interview for a first extraction test (synthetic text):

> Participant: I check every field and its default value before saving. I usually
> confirm that a budget was created by checking the saved list. I do not know the
> exact location of the budget menu in this product.

Review proposals and quotes before applying them. Missing information must not be
mistaken for a verified default. API connectivity alone does not establish persona
accuracy or guarantee that every model produces valid extraction results.

## 4. Save cards

Click **Save persona card** or **Save individual engine JSON files**. Files are
written to `data/personas/studio-<unique-id>.json` on the computer running the server.
Generation alone is a preview. The actual JSON files are Git-ignored; the folder
README is tracked. Browser Download uses your normal downloads location.

The simulation engine remains excluded. This API powers card generation, not
product-browser execution by a separately installed engine.
