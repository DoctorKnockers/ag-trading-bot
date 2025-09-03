# 🚀 Discord Webhook Monitor Setup Guide

## Overview
This webhook monitor allows you to receive and display Discord webhook calls in real-time, helping you understand the structure of Discord messages from the Alpha Gardeners #launchpads channel.

## 📋 Quick Setup Instructions

### Step 1: Install Dependencies
```bash
pip install flask colorama requests
```

### Step 2: Start the Webhook Monitor
```bash
python webhook_monitor.py
```
The server will start on port 8888 and display incoming webhooks with colored formatting.

### Step 3: Set Up Ngrok Tunnel
Open a **new terminal** and run:
```bash
ngrok http 8888
```

You'll see output like:
```
Session Status                online
Account                       your-email@example.com
Version                       3.0.0
Region                        United States (us)
Forwarding                    https://abc123xyz.ngrok.io -> http://localhost:8888
```

**Copy the HTTPS URL** (e.g., `https://abc123xyz.ngrok.io`)

### Step 4: Configure Discord Webhook
1. Go to Discord → **Alpha Gardeners** server
2. Navigate to **#launchpads** channel
3. Right-click the channel → **Edit Channel**
4. Go to **Integrations** → **Webhooks**
5. Click **Create Webhook** or **New Webhook**
6. Set the webhook URL to: `https://your-ngrok-url.ngrok.io/webhook`
   - Replace `your-ngrok-url` with your actual ngrok URL
   - Make sure to add `/webhook` at the end!
7. Save the webhook

### Step 5: Monitor Incoming Calls
Once configured, you'll see Discord messages appear in your terminal with:
- 📨 Message content
- 👤 Author information
- 📋 Embeds (token launches, etc.)
- 🔘 Buttons (Pump.fun, Birdeye links)
- 📍 Channel and guild IDs

## 🧪 Testing Locally

To test the webhook monitor without Discord:
```bash
# In another terminal
python test_webhook_local.py
```

This will send simulated Discord webhook payloads to test the monitor.

## 📊 Monitor Features

### Colored Output
- 🟢 **Green**: New webhook received
- 🟡 **Yellow**: Timestamps and warnings
- 🔵 **Blue**: Author information
- 🟣 **Purple**: Message content
- 🔴 **Red**: Attachments
- 🟦 **Cyan**: Embeds and separators

### Data Logging
- All webhooks are logged to `webhook_log.json` for later analysis
- Last 50 webhooks are kept in memory
- Access stats at: `http://localhost:8888/stats`
- Health check at: `http://localhost:8888/health`

## 📝 Understanding Discord Webhook Structure

### Key Fields to Watch:
```json
{
  "content": "The message text",
  "author": {
    "username": "Who sent it",
    "id": "User ID"
  },
  "embeds": [
    {
      "title": "Token Launch",
      "url": "https://pump.fun/coin/...",
      "description": "Token details"
    }
  ],
  "components": [
    {
      "components": [
        {
          "type": 2,
          "label": "Button text",
          "url": "https://..."
        }
      ]
    }
  ]
}
```

### Important URLs to Extract:
- **Pump.fun**: `pump.fun/coin/{MINT_ADDRESS}`
- **Birdeye**: `birdeye.so/token/{MINT_ADDRESS}`
- **Solscan**: `solscan.io/token/{MINT_ADDRESS}`
- **Dexscreener**: `dexscreener.com/solana/{MINT_ADDRESS}`

## 🔍 Troubleshooting

### Webhook not receiving data?
1. Check ngrok is running and forwarding to port 8888
2. Verify the webhook URL ends with `/webhook`
3. Make sure the Discord webhook is active
4. Check firewall settings

### Port already in use?
```bash
# Find process using port 8888
lsof -i :8888
# Kill the process if needed
kill -9 <PID>
```

### Ngrok session expired?
Free ngrok sessions expire after 2 hours. Simply restart ngrok and update the Discord webhook URL.

## 🎯 Next Steps

Once you're receiving webhooks:
1. Analyze the message structure
2. Identify mint addresses in embeds and buttons
3. Store relevant data in your database
4. Process token launches automatically

## 📚 Additional Resources
- [Discord Webhooks Documentation](https://discord.com/developers/docs/resources/webhook)
- [Ngrok Documentation](https://ngrok.com/docs)
- [Flask Documentation](https://flask.palletsprojects.com/)

---

**Note**: This monitor is for development and testing purposes. For production, consider using a proper webhook service with authentication and error handling.
