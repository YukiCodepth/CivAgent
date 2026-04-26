#!/usr/bin/env python3
"""CivAgent production-style MVP server.

This server intentionally uses only the Python standard library so the product
can ship and run on day one without dependency installation. It serves the
frontend, runs connected organization agents, persists evidence to SQLite,
exposes a small JSON API, records audit events, and applies baseline browser
security headers.
"""

from __future__ import annotations

import json
import importlib.util
import mimetypes
import os
import re
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlparse
from urllib.request import Request, urlopen


APP_ROOT = Path(__file__).resolve().parent
STATIC_ROOT = Path(os.environ.get("CIVAGENT_STATIC_ROOT", APP_ROOT)).resolve()
ENV_PATH = Path(os.environ.get("CIVAGENT_ENV", APP_ROOT / ".env")).expanduser()


def load_env_file() -> None:
    candidates = []
    for candidate in (ENV_PATH, APP_ROOT / ".env", STATIC_ROOT / ".env"):
        if candidate not in candidates:
            candidates.append(candidate)
    for env_path in candidates:
        if not env_path.exists():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


load_env_file()

DATA_DIR = APP_ROOT / "data"
DB_PATH = Path(os.environ.get("CIVAGENT_DB", DATA_DIR / "civagent.sqlite"))
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8080"))

CONFIG_FIELDS = [
    "AI_PROVIDER",
    "GEMINI_MODEL",
    "GEMINI_API_KEY",
    "TAVILY_API_KEY",
    "SUPABASE_URL",
    "SUPABASE_PUBLISHABLE_KEY",
    "SUPABASE_SECRET_KEY",
    "FIRECRAWL_API_KEY",
    "COMPOSIO_API_KEY",
    "E2B_API_KEY",
]
SECRET_FIELDS = {
    "GEMINI_API_KEY",
    "TAVILY_API_KEY",
    "SUPABASE_PUBLISHABLE_KEY",
    "SUPABASE_SECRET_KEY",
    "FIRECRAWL_API_KEY",
    "COMPOSIO_API_KEY",
    "E2B_API_KEY",
}


def config_value(key: str, default: str = "") -> str:
    env_value = os.environ.get(key)
    if env_value:
        return env_value.strip()
    if key == "GEMINI_API_KEY":
        google_key = os.environ.get("GOOGLE_API_KEY", "")
        if google_key:
            return google_key.strip()
    return str(default).strip()


def ai_provider_raw() -> str:
    return config_value("AI_PROVIDER")


def ai_provider() -> str:
    return ai_provider_raw().strip().lower() or "gemini"


def gemini_model_raw() -> str:
    return config_value("GEMINI_MODEL")


def gemini_model() -> str:
    return gemini_model_raw().strip() or "gemini-3-flash-preview"


def mask_config_value(value: str, reveal: bool = False) -> str:
    if not value:
        return ""
    if not reveal:
        return "configured"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def config_status() -> dict:
    values = {}
    for key in CONFIG_FIELDS:
        value = config_value(key)
        values[key] = {
            "configured": is_configured(value),
            "masked": mask_config_value(value, reveal=False) if key in SECRET_FIELDS or key == "SUPABASE_URL" else value,
            "source": "environment" if os.environ.get(key) or (key == "GEMINI_API_KEY" and os.environ.get("GOOGLE_API_KEY")) else "missing",
            "secret": key in SECRET_FIELDS,
        }
    return {
        "envPath": str(ENV_PATH),
        "provider": ai_provider(),
        "values": values,
        "integrations": integration_status(),
    }

MARKETS = {
    "Enterprise SaaS",
    "Healthcare operations",
    "Fintech infrastructure",
    "Legal services",
    "Industrial logistics",
    "Customer operations",
}
STAGES = {"Pre-seed", "Seed", "Series A", "Growth", "Enterprise transformation"}
AUTONOMY = {"Human-reviewed", "Human-supervised", "Autonomous with limits"}
HORIZONS = {"90": "90 days", "180": "180 days", "365": "12 months", "730": "24 months"}

DEFAULT_PROFILE = {
    "orgName": "Northstar Labs",
    "market": "Enterprise SaaS",
    "stage": "Seed",
    "thesis": (
        "A B2B company using AI agents to qualify accounts, coordinate customer "
        "onboarding, monitor risk, and prepare executive operating decisions."
    ),
    "website": "",
    "humans": 12,
    "agentCount": 32,
    "riskTolerance": 54,
    "autonomy": "Human-supervised",
    "horizon": "365",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class IntegrationMissing(Exception):
    """Raised when the user has not configured every required real-agent integration."""


class ExternalServiceError(Exception):
    """Raised when a configured external service rejects or fails a request."""


def normalize_url(value: str) -> str:
    if not value:
        return ""
    if not re.match(r"^https?://", value, re.IGNORECASE):
        value = f"https://{value}"
    parsed = urlparse(value)
    if not parsed.netloc:
        return ""
    return value[:240]


def is_configured(value: str) -> bool:
    return bool(value and not value.endswith("...") and "YOUR_" not in value.upper())


def integration_status() -> dict:
    provider_raw = ai_provider_raw()
    provider = ai_provider()
    model_raw = gemini_model_raw()
    model = gemini_model()
    gemini_key = config_value("GEMINI_API_KEY")
    tavily_key = config_value("TAVILY_API_KEY")
    supabase_url = config_value("SUPABASE_URL").rstrip("/")
    supabase_secret = config_value("SUPABASE_SECRET_KEY")
    supabase_publishable = config_value("SUPABASE_PUBLISHABLE_KEY")
    firecrawl_key = config_value("FIRECRAWL_API_KEY")
    composio_key = config_value("COMPOSIO_API_KEY")
    e2b_key = config_value("E2B_API_KEY")

    provider_ready = is_configured(provider_raw) and provider == "gemini"
    model_ready = is_configured(model_raw)
    gemini_ready = is_configured(gemini_key)
    tavily_ready = is_configured(tavily_key)
    supabase_ready = (
        is_configured(supabase_url)
        and is_configured(supabase_secret)
        and is_configured(supabase_publishable)
    )
    firecrawl_ready = is_configured(firecrawl_key)
    composio_ready = is_configured(composio_key)
    e2b_sdk_ready = importlib.util.find_spec("e2b_code_interpreter") is not None
    e2b_ready = is_configured(e2b_key) and e2b_sdk_ready
    all_ready = all(
        [
            provider_ready,
            model_ready,
            gemini_ready,
            tavily_ready,
            supabase_ready,
            firecrawl_ready,
            composio_ready,
            e2b_ready,
        ]
    )
    return {
        "agentAvailable": all_ready,
        "productionReady": all_ready,
        "provider": {
            "name": "Model Provider",
            "configured": provider_ready,
            "required": True,
            "status": "gemini selected" if provider_ready else "AI_PROVIDER must be gemini",
            "model": model,
        },
        "geminiModel": {
            "name": "Gemini Model",
            "configured": model_ready,
            "required": True,
            "status": "ready" if model_ready else "missing GEMINI_MODEL",
            "model": model,
        },
        "gemini": {
            "name": "Gemini",
            "configured": gemini_ready,
            "required": True,
            "status": "ready" if gemini_ready else "missing GEMINI_API_KEY",
            "model": model,
        },
        "tavily": {
            "name": "Tavily",
            "configured": tavily_ready,
            "required": True,
            "status": "ready" if tavily_ready else "missing TAVILY_API_KEY",
        },
        "supabase": {
            "name": "Supabase",
            "configured": supabase_ready,
            "required": True,
            "status": "ready" if supabase_ready else "missing SUPABASE_URL, SUPABASE_SECRET_KEY, or SUPABASE_PUBLISHABLE_KEY",
        },
        "firecrawl": {
            "name": "Firecrawl",
            "configured": firecrawl_ready,
            "required": True,
            "status": "ready" if firecrawl_ready else "missing FIRECRAWL_API_KEY",
        },
        "composio": {
            "name": "Composio",
            "configured": composio_ready,
            "required": True,
            "status": "ready" if composio_ready else "missing COMPOSIO_API_KEY",
        },
        "e2b": {
            "name": "E2B",
            "configured": e2b_ready,
            "required": True,
            "status": "ready"
            if e2b_ready
            else "missing E2B_API_KEY"
            if not is_configured(e2b_key)
            else "missing e2b-code-interpreter package; run npm run setup:python",
        },
    }


def compact_text(value: str, limit: int = 900) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


def http_json(method: str, url: str, payload: dict | None = None, headers: dict | None = None, timeout: int = 30) -> dict:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    request = Request(url, data=body, headers=request_headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            data = response.read().decode("utf-8")
            return json.loads(data) if data else {}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ExternalServiceError(f"{url} returned HTTP {exc.code}: {compact_text(detail, 500)}") from exc
    except URLError as exc:
        raise ExternalServiceError(f"{url} could not be reached: {exc.reason}") from exc
    except TimeoutError as exc:
        raise ExternalServiceError(f"{url} timed out") from exc


def db() -> sqlite3.Connection:
    DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS workspaces (
              id TEXT PRIMARY KEY,
              org_name TEXT NOT NULL,
              market TEXT NOT NULL,
              stage TEXT NOT NULL,
              profile_json TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS runs (
              id TEXT PRIMARY KEY,
              workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
              created_at TEXT NOT NULL,
              profile_json TEXT NOT NULL,
              result_json TEXT NOT NULL,
              readiness INTEGER NOT NULL,
              risk TEXT NOT NULL,
              deployment TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS audit_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              created_at TEXT NOT NULL,
              actor TEXT NOT NULL,
              action TEXT NOT NULL,
              entity_id TEXT,
              metadata_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS agent_runs (
              id TEXT PRIMARY KEY,
              workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
              created_at TEXT NOT NULL,
              status TEXT NOT NULL,
              model TEXT NOT NULL,
              integrations_json TEXT NOT NULL,
              profile_json TEXT NOT NULL,
              result_json TEXT NOT NULL,
              markdown_report TEXT NOT NULL,
              error_text TEXT
            );

            CREATE TABLE IF NOT EXISTS agent_artifacts (
              id TEXT PRIMARY KEY,
              run_id TEXT NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
              created_at TEXT NOT NULL,
              artifact_type TEXT NOT NULL,
              title TEXT NOT NULL,
              content_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS agent_sources (
              id TEXT PRIMARY KEY,
              run_id TEXT NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
              created_at TEXT NOT NULL,
              provider TEXT NOT NULL,
              title TEXT NOT NULL,
              url TEXT NOT NULL,
              snippet TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tool_calls (
              id TEXT PRIMARY KEY,
              run_id TEXT NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
              created_at TEXT NOT NULL,
              tool_name TEXT NOT NULL,
              status TEXT NOT NULL,
              input_json TEXT NOT NULL,
              output_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS approvals (
              id TEXT PRIMARY KEY,
              run_id TEXT NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
              created_at TEXT NOT NULL,
              title TEXT NOT NULL,
              policy TEXT NOT NULL,
              required INTEGER NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_runs_created ON runs(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_agent_runs_created ON agent_runs(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_events(created_at DESC);
            """
        )


def normalize_profile(payload: dict) -> dict:
    profile = {**DEFAULT_PROFILE, **(payload or {})}
    profile["orgName"] = str(profile.get("orgName", "")).strip()[:120] or DEFAULT_PROFILE["orgName"]
    profile["market"] = profile["market"] if profile.get("market") in MARKETS else DEFAULT_PROFILE["market"]
    profile["stage"] = profile["stage"] if profile.get("stage") in STAGES else DEFAULT_PROFILE["stage"]
    profile["autonomy"] = profile["autonomy"] if profile.get("autonomy") in AUTONOMY else DEFAULT_PROFILE["autonomy"]
    profile["horizon"] = str(profile.get("horizon")) if str(profile.get("horizon")) in HORIZONS else DEFAULT_PROFILE["horizon"]
    profile["thesis"] = str(profile.get("thesis", "")).strip()[:1800] or DEFAULT_PROFILE["thesis"]
    profile["website"] = normalize_url(str(profile.get("website", "")).strip()[:240])
    profile["humans"] = int(clamp(float(profile.get("humans", DEFAULT_PROFILE["humans"])), 2, 120))
    profile["agentCount"] = int(clamp(float(profile.get("agentCount", DEFAULT_PROFILE["agentCount"])), 4, 250))
    profile["riskTolerance"] = int(clamp(float(profile.get("riskTolerance", DEFAULT_PROFILE["riskTolerance"])), 10, 90))
    return profile


def role_pack(market: str) -> list[str]:
    packs = {
        "Enterprise SaaS": ["Market Scout", "Pipeline Operator", "Onboarding Architect", "Trust Sentinel"],
        "Healthcare operations": ["Care Flow Analyst", "Scheduling Operator", "Compliance Sentinel", "Patient Experience Agent"],
        "Fintech infrastructure": ["Transaction Monitor", "Risk Ledger Agent", "Revenue Operator", "Compliance Sentinel"],
        "Legal services": ["Matter Intake Agent", "Evidence Organizer", "Contract Analyst", "Partner Escalation Sentinel"],
        "Industrial logistics": ["Route Planner", "Exception Monitor", "Vendor Negotiator", "Safety Sentinel"],
        "Customer operations": ["Conversation Analyst", "Resolution Operator", "Churn Forecaster", "Quality Sentinel"],
    }
    return packs.get(market, packs["Enterprise SaaS"])


def market_pressure(market: str) -> str:
    pressures = {
        "Enterprise SaaS": "enterprise buyers demand proof of security, ROI, and human escalation before expanding usage",
        "Healthcare operations": "clinical teams demand auditability, low-friction approvals, and patient-safe handoffs",
        "Fintech infrastructure": "customers demand stronger transaction controls and regulator-ready evidence",
        "Legal services": "clients demand confidentiality, version traceability, and partner review before delivery",
        "Industrial logistics": "operators demand exception handling across vendors, time windows, and safety constraints",
        "Customer operations": "customers demand faster resolution without losing empathy or account context",
    }
    return pressures.get(market, pressures["Enterprise SaaS"])


def simulate(profile: dict) -> dict:
    profile = normalize_profile(profile)
    leverage_raw = profile["agentCount"] / max(profile["humans"], 1)
    autonomy_bonus = {
        "Human-reviewed": 4,
        "Human-supervised": 10,
        "Autonomous with limits": 16,
    }[profile["autonomy"]]
    stage_penalty = {
        "Pre-seed": 8,
        "Seed": 4,
        "Series A": 0,
        "Growth": -2,
        "Enterprise transformation": -6,
    }[profile["stage"]]
    leverage_score = clamp(leverage_raw * 9, 8, 30)
    risk_delta = abs(profile["riskTolerance"] - 55) / 2
    readiness = round(clamp(58 + leverage_score + autonomy_bonus - risk_delta - stage_penalty, 34, 96))
    risk = "Managed" if readiness >= 82 else "Medium" if readiness >= 68 else "High"
    approval_gates = 3 if risk == "Managed" else 4 if risk == "Medium" else 6
    control_checks = approval_gates + round(profile["agentCount"] / 16) + 5
    roles = role_pack(profile["market"])
    pressure = market_pressure(profile["market"])
    horizon_label = HORIZONS[profile["horizon"]]
    leverage = f"1 : {max(1, round(leverage_raw * 6))}"
    deployment = (
        "Scale through governed autonomy"
        if readiness >= 82
        else "Pilot with approval memory"
        if readiness >= 68
        else "Stabilize controls before launch"
    )

    run_id = str(uuid.uuid4())
    return {
        "id": run_id,
        "createdAt": now_iso(),
        "profile": profile,
        "readiness": readiness,
        "risk": risk,
        "leverage": leverage,
        "roles": roles,
        "pressure": pressure,
        "deployment": deployment,
        "approvalGates": approval_gates,
        "controlChecks": control_checks,
        "horizonLabel": horizon_label,
        "artifacts": {
            "memo": [
                f"{profile['orgName']} should begin with {profile['autonomy'].lower()} agent deployment across {profile['market'].lower()}.",
                "The strongest first workflow is a governed operating loop where agents prepare decisions and humans approve exceptions.",
                f"Recommended path: {deployment.lower()} over {horizon_label.lower()}.",
            ],
            "roster": [
                f"{role}: owns {['discovery', 'execution', 'coordination', 'risk review'][index] if index < 4 else 'operations'} with explicit escalation rules."
                for index, role in enumerate(roles)
            ],
            "risks": [
                "Approval memory can become the bottleneck if decisions are not logged and reused.",
                "Customer trust may drop if agents negotiate or promise outcomes without visible accountability.",
                "Tool access should remain scoped until exception handling reaches leadership standards.",
            ],
            "approvalMap": [
                "Agents can draft and classify without approval.",
                "Agents need human approval for customer-impacting commitments.",
                "Finance, legal, medical, or irreversible actions stay blocked until a responsible owner approves.",
            ],
            "scenarios": [
                f"Base case: {pressure}.",
                "Upside case: agent throughput creates a faster response loop than competitors can copy.",
                "Stress case: volume rises faster than managers can review edge cases.",
            ],
            "executive": [
                f"Readiness score: {readiness}%. Risk posture: {risk}.",
                f"Human leverage target: {leverage}. Control checks: {control_checks}.",
                f"Decision: {deployment}.",
            ],
        },
    }


def tool_event(tool_name: str, status: str, input_data: dict, output_data: dict) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "createdAt": now_iso(),
        "toolName": tool_name,
        "status": status,
        "input": input_data,
        "output": output_data,
    }


def tavily_research(profile: dict) -> tuple[list[dict], list[dict]]:
    tavily_key = config_value("TAVILY_API_KEY")
    if not is_configured(tavily_key):
        raise IntegrationMissing("TAVILY_API_KEY is required for real organization research.")

    query = (
        f"{profile['orgName']} {profile['market']} AI agents automation operations "
        f"competitors risks business model"
    )
    payload = {
        "query": query,
        "search_depth": "advanced",
        "max_results": 6,
        "include_answer": True,
        "include_raw_content": False,
    }
    data = http_json(
        "POST",
        "https://api.tavily.com/search",
        payload,
        {"Authorization": f"Bearer {tavily_key}"},
        timeout=35,
    )
    sources = []
    for item in data.get("results", [])[:6]:
        sources.append(
            {
                "provider": "tavily",
                "title": compact_text(item.get("title") or item.get("url") or "Web source", 160),
                "url": item.get("url") or "",
                "snippet": compact_text(item.get("content") or item.get("snippet") or "", 420),
            }
        )
    if data.get("answer"):
        sources.insert(
            0,
            {
                "provider": "tavily",
                "title": "Tavily synthesized answer",
                "url": "",
                "snippet": compact_text(data["answer"], 420),
            },
        )
    if not sources:
        raise ExternalServiceError("Tavily returned no live sources for this organization.")
    return sources, [tool_event("tavily.search", "completed", {"query": query}, {"sourceCount": len(sources)})]


def firecrawl_extract(profile: dict) -> tuple[list[dict], list[dict]]:
    if not profile.get("website"):
        raise ValueError("Website URL is required because Firecrawl must run on every real agent run.")
    firecrawl_key = config_value("FIRECRAWL_API_KEY")
    if not is_configured(firecrawl_key):
        raise IntegrationMissing("FIRECRAWL_API_KEY is required for website extraction.")

    payload = {
        "url": profile["website"],
        "formats": ["markdown"],
        "onlyMainContent": True,
        "timeout": 45000,
    }
    data = http_json(
        "POST",
        "https://api.firecrawl.dev/v2/scrape",
        payload,
        {"Authorization": f"Bearer {firecrawl_key}"},
        timeout=55,
    )
    markdown = ""
    if isinstance(data.get("data"), dict):
        markdown = data["data"].get("markdown") or data["data"].get("content") or ""
    if not markdown.strip():
        raise ExternalServiceError("Firecrawl scrape completed without usable markdown content.")
    source = {
        "provider": "firecrawl",
        "title": f"{profile['orgName']} website extraction",
        "url": profile["website"],
        "snippet": compact_text(markdown, 620),
    }
    return [source], [tool_event("firecrawl.scrape", "completed", {"url": profile["website"]}, {"characters": len(markdown)})]


def composio_toolkit_probe() -> tuple[list[dict], list[dict]]:
    composio_key = config_value("COMPOSIO_API_KEY")
    if not is_configured(composio_key):
        raise IntegrationMissing("COMPOSIO_API_KEY is required for SaaS tool discovery.")
    data = http_json(
        "GET",
        "https://backend.composio.dev/api/v3/toolkits",
        None,
        {"x-api-key": composio_key},
        timeout=25,
    )
    raw_toolkits = data.get("items", data.get("toolkits", [])) if isinstance(data, dict) else []
    toolkits = []
    for item in raw_toolkits[:12]:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("slug") or item.get("key") or item.get("toolkit") or "toolkit"
        toolkits.append(
            {
                "name": compact_text(name, 90),
                "description": compact_text(item.get("description") or item.get("meta", {}).get("description", ""), 220),
            }
        )
    if not toolkits:
        raise ExternalServiceError("Composio returned no available toolkits.")
    source = {
        "provider": "composio",
        "title": "Composio SaaS action toolkit graph",
        "url": "https://backend.composio.dev/api/v3/toolkits",
        "snippet": compact_text("; ".join(item["name"] for item in toolkits), 620),
    }
    return [source], [tool_event("composio.toolkits", "completed", {"limit": 12}, {"availableToolkits": len(toolkits), "toolkits": toolkits})]


def sandbox_analysis(profile: dict, sources: list[dict], tool_calls: list[dict]) -> list[dict]:
    e2b_key = config_value("E2B_API_KEY")
    if not is_configured(e2b_key):
        raise IntegrationMissing("E2B_API_KEY is required for sandboxed analysis.")
    try:
        from e2b_code_interpreter import Sandbox
    except ImportError as exc:
        raise ExternalServiceError("E2B SDK is not installed. Run `npm run setup:python` before production agent runs.") from exc

    os.environ["E2B_API_KEY"] = e2b_key

    code = """
import json
profile = __PROFILE__
source_count = __SOURCE_COUNT__
tool_call_count = __TOOL_CALL_COUNT__
leverage = profile["agentCount"] / max(profile["humans"], 1)
readiness = min(96, round(52 + leverage * 7 + min(source_count, 8) * 3 + min(tool_call_count, 8) * 2))
risk_score = max(8, min(90, round(100 - readiness + abs(profile["riskTolerance"] - 55) * 0.6)))
workflow_score = min(100, round(45 + leverage * 8 + min(source_count, 8) * 4))
roi_multiple = round(max(1.1, leverage * 1.8), 2)
print(json.dumps({
    "readiness": readiness,
    "riskScore": risk_score,
    "workflowScore": workflow_score,
    "roiMultiple": roi_multiple,
    "recommendation": "Proceed only with approval-gated rollout and evidence-backed tool access."
}))
""".replace("__PROFILE__", json.dumps(profile)).replace("__SOURCE_COUNT__", str(len(sources))).replace("__TOOL_CALL_COUNT__", str(len(tool_calls)))

    sandbox = Sandbox.create()
    try:
        execution = sandbox.run_code(code, language="python", timeout=30, request_timeout=45)
        if getattr(execution, "error", None):
            raise ExternalServiceError(f"E2B sandbox execution failed: {execution.error}")
        text = getattr(execution, "text", None) or execution.to_json()
        analysis = parse_json_object(text)
    finally:
        kill = getattr(sandbox, "kill", None)
        if callable(kill):
            try:
                kill()
            except Exception:
                pass
    return [tool_event("e2b.sandbox.run_code", "completed", {"runtime": "python"}, analysis)]


def sources_for_prompt(sources: list[dict]) -> list[dict]:
    return [
        {
            "provider": source.get("provider", ""),
            "title": source.get("title", ""),
            "url": source.get("url", ""),
            "snippet": compact_text(source.get("snippet", ""), 420),
        }
        for source in sources[:8]
    ]


def agent_system_prompt() -> str:
    return (
        "You are CivAgent, an enterprise-grade Organization Intelligence Agent. "
        "You coordinate four specialist agents: Research Agent, Workflow Architect "
        "Agent, Risk/Governance Agent, and Venture Strategy Agent. Build a serious "
        "company operating plan for deploying AI agents. Use the supplied live "
        "research sources and tool-call evidence. Return only valid JSON with keys: "
        "readiness, risk, leverage, deployment, roles, pressure, approvalGates, "
        "controlChecks, artifacts, approvals, strategicSummary. The artifacts object "
        "must include memo, roster, risks, approvalMap, scenarios, executive, "
        "companyBrief, workflowBlueprint, toolAccessPlan, and businessModel arrays."
    )


def agent_user_prompt(profile: dict, sources: list[dict], tool_calls: list[dict]) -> str:
    return json.dumps(
        {
            "profile": profile,
            "sources": sources_for_prompt(sources),
            "toolCalls": [
                {
                    "toolName": call["toolName"],
                    "status": call["status"],
                    "output": call.get("output", {}),
                }
                for call in tool_calls
            ],
            "requirements": [
                "Do not describe a generic chatbot.",
                "Design a deployable agent operating model for a real organization.",
                "Include tool access, human approvals, evidence, risks, and business moat.",
                "Use concise executive language suitable for founders and enterprise buyers.",
            ],
        },
        ensure_ascii=True,
    )


def extract_gemini_text(payload: dict) -> str:
    chunks = []
    for candidate in payload.get("candidates", []) or []:
        content = candidate.get("content", {})
        for part in content.get("parts", []) or []:
            text = part.get("text") if isinstance(part, dict) else None
            if text:
                chunks.append(text)
    return "\n".join(chunks)


def parse_json_object(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def run_gemini_generate_content(profile: dict, sources: list[dict], tool_calls: list[dict]) -> tuple[dict, list[dict]]:
    gemini_key = config_value("GEMINI_API_KEY")
    model = gemini_model()
    if not is_configured(gemini_key):
        raise IntegrationMissing("GEMINI_API_KEY is required for real agent generation.")
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": (
                            f"{agent_system_prompt()}\n\n"
                            "Return a single JSON object only.\n\n"
                            f"{agent_user_prompt(profile, sources, tool_calls)}"
                        )
                    }
                ],
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.35,
        },
    }
    model_path = quote(model, safe="")
    data = http_json(
        "POST",
        f"https://generativelanguage.googleapis.com/v1beta/models/{model_path}:generateContent",
        payload,
        {"x-goog-api-key": gemini_key},
        timeout=90,
    )
    text = extract_gemini_text(data)
    event = tool_event(
        "gemini.generateContent",
        "completed",
        {"model": model, "sourceCount": len(sources)},
        {"candidates": len(data.get("candidates", []) or []), "characters": len(text)},
    )
    return parse_json_object(text), [event]


def run_model_generation(profile: dict, sources: list[dict], tool_calls: list[dict]) -> tuple[dict, list[dict]]:
    return run_gemini_generate_content(profile, sources, tool_calls)


def base_artifacts(profile: dict, sources: list[dict], raw_output: str = "") -> dict:
    base = simulate(profile)
    source_phrase = sources[0]["snippet"] if sources else market_pressure(profile["market"])
    base["artifacts"]["companyBrief"] = [
        f"{profile['orgName']} operates in {profile['market']} with a live research signal: {compact_text(source_phrase, 220)}",
        "The first business wedge is an operating intelligence workspace that turns research into approved agent workflows.",
    ]
    base["artifacts"]["workflowBlueprint"] = [
        "Research intake -> workflow decomposition -> tool access review -> human approval -> measured rollout.",
        "Agents should produce evidence before acting in customer, finance, legal, or regulated systems.",
    ]
    base["artifacts"]["toolAccessPlan"] = [
        "Gemini handles model reasoning and orchestration.",
        "Tavily supplies live market and company research.",
        "Firecrawl, Composio, and E2B expand the platform into crawling, SaaS actions, and sandboxed execution.",
    ]
    base["artifacts"]["businessModel"] = [
        "Sell to AI transformation leaders, founders, consultancies, and regulated operations teams.",
        "Defensible moat: accumulated workflow evidence, approval memory, and company-specific agent operating graphs.",
    ]
    if raw_output:
        base["artifacts"]["executive"].append(f"Raw model note: {compact_text(raw_output, 260)}")
    return base


def coerce_agent_output(profile: dict, generated: dict, sources: list[dict], tool_calls: list[dict]) -> dict:
    base = base_artifacts(profile, sources)
    artifacts = {**base["artifacts"], **(generated.get("artifacts") or {})}
    for key, value in list(artifacts.items()):
        if isinstance(value, str):
            artifacts[key] = [value]
        elif not isinstance(value, list):
            artifacts[key] = [json.dumps(value)]
        artifacts[key] = [compact_text(item, 900) for item in artifacts[key] if str(item).strip()]

    roles = generated.get("roles") if isinstance(generated.get("roles"), list) else base["roles"]
    approvals = generated.get("approvals") if isinstance(generated.get("approvals"), list) else []
    if not approvals:
        approvals = [
            {"title": "Customer-impacting action", "policy": "Human approval required before commitments are sent.", "required": True},
            {"title": "Sensitive data access", "policy": "Restrict to least-privilege tools and log every retrieval.", "required": True},
            {"title": "Low-risk drafting", "policy": "Agent may draft, classify, and summarize without external side effects.", "required": False},
        ]

    return {
        **base,
        "readiness": int(clamp(float(generated.get("readiness", base["readiness"])), 1, 100)),
        "risk": generated.get("risk") if generated.get("risk") in {"Managed", "Medium", "High"} else base["risk"],
        "leverage": compact_text(generated.get("leverage") or base["leverage"], 40),
        "roles": [compact_text(role, 120) for role in roles[:8]],
        "pressure": compact_text(generated.get("pressure") or base["pressure"], 500),
        "deployment": compact_text(generated.get("deployment") or base["deployment"], 180),
        "approvalGates": int(clamp(float(generated.get("approvalGates", base["approvalGates"])), 1, 20)),
        "controlChecks": int(clamp(float(generated.get("controlChecks", base["controlChecks"])), 1, 80)),
        "artifacts": artifacts,
        "approvals": approvals[:8],
        "sources": sources,
        "toolCalls": tool_calls,
        "integrations": integration_status(),
        "strategicSummary": compact_text(generated.get("strategicSummary") or "", 800),
    }


def render_markdown_report(result: dict) -> str:
    profile = result["profile"]
    lines = [
        f"# CivAgent Report: {profile['orgName']}",
        "",
        f"- Market: {profile['market']}",
        f"- Stage: {profile['stage']}",
        f"- Readiness: {result['readiness']}%",
        f"- Risk: {result['risk']}",
        f"- Deployment: {result['deployment']}",
        "",
        "## Agent Roles",
    ]
    lines.extend(f"- {role}" for role in result.get("roles", []))
    for title, key in [
        ("Company Intelligence Brief", "companyBrief"),
        ("Workflow Automation Blueprint", "workflowBlueprint"),
        ("Tool Access Plan", "toolAccessPlan"),
        ("Human Approval Policy", "approvalMap"),
        ("Risk and Compliance Register", "risks"),
        ("Business Model and Moat", "businessModel"),
        ("Executive Brief", "executive"),
    ]:
        lines.extend(["", f"## {title}"])
        lines.extend(f"- {item}" for item in result["artifacts"].get(key, []))
    if result.get("sources"):
        lines.extend(["", "## Sources"])
        lines.extend(f"- {source.get('title')} {source.get('url')}".strip() for source in result["sources"])
    return "\n".join(lines)


def build_real_agent_run(profile: dict) -> dict:
    profile = normalize_profile(profile)
    if not profile["website"]:
        raise ValueError("Website URL is required for every real agent run.")
    status = integration_status()
    if not status["agentAvailable"]:
        missing = [
            item["status"]
            for key, item in status.items()
            if isinstance(item, dict) and item.get("required") and not item.get("configured")
        ]
        raise IntegrationMissing("Real agent is not configured: " + "; ".join(missing))

    run_id = str(uuid.uuid4())
    created_at = now_iso()
    sources, tool_calls = tavily_research(profile)
    website_sources, website_calls = firecrawl_extract(profile)
    sources.extend(website_sources)
    tool_calls.extend(website_calls)
    composio_sources, composio_calls = composio_toolkit_probe()
    sources.extend(composio_sources)
    tool_calls.extend(composio_calls)
    tool_calls.extend(sandbox_analysis(profile, sources, tool_calls))

    try:
        generated, model_calls = run_model_generation(profile, sources, tool_calls)
    except json.JSONDecodeError as exc:
        raise ExternalServiceError(f"{ai_provider().title()} returned non-JSON output: {exc}") from exc
    tool_calls.extend(model_calls)

    result = coerce_agent_output(profile, generated, sources, tool_calls)
    result.update(
        {
            "id": run_id,
            "createdAt": created_at,
            "status": "completed",
            "mode": "real-agent",
            "model": gemini_model(),
            "provider": "gemini",
            "horizonLabel": HORIZONS[profile["horizon"]],
        }
    )
    result["markdownReport"] = render_markdown_report(result)
    return result


def write_audit(conn: sqlite3.Connection, action: str, entity_id: str | None, metadata: dict) -> None:
    conn.execute(
        """
        INSERT INTO audit_events (created_at, actor, action, entity_id, metadata_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        (now_iso(), "system", action, entity_id, json.dumps(metadata)),
    )


def upsert_workspace(conn: sqlite3.Connection, profile: dict) -> str:
    existing = conn.execute(
        "SELECT id FROM workspaces WHERE org_name = ? ORDER BY updated_at DESC LIMIT 1",
        (profile["orgName"],),
    ).fetchone()
    workspace_id = existing["id"] if existing else str(uuid.uuid4())
    timestamp = now_iso()
    if existing:
        conn.execute(
            """
            UPDATE workspaces
            SET market = ?, stage = ?, profile_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (profile["market"], profile["stage"], json.dumps(profile), timestamp, workspace_id),
        )
    else:
        conn.execute(
            """
            INSERT INTO workspaces (id, org_name, market, stage, profile_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (workspace_id, profile["orgName"], profile["market"], profile["stage"], json.dumps(profile), timestamp, timestamp),
        )
    return workspace_id


def save_run(result: dict) -> dict:
    with db() as conn:
        workspace_id = upsert_workspace(conn, result["profile"])
        conn.execute(
            """
            INSERT INTO runs (id, workspace_id, created_at, profile_json, result_json, readiness, risk, deployment)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result["id"],
                workspace_id,
                result["createdAt"],
                json.dumps(result["profile"]),
                json.dumps(result),
                result["readiness"],
                result["risk"],
                result["deployment"],
            ),
        )
        write_audit(
            conn,
            "simulation.created",
            result["id"],
            {
                "orgName": result["profile"]["orgName"],
                "readiness": result["readiness"],
                "risk": result["risk"],
            },
        )
    return result


def supabase_key() -> str:
    return config_value("SUPABASE_SECRET_KEY")


def supabase_enabled() -> bool:
    return bool(
        config_value("SUPABASE_URL")
        and config_value("SUPABASE_SECRET_KEY")
        and config_value("SUPABASE_PUBLISHABLE_KEY")
    )


def supabase_insert(table: str, row: dict) -> None:
    key = supabase_key()
    if not supabase_enabled():
        raise IntegrationMissing("Supabase URL, secret key, and publishable key are required for company-grade sync.")
    http_json(
        "POST",
        f"{config_value('SUPABASE_URL').rstrip('/')}/rest/v1/{table}",
        row,
        {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Prefer": "return=minimal",
        },
        timeout=25,
    )


def sync_supabase_agent_run(result: dict, workspace_id: str) -> dict:
    if not supabase_enabled():
        raise IntegrationMissing("Supabase URL, secret key, and publishable key are required for company-grade sync.")
    supabase_insert(
        "agent_runs",
        {
            "id": result["id"],
            "workspace_id": workspace_id,
            "created_at": result["createdAt"],
            "status": result["status"],
            "model": result["model"],
            "integrations": result["integrations"],
            "profile": result["profile"],
            "result": {key: value for key, value in result.items() if key != "markdownReport"},
            "markdown_report": result["markdownReport"],
        },
    )
    for title, key in [
        ("Company Intelligence Brief", "companyBrief"),
        ("Agent Team Org Chart", "roster"),
        ("Workflow Automation Blueprint", "workflowBlueprint"),
        ("Tool Access Plan", "toolAccessPlan"),
        ("Human Approval Policy", "approvalMap"),
        ("Risk and Compliance Register", "risks"),
        ("Business Model and Moat", "businessModel"),
        ("Executive Brief", "executive"),
    ]:
        supabase_insert(
            "agent_artifacts",
            {
                "id": str(uuid.uuid4()),
                "run_id": result["id"],
                "created_at": now_iso(),
                "artifact_type": key,
                "title": title,
                "content": result["artifacts"].get(key, []),
            },
        )
    for source in result.get("sources", []):
        supabase_insert(
            "agent_sources",
            {
                "id": str(uuid.uuid4()),
                "run_id": result["id"],
                "created_at": now_iso(),
                "provider": source.get("provider", ""),
                "title": source.get("title", ""),
                "url": source.get("url", ""),
                "snippet": source.get("snippet", ""),
            },
        )
    for call in result.get("toolCalls", []):
        supabase_insert(
            "tool_calls",
            {
                "id": call.get("id") or str(uuid.uuid4()),
                "run_id": result["id"],
                "created_at": call.get("createdAt") or now_iso(),
                "tool_name": call.get("toolName", ""),
                "status": call.get("status", ""),
                "input": call.get("input", {}),
                "output": call.get("output", {}),
            },
        )
    for approval in result.get("approvals", []):
        supabase_insert(
            "approvals",
            {
                "id": str(uuid.uuid4()),
                "run_id": result["id"],
                "created_at": now_iso(),
                "title": compact_text(approval.get("title", "Approval"), 180),
                "policy": compact_text(approval.get("policy", ""), 700),
                "required": bool(approval.get("required", True)),
            },
        )
    return {"enabled": True, "status": "synced"}


def save_agent_run(result: dict) -> dict:
    with db() as conn:
        workspace_id = upsert_workspace(conn, result["profile"])
        result["supabaseSync"] = {"enabled": True, "status": "pending"}
        result["supabaseSync"] = sync_supabase_agent_run(result, workspace_id)
        sync_event = tool_event("supabase.sync", "completed", {"tables": 5}, result["supabaseSync"])
        result["toolCalls"].append(sync_event)
        supabase_insert(
            "tool_calls",
            {
                "id": sync_event["id"],
                "run_id": result["id"],
                "created_at": sync_event["createdAt"],
                "tool_name": sync_event["toolName"],
                "status": sync_event["status"],
                "input": sync_event["input"],
                "output": sync_event["output"],
            },
        )
        conn.execute(
            """
            INSERT INTO agent_runs
              (id, workspace_id, created_at, status, model, integrations_json, profile_json, result_json, markdown_report, error_text)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result["id"],
                workspace_id,
                result["createdAt"],
                result["status"],
                result["model"],
                json.dumps(result["integrations"]),
                json.dumps(result["profile"]),
                json.dumps(result),
                result["markdownReport"],
                None,
            ),
        )
        for title, key in [
            ("Company Intelligence Brief", "companyBrief"),
            ("Agent Team Org Chart", "roster"),
            ("Workflow Automation Blueprint", "workflowBlueprint"),
            ("Tool Access Plan", "toolAccessPlan"),
            ("Human Approval Policy", "approvalMap"),
            ("Risk and Compliance Register", "risks"),
            ("Business Model and Moat", "businessModel"),
            ("Executive Brief", "executive"),
        ]:
            conn.execute(
                """
                INSERT INTO agent_artifacts (id, run_id, created_at, artifact_type, title, content_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), result["id"], now_iso(), key, title, json.dumps(result["artifacts"].get(key, []))),
            )
        for source in result.get("sources", []):
            conn.execute(
                """
                INSERT INTO agent_sources (id, run_id, created_at, provider, title, url, snippet)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    result["id"],
                    now_iso(),
                    source.get("provider", ""),
                    source.get("title", ""),
                    source.get("url", ""),
                    source.get("snippet", ""),
                ),
            )
        for call in result.get("toolCalls", []):
            conn.execute(
                """
                INSERT INTO tool_calls (id, run_id, created_at, tool_name, status, input_json, output_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    call.get("id") or str(uuid.uuid4()),
                    result["id"],
                    call.get("createdAt") or now_iso(),
                    call.get("toolName", ""),
                    call.get("status", ""),
                    json.dumps(call.get("input", {})),
                    json.dumps(call.get("output", {})),
                ),
            )
        for approval in result.get("approvals", []):
            conn.execute(
                """
                INSERT INTO approvals (id, run_id, created_at, title, policy, required)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    result["id"],
                    now_iso(),
                    compact_text(approval.get("title", "Approval"), 180),
                    compact_text(approval.get("policy", ""), 700),
                    1 if approval.get("required", True) else 0,
                ),
            )
        write_audit(
            conn,
            "agent_run.completed",
            result["id"],
            {
                "orgName": result["profile"]["orgName"],
                "readiness": result["readiness"],
                "risk": result["risk"],
                "model": result["model"],
                "supabase": result["supabaseSync"]["status"],
            },
        )
    return result


def list_runs(limit: int = 8) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            "SELECT result_json FROM runs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [json.loads(row["result_json"]) for row in rows]


def get_run(run_id: str) -> dict | None:
    with db() as conn:
        row = conn.execute("SELECT result_json FROM runs WHERE id = ?", (run_id,)).fetchone()
    return json.loads(row["result_json"]) if row else None


def list_agent_runs(limit: int = 8) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            "SELECT result_json FROM agent_runs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [json.loads(row["result_json"]) for row in rows]


def get_agent_run(run_id: str) -> dict | None:
    with db() as conn:
        row = conn.execute("SELECT result_json FROM agent_runs WHERE id = ?", (run_id,)).fetchone()
    return json.loads(row["result_json"]) if row else None


def audit_events(limit: int = 20) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            "SELECT created_at, actor, action, entity_id, metadata_json FROM audit_events ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        {
            "createdAt": row["created_at"],
            "actor": row["actor"],
            "action": row["action"],
            "entityId": row["entity_id"],
            "metadata": json.loads(row["metadata_json"]),
        }
        for row in rows
    ]


def latest_profile() -> dict:
    with db() as conn:
        row = conn.execute("SELECT profile_json FROM workspaces ORDER BY updated_at DESC LIMIT 1").fetchone()
    return json.loads(row["profile_json"]) if row else DEFAULT_PROFILE


def clear_runs() -> None:
    with db() as conn:
        conn.execute("DELETE FROM runs")
        conn.execute("DELETE FROM agent_runs")
        conn.execute("DELETE FROM workspaces")
        write_audit(conn, "workspace.cleared", None, {"scope": "all_runs"})


def record_agent_failure(profile: dict | None, message: str) -> None:
    with db() as conn:
        metadata = {
            "orgName": profile.get("orgName") if profile else "unknown",
            "error": compact_text(message, 900),
            "integrations": integration_status(),
        }
        write_audit(conn, "agent_run.failed", None, metadata)


class CivAgentHandler(BaseHTTPRequestHandler):
    server_version = "CivAgent/1.0"

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "base-uri 'self'; "
            "form-action 'self'; "
            "frame-ancestors 'none'",
        )
        super().end_headers()

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length > 100_000:
            raise ValueError("Request body too large")
        body = self.rfile.read(length) if length else b"{}"
        return json.loads(body.decode("utf-8") or "{}")

    def json_response(self, status: HTTPStatus, payload: dict | list) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def error_json(self, status: HTTPStatus, message: str) -> None:
        self.json_response(status, {"error": message})

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/health":
            self.json_response(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "service": "civagent",
                    "time": now_iso(),
                    "integrations": integration_status(),
                },
            )
            return
        if path == "/api/bootstrap":
            agent_runs = list_agent_runs()
            runs = agent_runs or list_runs()
            profile = runs[0]["profile"] if runs else latest_profile()
            self.json_response(
                HTTPStatus.OK,
                {
                    "profile": profile,
                    "runs": runs,
                    "agentRuns": agent_runs,
                    "audit": audit_events(10),
                    "integrations": integration_status(),
                    "config": config_status(),
                    "mode": "server",
                },
            )
            return
        if path == "/api/config/status":
            self.json_response(HTTPStatus.OK, {"config": config_status(), "integrations": integration_status(), "mode": "server"})
            return
        if path == "/api/integrations":
            self.json_response(HTTPStatus.OK, {"integrations": integration_status(), "mode": "server"})
            return
        if path == "/api/agent/runs":
            self.json_response(HTTPStatus.OK, {"runs": list_agent_runs(), "integrations": integration_status()})
            return
        if path.startswith("/api/agent/runs/") and path.endswith("/export"):
            run_id = path.split("/")[4]
            run = get_agent_run(run_id)
            if not run:
                self.error_json(HTTPStatus.NOT_FOUND, "Agent run not found")
                return
            payload = {"product": "CivAgent", "exportedAt": now_iso(), "report": run, "markdown": run.get("markdownReport", "")}
            body = json.dumps(payload, indent=2).encode("utf-8")
            filename = f"{run['profile']['orgName'].lower().replace(' ', '-')}-civagent-agent-report.json"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path.startswith("/api/agent/runs/"):
            run_id = path.split("/")[4]
            run = get_agent_run(run_id)
            if not run:
                self.error_json(HTTPStatus.NOT_FOUND, "Agent run not found")
                return
            self.json_response(HTTPStatus.OK, {"run": run, "integrations": integration_status()})
            return
        if path == "/api/runs":
            self.json_response(HTTPStatus.OK, {"runs": list_runs()})
            return
        if path == "/api/audit":
            self.json_response(HTTPStatus.OK, {"audit": audit_events()})
            return
        if path.startswith("/api/runs/") and path.endswith("/export"):
            run_id = path.split("/")[3]
            run = get_run(run_id)
            if not run:
                self.error_json(HTTPStatus.NOT_FOUND, "Run not found")
                return
            payload = {"product": "CivAgent", "exportedAt": now_iso(), "report": run}
            body = json.dumps(payload, indent=2).encode("utf-8")
            filename = f"{run['profile']['orgName'].lower().replace(' ', '-')}-civagent-report.json"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path.startswith("/api/runs/"):
            run_id = path.split("/")[3]
            run = get_run(run_id)
            if not run:
                self.error_json(HTTPStatus.NOT_FOUND, "Run not found")
                return
            self.json_response(HTTPStatus.OK, {"run": run})
            return

        self.serve_static(path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/config":
            self.error_json(
                HTTPStatus.METHOD_NOT_ALLOWED,
                "CivAgent configuration is .env-only. Add required provider values to .env and restart the app.",
            )
            return
        if parsed.path == "/api/agent/runs":
            profile = None
            try:
                payload = self.read_json()
                profile = normalize_profile(payload.get("profile", payload))
                result = save_agent_run(build_real_agent_run(profile))
                self.json_response(
                    HTTPStatus.CREATED,
                    {
                        "run": result,
                        "runs": list_agent_runs(),
                        "audit": audit_events(10),
                        "integrations": integration_status(),
                        "mode": "server",
                    },
                )
            except IntegrationMissing as exc:
                record_agent_failure(profile, str(exc))
                self.error_json(HTTPStatus.SERVICE_UNAVAILABLE, str(exc))
            except (ValueError, json.JSONDecodeError) as exc:
                record_agent_failure(profile, str(exc))
                self.error_json(HTTPStatus.BAD_REQUEST, str(exc))
            except ExternalServiceError as exc:
                record_agent_failure(profile, str(exc))
                self.error_json(HTTPStatus.BAD_GATEWAY, str(exc))
            except Exception as exc:  # pragma: no cover - defensive safety net for connected services
                record_agent_failure(profile, str(exc))
                self.error_json(HTTPStatus.INTERNAL_SERVER_ERROR, f"Agent server error: {exc}")
            return
        if parsed.path != "/api/runs":
            self.error_json(HTTPStatus.NOT_FOUND, "Unknown endpoint")
            return
        try:
            payload = self.read_json()
            profile = normalize_profile(payload.get("profile", payload))
            result = save_run(simulate(profile))
            self.json_response(
                HTTPStatus.CREATED,
                {"run": result, "runs": list_runs(), "audit": audit_events(10), "mode": "server"},
            )
        except (ValueError, json.JSONDecodeError) as exc:
            self.error_json(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:  # pragma: no cover - defensive safety net for MVP server
            self.error_json(HTTPStatus.INTERNAL_SERVER_ERROR, f"Server error: {exc}")

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/runs":
            self.error_json(HTTPStatus.NOT_FOUND, "Unknown endpoint")
            return
        clear_runs()
        self.json_response(HTTPStatus.OK, {"runs": [], "audit": audit_events(10), "mode": "server"})

    def serve_static(self, path: str) -> None:
        decoded = "app.html" if path in {"/app", "/app/"} else unquote(path).lstrip("/") or "index.html"
        candidate = (STATIC_ROOT / decoded).resolve()
        if not str(candidate).startswith(str(STATIC_ROOT)) or not candidate.is_file():
            candidate = STATIC_ROOT / "index.html"
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        body = candidate.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    init_db()
    server = ThreadingHTTPServer((HOST, PORT), CivAgentHandler)
    print(f"CivAgent server running at http://{HOST}:{PORT}")
    print(f"SQLite database: {DB_PATH}")
    server.serve_forever()


if __name__ == "__main__":
    main()
