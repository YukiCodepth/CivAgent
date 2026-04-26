# CivAgent Security Notes

CivAgent is a hackathon-ready connected MVP with explicit enterprise boundaries.

## Included Now

- `.env` loading keeps API keys server-side.
- Frontend receives integration status only, never raw secrets.
- Server-side input normalization and bounds checks.
- Required key checks before real agent execution.
- SQLite evidence storage outside version control.
- Audit events for real agent runs and workspace clearing.
- Supabase sync uses server-side secret or publishable key from the backend only.
- Baseline browser headers:
  - `Content-Security-Policy`
  - `X-Content-Type-Options`
  - `X-Frame-Options`
  - `Referrer-Policy`
  - `Permissions-Policy`

## Integration Risks

- Do not commit `.env`.
- Do not paste API keys into the website or browser console.
- Use Supabase service-role/secret keys only on the backend.
- Review Tavily/Firecrawl source output before presenting high-stakes claims.
- Keep Composio and E2B actions in approval mode until production policies exist.

## Enterprise Next Steps

- Add Supabase Auth with tenant-scoped authorization.
- Enable RLS policies for all Supabase evidence tables.
- Add rate limits, request IDs, and structured logs.
- Add encrypted backups and retention controls.
- Add signed report exports.
- Add SSO/SAML and admin roles.
- Add human approval workflows before Composio tools perform external side effects.
- Add SOC2-style evidence export and model/tool-call retention policy.
