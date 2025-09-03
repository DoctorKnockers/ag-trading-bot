"""
Test the webhook monitor locally
Simulates Discord webhook calls
"""

import requests
import json
from datetime import datetime
import time
import random

def send_test_webhook(url="http://localhost:8888/webhook"):
    """Send a test webhook that mimics Discord structure."""
    
    # Sample Discord-like webhook payload
    test_payloads = [
        {
            "id": "1234567890123456789",
            "type": 0,
            "content": "🚀 New token launch: PEPE2024",
            "channel_id": "987654321098765432",
            "guild_id": "111222333444555666",
            "author": {
                "id": "555666777888999000",
                "username": "CryptoBot",
                "discriminator": "0001",
                "avatar": "abc123def456"
            },
            "embeds": [
                {
                    "title": "🔥 PEPE2024 Token Launch",
                    "url": "https://pump.fun/coin/EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                    "description": "The next big meme token is here! Get in early!",
                    "color": 5814783,
                    "fields": [
                        {
                            "name": "Contract",
                            "value": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                            "inline": True
                        },
                        {
                            "name": "Market Cap",
                            "value": "$50,000",
                            "inline": True
                        }
                    ]
                }
            ],
            "components": [
                {
                    "type": 1,
                    "components": [
                        {
                            "type": 2,
                            "label": "View on Pump.fun",
                            "style": 5,
                            "url": "https://pump.fun/coin/EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
                        },
                        {
                            "type": 2,
                            "label": "Birdeye",
                            "style": 5,
                            "url": "https://birdeye.so/token/EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
                        }
                    ]
                }
            ],
            "timestamp": datetime.now().isoformat()
        },
        {
            "id": "2345678901234567890",
            "type": 0,
            "content": "💎 Hidden gem alert! Check this out:",
            "channel_id": "987654321098765432",
            "guild_id": "111222333444555666",
            "author": {
                "id": "666777888999000111",
                "username": "AlphaHunter",
                "discriminator": "0002",
                "avatar": "def456ghi789"
            },
            "embeds": [
                {
                    "title": "New Solana Token",
                    "url": "https://solscan.io/token/So11111111111111111111111111111111111111112",
                    "description": "Low cap gem with huge potential",
                    "color": 16711680
                }
            ],
            "timestamp": datetime.now().isoformat()
        },
        {
            "id": "3456789012345678901",
            "type": 0,
            "content": "Check out this new launch on Dexscreener",
            "channel_id": "987654321098765432",
            "guild_id": "111222333444555666",
            "author": {
                "id": "777888999000111222",
                "username": "TokenTracker",
                "discriminator": "0003",
                "avatar": "ghi789jkl012"
            },
            "embeds": [],
            "components": [
                {
                    "type": 1,
                    "components": [
                        {
                            "type": 2,
                            "label": "Dexscreener",
                            "style": 5,
                            "url": "https://dexscreener.com/solana/7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr"
                        }
                    ]
                }
            ],
            "timestamp": datetime.now().isoformat()
        }
    ]
    
    # Send a random test payload
    payload = random.choice(test_payloads)
    
    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            print(f"✅ Test webhook sent successfully!")
            print(f"   Content: {payload.get('content', 'No content')[:50]}...")
        else:
            print(f"❌ Failed to send webhook: {response.status_code}")
            print(f"   Response: {response.text}")
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to webhook server. Make sure it's running on port 8888")
    except Exception as e:
        print(f"❌ Error sending webhook: {e}")

def main():
    """Send test webhooks periodically."""
    print("🚀 Starting webhook test client...")
    print("   This will send test webhooks to http://localhost:8888/webhook")
    print("   Press Ctrl+C to stop\n")
    
    try:
        while True:
            send_test_webhook()
            
            # Wait 5-15 seconds before next webhook
            wait_time = random.randint(5, 15)
            print(f"   Waiting {wait_time} seconds before next webhook...\n")
            time.sleep(wait_time)
            
    except KeyboardInterrupt:
        print("\n👋 Stopping test client...")

if __name__ == "__main__":
    main()
