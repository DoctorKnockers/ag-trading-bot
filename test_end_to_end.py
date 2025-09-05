#!/usr/bin/env python3
"""
End-to-End Pipeline Test with Comprehensive Debugging.
Tests the complete ag-trading-bot pipeline with detailed logging and error tracking.
"""

import json
import logging
import traceback
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

from config import settings
from ingest.metrics_parser import LaunchpadMetricsParser
from utils.time_utils import get_entry_timestamp, datetime_to_epoch_ms

load_dotenv()

# Setup comprehensive logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class EndToEndTester:
    """Comprehensive end-to-end pipeline tester with debugging."""
    
    def __init__(self):
        self.test_results = {
            "steps": {},
            "errors": [],
            "warnings": [],
            "data_flow": {},
            "performance": {}
        }
        
        self.parser = LaunchpadMetricsParser()
    
    def log_step(self, step_name: str, status: str, details: Dict[str, Any] = None, error: str = None):
        """Log a pipeline step with full details."""
        timestamp = datetime.now(timezone.utc).isoformat()
        
        step_info = {
            "timestamp": timestamp,
            "status": status,  # "START", "SUCCESS", "FAILED", "WARNING"
            "details": details or {},
            "error": error
        }
        
        self.test_results["steps"][step_name] = step_info
        
        # Console logging
        if status == "START":
            print(f"🔄 {step_name}...")
        elif status == "SUCCESS":
            print(f"✅ {step_name}: SUCCESS")
            if details:
                for key, value in details.items():
                    print(f"    {key}: {value}")
        elif status == "FAILED":
            print(f"❌ {step_name}: FAILED")
            if error:
                print(f"    Error: {error}")
            self.test_results["errors"].append(f"{step_name}: {error}")
        elif status == "WARNING":
            print(f"⚠️ {step_name}: WARNING")
            if error:
                print(f"    Warning: {error}")
            self.test_results["warnings"].append(f"{step_name}: {error}")
    
    def create_test_alpha_message(self) -> Dict[str, Any]:
        """Create realistic Alpha Gardeners test message."""
        self.log_step("create_test_message", "START")
        
        try:
            posted_time = datetime.now(timezone.utc)
            epoch_ms = datetime_to_epoch_ms(posted_time)
            
            # Generate snowflake
            discord_epoch = 1420070400000
            snowflake = ((epoch_ms - discord_epoch) << 22) | (1 << 17) | 99999
            
            message = {
                "id": str(snowflake),
                "channel_id": settings.DISCORD_CHANNEL_ID,
                "content": "@launchpads Fomo called TestCoin | TEST",
                "author": {
                    "id": "launchpads_bot_test",
                    "username": "Launchpads Bot"
                },
                "embeds": [
                    {
                        "title": "FOMO called TEST",
                        "description": "9WzDX...2hr 📄 Copy • 🔮 Win Prediction: 25%",
                        "color": 65280,
                        "url": "https://pump.fun/coin/9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM",
                        "fields": [
                            {
                                "name": "Stats TEST",
                                "value": "💰 MC: $25,500\n💧 Liq: $8,750 (65.2%)\n🚀 Via: PUMPFUN\n⏰ Token Age: 2 hours ago\n👥 Top 20: 35.4%\n📊 Holders: 73"
                            },
                            {
                                "name": "Stats Creator",
                                "value": "🎯 AG Score: 8/10\n🎭 Mint: No 🟢 Freeze: No 🟢\n🔧 Mut: No 🟢 Chg: No 🟢\n💼 Bundled: 5.2%\n🏛️ DS paid: Yes 🟢"
                            },
                            {
                                "name": "Recent Swaps",
                                "value": "F: 12 KYC: 2 Unq: 8 SM: 3"
                            },
                            {
                                "name": "1m Volume",
                                "value": "Total: 8.5K B: 55% S: 45%\nVol2MC: 33%"
                            },
                            {
                                "name": "Token Description",
                                "value": "Revolutionary test token for end-to-end validation"
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
                                "style": 5,
                                "label": "Insta Buy",
                                "url": "https://pump.fun/coin/9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM"
                            }
                        ]
                    }
                ],
                "timestamp": posted_time.isoformat()
            }
            
            self.log_step("create_test_message", "SUCCESS", {
                "message_id": message["id"],
                "embeds": len(message["embeds"]),
                "fields": len(message["embeds"][0]["fields"]),
                "components": len(message["components"])
            })
            
            return message
            
        except Exception as e:
            self.log_step("create_test_message", "FAILED", error=str(e))
            raise
    
    def store_discord_message(self, message: Dict[str, Any]) -> bool:
        """Store Discord message with debugging."""
        self.log_step("store_discord_message", "START")
        
        try:
            conn = psycopg2.connect(settings.DATABASE_URL)
            
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO discord_raw (
                        channel_id, message_id, posted_at, posted_at_epoch_ms,
                        author_id, payload, inserted_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (message_id) DO NOTHING
                """, (
                    message['channel_id'],
                    message['id'],
                    message['timestamp'],
                    int(datetime.fromisoformat(message['timestamp']).timestamp() * 1000),
                    message['author']['id'],
                    json.dumps(message)
                ))
                
                rows_affected = cur.rowcount
                conn.commit()
            
            conn.close()
            
            self.log_step("store_discord_message", "SUCCESS", {
                "message_id": message["id"],
                "rows_affected": rows_affected,
                "table": "discord_raw"
            })
            
            return True
            
        except Exception as e:
            self.log_step("store_discord_message", "FAILED", error=str(e))
            logger.error(f"Discord message storage error: {traceback.format_exc()}")
            return False
    
    def resolve_mint(self, message_id: str) -> Optional[str]:
        """Resolve mint address with debugging."""
        self.log_step("resolve_mint", "START")
        
        try:
            conn = psycopg2.connect(settings.DATABASE_URL, cursor_factory=RealDictCursor)
            
            # Get message payload
            with conn.cursor() as cur:
                cur.execute("SELECT payload FROM discord_raw WHERE message_id = %s", (message_id,))
                row = cur.fetchone()
                
                if not row:
                    self.log_step("resolve_mint", "FAILED", error="Message not found in discord_raw")
                    return None
                
                payload = row['payload']
            
            # Extract mint from URLs
            mint_address = None
            urls_found = []
            
            # Check embeds
            for embed in payload.get('embeds', []):
                if url := embed.get('url'):
                    urls_found.append(url)
                    if 'pump.fun' in url:
                        parts = url.split('/')
                        if len(parts) > 3:
                            mint_address = parts[-1]
            
            # Check components
            for comp_row in payload.get('components', []):
                for comp in comp_row.get('components', []):
                    if url := comp.get('url'):
                        urls_found.append(url)
                        if 'pump.fun' in url:
                            parts = url.split('/')
                            if len(parts) > 3:
                                mint_address = parts[-1]
            
            # Store resolution result
            with conn.cursor() as cur:
                if mint_address:
                    cur.execute("""
                        INSERT INTO mint_resolution (
                            message_id, resolved, mint, source_url, confidence, resolved_at
                        ) VALUES (%s, %s, %s, %s, %s, NOW())
                        ON CONFLICT (message_id) DO UPDATE SET
                            resolved = %s, mint = %s, source_url = %s, resolved_at = NOW()
                    """, (
                        message_id, True, mint_address, urls_found[0] if urls_found else None, 0.9,
                        True, mint_address, urls_found[0] if urls_found else None
                    ))
                else:
                    cur.execute("""
                        INSERT INTO mint_resolution (
                            message_id, resolved, error, resolved_at
                        ) VALUES (%s, %s, %s, NOW())
                        ON CONFLICT (message_id) DO UPDATE SET
                            resolved = %s, error = %s, resolved_at = NOW()
                    """, (
                        message_id, False, 'No mint found in URLs',
                        False, 'No mint found in URLs'
                    ))
                
                conn.commit()
            
            conn.close()
            
            self.log_step("resolve_mint", "SUCCESS" if mint_address else "WARNING", {
                "mint_address": mint_address,
                "urls_found": len(urls_found),
                "source_urls": urls_found
            }, error="No mint found" if not mint_address else None)
            
            return mint_address
            
        except Exception as e:
            self.log_step("resolve_mint", "FAILED", error=str(e))
            logger.error(f"Mint resolution error: {traceback.format_exc()}")
            return None
    
    def validate_acceptance(self, message_id: str, mint_address: str) -> str:
        """Validate acceptance with debugging."""
        self.log_step("validate_acceptance", "START")
        
        try:
            # For this test, we'll accept all mints that were resolved
            # In production, this would do SPL authority checks and Jupiter validation
            
            conn = psycopg2.connect(settings.DATABASE_URL)
            
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO acceptance_status (
                        message_id, mint, first_seen, status, reason_code, evidence, pool_deadline, last_checked
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (message_id) DO UPDATE SET
                        status = %s, reason_code = %s, evidence = %s, last_checked = NOW()
                """, (
                    message_id, mint_address, datetime.now(timezone.utc),
                    'ACCEPT', None,
                    json.dumps({"test": "end_to_end", "validation": "passed"}),
                    datetime.now(timezone.utc) + timedelta(minutes=30),
                    'ACCEPT', None,
                    json.dumps({"test": "end_to_end", "validation": "passed"})
                ))
                
                conn.commit()
            
            conn.close()
            
            self.log_step("validate_acceptance", "SUCCESS", {
                "status": "ACCEPT",
                "mint_address": mint_address
            })
            
            return "ACCEPT"
            
        except Exception as e:
            self.log_step("validate_acceptance", "FAILED", error=str(e))
            logger.error(f"Acceptance validation error: {traceback.format_exc()}")
            return "ERROR"
    
    def extract_features(self, message_id: str, mint_address: str) -> bool:
        """Extract enhanced features with debugging."""
        self.log_step("extract_features", "START")
        
        try:
            conn = psycopg2.connect(settings.DATABASE_URL, cursor_factory=RealDictCursor)
            
            # Get message payload
            with conn.cursor() as cur:
                cur.execute("SELECT payload FROM discord_raw WHERE message_id = %s", (message_id,))
                row = cur.fetchone()
                
                if not row:
                    self.log_step("extract_features", "FAILED", error="Message payload not found")
                    return False
                
                payload = row['payload']
            
            # Parse comprehensive metrics
            logger.debug(f"Parsing metrics for message {message_id}")
            discord_metrics = self.parser.parse_message_metrics(payload)
            validated_metrics = self.parser.validate_parsed_metrics(discord_metrics)
            
            # Add metadata
            validated_metrics.update({
                "message_id": message_id,
                "mint_address": mint_address,
                "t0_timestamp": get_entry_timestamp(message_id).isoformat(),
                "feature_version": 1,
                "test_run": True
            })
            
            # Store features
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO features_snapshot (
                        message_id, snapped_at, features, feature_version
                    ) VALUES (%s, %s, %s, %s)
                    ON CONFLICT (message_id) DO UPDATE SET
                        features = %s,
                        feature_version = %s
                """, (
                    message_id,
                    get_entry_timestamp(message_id),
                    json.dumps(validated_metrics),
                    1,
                    json.dumps(validated_metrics),
                    1
                ))
                
                conn.commit()
            
            conn.close()
            
            # Count non-null features
            non_null_features = sum(1 for v in validated_metrics.values() if v is not None)
            
            self.log_step("extract_features", "SUCCESS", {
                "total_features": len(validated_metrics),
                "non_null_features": non_null_features,
                "completeness_pct": f"{(non_null_features/len(validated_metrics)*100):.1f}%",
                "key_metrics": {
                    "market_cap": validated_metrics.get("market_cap_usd"),
                    "ag_score": validated_metrics.get("ag_score"),
                    "win_prediction": validated_metrics.get("win_prediction_pct"),
                    "bundled_pct": validated_metrics.get("bundled_pct")
                }
            })
            
            return True
            
        except Exception as e:
            self.log_step("extract_features", "FAILED", error=str(e))
            logger.error(f"Feature extraction error: {traceback.format_exc()}")
            return False
    
    def simulate_outcome(self, message_id: str, outcome_type: str = "winner") -> bool:
        """Simulate 24h outcome with debugging."""
        self.log_step("simulate_outcome", "START")
        
        try:
            # Generate realistic outcome based on type
            if outcome_type == "winner":
                entry_price = 0.000015
                max_price = entry_price * 15.7  # 15.7x winner
                touch_10x = True
                sustained_10x = True
                win = True
            else:
                entry_price = 0.000012
                max_price = entry_price * 6.3  # 6.3x loser
                touch_10x = False
                sustained_10x = False
                win = False
            
            conn = psycopg2.connect(settings.DATABASE_URL)
            
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO outcomes_24h (
                        message_id, entry_price_usd, max_24h_price_usd,
                        touch_10x, sustained_10x, win, computed_at, outcomes_version
                    ) VALUES (%s, %s, %s, %s, %s, %s, NOW(), 1)
                    ON CONFLICT (message_id) DO UPDATE SET
                        entry_price_usd = %s,
                        max_24h_price_usd = %s,
                        touch_10x = %s,
                        sustained_10x = %s,
                        win = %s,
                        computed_at = NOW()
                """, (
                    message_id, entry_price, max_price, touch_10x, sustained_10x, win,
                    entry_price, max_price, touch_10x, sustained_10x, win
                ))
                
                conn.commit()
            
            conn.close()
            
            multiple = max_price / entry_price
            
            self.log_step("simulate_outcome", "SUCCESS", {
                "outcome_type": outcome_type,
                "entry_price": entry_price,
                "max_price": max_price,
                "multiple": f"{multiple:.1f}x",
                "touch_10x": touch_10x,
                "sustained_10x": sustained_10x,
                "win": win
            })
            
            return True
            
        except Exception as e:
            self.log_step("simulate_outcome", "FAILED", error=str(e))
            logger.error(f"Outcome simulation error: {traceback.format_exc()}")
            return False
    
    def test_cluster_assignment(self, message_id: str) -> Optional[int]:
        """Test cluster assignment with debugging."""
        self.log_step("test_cluster_assignment", "START")
        
        try:
            conn = psycopg2.connect(settings.DATABASE_URL, cursor_factory=RealDictCursor)
            
            # Get features
            with conn.cursor() as cur:
                cur.execute("SELECT features FROM features_snapshot WHERE message_id = %s", (message_id,))
                row = cur.fetchone()
                
                if not row:
                    self.log_step("test_cluster_assignment", "FAILED", error="Features not found")
                    return None
                
                features = row['features']
            
            # Get clusters
            with conn.cursor() as cur:
                cur.execute("SELECT id, label, centroid FROM strategy_clusters ORDER BY id")
                clusters = cur.fetchall()
            
            conn.close()
            
            if not clusters:
                self.log_step("test_cluster_assignment", "WARNING", error="No clusters found")
                return None
            
            # Simple distance calculation
            feature_vector = [
                features.get("market_cap_usd", 0) / 100000,  # Normalize
                features.get("ag_score", 0) / 10,
                features.get("bundled_pct", 0) / 100,
                features.get("win_prediction_pct", 0) / 100
            ]
            
            best_cluster = None
            min_distance = float('inf')
            
            for cluster in clusters:
                centroid = cluster['centroid']['centroid'][:len(feature_vector)]  # Match dimensions
                
                # Euclidean distance
                distance = sum((a - b) ** 2 for a, b in zip(feature_vector, centroid)) ** 0.5
                
                if distance < min_distance:
                    min_distance = distance
                    best_cluster = cluster['id']
            
            self.log_step("test_cluster_assignment", "SUCCESS", {
                "assigned_cluster": best_cluster,
                "distance": f"{min_distance:.3f}",
                "total_clusters": len(clusters),
                "feature_vector": feature_vector
            })
            
            return best_cluster
            
        except Exception as e:
            self.log_step("test_cluster_assignment", "FAILED", error=str(e))
            logger.error(f"Cluster assignment error: {traceback.format_exc()}")
            return None
    
    def generate_test_signal(self, message_id: str, cluster_id: int) -> Optional[str]:
        """Generate trading signal with debugging."""
        self.log_step("generate_signal", "START")
        
        try:
            conn = psycopg2.connect(settings.DATABASE_URL, cursor_factory=RealDictCursor)
            
            # Get features
            with conn.cursor() as cur:
                cur.execute("SELECT features FROM features_snapshot WHERE message_id = %s", (message_id,))
                row = cur.fetchone()
                
                if not row:
                    self.log_step("generate_signal", "FAILED", error="Features not found")
                    return None
                
                features = row['features']
            
            # Simple signal generation logic
            ag_score = features.get("ag_score", 0)
            bundled_pct = features.get("bundled_pct", 100)
            win_prediction = features.get("win_prediction_pct", 0)
            market_cap = features.get("market_cap_usd", 0)
            
            # Simple scoring
            score = (
                (ag_score / 10) * 0.3 +
                (1 - bundled_pct / 100) * 0.2 +
                (win_prediction / 100) * 0.3 +
                min(1.0, market_cap / 50000) * 0.2
            )
            
            # Signal decision
            if score > 0.6:
                signal = "BUY"
            else:
                signal = "SKIP"
            
            # Store signal
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO signals (
                        message_id, cluster_id, strategy_id, signal, score, sent_at
                    ) VALUES (%s, %s, %s, %s, %s, NOW())
                    RETURNING id
                """, (
                    message_id, cluster_id, None, signal, score
                ))
                
                signal_id = cur.fetchone()[0]
                conn.commit()
            
            conn.close()
            
            self.log_step("generate_signal", "SUCCESS", {
                "signal": signal,
                "score": f"{score:.3f}",
                "signal_id": signal_id,
                "cluster_id": cluster_id,
                "decision_factors": {
                    "ag_score": ag_score,
                    "bundled_pct": bundled_pct,
                    "win_prediction": win_prediction,
                    "market_cap": market_cap
                }
            })
            
            return signal
            
        except Exception as e:
            self.log_step("generate_signal", "FAILED", error=str(e))
            logger.error(f"Signal generation error: {traceback.format_exc()}")
            return None
    
    def verify_data_integrity(self) -> bool:
        """Verify data integrity across all tables."""
        self.log_step("verify_data_integrity", "START")
        
        try:
            conn = psycopg2.connect(settings.DATABASE_URL, cursor_factory=RealDictCursor)
            
            integrity_checks = []
            
            with conn.cursor() as cur:
                # Check foreign key integrity
                cur.execute("""
                    SELECT 
                        (SELECT COUNT(*) FROM discord_raw) as discord_count,
                        (SELECT COUNT(*) FROM mint_resolution) as mint_count,
                        (SELECT COUNT(*) FROM acceptance_status) as accept_count,
                        (SELECT COUNT(*) FROM features_snapshot) as features_count,
                        (SELECT COUNT(*) FROM outcomes_24h) as outcomes_count,
                        (SELECT COUNT(*) FROM signals) as signals_count
                """)
                
                counts = cur.fetchone()
                
                # Check for orphaned records
                cur.execute("""
                    SELECT 
                        COUNT(*) as orphaned_mint_resolutions
                    FROM mint_resolution mr
                    WHERE NOT EXISTS (SELECT 1 FROM discord_raw dr WHERE dr.message_id = mr.message_id)
                """)
                
                orphaned = cur.fetchone()
            
            conn.close()
            
            # Analyze integrity
            issues = []
            
            if orphaned['orphaned_mint_resolutions'] > 0:
                issues.append(f"Orphaned mint resolutions: {orphaned['orphaned_mint_resolutions']}")
            
            if counts['features_count'] > counts['accept_count']:
                issues.append("More features than accepted calls")
            
            if counts['signals_count'] > counts['accept_count']:
                issues.append("More signals than accepted calls")
            
            self.log_step("verify_data_integrity", "SUCCESS" if not issues else "WARNING", {
                "table_counts": dict(counts),
                "integrity_issues": issues
            }, error="; ".join(issues) if issues else None)
            
            return len(issues) == 0
            
        except Exception as e:
            self.log_step("verify_data_integrity", "FAILED", error=str(e))
            logger.error(f"Data integrity check error: {traceback.format_exc()}")
            return False
    
    def run_complete_test(self) -> Dict[str, Any]:
        """Run complete end-to-end test."""
        print("🧪 AG-Trading-Bot End-to-End Pipeline Test")
        print("=" * 60)
        print("📋 Testing complete pipeline with comprehensive debugging...")
        
        start_time = datetime.now()
        
        # Step 1: Create test message
        try:
            message = self.create_test_alpha_message()
            message_id = message['id']
        except Exception as e:
            return {"error": f"Failed to create test message: {e}"}
        
        # Step 2: Store Discord message
        if not self.store_discord_message(message):
            return {"error": "Failed to store Discord message"}
        
        # Step 3: Resolve mint
        mint_address = self.resolve_mint(message_id)
        if not mint_address:
            return {"error": "Failed to resolve mint address"}
        
        # Step 4: Validate acceptance
        status = self.validate_acceptance(message_id, mint_address)
        if status != "ACCEPT":
            return {"error": f"Unexpected acceptance status: {status}"}
        
        # Step 5: Extract features
        if not self.extract_features(message_id, mint_address):
            return {"error": "Failed to extract features"}
        
        # Step 6: Simulate outcome
        if not self.simulate_outcome(message_id, "winner"):
            return {"error": "Failed to simulate outcome"}
        
        # Step 7: Test cluster assignment
        cluster_id = self.test_cluster_assignment(message_id)
        if cluster_id is None:
            return {"error": "Failed cluster assignment"}
        
        # Step 8: Generate signal
        signal = self.generate_test_signal(message_id, cluster_id)
        if not signal:
            return {"error": "Failed to generate signal"}
        
        # Step 9: Verify data integrity
        if not self.verify_data_integrity():
            self.log_step("verify_data_integrity", "WARNING", error="Data integrity issues detected")
        
        # Calculate performance
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        self.test_results["performance"] = {
            "total_duration_sec": duration,
            "steps_completed": len([s for s in self.test_results["steps"].values() if s["status"] == "SUCCESS"]),
            "steps_failed": len([s for s in self.test_results["steps"].values() if s["status"] == "FAILED"]),
            "steps_warned": len([s for s in self.test_results["steps"].values() if s["status"] == "WARNING"])
        }
        
        return {
            "success": True,
            "message_id": message_id,
            "mint_address": mint_address,
            "final_signal": signal,
            "test_results": self.test_results
        }
    
    def print_detailed_report(self, result: Dict[str, Any]):
        """Print comprehensive test report."""
        print("\n" + "=" * 60)
        print("📊 DETAILED END-TO-END TEST REPORT")
        print("=" * 60)
        
        if result.get("success"):
            print("🎉 OVERALL RESULT: ✅ SUCCESS")
            print(f"📞 Test Message: {result['message_id']}")
            print(f"🪙 Mint Address: {result['mint_address']}")
            print(f"🎯 Final Signal: {result['final_signal']}")
        else:
            print("❌ OVERALL RESULT: FAILED")
            print(f"Error: {result.get('error', 'Unknown error')}")
        
        # Performance summary
        perf = result.get("test_results", {}).get("performance", {})
        print(f"\n⚡ Performance:")
        print(f"  Duration: {perf.get('total_duration_sec', 0):.2f} seconds")
        print(f"  Steps completed: {perf.get('steps_completed', 0)}")
        print(f"  Steps failed: {perf.get('steps_failed', 0)}")
        print(f"  Steps warned: {perf.get('steps_warned', 0)}")
        
        # Step-by-step breakdown
        steps = result.get("test_results", {}).get("steps", {})
        print(f"\n📋 Step-by-Step Breakdown:")
        
        for step_name, step_info in steps.items():
            status_icon = {
                "SUCCESS": "✅",
                "FAILED": "❌", 
                "WARNING": "⚠️",
                "START": "🔄"
            }.get(step_info["status"], "❓")
            
            print(f"  {status_icon} {step_name}: {step_info['status']}")
            
            if step_info.get("details"):
                for key, value in step_info["details"].items():
                    print(f"      {key}: {value}")
            
            if step_info.get("error"):
                print(f"      Error: {step_info['error']}")
        
        # Errors and warnings summary
        errors = result.get("test_results", {}).get("errors", [])
        warnings = result.get("test_results", {}).get("warnings", [])
        
        if errors:
            print(f"\n❌ Errors ({len(errors)}):")
            for error in errors:
                print(f"  • {error}")
        
        if warnings:
            print(f"\n⚠️ Warnings ({len(warnings)}):")
            for warning in warnings:
                print(f"  • {warning}")
        
        # Recommendations
        print(f"\n💡 Recommendations:")
        if not errors:
            print("  🎯 Pipeline is working correctly!")
            print("  ✅ Ready for production Alpha Gardeners scraping")
            print("  🚀 Deploy to Linux server for 24/7 operation")
        else:
            print("  🔧 Fix identified errors before production")
            print("  🧪 Run additional tests to verify fixes")


def main():
    """Run end-to-end test with full debugging."""
    tester = EndToEndTester()
    
    try:
        result = tester.run_complete_test()
        tester.print_detailed_report(result)
        
        # Save detailed report to file
        with open("end_to_end_test_report.json", "w") as f:
            json.dump(result, f, indent=2, default=str)
        
        print(f"\n📄 Detailed report saved to: end_to_end_test_report.json")
        
    except Exception as e:
        print(f"❌ Test execution failed: {e}")
        logger.error(f"Test execution error: {traceback.format_exc()}")


if __name__ == "__main__":
    main()
