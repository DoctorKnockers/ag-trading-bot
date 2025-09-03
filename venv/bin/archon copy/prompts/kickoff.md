You are building **ag-trading-bot**. Use the Archon MCP ("archon") as your primary knowledge source.
Before coding, fetch:
- archon/knowledge/spec.md
- archon/knowledge/labels.md
- archon/knowledge/selectors.md
- archon/knowledge/ga.md
- archon/tasks.yaml

Follow `tasks.yaml` in order. Never gate coins by Discord text. Reject only objective reasons listed in spec. The winner label is **SUSTAINED_10X** with dwell 180s and executability via Jupiter Q_TEST_SOL=0.5, S_MAX=0.15. All times UTC, T0 from snowflake.

Start by generating:
1) `sql/001_schema.sql`, `sql/002_outcomes_10x.sql`, `sql/003_views_exports.sql` (match the DB we already installed; idempotent).
2) `ingest/mint_resolver.py` and `ingest/acceptance_validator.py` as per spec.

Add minimal tests for URL parsing, SPL authority checks, and the 10× dwell logic using mocks.
