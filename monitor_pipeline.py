#!/usr/bin/env python3
"""
Pipeline monitoring script for ag-trading-bot.
Monitors Discord scraping, database activity, and pipeline processing.
"""

import time
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
from dotenv import load_dotenv

from config import settings

load_dotenv()


def get_db_connection():
    """Get database connection."""
    return psycopg2.connect(settings.DATABASE_URL, cursor_factory=RealDictCursor)


def check_pipeline_activity():
    """Check current pipeline activity."""
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Overall counts
            cur.execute("""
                SELECT 
                    (SELECT COUNT(*) FROM discord_raw) as total_messages,
                    (SELECT COUNT(*) FROM discord_raw WHERE inserted_at >= NOW() - INTERVAL '1 hour') as messages_1h,
                    (SELECT COUNT(*) FROM mint_resolution WHERE resolved = true) as resolved_mints,
                    (SELECT COUNT(*) FROM acceptance_status WHERE status = 'ACCEPT') as accepted,
                    (SELECT COUNT(*) FROM acceptance_status WHERE status = 'REJECT') as rejected,
                    (SELECT COUNT(*) FROM outcomes_24h) as outcomes,
                    (SELECT COUNT(*) FROM features_snapshot) as features,
                    (SELECT COUNT(*) FROM signals) as signals
            """)
            
            stats = cur.fetchone()
            
            print(f"📊 Pipeline Activity ({datetime.now().strftime('%H:%M:%S')}):")
            print(f"  Discord messages: {stats['total_messages']} (last hour: {stats['messages_1h']})")
            print(f"  Resolved mints: {stats['resolved_mints']}")
            print(f"  Accepted: {stats['accepted']}")
            print(f"  Rejected: {stats['rejected']}")
            print(f"  Outcomes tracked: {stats['outcomes']}")
            print(f"  Features extracted: {stats['features']}")
            print(f"  Signals generated: {stats['signals']}")
            
            # Show recent activity if any
            if stats['total_messages'] > 0:
                cur.execute("""
                    SELECT 
                        dr.message_id,
                        dr.posted_at,
                        dr.payload->>'content' as content,
                        mr.mint,
                        a.status,
                        a.reason_code
                    FROM discord_raw dr
                    LEFT JOIN mint_resolution mr ON dr.message_id = mr.message_id
                    LEFT JOIN acceptance_status a ON dr.message_id = a.message_id
                    ORDER BY dr.inserted_at DESC
                    LIMIT 3
                """)
                
                recent = cur.fetchall()
                print(f"\n📋 Recent Messages:")
                
                for msg in recent:
                    content = (msg['content'] or '')[:50]
                    status = msg['status'] or 'PENDING'
                    mint = msg['mint'][:8] + '...' if msg['mint'] else 'None'
                    
                    print(f"  {msg['message_id']}: {content}...")
                    print(f"    Mint: {mint}, Status: {status}")
                    
                    if msg['reason_code']:
                        print(f"    Reason: {msg['reason_code']}")
            
            # Check for winners
            if stats['outcomes'] > 0:
                cur.execute("""
                    SELECT 
                        o.message_id,
                        a.mint,
                        o.max_24h_price_usd / NULLIF(o.entry_price_usd, 0) as max_multiple,
                        o.touch_10x,
                        o.sustained_10x,
                        o.win
                    FROM outcomes_24h o
                    JOIN acceptance_status a ON o.message_id = a.message_id
                    ORDER BY o.computed_at DESC
                    LIMIT 3
                """)
                
                outcomes = cur.fetchall()
                print(f"\n🏆 Recent Outcomes:")
                
                for outcome in outcomes:
                    status = "🏆 WIN" if outcome['win'] else "📈 TOUCH" if outcome['touch_10x'] else "📉 MISS"
                    multiple = outcome['max_multiple'] or 0
                    mint = outcome['mint'][:8] + '...' if outcome['mint'] else 'Unknown'
                    
                    print(f"  {status} {mint}: {multiple:.1f}x")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Database monitoring error: {e}")


def check_scraper_files():
    """Check for scraper session files."""
    from pathlib import Path
    
    session_file = Path("discord_session.json")
    cookies_file = Path("discord_cookies.pkl")
    
    print(f"\n📁 Scraper Session Files:")
    print(f"  Session file: {session_file.exists()} ({session_file})")
    print(f"  Cookies file: {cookies_file.exists()} ({cookies_file})")
    
    if session_file.exists():
        mod_time = datetime.fromtimestamp(session_file.stat().st_mtime)
        print(f"  Last session: {mod_time.strftime('%H:%M:%S')}")


def monitor_loop():
    """Continuous monitoring loop."""
    print("🔄 Starting Pipeline Monitor")
    print("Press Ctrl+C to stop monitoring")
    print("=" * 60)
    
    try:
        iteration = 0
        while True:
            iteration += 1
            print(f"\n🔍 Monitor Check #{iteration}")
            
            # Check pipeline activity
            check_pipeline_activity()
            
            # Check scraper files
            check_scraper_files()
            
            print("-" * 60)
            
            # Wait before next check
            time.sleep(30)  # Check every 30 seconds
            
    except KeyboardInterrupt:
        print("\n🛑 Monitoring stopped by user")
    except Exception as e:
        print(f"\n❌ Monitoring error: {e}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="AG-Trading-Bot Pipeline Monitor")
    parser.add_argument("--once", action="store_true", help="Run once instead of continuous monitoring")
    
    args = parser.parse_args()
    
    if args.once:
        check_pipeline_activity()
        check_scraper_files()
    else:
        monitor_loop()
