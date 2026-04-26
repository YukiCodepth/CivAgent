# CivAgent Deployment

## Local

```bash
npm run check
npm start
```

Open:

```text
http://localhost:8080
```

If port `8080` is busy:

```bash
PORT=8081 npm start
```

## Environment

```bash
HOST=127.0.0.1
PORT=8080
CIVAGENT_DB=data/civagent.sqlite

AI_PROVIDER=gemini
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-3-flash-preview
TAVILY_API_KEY=...

SUPABASE_URL=...
SUPABASE_PUBLISHABLE_KEY=...
SUPABASE_SECRET_KEY=...

FIRECRAWL_API_KEY=...
COMPOSIO_API_KEY=...
E2B_API_KEY=...
```

Real agent runs require Gemini, Tavily, Supabase, Firecrawl, Composio, and E2B.

Install the E2B runtime dependency before production agent runs:

```bash
npm run setup:python
```

## Supabase

Create the tables listed in `README.md`, then restart the server with `SUPABASE_URL` and `SUPABASE_SECRET_KEY` set. The backend writes:

- `agent_runs`
- `agent_artifacts`
- `agent_sources`
- `tool_calls`
- `approvals`

For demos, RLS can remain disabled. For production, enable RLS and restrict writes to a backend service role.

## Docker

```bash
docker build -t civagent .
docker run --rm -p 8080:8080 --env-file .env -v "$PWD/data:/app/data" civagent
```

## Production Notes

- Put the app behind HTTPS.
- Set `HOST=0.0.0.0` inside containers.
- Mount `data/` on persistent storage or rely on Supabase as the system of record.
- Add authentication before exposing beyond an internal evaluation environment.
- Keep Gemini, Tavily, Supabase, Firecrawl, Composio, and E2B keys in the server environment only.
