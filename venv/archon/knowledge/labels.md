# Outcome Label Policy (strict)

## Entry (T0)
- T0 = snowflake time (UTC) from `discord_raw.message_id`.
- Entry price = **1-min candle open** that spans T0 (Birdeye). If not available, use earliest reliable price after T0 (Dexscreener fallback). Later: switch to first on-chain swap ≥ T0.

## Winner definition
- `TOUCH_10X` (analytics): max price within 24h ≥ 10× entry.
- `SUSTAINED_10X` (label): price ≥ 10× entry for **≥ 180s** **AND** a simulated sell of `Q_TEST_SOL` via Jupiter has **effective slippage ≤ 15%** at the first crossing.
- `win = sustained_10x`.

## Execution simulation
- Step 1: Quote **buy** `Q_TEST_SOL` WSOL→MINT.
- Step 2: Quote **sell** MINT→WSOL using the **outAmount** from Step 1.
- Effective fee/impact = `max(priceImpactPct_buy, priceImpactPct_sell)` normalized to fraction; must be ≤ `S_MAX=0.15`.
