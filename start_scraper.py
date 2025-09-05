#!/usr/bin/env python3
"""
Simple Discord scraper starter that works around async/signal issues.
Uses subprocess to start the web scraper in a separate process.
"""

import subprocess
import sys
import time
import psycopg2
from dotenv import load_dotenv

from config import settings

load_dotenv()


def test_database():
    """Test database connection."""
    try:
        conn = psycopg2.connect(settings.DATABASE_URL)
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM discord_raw")
            count = cur.fetchone()[0]
        conn.close()
        
        print(f"✅ Database connected: {count} messages in discord_raw")
        return True
    except Exception as e:
        print(f"❌ Database error: {e}")
        return False


def start_scraper():
    """Start the Discord web scraper."""
    print("🚀 Starting AG-Trading-Bot Discord Web Scraper")
    print("=" * 50)
    
    # Validate setup
    print("🔧 Checking configuration...")
    if not settings.validate_config():
        print("❌ Configuration validation failed")
        return
    
    print("✅ Configuration valid")
    
    # Test database
    if not test_database():
        print("❌ Database connection failed")
        return
    
    print("✅ Database connected")
    
    # Show target info
    print(f"\n🎯 Target Configuration:")
    print(f"  Discord User: {settings.DISCORD_USERNAME}")
    print(f"  Alpha Gardeners Guild: {settings.DISCORD_GUILD_ID}")
    print(f"  #launchpads Channel: {settings.DISCORD_CHANNEL_ID}")
    
    target_url = f"https://discord.com/channels/{settings.DISCORD_GUILD_ID}/{settings.DISCORD_CHANNEL_ID}"
    print(f"  Direct URL: {target_url}")
    
    print(f"\n📡 Starting Discord Web Scraper...")
    print("  - Browser will open automatically")
    print("  - Login with your credentials if prompted")  
    print("  - Session will be saved for future runs")
    print("  - Watch console for scraped messages")
    print("  - Press Ctrl+C to stop")
    
    try:
        # Start the scraper subprocess
        result = subprocess.run([
            sys.executable, 
            "ingest/discord_web_scraper.py"
        ], cwd=".")
        
        print(f"\n📊 Scraper exited with code: {result.returncode}")
        
    except KeyboardInterrupt:
        print("\n🛑 Scraper stopped by user")
    except Exception as e:
        print(f"\n❌ Error starting scraper: {e}")


def show_recent_activity():
    """Show recent scraping activity."""
    try:
        conn = psycopg2.connect(settings.DATABASE_URL)
        with conn.cursor() as cur:
            # Check message counts
            cur.execute("SELECT COUNT(*) FROM discord_raw")
            total_messages = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM mint_resolution WHERE resolved = true")
            resolved_mints = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM acceptance_status WHERE status = 'ACCEPT'")
            accepted = cur.fetchone()[0]
            
            print(f"\n📊 Current Pipeline Status:")
            print(f"  Discord messages: {total_messages}")
            print(f"  Resolved mints: {resolved_mints}")
            print(f"  Accepted calls: {accepted}")
            
            # Show recent messages
            if total_messages > 0:
                cur.execute("""
                    SELECT message_id, posted_at, payload->>'content'
                    FROM discord_raw 
                    ORDER BY inserted_at DESC 
                    LIMIT 3
                """)
                
                recent = cur.fetchall()
                print(f"\n📋 Recent Messages:")
                for msg_id, posted_at, content in recent:
                    content_preview = (content or '')[:50]
                    print(f"  {msg_id}: {content_preview}...")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Database query error: {e}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="AG-Trading-Bot Discord Scraper")
    parser.add_argument("--stats", action="store_true", help="Show current stats only")
    
    args = parser.parse_args()
    
    if args.stats:
        show_recent_activity()
    else:
        start_scraper()
