from __future__ import annotations

import json
import os

from .contracts import IntelligenceEnvelope


SCHEMA = """
CREATE TABLE IF NOT EXISTS control_raw_records (
 record_id TEXT PRIMARY KEY, payload_hash TEXT NOT NULL, provider TEXT NOT NULL,
 as_of TIMESTAMPTZ NOT NULL, event_id TEXT NOT NULL, route TEXT NOT NULL,
 payload JSONB NOT NULL, admitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS control_raw_route_time ON control_raw_records(route, as_of DESC);
CREATE INDEX IF NOT EXISTS control_raw_event_time ON control_raw_records(event_id, as_of DESC);
CREATE TABLE IF NOT EXISTS control_entity_aliases (
 provider TEXT NOT NULL, provider_id TEXT NOT NULL, canonical_id TEXT,
 confidence DOUBLE PRECISION NOT NULL, status TEXT NOT NULL, valid_from TIMESTAMPTZ,
 valid_to TIMESTAMPTZ, evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
 PRIMARY KEY(provider, provider_id, valid_from)
);
CREATE TABLE IF NOT EXISTS control_intelligence_events (
 intelligence_id BIGSERIAL PRIMARY KEY, record_id TEXT NOT NULL,
 model_version TEXT NOT NULL, event_type TEXT NOT NULL, effective_at TIMESTAMPTZ,
 payload JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 UNIQUE(record_id, model_version)
);
CREATE TABLE IF NOT EXISTS control_drift_reports (
 drift_id BIGSERIAL PRIMARY KEY, scope TEXT NOT NULL, action TEXT NOT NULL,
 payload JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS control_model_registry (
 model_version TEXT PRIMARY KEY, artifact_uri TEXT NOT NULL, status TEXT NOT NULL,
 metrics JSONB NOT NULL, configuration JSONB NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), promoted_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS control_replay_cursors (
 consumer TEXT PRIMARY KEY, cursor_value TEXT, payload_hash TEXT,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS control_quarantine (
 quarantine_id BIGSERIAL PRIMARY KEY, record_id TEXT, reason TEXT NOT NULL,
 payload JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), resolved_at TIMESTAMPTZ
);
"""


class CloudSqlRepository:
    def __init__(self) -> None:
        try:
            from google.cloud.sql.connector import Connector, IPTypes
            from sqlalchemy import create_engine
        except ImportError as error:
            raise RuntimeError('install with pip install -e ".[cloudsql]"') from error
        connector = Connector()
        instance = os.environ["INSTANCE_CONNECTION_NAME"]
        ip_type = IPTypes.PRIVATE if os.getenv("PRIVATE_IP", "false").lower() == "true" else IPTypes.PUBLIC
        def connect():
            options = {"user": os.environ["DB_USER"], "db": os.environ["DB_NAME"], "ip_type": ip_type,
                       "enable_iam_auth": os.getenv("DB_IAM_AUTH", "false").lower() == "true"}
            if os.getenv("DB_PASS"): options["password"] = os.environ["DB_PASS"]
            return connector.connect(instance, "pg8000", **options)
        self.engine = create_engine("postgresql+pg8000://", creator=connect, pool_size=8, max_overflow=16, pool_pre_ping=True, pool_recycle=1800)

    def initialize(self) -> None:
        # LEGACY entry point (kept for service.py's /v1/ingest and /v1/enrich).
        # Codex-T3 introduces initialize_schema() (privileged setup) and
        # assert_ready() (runtime read-only). The runtime pull path
        # (cli.py::_run_pull) uses assert_ready() exclusively — no DDL.
        # service.py's per-request initialize() call is a separate defect
        # flagged for a follow-on piece (Codex-T4); this piece does not
        # modify service.py.
        self.initialize_schema()

    def initialize_schema(self) -> None:
        """PRIVILEGED SETUP ONLY. Runs CREATE TABLE + CREATE INDEX from the
        module SCHEMA constant. Must be invoked once by a role with schema
        ownership (e.g. axiom_user in the m31 DB). The runtime pull job
        must NOT invoke this — it lacks (and must not need) DDL privileges.
        """
        from sqlalchemy import text
        with self.engine.begin() as connection:
            for statement in SCHEMA.split(";"):
                if statement.strip():
                    connection.execute(text(statement))

    def assert_ready(self) -> None:
        """RUNTIME READ-ONLY. Verifies every table + expected index the
        engine writes to is present. Raises RuntimeError with a concrete
        list of missing objects if any are absent. Zero DDL, zero writes —
        safe to call from an unprivileged runtime role (e.g. m31_user with
        INSERT/SELECT/UPDATE only).
        """
        from sqlalchemy import text
        required_tables = {
            "control_raw_records",
            "control_entity_aliases",
            "control_intelligence_events",
            "control_drift_reports",
            "control_model_registry",
            "control_replay_cursors",
            "control_quarantine",
        }
        required_indexes = {
            "control_raw_route_time",
            "control_raw_event_time",
        }
        with self.engine.begin() as connection:
            present_tables = {
                row[0] for row in connection.execute(text(
                    "SELECT tablename FROM pg_tables "
                    "WHERE schemaname = 'public' AND tablename = ANY(:names)"
                ), {"names": list(required_tables)}).all()
            }
            present_indexes = {
                row[0] for row in connection.execute(text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE schemaname = 'public' AND indexname = ANY(:names)"
                ), {"names": list(required_indexes)}).all()
            }
        missing_tables = required_tables - present_tables
        missing_indexes = required_indexes - present_indexes
        if missing_tables or missing_indexes:
            problems = []
            if missing_tables:
                problems.append(f"missing tables: {sorted(missing_tables)}")
            if missing_indexes:
                problems.append(f"missing indexes: {sorted(missing_indexes)}")
            raise RuntimeError(
                "control_* schema not ready — run initialize_schema() "
                "as a privileged role. " + "; ".join(problems)
            )

    def put_record(self, record: IntelligenceEnvelope) -> None:
        from sqlalchemy import text
        with self.engine.begin() as connection:
            connection.execute(text("""INSERT INTO control_raw_records(record_id,payload_hash,provider,as_of,event_id,route,payload)
             VALUES(:record_id,:payload_hash,:provider,:as_of,:event_id,:route,CAST(:payload AS JSONB))
             ON CONFLICT(record_id) DO NOTHING"""), {"record_id": record.record_id, "payload_hash": record.payload_hash,
             "provider": record.source.provider, "as_of": record.as_of, "event_id": record.event_id,
             "route": record.route, "payload": json.dumps(record.to_dict(), separators=(",", ":"))})

    def put_intelligence(self, record_id: str, model_version: str, result: dict) -> None:
        from sqlalchemy import text
        with self.engine.begin() as connection:
            connection.execute(text("""INSERT INTO control_intelligence_events(record_id,model_version,event_type,payload)
             VALUES(:record_id,:model_version,:event_type,CAST(:payload AS JSONB))
             ON CONFLICT(record_id,model_version) DO UPDATE SET payload=EXCLUDED.payload,created_at=NOW()"""),
             {"record_id": record_id, "model_version": model_version, "event_type": result.get("event_class", "unknown"),
              "payload": json.dumps(result, separators=(",", ":"))})

    def put_drift(self, report: dict) -> None:
        from sqlalchemy import text
        with self.engine.begin() as connection:
            connection.execute(text("INSERT INTO control_drift_reports(scope,action,payload) VALUES(:scope,:action,CAST(:payload AS JSONB))"),
             {"scope": report["scope"], "action": report["action"], "payload": json.dumps(report, separators=(",", ":"))})

    def put_quarantine(self, record_id: str | None, reason: str, payload: dict) -> None:
        from sqlalchemy import text
        with self.engine.begin() as connection:
            connection.execute(text("""INSERT INTO control_quarantine(record_id,reason,payload)
             VALUES(:record_id,:reason,CAST(:payload AS JSONB))"""),
             {"record_id": record_id, "reason": reason,
              "payload": json.dumps(payload, separators=(",", ":"))})

    def put_cursor(self, consumer: str, cursor_value: str | None, payload_hash: str | None) -> None:
        from sqlalchemy import text
        with self.engine.begin() as connection:
            connection.execute(text("""INSERT INTO control_replay_cursors(consumer,cursor_value,payload_hash,updated_at)
             VALUES(:consumer,:cursor_value,:payload_hash,NOW())
             ON CONFLICT(consumer) DO UPDATE SET cursor_value=EXCLUDED.cursor_value,payload_hash=EXCLUDED.payload_hash,updated_at=NOW()"""),
             {"consumer": consumer, "cursor_value": cursor_value, "payload_hash": payload_hash})

    def get_cursor(self, consumer: str) -> str | None:
        from sqlalchemy import text
        with self.engine.begin() as connection:
            row = connection.execute(text("SELECT cursor_value FROM control_replay_cursors WHERE consumer=:consumer"),
             {"consumer": consumer}).first()
        return row[0] if row else None
