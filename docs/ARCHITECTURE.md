# CivAgent Architecture

CivAgent is now a desktop-first connected agent product with a separate public website.

## Runtime Surfaces

- `/` serves the CivAgent Desktop product website.
- `/app` serves the operating workspace used by the Electron app.
- `desktop/main.js` starts the Python backend, waits for `/api/health`, loads `/app`, and stops the backend when the app exits.
- `server.py` serves static files, config APIs, real-agent APIs, SQLite evidence, audit events, and Supabase sync.

## Agent Flow

1. User opens CivAgent Desktop and saves required integration settings.
2. Backend stores settings in the desktop config path supplied by Electron.
3. User submits an organization profile and required website.
4. Backend validates readiness for Gemini, Tavily, Supabase, Firecrawl, Composio, and E2B.
5. Tavily performs live company and market research.
6. Firecrawl extracts the submitted website.
7. Composio fetches available SaaS/action toolkits.
8. E2B executes sandboxed ROI, risk, and workflow analysis.
9. Gemini generates the company operating model through the Gemini `generateContent` REST API.
10. Supabase writes production evidence tables and must succeed before completion.
11. SQLite stores the completed local evidence record and audit event.

## Data Model

Local SQLite tables:

- `workspaces`: latest organization profile by name.
- `agent_runs`: complete real-agent report payloads.
- `agent_artifacts`: generated company artifacts.
- `agent_sources`: Tavily and Firecrawl research evidence.
- `tool_calls`: Gemini, Tavily, Firecrawl, Composio, E2B, and Supabase sync events.
- `approvals`: human approval policies.
- `audit_events`: append-only system activity.

Desktop config is stored outside the repository through `CIVAGENT_CONFIG`. The Electron app points this to the operating system user-data directory.

## External Integrations

- Gemini: required model reasoning and organization-agent orchestration.
- Tavily: required live research.
- Firecrawl: required website extraction.
- Composio: required SaaS tool/action graph.
- E2B: required sandbox execution lane.
- Supabase: required cloud evidence store.

## Why This Shape

The product can be evaluated as installable software while keeping the public website clean. Company users operate inside the desktop app, secrets stay local to the app/backend boundary, and completed runs require live tools, generated artifacts, cloud evidence, and local auditability.
