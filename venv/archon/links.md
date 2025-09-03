# ag-trading-bot — Curated Source Links (Core + Nice-to-have)

This page lists the authoritative docs we rely on for scraping, Solana validation, pricing/quotes, outcomes labeling, GA training, and ops. Use these for grounding code and for inline citations in PRs.

## CORE LINKS (add these to Archon as individual “Links”)



# Solana SPL / Token-2022 / RPC parsing
https://solana.com/docs/tokens
https://solana.com/docs/tokens/basics/freeze-account
https://www.helius.dev/docs/api-reference/rpc/http/getaccountinfo
https://www.helius.dev/docs/api-reference/rpc/http-methods
https://www.solana-program.com/docs/token-2022

# Routing, price, and market data (entry & executability)
https://dev.jup.ag/docs/swap-api/get-quote
https://docs.birdeye.so/
https://docs.birdeye.so/docs/per-api-rate-limit
https://docs.birdeye.so/docs/websocket
https://docs.dexscreener.com/api/reference

# GA, clustering, metrics
https://deap.readthedocs.io/
https://cma-es.github.io/apidocs-pycma/
https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html
https://scikit-learn.org/stable/modules/generated/sklearn.metrics.precision_recall_curve.html
https://en.wikipedia.org/wiki/Mahalanobis_distance

# Database & ops
https://www.postgresql.org/docs/current/explicit-locking.html
https://www.postgresql.org/docs/current/datatype-json.html
https://www.postgresql.org/docs/current/gin.html
https://www.postgresql.org/docs/current/indexes-partial.html
https://prometheus.github.io/client_python/
https://www.structlog.org/
https://magicstack.github.io/asyncpg/
https://www.python-httpx.org/
https://tenacity.readthedocs.io/

# Archon / Cursor (MCP)
https://github.com/coleam00/Archon
https://docs.cursor.com/context/model-context-protocol

## NICE-TO-HAVE (upload if you want broader context or examples)

# SPL low-level / Token-2022 repos and rust docs
https://docs.rs/spl-token/latest/spl_token/state/struct.Mint.html
https://github.com/solana-program/token-2022

# Jupiter V6 background / Postman collection
https://dev.jup.ag/docs/old/apis/swap-api
https://station.jup.ag/api-v6/get-quote  # if reachable
https://www.postman.com/solar-moon-456690/jupiter-v6-apis/collection/emussih/jupiter-apis

# DEAP paper + CMA-ES alt references
https://deap.readthedocs.io/en/master/api/algo.html
https://www.jmlr.org/papers/volume13/fortin12a/fortin12a.pdf
https://github.com/CMA-ES/pycma

# Postgres deep dives (JSONB GIN, partials)
https://www.postgresql.org/docs/current/sql-createindex.html
https://pganalyze.com/blog/gin-index
