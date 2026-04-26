# CivAgent Deployment

## Desktop Development

```bash
npm install
npm run setup:python
npm run brand:icons
npm run check
npm run desktop:dev
```

The Electron app starts the backend on `127.0.0.1`, waits for `/api/health`, and opens `/app`.

## Server Development

```bash
npm start
```

Open:

```text
http://localhost:8080
http://localhost:8080/app
```

If port `8080` is busy:

```bash
PORT=8081 npm start
```

## Configuration

Desktop mode stores provider settings in the app user-data directory through `CIVAGENT_CONFIG`.

Server mode can use `.env`:

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

## Desktop Packaging

Install Python dependencies first:

```bash
npm run setup:python
```

Build the backend sidecar:

```bash
npm run backend:build
```

Build the desktop app:

```bash
npm run desktop:dist
```

The Electron build includes `dist-backend/` as a backend resource. macOS can be verified locally from this machine; Windows and Linux targets are configured for their native build environments or CI.

## GitHub Release

The release workflow builds native installers on GitHub-hosted runners when a version tag is pushed:

```bash
git tag v1.0.0
git push origin main
git push origin v1.0.0
```

The public release receives macOS DMG/ZIP, Windows NSIS installer, and Linux AppImage assets.

## Supabase

Create the tables listed in `README.md`, then configure Supabase in the desktop Integrations panel or server `.env`. The backend writes:

- `agent_runs`
- `agent_artifacts`
- `agent_sources`
- `tool_calls`
- `approvals`

For short-lived judging environments, RLS can remain disabled. For production, enable RLS and restrict writes to a backend service role.

## Docker

```bash
docker build -t civagent .
docker run --rm -p 8080:8080 --env-file .env -v "$PWD/data:/app/data" civagent
```

## Production Notes

- Put the server deployment behind HTTPS.
- Set `HOST=0.0.0.0` inside containers.
- Mount `data/` on persistent storage or rely on Supabase as the system of record.
- Add authentication before exposing the server workspace beyond an internal evaluation environment.
- Keep Gemini, Tavily, Supabase, Firecrawl, Composio, and E2B keys in the desktop settings store or backend environment only.
