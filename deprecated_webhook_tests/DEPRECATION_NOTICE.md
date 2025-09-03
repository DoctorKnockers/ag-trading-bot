# ⚠️ DEPRECATION NOTICE - DO NOT USE IN PRODUCTION

## These webhook-based files are DEPRECATED and for testing/reference only

The files in this directory (`deprecated_webhook_tests/`) are **NOT** to be used for production or live message ingestion in the AG-Trading-Bot project.

### Why These Files Are Deprecated:

1. **Compliance Violation**: Discord webhooks violate the "observer only" compliance requirement
2. **Security Risk**: Webhooks require admin/integration permissions in Discord
3. **Not Passive**: Webhooks are push-based, not passive scraping
4. **Against Spec**: The AG-Trading-Bot specification explicitly forbids webhook-based flows

### What These Files Were:

- `webhook_monitor.py` - Flask server that received webhook POST requests (FORBIDDEN)
- `test_webhook_local.py` - Local testing of webhook payloads
- `WEBHOOK_MONITOR_GUIDE.md` - Setup guide for webhooks (DO NOT FOLLOW)
- `webhook_log.json` - Sample webhook data for structure reference only

### The Correct Approach:

✅ **Use `ingest/gateway_listener.py` instead**, which implements:
- Passive Discord message scraping via user session
- Read-only access without webhooks or bots
- Compliant with AG-Trading-Bot requirements
- No Discord permissions or integrations needed

### Allowed Use Cases for These Files:

These deprecated files may ONLY be used for:
- Understanding Discord message structure
- Local testing of message processing logic
- Reference for payload formats
- Offline development without Discord access

### Production Message Ingestion:

For production, ALWAYS use the compliant passive scraping approach:
```python
# Correct way - passive scraping
from ingest.gateway_listener import DiscordMessageScraper
```

**NEVER** set up Discord webhooks, bot tokens, or integrations for this project.

---

**Last Updated**: September 2, 2025  
**Status**: PERMANENTLY DEPRECATED  
**Alternative**: Use `ingest/gateway_listener.py` for compliant message scraping
