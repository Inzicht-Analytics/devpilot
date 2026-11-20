-- PROPOSAL ONLY. Do not apply without separate Supabase project and review.
create schema if not exists devpilot_private;
create table if not exists devpilot_private.tasks (
 id uuid primary key default gen_random_uuid(),
 repository text not null, title text not null,
 status text not null default 'queued' check(status in ('queued','planning','blocked','awaiting_approval','completed','failed','cancelled')),
 created_at timestamptz not null default now()
);
create table if not exists devpilot_private.approvals (
 id uuid primary key default gen_random_uuid(),
 task_id uuid not null references devpilot_private.tasks(id),
 action text not null, status text not null default 'pending'
 check(status in ('pending','approved','rejected')),
 decided_at timestamptz
);
create table if not exists devpilot_private.audit_events (
 id bigint generated always as identity primary key,
 task_id uuid references devpilot_private.tasks(id),
 event_type text not null, details jsonb not null default '{}'::jsonb,
 created_at timestamptz not null default now()
);
revoke all on schema devpilot_private from public, anon, authenticated;
revoke all on all tables in schema devpilot_private from public, anon, authenticated;
alter table devpilot_private.tasks enable row level security;
alter table devpilot_private.approvals enable row level security;
alter table devpilot_private.audit_events enable row level security;
