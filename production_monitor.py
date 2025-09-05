#!/usr/bin/env python3
"""
Production monitoring dashboard for ag-trading-bot.
Provides real-time status and health monitoring.
"""

import json
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
from typing import Dict, Any
import time
from dotenv import load_dotenv

from config import settings

load_dotenv()


def get_pipeline_health() -> Dict[str, Any]:
    """Get comprehensive pipeline health status for REAL data only."""
    try:
        conn = psycopg2.connect(settings.DATABASE_URL, cursor_factory=RealDictCursor)
        
        health = {}
        
        # First, check if we have any real vs synthetic data
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    COUNT(*) as total_messages,
                    COUNT(CASE WHEN payload->>'content' LIKE '%@launchpads%' 
                              AND (payload->'author'->>'username') IN ('Launchpads Bot', 'AlphaGardeners', 'Alpha Gardeners')
                              THEN 1 END) as real_alpha_messages,
                    COUNT(CASE WHEN author_id LIKE '%test%' OR author_id LIKE '%bot_123%' THEN 1 END) as synthetic_messages
                FROM discord_raw
            """)
            
            data_check = cur.fetchone()
            
            health["data_validation"] = {
                "total_messages": data_check[0],
                "real_alpha_messages": data_check[1], 
                "synthetic_messages": data_check[2],
                "is_real_data": data_check[1] > 0
            }
        
        with conn.cursor() as cur:
            # Recent activity (last hour)
            cur.execute("""
                SELECT 
                    COUNT(DISTINCT dr.message_id) as messages_1h,
                    COUNT(DISTINCT mr.message_id) as resolved_1h,
                    COUNT(DISTINCT a.message_id) as accepted_1h,
                    COUNT(DISTINCT fs.message_id) as featured_1h,
                    COUNT(DISTINCT s.message_id) as signaled_1h
                FROM discord_raw dr
                LEFT JOIN mint_resolution mr ON dr.message_id = mr.message_id AND mr.resolved = true
                LEFT JOIN acceptance_status a ON dr.message_id = a.message_id AND a.status = 'ACCEPT'
                LEFT JOIN features_snapshot fs ON dr.message_id = fs.message_id
                LEFT JOIN signals s ON dr.message_id = s.message_id
                WHERE dr.inserted_at >= NOW() - INTERVAL '1 hour'
            """)
            
            health["recent_activity"] = dict(cur.fetchone())
            
            # Overall totals
            cur.execute("""
                SELECT 
                    (SELECT COUNT(*) FROM discord_raw) as total_messages,
                    (SELECT COUNT(*) FROM acceptance_status WHERE status = 'ACCEPT') as total_accepted,
                    (SELECT COUNT(*) FROM outcomes_24h WHERE win = true) as total_winners,
                    (SELECT COUNT(*) FROM strategy_clusters) as active_clusters,
                    (SELECT COUNT(*) FROM strategy_params WHERE active = true) as active_strategies
            """)
            
            health["totals"] = dict(cur.fetchone())
            
            # Feature quality
            cur.execute("""
                SELECT 
                    COUNT(*) as samples_with_features,
                    AVG(CASE WHEN features->>'market_cap_usd' IS NOT NULL THEN 1.0 ELSE 0.0 END) as market_cap_rate,
                    AVG(CASE WHEN features->>'ag_score' IS NOT NULL THEN 1.0 ELSE 0.0 END) as ag_score_rate,
                    AVG(CASE WHEN features->>'bundled_pct' IS NOT NULL THEN 1.0 ELSE 0.0 END) as bundled_rate,
                    AVG(COALESCE((features->>'ag_score')::numeric, 0)) as avg_ag_score
                FROM features_snapshot fs
                WHERE fs.snapped_at >= NOW() - INTERVAL '24 hours'
            """)
            
            health["feature_quality"] = dict(cur.fetchone())
            
            # Signal performance
            cur.execute("""
                SELECT 
                    COUNT(*) as total_signals,
                    COUNT(CASE WHEN signal = 'BUY' THEN 1 END) as buy_signals,
                    COUNT(CASE WHEN s.signal = 'BUY' AND o.win = true THEN 1 END) as winning_buys
                FROM signals s
                LEFT JOIN outcomes_24h o ON s.message_id = o.message_id
                WHERE s.sent_at >= NOW() - INTERVAL '7 days'
            """)
            
            signal_stats = cur.fetchone()
            health["signal_performance"] = dict(signal_stats)
            
            # Calculate precision
            if signal_stats and signal_stats['buy_signals'] > 0:
                precision = signal_stats['winning_buys'] / signal_stats['buy_signals']
                health["signal_performance"]["buy_precision"] = precision
            else:
                health["signal_performance"]["buy_precision"] = 0.0
        
        conn.close()
        
        # Calculate health score
        health["health_score"] = calculate_health_score(health)
        health["status"] = "HEALTHY" if health["health_score"] > 0.7 else "DEGRADED" if health["health_score"] > 0.3 else "UNHEALTHY"
        
        return health
        
    except Exception as e:
        return {"error": f"Health check failed: {e}", "status": "ERROR"}


def calculate_health_score(health: Dict[str, Any]) -> float:
    """Calculate overall health score (0-1)."""
    score = 0.0
    
    # Recent activity weight (40%)
    recent = health.get("recent_activity", {})
    if recent.get("messages_1h", 0) > 0:
        score += 0.4
    
    # Feature quality weight (30%)
    quality = health.get("feature_quality", {})
    avg_feature_rate = (
        float(quality.get("market_cap_rate", 0)) +
        float(quality.get("ag_score_rate", 0)) +
        float(quality.get("bundled_rate", 0))
    ) / 3
    score += avg_feature_rate * 0.3
    
    # Signal performance weight (30%)
    signal_perf = health.get("signal_performance", {})
    precision = signal_perf.get("buy_precision", 0)
    score += precision * 0.3
    
    return min(1.0, score)


def print_dashboard(health: Dict[str, Any]):
    """Print monitoring dashboard."""
    print("🎯 AG-Trading-Bot Production Monitor")
    print("=" * 50)
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    
    status = health.get("status", "UNKNOWN")
    status_icon = {"HEALTHY": "🟢", "DEGRADED": "🟡", "UNHEALTHY": "🔴", "ERROR": "❌"}.get(status, "❓")
    
    print(f"\n{status_icon} SYSTEM STATUS: {status}")
    print(f"📊 Health Score: {health.get('health_score', 0):.2f}/1.0")
    
    if "error" in health:
        print(f"❌ Error: {health['error']}")
        return
    
    # Recent activity
    recent = health.get("recent_activity", {})
    print(f"\n📈 Recent Activity (1 hour):")
    print(f"  Messages: {recent.get('messages_1h', 0)}")
    print(f"  Resolved: {recent.get('resolved_1h', 0)}")
    print(f"  Accepted: {recent.get('accepted_1h', 0)}")
    print(f"  Featured: {recent.get('featured_1h', 0)}")
    print(f"  Signaled: {recent.get('signaled_1h', 0)}")
    
    # Overall totals
    totals = health.get("totals", {})
    print(f"\n📊 Overall Totals:")
    print(f"  Total Messages: {totals.get('total_messages', 0)}")
    print(f"  Total Accepted: {totals.get('total_accepted', 0)}")
    print(f"  Total Winners: {totals.get('total_winners', 0)}")
    print(f"  Active Clusters: {totals.get('active_clusters', 0)}")
    print(f"  Active Strategies: {totals.get('active_strategies', 0)}")
    
    # Feature quality
    quality = health.get("feature_quality", {})
    print(f"\n🔍 Feature Quality (24h):")
    print(f"  Samples with Features: {quality.get('samples_with_features', 0)}")
    print(f"  Market Cap Rate: {quality.get('market_cap_rate', 0):.1%}")
    print(f"  AG Score Rate: {quality.get('ag_score_rate', 0):.1%}")
    print(f"  Bundled Rate: {quality.get('bundled_rate', 0):.1%}")
    print(f"  Avg AG Score: {quality.get('avg_ag_score', 0):.1f}/10")
    
    # Signal performance
    signals = health.get("signal_performance", {})
    print(f"\n🎯 Signal Performance (7d):")
    print(f"  Total Signals: {signals.get('total_signals', 0)}")
    print(f"  BUY Signals: {signals.get('buy_signals', 0)}")
    print(f"  Winning BUYs: {signals.get('winning_buys', 0)}")
    print(f"  BUY Precision: {signals.get('buy_precision', 0):.1%}")
    
    # Health indicators
    print(f"\n🩺 Health Indicators:")
    
    # Data flow health
    if recent.get('messages_1h', 0) > 0:
        print("  ✅ Discord scraping: Active")
    else:
        print("  ⚠️ Discord scraping: No recent messages")
    
    # Feature extraction health
    if quality.get('market_cap_rate', 0) > 0.8:
        print("  ✅ Feature extraction: High quality")
    elif quality.get('market_cap_rate', 0) > 0.5:
        print("  ⚠️ Feature extraction: Moderate quality")
    else:
        print("  ❌ Feature extraction: Poor quality")
    
    # ML pipeline health
    if totals.get('active_clusters', 0) >= 3 and totals.get('active_strategies', 0) >= 1:
        print("  ✅ ML pipeline: Active")
    else:
        print("  ⚠️ ML pipeline: Needs training")


def monitor_continuous():
    """Continuous monitoring loop."""
    print("🔄 Starting Continuous Production Monitor")
    print("Press Ctrl+C to stop")
    print("=" * 50)
    
    try:
        while True:
            print("\033[2J\033[H")  # Clear screen
            
            health = get_pipeline_health()
            print_dashboard(health)
            
            print(f"\n🔄 Refreshing in 30 seconds...")
            time.sleep(30)
            
    except KeyboardInterrupt:
        print("\n🛑 Monitoring stopped")


def main():
    """Main monitoring function."""
    import argparse
    
    parser = argparse.ArgumentParser(description="AG-Trading-Bot Production Monitor")
    parser.add_argument("--continuous", action="store_true", help="Continuous monitoring")
    parser.add_argument("--json", action="store_true", help="JSON output")
    
    args = parser.parse_args()
    
    if args.continuous:
        monitor_continuous()
    else:
        health = get_pipeline_health()
        
        if args.json:
            print(json.dumps(health, indent=2, default=str))
        else:
            print_dashboard(health)


if __name__ == "__main__":
    main()
