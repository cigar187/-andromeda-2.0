CREATE SCHEMA IF NOT EXISTS trade_one_core;
CREATE SCHEMA IF NOT EXISTS trade_one_models;
CREATE SCHEMA IF NOT EXISTS trade_one_intelligence;
CREATE SCHEMA IF NOT EXISTS trade_one_audit;

CREATE TABLE IF NOT EXISTS trade_one_models.component_registry (
    component_id TEXT NOT NULL,
    version TEXT NOT NULL,
    contract_version TEXT NOT NULL,
    kind TEXT NOT NULL,
    artifact_uri TEXT,
    artifact_sha256 TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL CHECK (status IN ('candidate','challenger','champion','retired','blocked')),
    manifest JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    promoted_at TIMESTAMPTZ,
    PRIMARY KEY (component_id, version, artifact_sha256)
);

CREATE TABLE IF NOT EXISTS trade_one_models.compositions (
    composition_id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    contract_version TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('pregame','live')),
    slots JSONB NOT NULL,
    configuration_sha256 TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('candidate','challenger','champion','retired')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS trade_one_one_champion_per_mode
ON trade_one_models.compositions(mode) WHERE status = 'champion';

CREATE TABLE IF NOT EXISTS trade_one_intelligence.responses (
    trace_id TEXT PRIMARY KEY,
    contract_version TEXT NOT NULL,
    request_id TEXT NOT NULL,
    mode TEXT NOT NULL,
    game_id TEXT NOT NULL,
    market_id TEXT NOT NULL,
    as_of TIMESTAMPTZ NOT NULL,
    state_revision BIGINT NOT NULL,
    composition_id UUID,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (composition_id) REFERENCES trade_one_models.compositions(composition_id)
);

CREATE INDEX IF NOT EXISTS trade_one_response_game_time
ON trade_one_intelligence.responses(game_id, as_of DESC);

CREATE TABLE IF NOT EXISTS trade_one_audit.component_events (
    audit_id BIGSERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    component_id TEXT,
    component_version TEXT,
    before_value JSONB,
    after_value JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Cloud SQL stores operational state and lineage. Raw provider payloads,
-- high-volume live events, and model artifacts belong in object storage.

