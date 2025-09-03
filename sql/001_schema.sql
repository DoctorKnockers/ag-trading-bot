-- AG-Trading-Bot Database Schema - MATCHES EXISTING SUPABASE SCHEMA
-- This file documents the actual schema in production
-- DO NOT RUN - Schema already exists in Supabase

-- Note: Actual schema uses text with CHECK constraints instead of ENUMs for flexibility

-- 1. Discord raw messages table (EXISTING SCHEMA)
CREATE TABLE discord_raw (
    channel_id TEXT NOT NULL,
    message_id TEXT PRIMARY KEY,
    posted_at TIMESTAMPTZ NOT NULL,
    posted_at_epoch_ms BIGINT NOT NULL,
    author_id TEXT NOT NULL,
    payload JSONB NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- Comment: "Lossless Discord payloads (UTC). UI may show HST, but this is UTC."

-- 2. Mint resolution table (EXISTING SCHEMA)
CREATE TABLE mint_resolution (
    message_id TEXT PRIMARY KEY REFERENCES discord_raw(message_id),
    resolved BOOLEAN NOT NULL,
    mint TEXT,
    source_url TEXT,
    confidence NUMERIC,
    resolved_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    error TEXT
);

-- 3. Acceptance status table (EXISTING SCHEMA)
CREATE TABLE acceptance_status (
    message_id TEXT PRIMARY KEY REFERENCES mint_resolution(message_id),
    mint TEXT NOT NULL,
    first_seen TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL CHECK (status = ANY (ARRAY['PENDING'::text, 'ACCEPT'::text, 'REJECT'::text])),
    reason_code TEXT,
    evidence JSONB,
    pool_deadline TIMESTAMPTZ NOT NULL,
    last_checked TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    claimed_by TEXT,
    claimed_at TIMESTAMPTZ
);

-- 4. Outcomes 24h table (EXISTING SCHEMA)
CREATE TABLE outcomes_24h (
    message_id TEXT PRIMARY KEY REFERENCES acceptance_status(message_id),
    entry_price_usd NUMERIC NOT NULL CHECK (entry_price_usd >= 0::numeric),
    max_24h_price_usd NUMERIC NOT NULL CHECK (max_24h_price_usd >= 0::numeric),
    touch_10x BOOLEAN NOT NULL,
    sustained_10x BOOLEAN NOT NULL,
    win BOOLEAN NOT NULL,  -- Comment: "Training label: win = sustained_10x (strict executability + dwell)."
    computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    outcomes_version INTEGER NOT NULL DEFAULT 1
);

-- Additional constraint exists: fk_outcomes_accept

-- 5. Features snapshot table (EXISTING SCHEMA)
CREATE TABLE features_snapshot (
    message_id TEXT PRIMARY KEY REFERENCES acceptance_status(message_id),
    snapped_at TIMESTAMPTZ NOT NULL,
    features JSONB NOT NULL,
    feature_version INTEGER NOT NULL DEFAULT 1
);

-- 6. Strategy clusters table (EXISTING SCHEMA)
CREATE TABLE strategy_clusters (
    id INTEGER PRIMARY KEY,  -- Note: Uses explicit IDs, not SERIAL
    label TEXT NOT NULL,
    centroid JSONB NOT NULL,
    covariance JSONB,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 7. Strategy params table (EXISTING SCHEMA)
CREATE TABLE strategy_params (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cluster_id INTEGER REFERENCES strategy_clusters(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    thresholds JSONB NOT NULL,
    weights JSONB NOT NULL,
    metrics JSONB NOT NULL,
    active BOOLEAN NOT NULL DEFAULT false,
    algo_version INTEGER NOT NULL DEFAULT 1
);

-- 8. Signals table (EXISTING SCHEMA)
CREATE TABLE signals (
    id BIGINT PRIMARY KEY DEFAULT nextval('signals_id_seq'::regclass),
    message_id TEXT REFERENCES acceptance_status(message_id),
    cluster_id INTEGER REFERENCES strategy_clusters(id),
    strategy_id UUID REFERENCES strategy_params(id),
    signal TEXT NOT NULL CHECK (signal = ANY (ARRAY['BUY'::text, 'SKIP'::text])),
    score NUMERIC,
    sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 9. Price events table (EXISTING SCHEMA)
CREATE TABLE price_events (
    id BIGINT PRIMARY KEY DEFAULT nextval('price_events_id_seq'::regclass),
    message_id TEXT REFERENCES monitor_state(message_id),
    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    kind TEXT NOT NULL,
    price_usd NUMERIC,
    notes JSONB
);

-- 10. Monitor state table (EXISTING SCHEMA)
-- Real-time monitoring state for SUSTAINED_10X tracking
CREATE TABLE monitor_state (
    message_id TEXT PRIMARY KEY REFERENCES acceptance_status(message_id),
    mint TEXT NOT NULL,
    entry_price_usd NUMERIC,
    started_at TIMESTAMPTZ NOT NULL,
    max_price_usd NUMERIC,
    above_since TIMESTAMPTZ,
    time_above_mult_s INTEGER DEFAULT 0,
    size_ok BOOLEAN DEFAULT false,
    sustained BOOLEAN DEFAULT false,
    last_seen_at TIMESTAMPTZ
);

-- 11. Rejects quarantine table (EXISTING SCHEMA)
CREATE TABLE rejects_quarantine (
    message_id TEXT PRIMARY KEY REFERENCES mint_resolution(message_id),
    mint TEXT,
    reason_code TEXT,
    evidence JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Note: The existing Supabase schema is streamlined and production-ready
-- Key differences from our original design:
-- 1. Simpler column types (TEXT vs VARCHAR with specific lengths)
-- 2. monitor_state table for real-time tracking state
-- 3. More focused outcomes_24h table
-- 4. UUID strategy_params IDs for better scalability
-- 5. Existing foreign key relationships are well-designed

-- This schema is MORE EFFECTIVE for our goals and should be kept as-is
