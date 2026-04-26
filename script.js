const canvas = document.getElementById("field");
const ctx = canvas.getContext("2d");
const reveals = document.querySelectorAll(".reveal");
const form = document.getElementById("simForm");
const brief = document.getElementById("brief");
const runList = document.getElementById("runList");
const artifactGrid = document.getElementById("artifactGrid");
const scoreStrip = document.getElementById("scoreStrip");
const exportRunButton = document.getElementById("exportRun");
const clearRunsButton = document.getElementById("clearRuns");
const resetWorkspaceButton = document.getElementById("resetWorkspace");
const workspaceStatus = document.getElementById("workspaceStatus");
const auditList = document.getElementById("auditList");
const auditMode = document.getElementById("auditMode");
const runAgentButton = document.getElementById("runAgentButton");
const agentNotice = document.getElementById("agentNotice");
const agentMode = document.getElementById("agentMode");
const integrationGrid = document.getElementById("integrationGrid");
const agentTimeline = document.getElementById("agentTimeline");
const sourceList = document.getElementById("sourceList");
const toolList = document.getElementById("toolList");
const approvalList = document.getElementById("approvalList");
const configNotice = document.getElementById("configNotice");

const storageKey = "civagent.workspace.v1";
const defaultProfile = {
  orgName: "Northstar Labs",
  market: "Enterprise SaaS",
  stage: "Seed",
  thesis:
    "A B2B company using AI agents to qualify accounts, coordinate customer onboarding, monitor risk, and prepare executive operating decisions.",
  website: "",
  humans: 12,
  agentCount: 32,
  riskTolerance: 54,
  autonomy: "Human-supervised",
  horizon: "365"
};

let width = 0;
let height = 0;
let particles = [];
let scrollRatio = 0;
let activeRun = null;
let savedRuns = [];
let auditEvents = [];
let serverMode = false;
let integrationState = null;
let configState = null;
let agentAvailable = false;

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function createId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return `run-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function readStore() {
  try {
    return JSON.parse(localStorage.getItem(storageKey)) || {};
  } catch {
    return {};
  }
}

function writeStore(profile, runs) {
  localStorage.setItem(storageKey, JSON.stringify({ profile, runs }));
}

async function apiRequest(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options
  });
  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    throw new Error("CivAgent API is not available");
  }
  const payload = await response.json();
  if (!response.ok) {
    const error = new Error(payload.error || "CivAgent API request failed");
    error.status = response.status;
    error.payload = payload;
    throw error;
  }
  return payload;
}

function setWorkspaceMode(mode) {
  if (!workspaceStatus) return;
  const label =
    mode === "agent"
      ? "Real agent workspace"
      : mode === "server"
        ? "Server connected - .env required"
        : "Server unavailable - agent locked";
  workspaceStatus.innerHTML = "<span></span>";
  workspaceStatus.append(` ${label}`);
  if (auditMode) {
    auditMode.textContent = mode === "agent" ? "Real agent audit enabled" : mode === "server" ? "Server audit enabled" : "Local activity only";
  }
}

function getProfileFromForm() {
  const formData = new FormData(form);
  return {
    orgName: formData.get("orgName")?.toString().trim() || defaultProfile.orgName,
    market: formData.get("market")?.toString() || defaultProfile.market,
    stage: formData.get("stage")?.toString() || defaultProfile.stage,
    thesis: formData.get("thesis")?.toString().trim() || defaultProfile.thesis,
    website: formData.get("website")?.toString().trim() || "",
    humans: Number(formData.get("humans")) || defaultProfile.humans,
    agentCount: Number(formData.get("agentCount")) || defaultProfile.agentCount,
    riskTolerance: Number(formData.get("riskTolerance")) || defaultProfile.riskTolerance,
    autonomy: formData.get("autonomy")?.toString() || defaultProfile.autonomy,
    horizon: formData.get("horizon")?.toString() || defaultProfile.horizon
  };
}

function setForm(profile) {
  Object.entries(profile).forEach(([key, value]) => {
    const field = form.elements[key];
    if (field) field.value = value;
  });
  syncRangeOutputs();
}

function syncRangeOutputs() {
  document.getElementById("humanOutput").textContent = form.elements.humans.value;
  document.getElementById("agentOutput").textContent = form.elements.agentCount.value;
  document.getElementById("riskOutput").textContent = form.elements.riskTolerance.value;
}

function rolePack(market) {
  const packs = {
    "Enterprise SaaS": ["Market Scout", "Pipeline Operator", "Onboarding Architect", "Trust Sentinel"],
    "Healthcare operations": ["Care Flow Analyst", "Scheduling Operator", "Compliance Sentinel", "Patient Experience Agent"],
    "Fintech infrastructure": ["Transaction Monitor", "Risk Ledger Agent", "Revenue Operator", "Compliance Sentinel"],
    "Legal services": ["Matter Intake Agent", "Evidence Organizer", "Contract Analyst", "Partner Escalation Sentinel"],
    "Industrial logistics": ["Route Planner", "Exception Monitor", "Vendor Negotiator", "Safety Sentinel"],
    "Customer operations": ["Conversation Analyst", "Resolution Operator", "Churn Forecaster", "Quality Sentinel"]
  };
  return packs[market] || packs["Enterprise SaaS"];
}

function marketPressure(market) {
  const pressures = {
    "Enterprise SaaS": "enterprise buyers demand proof of security, ROI, and human escalation before expanding usage",
    "Healthcare operations": "clinical teams demand auditability, low-friction approvals, and patient-safe handoffs",
    "Fintech infrastructure": "customers demand stronger transaction controls and regulator-ready evidence",
    "Legal services": "clients demand confidentiality, version traceability, and partner review before delivery",
    "Industrial logistics": "operators demand exception handling across vendors, time windows, and safety constraints",
    "Customer operations": "customers demand faster resolution without losing empathy or account context"
  };
  return pressures[market] || pressures["Enterprise SaaS"];
}

function calculateRun(profile) {
  const leverageRaw = profile.agentCount / Math.max(profile.humans, 1);
  const autonomyBonus = {
    "Human-reviewed": 4,
    "Human-supervised": 10,
    "Autonomous with limits": 16
  }[profile.autonomy];
  const stagePenalty = {
    "Pre-seed": 8,
    "Seed": 4,
    "Series A": 0,
    "Growth": -2,
    "Enterprise transformation": -6
  }[profile.stage];
  const leverageScore = clamp(leverageRaw * 9, 8, 30);
  const riskDelta = Math.abs(profile.riskTolerance - 55) / 2;
  const readiness = Math.round(clamp(58 + leverageScore + autonomyBonus - riskDelta - stagePenalty, 34, 96));
  const risk = readiness >= 82 ? "Managed" : readiness >= 68 ? "Medium" : "High";
  const approvalGates = risk === "Managed" ? 3 : risk === "Medium" ? 4 : 6;
  const controlChecks = approvalGates + Math.round(profile.agentCount / 16) + 5;
  const roles = rolePack(profile.market);
  const pressure = marketPressure(profile.market);
  const horizonLabel = form.elements.horizon.selectedOptions[0]?.textContent || "12 months";
  const leverage = `1 : ${Math.max(1, Math.round(leverageRaw * 6))}`;
  const deployment = readiness >= 82 ? "Scale through governed autonomy" : readiness >= 68 ? "Pilot with approval memory" : "Stabilize controls before launch";

  return {
    id: createId(),
    createdAt: new Date().toISOString(),
    profile,
    readiness,
    risk,
    leverage,
    roles,
    pressure,
    deployment,
    approvalGates,
    controlChecks,
    horizonLabel,
    artifacts: {
      memo: [
        `${profile.orgName} should begin with ${profile.autonomy.toLowerCase()} agent deployment across ${profile.market.toLowerCase()}.`,
        `The strongest first workflow is a governed operating loop where agents prepare decisions and humans approve exceptions.`,
        `Recommended path: ${deployment.toLowerCase()} over ${horizonLabel.toLowerCase()}.`
      ],
      roster: roles.map((role, index) => `${role}: owns ${["discovery", "execution", "coordination", "risk review"][index] || "operations"} with explicit escalation rules.`),
      risks: [
        "Approval memory can become the bottleneck if decisions are not logged and reused.",
        "Customer trust may drop if agents negotiate or promise outcomes without visible accountability.",
        "Tool access should remain scoped until exception handling reaches leadership standards."
      ],
      approvalMap: [
        "Agents can draft and classify without approval.",
        "Agents need human approval for customer-impacting commitments.",
        "Finance, legal, medical, or irreversible actions stay blocked until a responsible owner approves."
      ],
      scenarios: [
        `Base case: ${pressure}.`,
        "Upside case: agent throughput creates a faster response loop than competitors can copy.",
        "Stress case: volume rises faster than managers can review edge cases."
      ],
      executive: [
        `Readiness score: ${readiness}%. Risk posture: ${risk}.`,
        `Human leverage target: ${leverage}. Control checks: ${controlChecks}.`,
        `Decision: ${deployment}.`
      ]
    }
  };
}

function renderScore(run) {
  scoreStrip.replaceChildren();
  [
    ["Readiness", `${run.readiness}%`],
    ["Human leverage", run.leverage],
    ["Risk level", run.risk]
  ].forEach(([label, value]) => {
    const card = document.createElement("div");
    const small = document.createElement("small");
    const strong = document.createElement("strong");
    small.textContent = label;
    strong.textContent = value;
    card.append(small, strong);
    scoreStrip.append(card);
  });

  document.getElementById("heroOrg").textContent = run.profile.orgName;
  document.getElementById("heroReadiness").textContent = `${run.readiness}%`;
  document.getElementById("heroLeverage").textContent = run.leverage;
  document.getElementById("heroAgents").textContent = run.roles.length;
  document.getElementById("heroRisk").textContent = run.risk;
  document.getElementById("controlCount").textContent = run.controlChecks;
  document.getElementById("approvalCount").textContent = run.approvalGates;
  document.getElementById("modelLabelA").textContent = run.profile.market;
  document.getElementById("modelLabelB").textContent = `${run.roles.length} core roles`;
  document.getElementById("modelLabelC").textContent = `${run.approvalGates} approval gates`;
  document.getElementById("governanceCopy").textContent =
    `${run.profile.orgName} is mapped for ${run.profile.autonomy.toLowerCase()} deployment with ${run.approvalGates} approval gates, ${run.controlChecks} control checks, and a ${run.risk.toLowerCase()} risk posture.`;
}

function renderBrief(run) {
  brief.replaceChildren();
  [
    ["Agent mode", run.mode === "real-agent" ? `Live Gemini ${run.model || ""}` : "Configuration preview"],
    ["Operating memo", run.artifacts.memo[0]],
    ["Agent roster", run.roles.join(", ")],
    ["Risk queue", run.artifacts.risks[0]],
    ["Deployment decision", run.deployment]
  ].forEach(([label, value]) => {
    const line = document.createElement("div");
    const labelNode = document.createElement("span");
    const valueNode = document.createElement("strong");
    line.className = "brief-line";
    labelNode.textContent = label;
    valueNode.textContent = value;
    line.append(labelNode, valueNode);
    brief.append(line);
  });
}

function renderArtifacts(run) {
  const artifactData = [
    ["01", "Company Intelligence Brief", run.artifacts.companyBrief || run.artifacts.memo],
    ["02", "Agent Team Org Chart", run.artifacts.roster],
    ["03", "Workflow Blueprint", run.artifacts.workflowBlueprint || run.artifacts.scenarios],
    ["04", "Tool Access Plan", run.artifacts.toolAccessPlan || run.artifacts.approvalMap],
    ["05", "Risk and Approval Register", [...(run.artifacts.risks || []), ...(run.artifacts.approvalMap || [])]],
    ["06", "Business Model and Moat", run.artifacts.businessModel || run.artifacts.executive],
    ["07", "Executive Brief", run.artifacts.executive]
  ];

  artifactGrid.replaceChildren();
  artifactData.forEach(([number, title, rawItems]) => {
    const items = Array.isArray(rawItems) && rawItems.length ? rawItems : ["Awaiting real agent output."];
    const article = document.createElement("article");
    const icon = document.createElement("span");
    const heading = document.createElement("h3");
    const summary = document.createElement("p");
    const list = document.createElement("ul");

    article.className = "artifact-card reveal visible";
    icon.className = "artifact-icon";
    icon.textContent = number;
    heading.textContent = title;
    summary.textContent = items[0];

    items.slice(1, 5).forEach(item => {
      const li = document.createElement("li");
      li.textContent = item;
      list.append(li);
    });

    article.append(icon, heading, summary, list);
    artifactGrid.append(article);
  });
}

function renderRuns() {
  runList.replaceChildren();
  document.getElementById("storedRuns").textContent = savedRuns.length;

  if (!savedRuns.length) {
    const empty = document.createElement("div");
    empty.className = "run-card";
    const content = document.createElement("div");
    const label = document.createElement("span");
    const title = document.createElement("strong");
    label.textContent = "No saved runs yet";
    title.textContent = agentAvailable
      ? "Run the organization agent to create your first evidence record."
      : "Complete every required .env value to unlock real agent runs.";
    content.append(label, title);
    empty.append(content);
    runList.append(empty);
    return;
  }

  savedRuns.slice(0, 5).forEach(run => {
    const card = document.createElement("div");
    const content = document.createElement("div");
    const label = document.createElement("span");
    const title = document.createElement("strong");
    const meta = document.createElement("span");
    const button = document.createElement("button");

    card.className = "run-card";
    label.textContent = new Date(run.createdAt).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
    title.textContent = `${run.profile.orgName} - ${run.deployment}`;
    meta.textContent = `${run.profile.market} | ${run.readiness}% readiness | ${run.risk} risk | ${run.mode === "real-agent" ? "real agent" : "configuration"}`;
    button.type = "button";
    button.textContent = "Load";
    button.addEventListener("click", () => {
      activeRun = run;
      setForm(run.profile);
      renderAll(run);
      writeStore(run.profile, savedRuns);
    });

    content.append(label, title, meta);
    card.append(content, button);
    runList.append(card);
  });
}

function renderAudit() {
  auditList.replaceChildren();

  if (!auditEvents.length) {
    const empty = document.createElement("div");
    empty.className = "audit-event";
    const label = document.createElement("span");
    const title = document.createElement("strong");
    const body = document.createElement("p");
    label.textContent = "No events";
    title.textContent = "Audit log is ready";
    body.textContent = "Run events will appear here when the product API records activity.";
    empty.append(label, title, body);
    auditList.append(empty);
    return;
  }

  auditEvents.slice(0, 6).forEach(event => {
    const card = document.createElement("div");
    const label = document.createElement("span");
    const title = document.createElement("strong");
    const body = document.createElement("p");
    card.className = "audit-event";
    label.textContent = new Date(event.createdAt).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
    title.textContent = event.action;
    body.textContent = event.metadata?.orgName
      ? `${event.metadata.orgName} | ${event.metadata.readiness}% readiness | ${event.metadata.risk} risk`
      : JSON.stringify(event.metadata || {});
    card.append(label, title, body);
    auditList.append(card);
  });
}

function integrationItems() {
  if (!integrationState) return [];
  return ["provider", "geminiModel", "gemini", "tavily", "supabase", "firecrawl", "composio", "e2b"]
    .map(key => ({ key, ...(integrationState[key] || {}) }))
    .filter(item => item.name);
}

function missingRequiredStatuses() {
  return integrationItems()
    .filter(item => item.required && !item.configured)
    .map(item => item.status)
    .filter(Boolean);
}

function renderIntegrations() {
  if (!integrationGrid) return;
  integrationGrid.replaceChildren();
  const items = integrationItems();
  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "integration-card missing";
    empty.textContent = "Integration status will appear when the product API is running.";
    integrationGrid.append(empty);
    return;
  }

  agentAvailable = Boolean(integrationState?.agentAvailable);
  agentMode.textContent = integrationState?.productionReady
    ? "Fully connected production stack"
    : "Required integrations locked";

  items.forEach(item => {
    const card = document.createElement("div");
    const label = document.createElement("span");
    const title = document.createElement("strong");
    const body = document.createElement("p");
    card.className = `integration-card ${item.configured ? "ready" : "missing"}`;
    label.textContent = item.configured ? "ready" : "missing/error";
    title.textContent = item.name;
    body.textContent = item.model ? `${item.status} | ${item.model}` : item.status;
    card.append(label, title, body);
    integrationGrid.append(card);
  });
}

function renderConfigStatus(config) {
  configState = config || configState;
  if (!configNotice || !configState?.values) return;

  const configuredCount = Object.values(configState.values).filter(item => item.configured).length;
  const totalCount = Object.keys(configState.values).length;
  const missing = Object.entries(configState.values)
    .filter(([, item]) => !item.configured)
    .map(([key]) => key)
    .join(", ");
  const envPath = configState.envPath ? ` Env path: ${configState.envPath}.` : "";
  configNotice.textContent = missing
    ? `${configuredCount}/${totalCount} .env values detected. Missing: ${missing}.${envPath}`
    : `${configuredCount}/${totalCount} .env values detected. Required stack ready.${envPath}`;
}

function renderAgentNotice(message) {
  if (!agentNotice) return;
  if (message) {
    agentNotice.textContent = message;
    return;
  }
  if (serverMode && agentAvailable) {
    agentNotice.textContent = "Real agent is ready: Gemini, Tavily, Supabase, Firecrawl, Composio, and E2B are configured.";
  } else if (serverMode) {
    const missing = missingRequiredStatuses();
    agentNotice.textContent = `Real agent is locked. Add missing values to .env and restart: ${missing.join("; ") || "required integrations"}.`;
  } else {
    agentNotice.textContent = "Product API is unavailable. Start the desktop backend with a complete .env file.";
  }
  if (runAgentButton) {
    runAgentButton.disabled = serverMode && !agentAvailable;
    runAgentButton.textContent = serverMode
      ? agentAvailable
        ? "Run organization agent"
        : "Complete .env to run"
      : "Server required";
  }
}

function renderAgentTimeline(run) {
  if (!agentTimeline) return;
  agentTimeline.replaceChildren();
  const steps = run?.mode === "real-agent"
    ? [
        ["01", "Research Agent", `${run.sources?.length || 0} source signals collected.`],
        ["02", "Workflow Architect", `${run.roles?.length || 0} deployable agent roles designed.`],
        ["03", "Risk Governor", `${run.approvalGates || 0} approval gates and ${run.controlChecks || 0} control checks mapped.`],
        ["04", "Venture Strategist", "Business model, launch wedge, and moat memo generated."],
        ["05", "Orchestrator", `${run.toolCalls?.length || 0} tool events recorded and report exported.`]
      ]
    : [
        ["01", "Configuration preview", "Waiting for required integrations before live research starts."],
        ["02", ".env readiness", "Gemini, Tavily, Supabase, Firecrawl, Composio, and E2B must all be present in .env or the backend environment."],
        ["03", "No local completion", "CivAgent only completes runs after every required provider succeeds."]
      ];

  steps.forEach(([number, title, body], index) => {
    const node = document.createElement("div");
    const badge = document.createElement("span");
    const strong = document.createElement("strong");
    const p = document.createElement("p");
    node.className = `agent-step ${index === 0 ? "active" : ""}`;
    badge.textContent = number;
    strong.textContent = title;
    p.textContent = body;
    node.append(badge, strong, p);
    agentTimeline.append(node);
  });
}

function renderSources(run) {
  if (!sourceList) return;
  sourceList.replaceChildren();
  const sources = run?.sources || [];
  if (!sources.length) {
    const empty = document.createElement("div");
    empty.className = "source-card";
    empty.innerHTML = "<strong>No live sources yet</strong><p>Real source evidence appears after a configured agent run.</p>";
    sourceList.append(empty);
    return;
  }
  sources.slice(0, 6).forEach(source => {
    const card = document.createElement("div");
    const title = document.createElement("strong");
    const provider = document.createElement("span");
    const body = document.createElement("p");
    card.className = "source-card";
    title.textContent = source.title || source.url || "Research source";
    provider.textContent = source.provider || "source";
    body.textContent = source.snippet || source.url || "No snippet returned.";
    card.append(provider, title, body);
    if (source.url) {
      const link = document.createElement("a");
      link.href = source.url;
      link.target = "_blank";
      link.rel = "noreferrer";
      link.textContent = "Open source";
      card.append(link);
    }
    sourceList.append(card);
  });
}

function renderToolsAndApprovals(run) {
  if (!toolList || !approvalList) return;
  toolList.replaceChildren();
  approvalList.replaceChildren();
  const calls = run?.toolCalls || [];
  if (!calls.length) {
    const empty = document.createElement("div");
    empty.className = "tool-card";
    empty.innerHTML = "<strong>No tool calls yet</strong><p>Gemini, Tavily, Firecrawl, Composio, E2B, and Supabase events appear here.</p>";
    toolList.append(empty);
  } else {
    calls.slice(0, 8).forEach(call => {
      const card = document.createElement("div");
      const title = document.createElement("strong");
      const status = document.createElement("span");
      const body = document.createElement("p");
      card.className = `tool-card ${call.status}`;
      title.textContent = call.toolName || "tool";
      status.textContent = call.status || "unknown";
      body.textContent = JSON.stringify(call.output || {}).slice(0, 240);
      card.append(status, title, body);
      toolList.append(card);
    });
  }

  const approvals = run?.approvals || [];
  approvals.slice(0, 5).forEach(approval => {
    const card = document.createElement("div");
    const title = document.createElement("strong");
    const status = document.createElement("span");
    const body = document.createElement("p");
    card.className = "approval-card";
    title.textContent = approval.title || "Approval";
    status.textContent = approval.required === false ? "advisory" : "required";
    body.textContent = approval.policy || "";
    card.append(status, title, body);
    approvalList.append(card);
  });
}

function renderAll(run) {
  renderScore(run);
  renderBrief(run);
  renderArtifacts(run);
  renderRuns();
  renderAudit();
  renderIntegrations();
  renderAgentNotice();
  renderAgentTimeline(run);
  renderSources(run);
  renderToolsAndApprovals(run);
}

function saveRun(run) {
  savedRuns = [run, ...savedRuns.filter(item => item.id !== run.id)].slice(0, 8);
  writeStore(run.profile, savedRuns);
}

async function runSimulation(event) {
  event?.preventDefault();
  const profile = getProfileFromForm();
  if (serverMode) {
    if (!agentAvailable) {
      renderAgentNotice(`Real agent is not configured yet. Add these to .env and restart: ${missingRequiredStatuses().join("; ") || "required integrations"}.`);
      return;
    }
    runAgentButton.disabled = true;
    runAgentButton.textContent = "Agent running...";
    renderAgentNotice("Running live organization agent: researching, calling tools, generating artifacts, and saving evidence.");
    try {
      const data = await apiRequest("/api/agent/runs", {
        method: "POST",
        body: JSON.stringify({ profile })
      });
      activeRun = data.run;
      savedRuns = data.runs || [activeRun];
      auditEvents = data.audit || auditEvents;
      integrationState = data.integrations || integrationState;
      agentAvailable = Boolean(integrationState?.agentAvailable);
      setForm(activeRun.profile);
      writeStore(activeRun.profile, savedRuns);
      setWorkspaceMode(agentAvailable ? "agent" : "server");
      renderAll(activeRun);
      return;
    } catch (error) {
      renderAgentNotice(error.message || "Real agent run failed. Check your .env values and server logs.");
      console.warn(error);
      renderAll(activeRun);
      return;
    } finally {
      runAgentButton.disabled = serverMode && !agentAvailable;
      runAgentButton.textContent = agentAvailable ? "Run organization agent" : "Complete .env to run";
    }
  }

  renderAgentNotice("Server is required. Start the CivAgent API with a complete .env file before running the agent.");
}

function exportActiveRun() {
  if (!activeRun) return;
  if (serverMode && activeRun.id) {
    const path = activeRun.mode === "real-agent" ? "agent/runs" : "runs";
    window.location.href = `/api/${path}/${activeRun.id}/export`;
    return;
  }
  const payload = {
    product: "CivAgent",
    exportedAt: new Date().toISOString(),
    report: activeRun
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${activeRun.profile.orgName.toLowerCase().replace(/[^a-z0-9]+/g, "-")}-civagent-report.json`;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

async function clearRuns() {
  if (!window.confirm("Clear all saved CivAgent runs from this workspace? This cannot be undone.")) return;
  if (serverMode) {
    try {
      const data = await apiRequest("/api/runs", { method: "DELETE" });
      savedRuns = data.runs || [];
      auditEvents = data.audit || [];
      writeStore(getProfileFromForm(), savedRuns);
      renderRuns();
      renderAudit();
      return;
    } catch (error) {
      serverMode = false;
      setWorkspaceMode("local");
      console.warn(error);
    }
  }
  savedRuns = [];
  writeStore(getProfileFromForm(), savedRuns);
  renderRuns();
}

function resetWorkspace() {
  setForm(defaultProfile);
  if (serverMode) {
    renderAgentNotice("Profile reset. Run the real organization agent after your .env values are configured.");
    return;
  }
  renderAgentNotice("Profile reset. Start the CivAgent API before running the organization agent.");
}

function resize() {
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  width = window.innerWidth;
  height = window.innerHeight;
  canvas.width = width * ratio;
  canvas.height = height * ratio;
  canvas.style.width = `${width}px`;
  canvas.style.height = `${height}px`;
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  particles = Array.from({ length: Math.min(90, Math.floor(width / 18)) }, () => ({
    x: Math.random() * width,
    y: Math.random() * height,
    vx: (Math.random() - 0.5) * 0.22,
    vy: (Math.random() - 0.5) * 0.18,
    r: Math.random() * 1.8 + 0.5,
    hue: Math.random() > 0.72 ? "255, 180, 84" : "82, 224, 196"
  }));
}

function drawField() {
  ctx.clearRect(0, 0, width, height);

  particles.forEach((point, index) => {
    point.x += point.vx + scrollRatio * 0.16;
    point.y += point.vy;

    if (point.x < -20) point.x = width + 20;
    if (point.x > width + 20) point.x = -20;
    if (point.y < -20) point.y = height + 20;
    if (point.y > height + 20) point.y = -20;

    ctx.beginPath();
    ctx.arc(point.x, point.y, point.r, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(${point.hue}, 0.55)`;
    ctx.fill();

    for (let j = index + 1; j < particles.length; j += 1) {
      const other = particles[j];
      const dx = point.x - other.x;
      const dy = point.y - other.y;
      const distance = Math.hypot(dx, dy);
      if (distance < 118) {
        ctx.beginPath();
        ctx.moveTo(point.x, point.y);
        ctx.lineTo(other.x, other.y);
        ctx.strokeStyle = `rgba(245, 241, 232, ${0.09 * (1 - distance / 118)})`;
        ctx.stroke();
      }
    }
  });

  requestAnimationFrame(drawField);
}

const observer = new IntersectionObserver(
  entries => {
    entries.forEach(entry => {
      if (entry.isIntersecting) entry.target.classList.add("visible");
    });
  },
  { threshold: 0.16 }
);

reveals.forEach(item => {
  const delay = item.dataset.delay;
  if (delay) item.style.setProperty("--delay", `${delay}ms`);
  observer.observe(item);
});

function revealOnScroll() {
  reveals.forEach(item => {
    const rect = item.getBoundingClientRect();
    const entersViewport = rect.top < window.innerHeight * 1.25 && rect.bottom > -160;
    if (entersViewport) item.classList.add("visible");
  });
}

function updateScroll() {
  const max = document.documentElement.scrollHeight - window.innerHeight;
  scrollRatio = max > 0 ? window.scrollY / max : 0;
  revealOnScroll();
}

function scheduleReveal() {
  requestAnimationFrame(revealOnScroll);
}

async function boot() {
  try {
    const data = await apiRequest("/api/bootstrap");
    serverMode = data.mode === "server";
    auditEvents = data.audit || [];
    integrationState = data.integrations || null;
    configState = data.config || null;
    agentAvailable = Boolean(integrationState?.agentAvailable);
    savedRuns = Array.isArray(data.agentRuns) ? data.agentRuns : [];
    const profile = { ...defaultProfile, ...(data.profile || {}) };
    setForm(profile);
    activeRun = savedRuns[0] || { ...calculateRun(profile), mode: "configuration-preview", sources: [], toolCalls: [], approvals: [] };
    setWorkspaceMode(agentAvailable ? "agent" : "server");
    writeStore(profile, savedRuns);
    renderConfigStatus(configState);
    renderAll(activeRun);
    return;
  } catch (error) {
    serverMode = false;
    setWorkspaceMode("local");
    console.warn(error);
  }

  const store = readStore();
  const profile = { ...defaultProfile, ...(store.profile || {}) };
  savedRuns = [];
  setForm(profile);
  activeRun = savedRuns[0] || { ...calculateRun(profile), mode: "configuration-preview", sources: [], toolCalls: [], approvals: [] };
  renderAll(activeRun);
}

window.addEventListener("resize", resize);
window.addEventListener("scroll", updateScroll, { passive: true });
window.addEventListener("hashchange", scheduleReveal);
window.addEventListener("load", scheduleReveal);
form.addEventListener("submit", runSimulation);
form.addEventListener("input", syncRangeOutputs);
exportRunButton.addEventListener("click", exportActiveRun);
clearRunsButton.addEventListener("click", clearRuns);
resetWorkspaceButton.addEventListener("click", resetWorkspace);

resize();
boot();
updateScroll();
revealOnScroll();
drawField();
