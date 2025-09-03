# GA Training & Promotion

## Splits
- Temporal blocked CV (e.g., 5 folds by day/week). Group by `mint`. Holdout = most recent block not used in training.

## Genome (ranges)
- thresholds: `min_liq_usd[0,1e7]`, `max_effective_fee[0,0.5]`, `min_smart_wallets[0,10]`, `max_top10_pct[0.3,1.0]`, `buy_cut[0.5,0.95]`
- weights: `liq[0,2]`, `honeypot[0,2]`, `smart[0,2]`, `sent[0,1]`, `holders[0,1]`, `age[-1,1]`, `vol2mc[-1,1]`
- gates: booleans like `route_diversity_ge2`

Enforce monotonicity where obvious (higher liquidity shouldn’t reduce score).

## Fitness (maximize precision on BUYs)
- Obj1: **− BUY win-rate** (precision)  → higher is better
- Obj2: **|buy_rate − target|** (target ~ 5–20%)
- Obj3: **− picks/day** (tie-break; prefer not too sparse)

Aggregate per candidate by **worst-fold** (or 5th percentile).

## Promotion gate
- Holdout **BUY win-rate ≥ 60%**, buy-rate within band, min picks (≥30). Enable **shadow** for 1–2 days before activation.

## Router & OOD
- Nightly k-means K=3–4; persist centroids/variance.
- At runtime: assign cluster; if distance > τ (e.g., 97.5% train dist), mark OOD (down-weight or suppress BUY).
