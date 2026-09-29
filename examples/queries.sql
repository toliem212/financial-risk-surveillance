-- Vietnam Financial Risk Surveillance — example PostgreSQL queries

-- 1) Latest source-run health by worker.
select distinct on (worker)
       worker, source, status, started_at, finished_at,
       records_new, records_invalid, error_type, error_message
from source_run
order by worker, started_at desc;

-- 2) Latest observation per metric/entity.
select distinct on (metric_id, entity_id)
       metric_id, entity_id, value, unit, period_end,
       source, quality_flag, observation_method, fetched_at
from market_observation
order by metric_id, entity_id, period_end desc, fetched_at desc;

-- 3) Open higher-severity signals.
select generated_at, severity, domain, signal_type, entity_id,
       current_value, baseline_value, threshold, evidence_json
from risk_signal
where status = 'OPEN'
  and severity in ('MEDIUM','HIGH','CRITICAL')
order by case severity
           when 'CRITICAL' then 4 when 'HIGH' then 3 when 'MEDIUM' then 2 else 0
         end desc,
         generated_at desc;

-- 4) VIRA weekly-flow observations: deliberately not treated as Friday daily values.
select period_start, period_end, metric_id, value, unit,
       measure_type, frequency, observation_method, quality_flag
from market_observation
where source = 'VIRA'
  and observation_method = 'WEEKLY_AGGREGATE'
order by period_end desc, metric_id;

-- 5) Corporate-bond event timeline for one bond.
select event_date, effective_date, announced_at, event_type,
       quality_flag, event_payload, source_url
from bond_event
where bond_id = :bond_id
order by coalesce(announced_at, first_observed_at) desc;

-- 6) Strict point-in-time observations known by the pipeline at a cutoff.
select *
from market_observation
where first_observed_at <= :cutoff::timestamptz
  and fetched_at <= :cutoff::timestamptz
  and (source_published_at is null or source_published_at <= :cutoff::timestamptz)
order by period_end, fetched_at;

-- 7) Slow-moving structural context.
select metric_id, entity_id, period_end, value, unit, first_observed_at
from market_observation
where metric_id like 'SBV.MACRO.%'
order by period_end desc, metric_id;

-- 8) AI audit / cost-control usage (AI remains optional).
select date_trunc('day', created_at) as day,
       feature,
       count(*) filter (where cached_hit=false) as api_calls,
       count(*) filter (where cached_hit=true) as cache_hits,
       sum(total_tokens) as total_tokens,
       sum(estimated_cost_usd) as estimated_cost_usd
from ai_usage_log
group by 1, 2
order by 1 desc, 2;
