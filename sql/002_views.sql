-- AG-Trading-Bot Views - MATCHES EXISTING SUPABASE VIEWS
-- This file documents the actual views in production
-- DO NOT RUN - Views already exist in Supabase

-- View: All calls with full pipeline status
CREATE OR REPLACE VIEW v_calls_all AS
SELECT 
    r.message_id,
    r.channel_id,
    r.posted_at,
    r.posted_at_epoch_ms,
    r.author_id,
    m.resolved,
    m.mint,
    m.source_url,
    m.confidence,
    a.status,
    a.reason_code,
    a.first_seen,
    a.pool_deadline
FROM discord_raw r
LEFT JOIN mint_resolution m ON m.message_id = r.message_id
LEFT JOIN acceptance_status a ON a.message_id = r.message_id;

-- View: Accepted calls only
CREATE OR REPLACE VIEW v_calls_accepted AS
SELECT 
    message_id,
    channel_id,
    posted_at,
    posted_at_epoch_ms,
    author_id,
    resolved,
    mint,
    source_url,
    confidence,
    status,
    reason_code,
    first_seen,
    pool_deadline
FROM v_calls_all
WHERE status = 'ACCEPT';

-- View: GA training data export
CREATE OR REPLACE VIEW v_ga_export AS
SELECT 
    f.message_id,
    a.mint,
    a.first_seen::date AS day,
    date_trunc('week', a.first_seen)::date AS week,
    f.snapped_at,
    f.features,
    o.win,
    o.touch_10x,
    o.sustained_10x
FROM features_snapshot f
JOIN acceptance_status a ON a.message_id = f.message_id
LEFT JOIN outcomes_24h o ON o.message_id = f.message_id
WHERE a.status = 'ACCEPT';

-- View: Outcomes with acceptance info
CREATE OR REPLACE VIEW v_outcomes_join AS
SELECT 
    a.message_id,
    a.mint,
    a.first_seen,
    o.entry_price_usd,
    o.max_24h_price_usd,
    o.touch_10x,
    o.sustained_10x,
    o.win,
    o.computed_at
FROM acceptance_status a
JOIN outcomes_24h o ON o.message_id = a.message_id
WHERE a.status = 'ACCEPT';

-- Note: The existing Supabase views are well-designed and focused
-- They provide exactly what's needed for:
-- 1. Pipeline monitoring (v_calls_all, v_calls_accepted)
-- 2. ML training data export (v_ga_export)
-- 3. Outcome analysis (v_outcomes_join)
--
-- These views are MORE EFFECTIVE than our original complex design
-- and should be kept as-is for production use.