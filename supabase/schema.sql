-- CivAgent Supabase schema
-- Run this in Supabase Dashboard -> SQL Editor before starting real agent runs.

create table if not exists public.agent_runs (
  id text primary key,
  workspace_id text not null,
  created_at timestamptz not null,
  status text not null,
  model text not null,
  integrations jsonb not null,
  profile jsonb not null,
  result jsonb not null,
  markdown_report text not null
);

create table if not exists public.agent_artifacts (
  id text primary key,
  run_id text not null references public.agent_runs(id) on delete cascade,
  created_at timestamptz not null,
  artifact_type text not null,
  title text not null,
  content jsonb not null
);

create table if not exists public.agent_sources (
  id text primary key,
  run_id text not null references public.agent_runs(id) on delete cascade,
  created_at timestamptz not null,
  provider text not null,
  title text not null,
  url text not null,
  snippet text not null
);

create table if not exists public.tool_calls (
  id text primary key,
  run_id text not null references public.agent_runs(id) on delete cascade,
  created_at timestamptz not null,
  tool_name text not null,
  status text not null,
  input jsonb not null,
  output jsonb not null
);

create table if not exists public.approvals (
  id text primary key,
  run_id text not null references public.agent_runs(id) on delete cascade,
  created_at timestamptz not null,
  title text not null,
  policy text not null,
  required boolean not null default true
);

create index if not exists idx_agent_runs_created on public.agent_runs(created_at desc);
create index if not exists idx_agent_artifacts_run on public.agent_artifacts(run_id);
create index if not exists idx_agent_sources_run on public.agent_sources(run_id);
create index if not exists idx_tool_calls_run on public.tool_calls(run_id);
create index if not exists idx_approvals_run on public.approvals(run_id);
