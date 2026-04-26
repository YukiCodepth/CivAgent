# CivAgent Security Notes

CivAgent is a hackathon-ready connected MVP with explicit desktop and backend boundaries.

## Included Now

- Provider values are loaded from `.env` or backend environment variables.
- The desktop app displays masked readiness only; it does not collect provider secrets in UI forms.
- Frontend receives masked config status and integration readiness, never raw secrets.
- Server-side input normalization and bounds checks.
- Required key checks before real agent execution.
- SQLite evidence storage outside version control.
- Audit events for failed runs, completed runs, and workspace clearing.
- Supabase sync uses server-side credentials from the backend process only.
- Baseline browser headers:
  - `Content-Security-Policy`
  - `X-Content-Type-Options`
  - `X-Frame-Options`
  - `Referrer-Policy`
  - `Permissions-Policy`

## Integration Risks

- Do not commit `.env`, SQLite databases, or build artifacts.
- Use Supabase service-role or secret keys only inside the desktop app/backend boundary.
- Review Tavily and Firecrawl source output before presenting high-stakes claims.
- Keep Composio and E2B actions approval-gated until production policies exist.
- Rotate keys after public presentations or screen shares.

## Enterprise Next Steps

- Add OS keychain-backed secret import if the product later needs in-app secret management.
- Add Supabase Auth with tenant-scoped authorization.
- Enable RLS policies for all Supabase evidence tables.
- Add rate limits, request IDs, and structured logs.
- Add encrypted backups and retention controls.
- Add signed report exports.
- Add SSO/SAML and admin roles.
- Add human approval workflows before Composio tools perform external side effects.
- Add SOC2-style evidence export and model/tool-call retention policy.
