# URL & Selector Rules (Launchpads embeds)

## Sources inside Discord payload
- `embeds[].url`
- Markdown in `embeds[].title|description|fields[].name|value`
- `embeds[].footer.text`
- Button components: any `components[*].*.url`
- `content` as fallback

## Known patterns
- `solscan.io/token/<MINT>` → MINT
- `birdeye.so/token/<MINT>` or `/token/SOLANA/<MINT>` → MINT
- `pump.fun/coin/<MINT>` → MINT (verify via RPC)
- `dexscreener.com/solana/<PAIR_OR_MINT>` → if pair, call Dexscreener API to map **pair→mint** (choose the non-quote side; verify via RPC)
- Query params: `token|address|mint=?` → MINT

## Base58 scrape (last resort)
Regex: `[1-9A-HJ-NP-Za-km-z]{32,44}` (validate via SPL RPC)

## Validation
- SPL owner in {Tokenkeg..., TokenzQ...}
- Parsed `type == "mint"` in `getAccountInfo(..., jsonParsed)`
