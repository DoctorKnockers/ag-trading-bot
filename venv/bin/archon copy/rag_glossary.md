
---

# File 2: `archon/knowledge/rag_glossary.md`

> Paste exactly as-is.

```markdown
# ag-trading-bot — RAG Glossary & Guardrails

**Purpose:** keep assistants aligned on definitions, thresholds, and what *not* to do.

## Core labels & timing
- **T0**: Discord message snowflake time (UTC). Entry candle = 1-min candle **spanning T0**.
- **TOUCH_10X**: any price within 24h ≥ 10× entry (analytics only).
- **SUSTAINED_10X (label)**: price ≥ 10× entry for ≥ **180s** **AND** simulated sell of **Q_TEST_SOL=0.5 SOL** via Jupiter shows **effective slippage ≤ 15%** at the first crossing. **win = sustained_10x**.
- **Executability test**: Quote WSOL→MINT (buy), then MINT→WSOL (sell) using outAmount; effective fee/impact = max(priceImpactPct_buy, priceImpactPct_sell).

## Objective rejects (store REJECT with reason)
- `INVALID_MINT`: not an SPL Mint or wrong owner program.
- `INFINITE_MINT`: `mintAuthority` present (unfixed supply).
- `FREEZE_BACKDOOR`: `freezeAuthority` present.
- `CONFISCATORY_FEE`: tiny-route price impact/fees > 40%.
- `NO_POOL_AFTER_TIMEOUT`: no buy+sell routes within 30 min.
- Optional flags (off by default): `TEAM_CONCENTRATION`.

## Data sources (preferred order)
- **Mint discovery**: Links in embed → Solscan/Birdeye/pump.fun; Dexscreener pair→mint; last-resort Base58 regex + RPC verify.
- **Entry & history**: Birdeye OHLCV; Dexscreener fallback.
- **Quotes**: Jupiter Get Quote API (both directions).
- **RPC**: Helius `getAccountInfo` jsonParsed for SPL fields.

## Guardrails
- Never accept/reject based on Discord prose. Only objective tests above.
- All times in DB are UTC; store `posted_at_epoch_ms` as well.
- Training features are **T0-only** (no leakage).
- Final product emits **BUY/SKIP** only after GA promotion (≥60% BUY precision on holdout).

## Training & promotion
- Temporal blocked CV (TimeSeriesSplit). Aggregate by **worst-fold**.
- Nightly clustering (K=3–4); OOD if distance > τ (e.g., 97.5%).
- Promotion gate: holdout BUY precision ≥ 60%, buy-rate within band, min picks/day met; shadow 1–2 days before activation.
