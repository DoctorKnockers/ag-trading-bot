#!/usr/bin/env python3
"""
Real Discord Scraping Monitor - REAL DATA ONLY
Monitors only authentic Alpha Gardeners Discord messages.
NO synthetic data allowed.
"""

import time
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
from dotenv import load_dotenv

from config import settings

load_dotenv()


def check_real_alpha_gardeners_activity():
    """Check for real Alpha Gardeners activity only."""
    try:
        conn = psycopg2.connect(settings.DATABASE_URL, cursor_factory=RealDictCursor)
        
        with conn.cursor() as cur:
            # Check for real Alpha Gardeners messages
            cur.execute("""
                SELECT 
                    COUNT(*) as total_messages,
                    COUNT(CASE WHEN payload->>'content' LIKE '%@launchpads%' 
                              AND (payload->'author'->>'username') IN ('Launchpads Bot', 'AlphaGardeners')
                              AND author_id NOT LIKE '%test%'
                              THEN 1 END) as real_alpha_messages,
                    COUNT(CASE WHEN author_id LIKE '%test%' OR payload->>'content' LIKE '%test%' THEN 1 END) as synthetic_messages
                FROM discord_raw
                WHERE inserted_at >= NOW() - INTERVAL '1 hour'
            """)
            
            recent_stats = cur.fetchone()
            
            # Get overall stats
            cur.execute("""
                SELECT 
                    COUNT(*) as total_all_time,
                    COUNT(CASE WHEN payload->>'content' LIKE '%@launchpads%' 
                              AND (payload->'author'->>'username') IN ('Launchpads Bot', 'AlphaGardeners')
                              AND author_id NOT LIKE '%test%'
                              THEN 1 END) as real_alpha_all_time
                FROM discord_raw
            """)
            
            overall_stats = cur.fetchone()
            
            # Check recent real messages
            cur.execute("""
                SELECT 
                    dr.message_id,
                    dr.posted_at,
                    dr.payload->>'content' as content,
                    (dr.payload->'author'->>'username') as author,
                    mr.mint,
                    a.status
                FROM discord_raw dr
                LEFT JOIN mint_resolution mr ON dr.message_id = mr.message_id
                LEFT JOIN acceptance_status a ON dr.message_id = a.message_id
                WHERE dr.payload->>'content' LIKE '%@launchpads%'
                  AND (dr.payload->'author'->>'username') IN ('Launchpads Bot', 'AlphaGardeners')
                  AND dr.author_id NOT LIKE '%test%'
                ORDER BY dr.inserted_at DESC
                LIMIT 5
            """)
            
            real_messages = cur.fetchall()
        
        conn.close()
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "recent_stats": dict(recent_stats),
            "overall_stats": dict(overall_stats),
            "real_messages": [dict(msg) for msg in real_messages],
            "scraper_status": "ACTIVE" if recent_stats['real_alpha_messages'] > 0 else "NO_REAL_DATA"
        }
        
    except Exception as e:
        return {"error": f"Monitor check failed: {e}"}


def print_real_data_status(status):
    """Print real data status."""
    print("🎯 Real Alpha Gardeners Discord Monitor")
    print("=" * 50)
    print(f"⏰ {datetime.now().strftime('%H:%M:%S UTC')}")
    
    if "error" in status:
        print(f"❌ Error: {status['error']}")
        return
    
    recent = status["recent_stats"]
    overall = status["overall_stats"]
    scraper_status = status["scraper_status"]
    
    # Overall status
    if scraper_status == "ACTIVE":
        print("🟢 SCRAPER STATUS: COLLECTING REAL DATA")
    else:
        print("🔴 SCRAPER STATUS: NO REAL ALPHA GARDENERS DATA")
    
    print(f"\n📊 Real Data Statistics:")
    print(f"  Recent (1h): {recent['real_alpha_messages']} real Alpha Gardeners messages")
    print(f"  Total: {overall['real_alpha_all_time']} real messages all-time")
    print(f"  Synthetic: {recent['synthetic_messages']} (should be 0)")
    
    # Show recent real messages
    real_messages = status["real_messages"]
    if real_messages:
        print(f"\n📋 Recent Real Alpha Gardeners Messages:")
        for msg in real_messages:
            content = msg['content'][:50] if msg['content'] else 'No content'
            mint = msg['mint'][:8] + '...' if msg['mint'] else 'No mint'
            status_text = msg['status'] or 'Pending'
            
            print(f"  📞 {msg['message_id']}: {content}...")
            print(f"      🪙 Mint: {mint}")
            print(f"      ✅ Status: {status_text}")
            print(f"      👤 Author: {msg['author']}")
            print()
    else:
        print(f"\n⚠️ No real Alpha Gardeners messages found")
        print(f"   This means:")
        print(f"   - Discord scraper is not connected, OR")
        print(f"   - No new launchpad calls in Alpha Gardeners channel, OR")
        print(f"   - Scraper validation is too strict")
    
    # Recommendations
    print(f"\n💡 Status:")
    if scraper_status == "ACTIVE":
        print("  🎯 Excellent! Real Alpha Gardeners data flowing")
        print("  ✅ Pipeline processing authentic launchpad calls")
        print("  🚀 Ready for ML training with real data")
    else:
        print("  🔧 Need to get real Discord scraping working")
        print("  📱 Check Discord scraper browser window")
        print("  🔑 Verify login credentials and channel access")


def monitor_real_scraping():
    """Continuous monitoring of real scraping activity."""
    print("🔄 Starting Real Alpha Gardeners Monitor")
    print("⚠️ REAL DATA ONLY - No synthetic messages")
    print("Press Ctrl+C to stop")
    print("=" * 50)
    
    try:
        while True:
            status = check_real_alpha_gardeners_activity()
            
            # Clear screen and show status
            print("\033[2J\033[H")  # Clear screen
            print_real_data_status(status)
            
            # Wait before next check
            print(f"🔄 Refreshing in 30 seconds...")
            time.sleep(30)
            
    except KeyboardInterrupt:
        print("\n🛑 Real data monitoring stopped")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Real Alpha Gardeners Monitor")
    parser.add_argument("--continuous", action="store_true", help="Continuous monitoring")
    
    args = parser.parse_args()
    
    if args.continuous:
        monitor_real_scraping()
    else:
        status = check_real_alpha_gardeners_activity()
        print_real_data_status(status)
