from __future__ import annotations

import json
import sqlite3
from pathlib import Path


DDL = """
CREATE TABLE IF NOT EXISTS source_run (
    run_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    worker TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    records_downloaded INTEGER DEFAULT 0,
    records_new INTEGER DEFAULT 0,
    records_changed INTEGER DEFAULT 0,
    records_invalid INTEGER DEFAULT 0,
    last_source_timestamp TEXT,
    error_type TEXT,
    error_message TEXT,
    code_version TEXT,
    parser_version TEXT
);

CREATE TABLE IF NOT EXISTS market_observation (
    observation_id TEXT PRIMARY KEY,
    metric_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT NOT NULL,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    as_of_time TEXT,
    measure_type TEXT NOT NULL,
    frequency TEXT NOT NULL,
    source TEXT NOT NULL,
    source_url TEXT,
    source_published_at TEXT,
    first_observed_at TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    processed_at TEXT NOT NULL,
    observation_method TEXT NOT NULL,
    quality_flag TEXT NOT NULL,
    raw_object_id TEXT,
    parser_version TEXT NOT NULL,
    record_hash TEXT NOT NULL,
    dims_json TEXT,
    UNIQUE(source, metric_id, entity_id, period_start, period_end, record_hash)
);

CREATE INDEX IF NOT EXISTS idx_obs_metric_entity_period
ON market_observation(metric_id, entity_id, period_end);

CREATE TABLE IF NOT EXISTS risk_signal (
    signal_id TEXT PRIMARY KEY,
    signal_type TEXT NOT NULL,
    domain TEXT NOT NULL,
    entity_type TEXT,
    entity_id TEXT,
    generated_at TEXT NOT NULL,
    current_value REAL,
    baseline_value REAL,
    absolute_change REAL,
    relative_change REAL,
    z_score REAL,
    percentile REAL,
    threshold REAL,
    severity TEXT NOT NULL,
    evidence_json TEXT,
    status TEXT NOT NULL DEFAULT 'OPEN'
);

CREATE TABLE IF NOT EXISTS issuer_master (
    issuer_id TEXT PRIMARY KEY,
    issuer_code TEXT,
    issuer_name TEXT NOT NULL,
    normalized_name TEXT,
    sector TEXT,
    charter_capital REAL,
    first_seen_at TEXT,
    last_seen_at TEXT
);


CREATE TABLE IF NOT EXISTS bond_master (
    bond_id TEXT PRIMARY KEY,
    issuer_id TEXT,
    disclosure_code TEXT NOT NULL,
    trading_code TEXT,
    isin TEXT,
    issuer_name TEXT NOT NULL,
    face_value_vnd REAL,
    registered_quantity REAL,
    registration_status TEXT,
    first_trade_date TEXT,
    last_trade_date TEXT,
    investor_scope TEXT,
    first_seen_at TEXT,
    last_seen_at TEXT,
    UNIQUE(disclosure_code, trading_code, isin)
);

CREATE TABLE IF NOT EXISTS bond_event (
    event_id TEXT PRIMARY KEY,
    issuer_id TEXT,
    bond_id TEXT,
    event_type TEXT NOT NULL,
    event_date TEXT,
    effective_date TEXT,
    announced_at TEXT,
    first_observed_at TEXT NOT NULL,
    source TEXT NOT NULL,
    source_url TEXT,
    event_payload TEXT,
    quality_flag TEXT NOT NULL,
    event_hash TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS ai_cache (
    cache_key TEXT PRIMARY KEY,
    feature TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    response_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_usage_log (
    request_id TEXT PRIMARY KEY,
    feature TEXT NOT NULL,
    model TEXT NOT NULL,
    created_at TEXT NOT NULL,
    cached_hit INTEGER NOT NULL DEFAULT 0,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    cached_input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    estimated_cost_usd REAL,
    status TEXT NOT NULL,
    error_message TEXT,
    content_hash TEXT,
    response_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_ai_usage_created_at ON ai_usage_log(created_at);

CREATE TABLE IF NOT EXISTS project_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

"""


class SQLiteStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(DDL)

    def close(self):
        self.conn.close()

    def insert_source_run(self, row: dict) -> None:
        cols = list(row)
        sql = f"INSERT OR REPLACE INTO source_run ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})"
        self.conn.execute(sql, [row[c] for c in cols])
        self.conn.commit()

    def insert_observations(self, observations: list[dict]) -> int:
        added = 0
        for row in observations:
            cols = list(row)
            sql = f"INSERT OR IGNORE INTO market_observation ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})"
            cur = self.conn.execute(sql, [row[c] for c in cols])
            added += max(cur.rowcount, 0)
        self.conn.commit()
        return added

    def latest_observation(self, metric_id: str, entity_id: str, before_period: str | None = None):
        sql = "SELECT * FROM market_observation WHERE metric_id=? AND entity_id=?"
        args: list = [metric_id, entity_id]
        if before_period:
            sql += " AND period_end < ?"
            args.append(before_period)
        sql += " ORDER BY period_end DESC, fetched_at DESC LIMIT 1"
        row = self.conn.execute(sql, args).fetchone()
        return dict(row) if row else None


    def observations_for_period(self, *, metric_id: str, entity_id: str | None, period_end: str, source: str | None = None) -> list[dict]:
        sql = "SELECT * FROM market_observation WHERE metric_id=? AND period_end=?"
        args: list = [metric_id, period_end]
        if entity_id is not None:
            sql += " AND entity_id=?"
            args.append(entity_id)
        if source is not None:
            sql += " AND source=?"
            args.append(source)
        sql += " ORDER BY fetched_at DESC"
        rows = self.conn.execute(sql, args).fetchall()
        return [dict(r) for r in rows]

    def observations_between(self, *, metric_id: str, entity_id: str | None, start_date: str, end_date: str, source: str | None = None) -> list[dict]:
        sql = "SELECT * FROM market_observation WHERE metric_id=? AND period_end>=? AND period_end<=?"
        args: list = [metric_id, start_date, end_date]
        if entity_id is not None:
            sql += " AND entity_id=?"
            args.append(entity_id)
        if source is not None:
            sql += " AND source=?"
            args.append(source)
        sql += " ORDER BY period_end, fetched_at"
        rows = self.conn.execute(sql, args).fetchall()
        return [dict(r) for r in rows]

    def insert_signals(self, signals: list[dict]) -> int:
        added = 0
        for row in signals:
            clean = {**row}
            if isinstance(clean.get("evidence_json"), (dict, list)):
                clean["evidence_json"] = json.dumps(clean["evidence_json"], ensure_ascii=False, sort_keys=True)
            cols = list(clean)
            sql = f"INSERT OR IGNORE INTO risk_signal ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})"
            cur = self.conn.execute(sql, [clean[c] for c in cols])
            added += max(cur.rowcount, 0)
        self.conn.commit()
        return added

    def upsert_issuers(self, rows: list[dict]) -> int:
        changed = 0
        for row in rows:
            existing = self.conn.execute("SELECT issuer_id FROM issuer_master WHERE issuer_id=?", (row["issuer_id"],)).fetchone()
            cols = list(row)
            if existing:
                updates = ",".join(f"{c}=?" for c in cols if c not in {"issuer_id", "first_seen_at"})
                vals = [row[c] for c in cols if c not in {"issuer_id", "first_seen_at"}] + [row["issuer_id"]]
                self.conn.execute(f"UPDATE issuer_master SET {updates} WHERE issuer_id=?", vals)
            else:
                self.conn.execute(f"INSERT INTO issuer_master ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})", [row[c] for c in cols])
                changed += 1
        self.conn.commit()
        return changed

    def upsert_bonds(self, rows: list[dict]) -> int:
        changed = 0
        for row in rows:
            existing = self.conn.execute("SELECT bond_id FROM bond_master WHERE bond_id=?", (row["bond_id"],)).fetchone()
            cols = list(row)
            if existing:
                updates = ",".join(f"{c}=?" for c in cols if c not in {"bond_id", "first_seen_at"})
                vals = [row[c] for c in cols if c not in {"bond_id", "first_seen_at"}] + [row["bond_id"]]
                self.conn.execute(f"UPDATE bond_master SET {updates} WHERE bond_id=?", vals)
            else:
                self.conn.execute(f"INSERT INTO bond_master ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})", [row[c] for c in cols])
                changed += 1
        self.conn.commit()
        return changed

    def insert_bond_events(self, events: list[dict]) -> int:
        added = 0
        for row in events:
            clean = dict(row)
            if isinstance(clean.get("event_payload"), (dict, list)):
                clean["event_payload"] = json.dumps(clean["event_payload"], ensure_ascii=False, sort_keys=True)
            cols = list(clean)
            sql = f"INSERT OR IGNORE INTO bond_event ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})"
            cur = self.conn.execute(sql, [clean[c] for c in cols])
            added += max(cur.rowcount, 0)
        self.conn.commit()
        return added


    def replay_observation_history(self, cutoff: str, *, mode: str = "SYSTEM_KNOWN", limit: int = 10000) -> list[dict]:
        mode = mode.upper()
        if mode not in {"SYSTEM_KNOWN", "SOURCE_AVAILABLE"}:
            raise ValueError("mode must be SYSTEM_KNOWN or SOURCE_AVAILABLE")
        if mode == "SYSTEM_KNOWN":
            sql = """
            SELECT * FROM market_observation
            WHERE datetime(first_observed_at) <= datetime(?)
              AND datetime(fetched_at) <= datetime(?)
              AND (source_published_at IS NULL OR datetime(source_published_at) <= datetime(?))
            ORDER BY period_end, fetched_at
            LIMIT ?
            """
            args = [cutoff, cutoff, cutoff, limit]
        else:
            sql = """
            SELECT * FROM market_observation
            WHERE datetime(COALESCE(source_published_at, first_observed_at)) <= datetime(?)
            ORDER BY period_end, fetched_at
            LIMIT ?
            """
            args = [cutoff, limit]
        rows = self.conn.execute(sql, args).fetchall()
        return [dict(r) for r in rows]

    def replay_bond_events(self, cutoff: str, *, mode: str = "SYSTEM_KNOWN", limit: int = 5000) -> list[dict]:
        mode = mode.upper()
        if mode not in {"SYSTEM_KNOWN", "SOURCE_AVAILABLE"}:
            raise ValueError("mode must be SYSTEM_KNOWN or SOURCE_AVAILABLE")
        if mode == "SYSTEM_KNOWN":
            sql = """
            SELECT * FROM bond_event
            WHERE datetime(first_observed_at) <= datetime(?)
              AND (announced_at IS NULL OR datetime(announced_at) <= datetime(?))
            ORDER BY COALESCE(announced_at, first_observed_at), first_observed_at
            LIMIT ?
            """
            args = [cutoff, cutoff, limit]
        else:
            sql = """
            SELECT * FROM bond_event
            WHERE datetime(COALESCE(announced_at, first_observed_at)) <= datetime(?)
            ORDER BY COALESCE(announced_at, first_observed_at), first_observed_at
            LIMIT ?
            """
            args = [cutoff, limit]
        rows = self.conn.execute(sql, args).fetchall()
        return [dict(r) for r in rows]

    def replay_recorded_signals(self, cutoff: str, limit: int = 5000) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM risk_signal WHERE datetime(generated_at) <= datetime(?) ORDER BY generated_at LIMIT ?",
            (cutoff, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def replay_source_runs(self, cutoff: str, limit: int = 1000) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM source_run WHERE datetime(started_at) <= datetime(?) ORDER BY started_at DESC LIMIT ?",
            (cutoff, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def recent_bond_events(self, limit: int = 100) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM bond_event ORDER BY COALESCE(event_date, effective_date) DESC, first_observed_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def recent_bonds(self, limit: int = 100) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM bond_master ORDER BY last_seen_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_ai_cache(self, cache_key: str):
        row = self.conn.execute("SELECT * FROM ai_cache WHERE cache_key=?", (cache_key,)).fetchone()
        return dict(row) if row else None

    def put_ai_cache(self, row: dict) -> None:
        clean = dict(row)
        if isinstance(clean.get("response_json"), (dict, list)):
            clean["response_json"] = json.dumps(clean["response_json"], ensure_ascii=False, sort_keys=True)
        cols = list(clean)
        sql = f"INSERT OR REPLACE INTO ai_cache ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})"
        self.conn.execute(sql, [clean[c] for c in cols])
        self.conn.commit()

    def insert_ai_usage(self, row: dict) -> None:
        cols = list(row)
        sql = f"INSERT OR REPLACE INTO ai_usage_log ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})"
        self.conn.execute(sql, [row[c] for c in cols])
        self.conn.commit()

    def ai_usage_summary(self, since: str) -> dict:
        row = self.conn.execute(
            """
            SELECT
              SUM(CASE WHEN cached_hit=0 THEN 1 ELSE 0 END) AS api_calls,
              SUM(CASE WHEN cached_hit=1 THEN 1 ELSE 0 END) AS cache_hits,
              COALESCE(SUM(input_tokens),0) AS input_tokens,
              COALESCE(SUM(cached_input_tokens),0) AS cached_input_tokens,
              COALESCE(SUM(output_tokens),0) AS output_tokens,
              COALESCE(SUM(total_tokens),0) AS total_tokens,
              SUM(estimated_cost_usd) AS estimated_cost_usd
            FROM ai_usage_log WHERE created_at>=?
            """, (since,)
        ).fetchone()
        out = dict(row) if row else {}
        out["api_calls"] = int(out.get("api_calls") or 0)
        out["cache_hits"] = int(out.get("cache_hits") or 0)
        return out

    def recent_ai_usage(self, limit: int = 100) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM ai_usage_log ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def set_project_meta(self, key: str, value: str, updated_at: str) -> None:
        self.conn.execute(
            "INSERT INTO project_meta(key,value,updated_at) VALUES (?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, value, updated_at),
        )
        self.conn.commit()

    def get_project_meta(self, key: str):
        row = self.conn.execute("SELECT value, updated_at FROM project_meta WHERE key=?", (key,)).fetchone()
        return dict(row) if row else None

    def counts(self) -> dict:
        out = {}
        for table in ["source_run", "market_observation", "risk_signal", "issuer_master", "bond_master", "bond_event", "ai_cache", "ai_usage_log", "project_meta"]:
            out[table] = self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        return out

    def recent_observations(self, *, source: str | None = None, limit: int = 200) -> list[dict]:
        sql = "SELECT * FROM market_observation"
        args: list = []
        if source is not None:
            sql += " WHERE source=?"
            args.append(source)
        sql += " ORDER BY period_end DESC, fetched_at DESC LIMIT ?"
        args.append(limit)
        rows = self.conn.execute(sql, args).fetchall()
        return [dict(r) for r in rows]

    def recent_source_runs(self, limit: int = 20) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM source_run ORDER BY started_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_signal(self, signal_id: str):
        row = self.conn.execute("SELECT * FROM risk_signal WHERE signal_id=?", (signal_id,)).fetchone()
        return dict(row) if row else None

    def recent_signals(self, limit: int = 50) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM risk_signal ORDER BY generated_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def latest_observations(self, limit: int = 100) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT m.*
            FROM market_observation m
            JOIN (
              SELECT metric_id, entity_id, MAX(period_end || '|' || fetched_at) AS mx
              FROM market_observation
              GROUP BY metric_id, entity_id
            ) x
              ON m.metric_id=x.metric_id AND m.entity_id=x.entity_id
             AND (m.period_end || '|' || m.fetched_at)=x.mx
            ORDER BY m.metric_id, m.entity_id
            LIMIT ?
            """, (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

