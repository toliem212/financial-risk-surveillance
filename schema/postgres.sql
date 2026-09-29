-- Supabase/PostgreSQL schema for Project 2 MVP.
-- Keep business keys and types aligned with src/storage/sqlite_store.py.

create table if not exists source_run (
  run_id uuid primary key,
  source text not null,
  worker text not null,
  started_at timestamptz not null,
  finished_at timestamptz,
  status text not null,
  records_downloaded integer default 0,
  records_new integer default 0,
  records_changed integer default 0,
  records_invalid integer default 0,
  last_source_timestamp timestamptz,
  error_type text,
  error_message text,
  code_version text,
  parser_version text
);

create table if not exists market_observation (
  observation_id uuid primary key,
  metric_id text not null,
  entity_type text not null,
  entity_id text not null,
  value double precision not null,
  unit text not null,
  period_start date not null,
  period_end date not null,
  as_of_time timestamptz,
  measure_type text not null check (measure_type in ('SNAPSHOT','FLOW','STOCK','AVERAGE','INDEX','EVENT')),
  frequency text not null,
  source text not null,
  source_url text,
  source_published_at timestamptz,
  first_observed_at timestamptz not null,
  fetched_at timestamptz not null,
  processed_at timestamptz not null,
  observation_method text not null,
  quality_flag text not null check (quality_flag in ('A','B','C','D','X')),
  raw_object_id text,
  parser_version text not null,
  record_hash text not null,
  dims_json jsonb,
  unique(source, metric_id, entity_id, period_start, period_end, record_hash)
);
create index if not exists idx_obs_metric_entity_period
  on market_observation(metric_id, entity_id, period_end desc);

create table if not exists risk_signal (
  signal_id uuid primary key,
  signal_type text not null,
  domain text not null,
  entity_type text,
  entity_id text,
  generated_at timestamptz not null,
  current_value double precision,
  baseline_value double precision,
  absolute_change double precision,
  relative_change double precision,
  z_score double precision,
  percentile double precision,
  threshold double precision,
  severity text not null check (severity in ('INFO','LOW','MEDIUM','HIGH','CRITICAL')),
  evidence_json jsonb,
  status text not null default 'OPEN'
);

create table if not exists issuer_master (
  issuer_id uuid primary key,
  issuer_code text,
  issuer_name text not null,
  normalized_name text,
  sector text,
  charter_capital double precision,
  first_seen_at timestamptz,
  last_seen_at timestamptz
);


create table if not exists bond_master (
  bond_id uuid primary key,
  issuer_id uuid references issuer_master(issuer_id),
  disclosure_code text not null,
  trading_code text,
  isin text,
  issuer_name text not null,
  face_value_vnd double precision,
  registered_quantity double precision,
  registration_status text,
  first_trade_date date,
  last_trade_date date,
  investor_scope text,
  first_seen_at timestamptz,
  last_seen_at timestamptz,
  unique(disclosure_code, trading_code, isin)
);
create index if not exists idx_bond_master_issuer on bond_master(issuer_id);

create table if not exists bond_event (
  event_id uuid primary key,
  issuer_id uuid references issuer_master(issuer_id),
  bond_id text,
  event_type text not null,
  event_date date,
  effective_date date,
  announced_at timestamptz,
  first_observed_at timestamptz not null,
  source text not null,
  source_url text,
  event_payload jsonb,
  quality_flag text not null check (quality_flag in ('A','B','C','D','X')),
  event_hash text not null unique
);

-- Optional AI enrichment layer. No paid API call is required for the deterministic core.
create table if not exists ai_cache (
  cache_key text primary key,
  feature text not null,
  content_hash text not null,
  model text not null,
  prompt_version text not null,
  response_json jsonb not null,
  created_at timestamptz not null
);
create index if not exists idx_ai_cache_feature_hash on ai_cache(feature, content_hash);

create table if not exists ai_usage_log (
  request_id uuid primary key,
  feature text not null,
  model text not null,
  created_at timestamptz not null,
  cached_hit boolean not null default false,
  input_tokens integer not null default 0,
  cached_input_tokens integer not null default 0,
  output_tokens integer not null default 0,
  total_tokens integer not null default 0,
  estimated_cost_usd double precision,
  status text not null,
  error_message text,
  content_hash text,
  response_id text
);
create index if not exists idx_ai_usage_created_at on ai_usage_log(created_at desc);

create table if not exists project_meta (
  key text primary key,
  value text not null,
  updated_at timestamptz not null
);

insert into project_meta(key, value, updated_at)
values ('schema_version', '1', now())
on conflict (key) do update set value=excluded.value, updated_at=excluded.updated_at;
