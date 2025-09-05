#!/usr/bin/env python3
"""
Data Collection Validator for ag-trading-bot.
Ensures all necessary metrics are being reliably collected from Alpha Gardeners.
"""

import json
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
from typing import Dict, List, Any
from dotenv import load_dotenv

from config import settings

load_dotenv()


class DataCollectionValidator:
    """Validates data collection quality and completeness."""
    
    def __init__(self):
        self.required_features = [
            # Critical market metrics
            "market_cap_usd", "liquidity_usd", "liquidity_pct",
            
            # Security metrics (for objective validation)
            "ag_score", "mint_authority_flag", "freeze_authority_flag",
            "bundled_pct", "ds_paid_flag",
            
            # Holder metrics
            "holders_count", "top20_holders_pct",
            
            # Activity metrics
            "swaps_f_count", "swaps_kyc_count", "swaps_unique_count",
            
            # Volume metrics
            "volume_1m_to_mc_pct",
            
            # Platform and timing
            "source_platform", "token_age_sec", "win_prediction_pct",
            
            # Risk factors
            "fresh_deployer_flag", "skip_duplicates_flag"
        ]
        
        self.critical_features = [
            "market_cap_usd", "liquidity_usd", "ag_score", 
            "mint_authority_flag", "freeze_authority_flag"
        ]
    
    def check_data_completeness(self, hours_back: int = 24) -> Dict[str, Any]:
        """Check data collection completeness over recent period."""
        try:
            conn = psycopg2.connect(settings.DATABASE_URL, cursor_factory=RealDictCursor)
            
            # Overall pipeline stats
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 
                        COUNT(DISTINCT dr.message_id) as total_messages,
                        COUNT(DISTINCT mr.message_id) as resolved_messages,
                        COUNT(DISTINCT a.message_id) as accepted_messages,
                        COUNT(DISTINCT fs.message_id) as featured_messages,
                        COUNT(DISTINCT o.message_id) as outcome_messages
                    FROM discord_raw dr
                    LEFT JOIN mint_resolution mr ON dr.message_id = mr.message_id AND mr.resolved = true
                    LEFT JOIN acceptance_status a ON dr.message_id = a.message_id AND a.status = 'ACCEPT'
                    LEFT JOIN features_snapshot fs ON dr.message_id = fs.message_id
                    LEFT JOIN outcomes_24h o ON dr.message_id = o.message_id
                    WHERE dr.inserted_at >= NOW() - INTERVAL '%s hours'
                """, (hours_back,))
                
                pipeline_stats = cur.fetchone()
            
            # Feature completeness for accepted calls
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 
                        fs.message_id,
                        fs.features,
                        a.mint
                    FROM features_snapshot fs
                    JOIN acceptance_status a ON fs.message_id = a.message_id
                    WHERE a.status = 'ACCEPT'
                      AND fs.snapped_at >= NOW() - INTERVAL '%s hours'
                """, (hours_back,))
                
                feature_records = cur.fetchall()
            
            conn.close()
            
            # Analyze feature completeness
            feature_analysis = self._analyze_feature_completeness(feature_records)
            
            return {
                "period_hours": hours_back,
                "pipeline_stats": dict(pipeline_stats) if pipeline_stats else {},
                "feature_analysis": feature_analysis,
                "data_quality_score": self._calculate_quality_score(pipeline_stats, feature_analysis)
            }
            
        except Exception as e:
            return {"error": f"Data completeness check failed: {e}"}
    
    def _analyze_feature_completeness(self, feature_records: List[Dict]) -> Dict[str, Any]:
        """Analyze completeness of feature extraction."""
        if not feature_records:
            return {
                "total_records": 0,
                "feature_completeness": {},
                "critical_missing": [],
                "overall_completeness": 0.0
            }
        
        total_records = len(feature_records)
        feature_completeness = {}
        
        # Check each required feature
        for feature in self.required_features:
            present_count = 0
            
            for record in feature_records:
                features = record['features']
                if features.get(feature) is not None:
                    present_count += 1
            
            completeness_pct = (present_count / total_records) * 100
            feature_completeness[feature] = {
                "present": present_count,
                "total": total_records,
                "completeness_pct": completeness_pct
            }
        
        # Identify critical missing features
        critical_missing = []
        for feature in self.critical_features:
            if feature_completeness.get(feature, {}).get("completeness_pct", 0) < 80:
                critical_missing.append(feature)
        
        # Calculate overall completeness
        avg_completeness = sum(
            f["completeness_pct"] for f in feature_completeness.values()
        ) / len(feature_completeness)
        
        return {
            "total_records": total_records,
            "feature_completeness": feature_completeness,
            "critical_missing": critical_missing,
            "overall_completeness": avg_completeness
        }
    
    def _calculate_quality_score(self, pipeline_stats: Dict, feature_analysis: Dict) -> float:
        """Calculate overall data quality score (0-1)."""
        if not pipeline_stats or not feature_analysis:
            return 0.0
        
        # Pipeline efficiency (resolution rate)
        total_msgs = pipeline_stats.get("total_messages", 0)
        resolved_msgs = pipeline_stats.get("resolved_messages", 0)
        
        if total_msgs == 0:
            resolution_rate = 0
        else:
            resolution_rate = resolved_msgs / total_msgs
        
        # Feature completeness
        feature_completeness = feature_analysis.get("overall_completeness", 0) / 100
        
        # Critical feature penalty
        critical_missing = len(feature_analysis.get("critical_missing", []))
        critical_penalty = critical_missing * 0.2
        
        # Combined score
        quality_score = (resolution_rate * 0.4 + feature_completeness * 0.6) - critical_penalty
        
        return max(0.0, min(1.0, quality_score))
    
    def validate_training_readiness(self, min_samples: int = 100) -> Dict[str, Any]:
        """Check if we have enough quality data for training."""
        try:
            conn = psycopg2.connect(settings.DATABASE_URL, cursor_factory=RealDictCursor)
            
            with conn.cursor() as cur:
                # Check training data availability
                cur.execute("""
                    SELECT 
                        COUNT(*) as total_samples,
                        COUNT(CASE WHEN o.win = true THEN 1 END) as winners,
                        COUNT(CASE WHEN o.win = false THEN 1 END) as losers,
                        COUNT(DISTINCT DATE(fs.snapped_at)) as unique_days
                    FROM features_snapshot fs
                    JOIN acceptance_status a ON fs.message_id = a.message_id
                    LEFT JOIN outcomes_24h o ON fs.message_id = o.message_id
                    WHERE a.status = 'ACCEPT'
                      AND o.win IS NOT NULL
                """)
                
                training_stats = cur.fetchone()
                
                # Check feature quality for training samples
                cur.execute("""
                    SELECT 
                        fs.message_id,
                        fs.features
                    FROM features_snapshot fs
                    JOIN acceptance_status a ON fs.message_id = a.message_id
                    JOIN outcomes_24h o ON fs.message_id = o.message_id
                    WHERE a.status = 'ACCEPT'
                      AND o.win IS NOT NULL
                    ORDER BY fs.snapped_at DESC
                """)
                
                training_records = cur.fetchall()
            
            conn.close()
            
            # Analyze training data quality
            feature_quality = self._analyze_training_features(training_records)
            
            # Determine readiness
            total_samples = training_stats['total_samples'] if training_stats else 0
            is_ready = (
                total_samples >= min_samples and
                feature_quality["critical_completeness"] > 0.8 and
                len(feature_quality["unusable_records"]) < (total_samples * 0.1)
            )
            
            return {
                "is_ready": is_ready,
                "min_samples_required": min_samples,
                "training_stats": dict(training_stats) if training_stats else {},
                "feature_quality": feature_quality,
                "readiness_issues": self._identify_readiness_issues(training_stats, feature_quality, min_samples)
            }
            
        except Exception as e:
            return {"error": f"Training readiness check failed: {e}"}
    
    def _analyze_training_features(self, records: List[Dict]) -> Dict[str, Any]:
        """Analyze feature quality for training."""
        if not records:
            return {
                "critical_completeness": 0.0,
                "unusable_records": [],
                "feature_stats": {}
            }
        
        unusable_records = []
        feature_stats = {}
        
        # Check each record
        for record in records:
            features = record['features']
            message_id = record['message_id']
            
            # Check critical features
            missing_critical = []
            for feature in self.critical_features:
                if features.get(feature) is None:
                    missing_critical.append(feature)
            
            # Mark as unusable if missing too many critical features
            if len(missing_critical) > len(self.critical_features) * 0.5:
                unusable_records.append({
                    "message_id": message_id,
                    "missing_critical": missing_critical
                })
        
        # Calculate critical feature completeness
        usable_count = len(records) - len(unusable_records)
        critical_completeness = usable_count / len(records) if records else 0
        
        return {
            "total_records": len(records),
            "usable_records": usable_count,
            "unusable_records": unusable_records,
            "critical_completeness": critical_completeness,
            "feature_stats": feature_stats
        }
    
    def _identify_readiness_issues(self, training_stats: Dict, feature_quality: Dict, min_samples: int) -> List[str]:
        """Identify specific issues preventing training readiness."""
        issues = []
        
        total_samples = training_stats.get("total_samples", 0)
        
        if total_samples < min_samples:
            issues.append(f"Insufficient samples: {total_samples} < {min_samples}")
        
        if feature_quality["critical_completeness"] < 0.8:
            issues.append(f"Poor feature quality: {feature_quality['critical_completeness']:.1%} < 80%")
        
        if len(feature_quality["unusable_records"]) > total_samples * 0.1:
            issues.append(f"Too many unusable records: {len(feature_quality['unusable_records'])}")
        
        winners = training_stats.get("winners", 0)
        if winners < 10:
            issues.append(f"Insufficient winners for training: {winners} < 10")
        
        unique_days = training_stats.get("unique_days", 0)
        if unique_days < 7:
            issues.append(f"Insufficient temporal diversity: {unique_days} days < 7")
        
        return issues
    
    def generate_collection_report(self) -> Dict[str, Any]:
        """Generate comprehensive data collection report."""
        print("📊 Generating Data Collection Report...")
        
        # Check multiple time periods
        periods = [1, 6, 24, 168]  # 1h, 6h, 24h, 7d
        period_reports = {}
        
        for hours in periods:
            period_name = f"{hours}h" if hours < 24 else f"{hours//24}d"
            period_reports[period_name] = self.check_data_completeness(hours)
        
        # Training readiness
        training_readiness = self.validate_training_readiness()
        
        return {
            "generated_at": datetime.utcnow().isoformat(),
            "period_analysis": period_reports,
            "training_readiness": training_readiness
        }


def main():
    """Run comprehensive data collection validation."""
    print("🔍 AG-Trading-Bot Data Collection Validation")
    print("=" * 60)
    
    validator = DataCollectionValidator()
    
    # Generate full report
    report = validator.generate_collection_report()
    
    if "error" in report:
        print(f"❌ Validation error: {report['error']}")
        return
    
    # Display results
    print(f"\n📊 Data Collection Analysis:")
    
    for period, data in report["period_analysis"].items():
        if "error" in data:
            print(f"  ❌ {period}: {data['error']}")
            continue
        
        stats = data["pipeline_stats"]
        quality = data["data_quality_score"]
        
        print(f"\n  📅 {period} Period:")
        print(f"    Messages: {stats.get('total_messages', 0)}")
        print(f"    Resolved: {stats.get('resolved_messages', 0)}")
        print(f"    Accepted: {stats.get('accepted_messages', 0)}")
        print(f"    Featured: {stats.get('featured_messages', 0)}")
        print(f"    Quality Score: {quality:.2f}/1.0")
        
        # Feature completeness
        feature_analysis = data["feature_analysis"]
        if feature_analysis.get("total_records", 0) > 0:
            completeness = feature_analysis["overall_completeness"]
            print(f"    Feature Completeness: {completeness:.1f}%")
            
            if feature_analysis["critical_missing"]:
                print(f"    ⚠️ Critical Missing: {feature_analysis['critical_missing']}")
    
    # Training readiness
    training = report["training_readiness"]
    
    print(f"\n🧠 Training Readiness:")
    
    if "error" in training:
        print(f"  ❌ Error: {training['error']}")
    else:
        print(f"  Status: {'✅ READY' if training['is_ready'] else '⚠️ NOT READY'}")
        
        if training_stats := training.get("training_stats"):
            print(f"  Samples: {training_stats.get('total_samples', 0)}")
            print(f"  Winners: {training_stats.get('winners', 0)}")
            print(f"  Losers: {training_stats.get('losers', 0)}")
            print(f"  Days: {training_stats.get('unique_days', 0)}")
        
        if issues := training.get("readiness_issues"):
            print(f"\n  📋 Issues to Address:")
            for issue in issues:
                print(f"    • {issue}")
    
    # Recommendations
    print(f"\n💡 Recommendations:")
    
    # Check if we need more data
    latest_period = report["period_analysis"].get("24h", {})
    if latest_period.get("pipeline_stats", {}).get("total_messages", 0) == 0:
        print("  🚨 No recent messages - Discord scraper may not be working")
        print("    → Check Discord scraper process")
        print("    → Verify Discord credentials")
        print("    → Test manual message collection")
    
    # Check feature quality
    if latest_period.get("data_quality_score", 0) < 0.8:
        print("  ⚠️ Low data quality detected")
        print("    → Review metrics parser for missed fields")
        print("    → Check Discord message format changes")
        print("    → Validate feature extraction logic")
    
    # Training recommendations
    if not training.get("is_ready", False):
        print("  📚 Not ready for training")
        print("    → Collect more Alpha Gardeners calls")
        print("    → Wait for 24h outcome labeling")
        print("    → Ensure feature extraction is working")
    else:
        print("  🎯 Ready to begin ML training!")
        print("    → Run clustering: python train/cluster_router.py")
        print("    → Start GA training: python train/ga_trainer.py")
    
    return report


if __name__ == "__main__":
    main()
