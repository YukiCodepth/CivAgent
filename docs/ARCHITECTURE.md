# CivAgent Architecture

CivAgent is now a connected agent product, not only a static product shell.

## Runtime

- `server.py` serves the frontend and JSON API from one process.
- `/api/agent/runs` runs the Organization Intelligence Agent.
- The backend loads `.env`, checks every required integration, calls external services, syncs to Supabase, and then saves completed local evidence.
- `script.js` renders integration readiness, live sources, tool calls, approval gates, artifacts, saved runs, and audit events.

## Agent Flow

1. User submits an organization profile and required website.
2. Backend validates the profile and checks required keys.
3. Tavily performs live company/market research.
4. Firecrawl extracts the submitted website.
5. Composio fetches available SaaS/action toolkits.
6. E2B executes a sandboxed ROI, risk, and workflow analysis.
7. Gemini generates the company operating model through the Gemini `generateContent` REST API.
8. Supabase REST sync writes production evidence tables and must succeed.
9. CivAgent stores the completed run, artifacts, sources, tool calls, approvals, markdown report, and audit event.

## Data Model

Local SQLite tables:

- `workspaces`: latest organization profile by name.
- `agent_runs`: complete real-agent report payloads.
- `agent_artifacts`: generated company artifacts.
- `agent_sources`: Tavily and Firecrawl research evidence.
- `tool_calls`: Gemini, Tavily, Firecrawl, Composio, E2B, and Supabase sync events.
- `approvals`: human approval policies.
- `audit_events`: append-only system activity.

Legacy `/api/runs` planning tables remain for compatibility, but the website’s primary workflow uses `/api/agent/runs`.

## External Integrations

- Gemini: default model reasoning and organization-agent orchestration.
- Tavily: required live research.
- Supabase: required cloud evidence store.
- Firecrawl: required website extraction.
- Composio: required SaaS tool/action graph.
- E2B: required sandbox execution lane.

## Why This Shape

The product can be opened locally for hackathon evaluation, but completed agent runs require model calls, live research, tool traces, sandbox analysis, generated business artifacts, and successful Supabase persistence.
