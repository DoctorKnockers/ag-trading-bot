# ag-trading-bot — System Spec (source of truth)

## Mission
Realtime pipeline for Alpha Gardeners #launchpads calls → objective acceptance → strict 24h outcome labeling (SUSTAINED_10X) → nightly clustering → GA training → promotion → BUY/SKIP notifier (manual trading only).

## Non-negotiables
- **No text gating.** Never accept/reject based on Discord prose. Only objective facts.
- **Entry T0:** from Discord snowflake (UTC). Entry = 1m candle open spanning T0 (pref) or first trade ≥ T0 (later with Helius WSS).
- **Winner label:** `win = sustained_10x` only.
  - `SUSTAINED_10X`: price ≥ 10× entry for ≥ **180s** AND a simulated **sell** of **Q_TEST_SOL** (default 0.5 SOL) via Jupiter shows **effective slippage ≤ 15%** at the crossing.
  - `TOUCH_10X`: any tick ≥ 10× (analytics only).
- **Timezones:** All timestamps are **UTC** in DB, plus `posted_at_epoch_ms` for APIs needing epoch.

## Reject reasons (objective only)
- `INVALID_MINT` (not SPL mint / wrong owner)
- `INFINITE_MINT` (mintAuthority present)
- `FREEZE_BACKDOOR` (freezeAuthority present)
- `CONFISCATORY_FEE` (buy or sell tiny route price-impact/fee > 40%)
- `NO_POOL_AFTER_TIMEOUT` (no buy+sell routes within 30 min)
- Optional (off by default): `TEAM_CONCENTRATION` (Top5>50% or Top10>80% with reliable data)

## Dataflow (abridged)
1) **ingest/gateway_listener** → `discord_raw`
2) **ingest/mint_resolver** (URLs/buttons, pair→mint, RPC verify, pump.fun fallback) → `mint_resolution`
3) **ingest/acceptance_validator** (Jupiter quotes, SPL authorities) → `acceptance_status`
4) **outcomes/outcome_tracker** (24h monitor, dwell+executability) → `outcomes_24h`
5) **features/snapshot** (T0 features, normalized) → `features_snapshot`
6) **train/cluster_router** (K=3–4) → `strategy_clusters`
7) **train/ga_train** (temporal CV; ≥60% BUY win-rate holdout) → `strategy_params`
8) **train/cma_polish + promote** → set `active=true`
9) **signal/signal_service** → BUY/SKIP log to `signals`

## Tables (keys)
- `discord_raw(message_id PK, posted_at timestamptz UTC, posted_at_epoch_ms bigint, payload jsonb)`
- `mint_resolution(message_id PK, resolved, mint, source_url, confidence, error)`
- `acceptance_status(message_id PK, mint, first_seen, status ENUM, reason_code, evidence, pool_deadline)`
- `outcomes_24h(message_id PK, entry_price_usd, max_24h_price_usd, touch_10x, sustained_10x, win)`
- `features_snapshot(message_id PK, snapped_at, features jsonb)`
- `strategy_clusters(id PK, label, centroid jsonb, covariance jsonb)`
- `strategy_params(id PK, cluster_id FK, thresholds jsonb, weights jsonb, metrics jsonb, active)`
- `signals(id PK, message_id FK, cluster_id, strategy_id, signal ENUM, score)`

## Tunables (defaults)
- `MULTIPLE=10`, `T_DWELL_SEC=180`, `Q_TEST_SOL=0.5`, `S_MAX=0.15`
- `POOL_WAIT_TIMEOUT_SEC=1800`, `MAX_EFFECTIVE_FEE=0.40`
