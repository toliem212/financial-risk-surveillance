from __future__ import annotations

import json
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


class PostgresStore:
    """PostgreSQL/Supabase storage backend matching the SQLiteStore contract."""

    def __init__(self, database_url: str):
        if not database_url:
            raise ValueError("DATABASE_URL is required for PostgresStore")
        self.conn = psycopg.connect(database_url, row_factory=dict_row, prepare_threshold=None)

    def close(self):
        self.conn.close()

    @staticmethod
    def _json_value(value: Any):
        if value is None:
            return None
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                return Jsonb({"raw": value})
        return Jsonb(value)

    def insert_source_run(self, row: dict) -> None:
        cols = list(row)
        values = [row[c] for c in cols]
        placeholders = ",".join(["%s"] * len(cols))
        updates = ",".join(f"{c}=EXCLUDED.{c}" for c in cols if c != "run_id")
        sql = (
            f"INSERT INTO source_run ({','.join(cols)}) VALUES ({placeholders}) "
            f"ON CONFLICT (run_id) DO UPDATE SET {updates}"
        )
        with self.conn.cursor() as cur:
            cur.execute(sql, values)
        self.conn.commit()

    def insert_observations(self, observations: list[dict]) -> int:
        added = 0
        with self.conn.cursor() as cur:
            for row in observations:
                clean = dict(row)
                clean["dims_json"] = self._json_value(clean.get("dims_json"))
                cols = list(clean)
                placeholders = ",".join(["%s"] * len(cols))
                sql = (
                    f"INSERT INTO market_observation ({','.join(cols)}) VALUES ({placeholders}) "
                    "ON CONFLICT (source, metric_id, entity_id, period_start, period_end, record_hash) "
                    "DO NOTHING RETURNING observation_id"
                )
                cur.execute(sql, [clean[c] for c in cols])
                if cur.fetchone() is not None:
                    added += 1
        self.conn.commit()
        return added

    def latest_observation(self, metric_id: str, entity_id: str, before_period: str | None = None):
        sql = "SELECT * FROM market_observation WHERE metric_id=%s AND entity_id=%s"
        args: list[Any] = [metric_id, entity_id]
        if before_period:
            sql += " AND period_end < %s"
            args.append(before_period)
        sql += " ORDER BY period_end DESC, fetched_at DESC LIMIT 1"
        with self.conn.cursor() as cur:
            cur.execute(sql, args)
            return cur.fetchone()


    def observations_for_period(self, *, metric_id: str, entity_id: str | None, period_end: str, source: str | None = None) -> list[dict]:
        sql = "SELECT * FROM market_observation WHERE metric_id=%s AND period_end=%s"
        args: list[Any] = [metric_id, period_end]
        if entity_id is not None:
            sql += " AND entity_id=%s"
            args.append(entity_id)
        if source is not None:
            sql += " AND source=%s"
            args.append(source)
        sql += " ORDER BY fetched_at DESC"
        with self.conn.cursor() as cur:
            cur.execute(sql, args)
            return list(cur.fetchall())

    def observations_between(self, *, metric_id: str, entity_id: str | None, start_date: str, end_date: str, source: str | None = None) -> list[dict]:
        sql = "SELECT * FROM market_observation WHERE metric_id=%s AND period_end>=%s AND period_end<=%s"
        args: list[Any] = [metric_id, start_date, end_date]
        if entity_id is not None:
            sql += " AND entity_id=%s"
            args.append(entity_id)
        if source is not None:
            sql += " AND source=%s"
            args.append(source)
        sql += " ORDER BY period_end, fetched_at"
        with self.conn.cursor() as cur:
            cur.execute(sql, args)
            return list(cur.fetchall())

    def insert_signals(self, signals: list[dict]) -> int:
        added = 0
        with self.conn.cursor() as cur:
            for row in signals:
                clean = dict(row)
                clean["evidence_json"] = self._json_value(clean.get("evidence_json"))
                cols = list(clean)
                placeholders = ",".join(["%s"] * len(cols))
                sql = (
                    f"INSERT INTO risk_signal ({','.join(cols)}) VALUES ({placeholders}) "
                    "ON CONFLICT (signal_id) DO NOTHING RETURNING signal_id"
                )
                cur.execute(sql, [clean[c] for c in cols])
                if cur.fetchone() is not None:
                    added += 1
        self.conn.commit()
        return added

    def upsert_issuers(self, rows: list[dict]) -> int:
        changed = 0
        with self.conn.cursor() as cur:
            for row in rows:
                cols = list(row)
                placeholders = ",".join(["%s"] * len(cols))
                updates = ",".join(f"{c}=EXCLUDED.{c}" for c in cols if c not in {"issuer_id", "first_seen_at"})
                sql = (f"INSERT INTO issuer_master ({','.join(cols)}) VALUES ({placeholders}) "
                       f"ON CONFLICT (issuer_id) DO UPDATE SET {updates} "
                       "RETURNING (xmax = 0) AS inserted")
                cur.execute(sql, [row[c] for c in cols])
                res = cur.fetchone()
                if res and res["inserted"]:
                    changed += 1
        self.conn.commit()
        return changed

    def upsert_bonds(self, rows: list[dict]) -> int:
        changed = 0
        with self.conn.cursor() as cur:
            for row in rows:
                cols = list(row)
                placeholders = ",".join(["%s"] * len(cols))
                updates = ",".join(f"{c}=EXCLUDED.{c}" for c in cols if c not in {"bond_id", "first_seen_at"})
                sql = (f"INSERT INTO bond_master ({','.join(cols)}) VALUES ({placeholders}) "
                       f"ON CONFLICT (bond_id) DO UPDATE SET {updates} "
                       "RETURNING (xmax = 0) AS inserted")
                cur.execute(sql, [row[c] for c in cols])
                res = cur.fetchone()
                if res and res["inserted"]:
                    changed += 1
        self.conn.commit()
        return changed

    def insert_bond_events(self, events: list[dict]) -> int:
        added = 0
        with self.conn.cursor() as cur:
            for row in events:
                clean = dict(row)
                clean["event_payload"] = self._json_value(clean.get("event_payload"))
                cols = list(clean)
                placeholders = ",".join(["%s"] * len(cols))
                sql = (f"INSERT INTO bond_event ({','.join(cols)}) VALUES ({placeholders}) "
                       "ON CONFLICT (event_hash) DO NOTHING RETURNING event_id")
                cur.execute(sql, [clean[c] for c in cols])
                if cur.fetchone() is not None:
                    added += 1
        self.conn.commit()
        return added


    def replay_observation_history(self, cutoff: str, *, mode: str = "SYSTEM_KNOWN", limit: int = 10000) -> list[dict]:
        mode = mode.upper()
        if mode not in {"SYSTEM_KNOWN", "SOURCE_AVAILABLE"}:
            raise ValueError("mode must be SYSTEM_KNOWN or SOURCE_AVAILABLE")
        if mode == "SYSTEM_KNOWN":
            sql = """
            SELECT * FROM market_observation
            WHERE first_observed_at <= %s::timestamptz
              AND fetched_at <= %s::timestamptz
              AND (source_published_at IS NULL OR source_published_at <= %s::timestamptz)
            ORDER BY period_end, fetched_at
            LIMIT %s
            """
            args = [cutoff, cutoff, cutoff, limit]
        else:
            sql = """
            SELECT * FROM market_observation
            WHERE COALESCE(source_published_at, first_observed_at) <= %s::timestamptz
            ORDER BY period_end, fetched_at
            LIMIT %s
            """
            args = [cutoff, limit]
        with self.conn.cursor() as cur:
            cur.execute(sql, args)
            return list(cur.fetchall())

    def replay_bond_events(self, cutoff: str, *, mode: str = "SYSTEM_KNOWN", limit: int = 5000) -> list[dict]:
        mode = mode.upper()
        if mode not in {"SYSTEM_KNOWN", "SOURCE_AVAILABLE"}:
            raise ValueError("mode must be SYSTEM_KNOWN or SOURCE_AVAILABLE")
        if mode == "SYSTEM_KNOWN":
            sql = """
            SELECT * FROM bond_event
            WHERE first_observed_at <= %s::timestamptz
              AND (announced_at IS NULL OR announced_at <= %s::timestamptz)
            ORDER BY COALESCE(announced_at, first_observed_at), first_observed_at
            LIMIT %s
            """
            args = [cutoff, cutoff, limit]
        else:
            sql = """
            SELECT * FROM bond_event
            WHERE COALESCE(announced_at, first_observed_at) <= %s::timestamptz
            ORDER BY COALESCE(announced_at, first_observed_at), first_observed_at
            LIMIT %s
            """
            args = [cutoff, limit]
        with self.conn.cursor() as cur:
            cur.execute(sql, args)
            return list(cur.fetchall())

    def replay_recorded_signals(self, cutoff: str, limit: int = 5000) -> list[dict]:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM risk_signal WHERE generated_at <= %s::timestamptz ORDER BY generated_at LIMIT %s",
                (cutoff, limit),
            )
            return list(cur.fetchall())

    def replay_source_runs(self, cutoff: str, limit: int = 1000) -> list[dict]:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM source_run WHERE started_at <= %s::timestamptz ORDER BY started_at DESC LIMIT %s",
                (cutoff, limit),
            )
            return list(cur.fetchall())

    def recent_bond_events(self, limit: int = 100) -> list[dict]:
        with self.conn.cursor() as cur:
            cur.execute("SELECT * FROM bond_event ORDER BY COALESCE(event_date, effective_date) DESC NULLS LAST, first_observed_at DESC LIMIT %s", (limit,))
            return list(cur.fetchall())

    def recent_bonds(self, limit: int = 100) -> list[dict]:
        with self.conn.cursor() as cur:
            cur.execute("SELECT * FROM bond_master ORDER BY last_seen_at DESC NULLS LAST LIMIT %s", (limit,))
            return list(cur.fetchall())

    def get_ai_cache(self, cache_key: str):
        with self.conn.cursor() as cur:
            cur.execute("SELECT * FROM ai_cache WHERE cache_key=%s", (cache_key,))
            return cur.fetchone()

    def put_ai_cache(self, row: dict) -> None:
        clean = dict(row)
        clean["response_json"] = self._json_value(clean.get("response_json"))
        cols = list(clean)
        placeholders = ",".join(["%s"] * len(cols))
        updates = ",".join(f"{c}=EXCLUDED.{c}" for c in cols if c != "cache_key")
        sql = f"INSERT INTO ai_cache ({','.join(cols)}) VALUES ({placeholders}) ON CONFLICT (cache_key) DO UPDATE SET {updates}"
        with self.conn.cursor() as cur:
            cur.execute(sql, [clean[c] for c in cols])
        self.conn.commit()

    def insert_ai_usage(self, row: dict) -> None:
        cols = list(row)
        placeholders = ",".join(["%s"] * len(cols))
        updates = ",".join(f"{c}=EXCLUDED.{c}" for c in cols if c != "request_id")
        sql = f"INSERT INTO ai_usage_log ({','.join(cols)}) VALUES ({placeholders}) ON CONFLICT (request_id) DO UPDATE SET {updates}"
        with self.conn.cursor() as cur:
            cur.execute(sql, [row[c] for c in cols])
        self.conn.commit()

    def ai_usage_summary(self, since: str) -> dict:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  COUNT(*) FILTER (WHERE cached_hit=false) AS api_calls,
                  COUNT(*) FILTER (WHERE cached_hit=true) AS cache_hits,
                  COALESCE(SUM(input_tokens),0) AS input_tokens,
                  COALESCE(SUM(cached_input_tokens),0) AS cached_input_tokens,
                  COALESCE(SUM(output_tokens),0) AS output_tokens,
                  COALESCE(SUM(total_tokens),0) AS total_tokens,
                  SUM(estimated_cost_usd) AS estimated_cost_usd
                FROM ai_usage_log WHERE created_at >= %s::timestamptz
                """, (since,)
            )
            row = cur.fetchone() or {}
            return dict(row)

    def recent_ai_usage(self, limit: int = 100) -> list[dict]:
        with self.conn.cursor() as cur:
            cur.execute("SELECT * FROM ai_usage_log ORDER BY created_at DESC LIMIT %s", (limit,))
            return list(cur.fetchall())

    def set_project_meta(self, key: str, value: str, updated_at: str) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO project_meta(key,value,updated_at) VALUES (%s,%s,%s::timestamptz) "
                "ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value, updated_at=EXCLUDED.updated_at",
                (key, value, updated_at),
            )
        self.conn.commit()

    def get_project_meta(self, key: str):
        with self.conn.cursor() as cur:
            cur.execute("SELECT value, updated_at FROM project_meta WHERE key=%s", (key,))
            return cur.fetchone()

    def counts(self) -> dict:
        out = {}
        with self.conn.cursor() as cur:
            for table in ["source_run", "market_observation", "risk_signal", "issuer_master", "bond_master", "bond_event", "ai_cache", "ai_usage_log", "project_meta"]:
                cur.execute(f"SELECT COUNT(*) AS n FROM {table}")
                out[table] = cur.fetchone()["n"]
        return out


    def recent_observations(self, *, source: str | None = None, limit: int = 200) -> list[dict]:
        sql = "SELECT * FROM market_observation"
        args: list[Any] = []
        if source is not None:
            sql += " WHERE source=%s"
            args.append(source)
        sql += " ORDER BY period_end DESC, fetched_at DESC LIMIT %s"
        args.append(limit)
        with self.conn.cursor() as cur:
            cur.execute(sql, args)
            return list(cur.fetchall())

    def recent_source_runs(self, limit: int = 20) -> list[dict]:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM source_run ORDER BY started_at DESC LIMIT %s",
                (limit,),
            )
            return list(cur.fetchall())

    def get_signal(self, signal_id: str):
        with self.conn.cursor() as cur:
            cur.execute("SELECT * FROM risk_signal WHERE signal_id=%s", (signal_id,))
            return cur.fetchone()

    def recent_signals(self, limit: int = 50) -> list[dict]:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM risk_signal ORDER BY generated_at DESC LIMIT %s",
                (limit,),
            )
            return list(cur.fetchall())

    def latest_observations(self, limit: int = 100) -> list[dict]:
        sql = """
        SELECT DISTINCT ON (metric_id, entity_id)
            *
        FROM market_observation
        ORDER BY metric_id, entity_id, period_end DESC, fetched_at DESC
        LIMIT %s
        """
        with self.conn.cursor() as cur:
            cur.execute(sql, (limit,))
            return list(cur.fetchall())
