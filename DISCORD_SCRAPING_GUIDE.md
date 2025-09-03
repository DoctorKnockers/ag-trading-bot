# 📡 Discord Message Scraping Guide - COMPLIANT VERSION

## ✅ AG-Trading-Bot Compliant Message Ingestion

This guide explains the **ONLY** approved method for ingesting Discord messages from the Alpha Gardeners #launchpads channel.

## 🚫 What NOT to Do

**NEVER** use any of these forbidden approaches:
- ❌ Discord Webhooks (violates observer-only requirement)
- ❌ Discord Bots (requires bot token and permissions)
- ❌ Discord Integrations (requires admin access)
- ❌ Any POST endpoints or interactive features
- ❌ Any approach that requires Discord server permissions

## ✅ The Compliant Approach: Web Scraping

### Overview

The AG-Trading-Bot uses **web scraping** via browser automation:
- Logs into Discord web interface with credentials
- Maintains persistent session with saved cookies
- Scrapes messages directly from the web page
- No Discord API, no bots, no webhooks
- Pure web scraping - fully compliant with "observer only" requirements

### Architecture

```
Discord Web Interface (#launchpads)
         ↓
    [Browser Login]
         ↓
discord_web_scraper.py (Playwright)
         ↓
    [Save Cookies]
         ↓
    [Scrape Messages]
         ↓
PostgreSQL (discord_raw table)
         ↓
mint_resolver.py (Extract Mints)
         ↓
outcome_tracker.py (Track Results)
```

## 🔧 Setup Instructions

### 1. Set Your Discord Login Credentials

**⚠️ WARNING**: Never commit credentials to version control. Keep them in .env only.

Add to your `.env` file:
```bash
# Discord login credentials for web scraping
DISCORD_EMAIL=your_discord_email@example.com
DISCORD_PASSWORD=your_discord_password
```

The scraper will:
1. Login to Discord web interface
2. Save session cookies for future use
3. Automatically re-authenticate using saved cookies

### 2. Get Discord IDs

1. Enable Developer Mode in Discord:
   - Settings → Advanced → Developer Mode ✓

2. Get the Guild ID:
   - Right-click on "Alpha Gardeners" server
   - Click "Copy Server ID"

3. Get the Channel ID:
   - Right-click on "#launchpads" channel
   - Click "Copy Channel ID"

### 3. Configure Environment

Create a `.env` file:
```bash
# Discord Web Scraping Configuration
DISCORD_EMAIL=your_email@example.com
DISCORD_PASSWORD=your_password
DISCORD_CHANNEL_ID=123456789012345678  # #launchpads channel
DISCORD_GUILD_ID=987654321098765432    # Alpha Gardeners guild

# Database
DATABASE_URL=postgresql://localhost/ag_trading_bot

# Solana RPC
HELIUS_API_KEY=your_helius_key
BIRDEYE_API_KEY=your_birdeye_key
```

### 4. Install Browser Dependencies and Run Scraper

```bash
# Install Playwright browsers
playwright install chromium

# Start the web scraper
python ingest/discord_web_scraper.py
```

The scraper will:
1. Open a browser window (headless in production)
2. Login to Discord (or use saved cookies)
3. Navigate to #launchpads channel
4. Continuously scrape messages
5. Store in database for processing

**First Run:**
- Browser will open Discord login page
- Enter credentials (or they'll be auto-filled)
- If 2FA is enabled, enter code manually
- Session cookies are saved for next time

**Subsequent Runs:**
- Automatically uses saved cookies
- No login required unless session expires

## 📊 Message Processing Pipeline

### 1. Gateway Listener (`ingest/gateway_listener.py`)
- Connects via user session (NOT bot)
- Listens for messages in #launchpads
- Converts to raw JSON payload
- Stores in `discord_raw` table

### 2. Mint Resolver (`ingest/mint_resolver.py`)
- Reads raw messages from database
- Extracts Solana mint addresses from:
  - Embed URLs (Pump.fun, Birdeye, etc.)
  - Button components
  - Message content
- Validates mints via RPC
- Stores in `mint_resolution` table

### 3. Outcome Tracker (`outcomes/outcome_tracker.py`)
- Monitors resolved mints
- Tracks price performance
- Labels winners/losers
- Feeds training pipeline

## 🔍 Understanding Message Structure

Discord messages from #launchpads typically contain:

```json
{
  "id": "message_snowflake_id",
  "content": "🚀 New token launch!",
  "author": {
    "username": "TokenBot",
    "id": "user_id"
  },
  "embeds": [{
    "title": "Token Name",
    "url": "https://pump.fun/coin/MINT_ADDRESS",
    "description": "Token details..."
  }],
  "components": [{
    "type": 1,
    "components": [{
      "type": 2,
      "label": "View on Birdeye",
      "url": "https://birdeye.so/token/MINT_ADDRESS"
    }]
  }]
}
```

## 🛡️ Security & Compliance

### DO:
- ✅ Use user tokens for passive scraping
- ✅ Read messages only (no posting)
- ✅ Store raw payloads for audit trail
- ✅ Respect rate limits
- ✅ Handle disconnections gracefully

### DON'T:
- ❌ Share or expose user tokens
- ❌ Create Discord bots
- ❌ Set up webhooks
- ❌ Post messages or reactions
- ❌ Request server permissions

## 🐛 Troubleshooting

### "Cannot access guild"
- Ensure you're a member of Alpha Gardeners
- Check DISCORD_GUILD_ID is correct

### "Cannot access channel"
- Verify you can see #launchpads in Discord
- Check DISCORD_CHANNEL_ID is correct

### "Invalid token"
- User token may have expired
- Get a fresh token from browser

### "Connection lost"
- Normal for long-running connections
- Script will auto-reconnect

## 📝 Testing

Test the scraper without Discord:
```python
# Use the deprecated webhook test files for LOCAL TESTING ONLY
python deprecated_webhook_tests/test_webhook_local.py
```

## 🚀 Production Deployment

1. Use a dedicated Discord account for scraping
2. Run gateway_listener as a systemd service
3. Monitor logs for disconnections
4. Set up database backups
5. Never expose user tokens in logs

## 📚 Related Documentation

- `ingest/gateway_listener.py` - Main scraper implementation
- `ingest/mint_resolver.py` - Mint extraction logic
- `config/settings.py` - Configuration
- `sql/001_schema.sql` - Database schema
- `deprecated_webhook_tests/` - DO NOT USE (testing only)

## ⚖️ Legal & Compliance

This implementation:
- Complies with AG-Trading-Bot specifications
- Uses only passive, read-only access
- Requires no Discord permissions
- Maintains full audit trail
- Respects Discord Terms of Service for automation

---

**Remember**: The AG-Trading-Bot MUST use passive scraping only. Never use webhooks, bots, or any interactive Discord features. This ensures compliance, security, and reproducibility.
