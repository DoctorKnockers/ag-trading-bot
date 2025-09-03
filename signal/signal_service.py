"""
Signal Service - BUY/SKIP signal generation for manual trading.
Source: spec.md - On ACCEPT events, load active strategy per cluster and emit BUY/SKIP to signals.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
import asyncpg

from config import settings
from features.snapshot import FeatureSnapshot
from train.cluster_router import ClusterRouter

logger = logging.getLogger(__name__)


class SignalService:
    """
    Generates BUY/SKIP signals for manual trading.
    
    Processes new accepted calls through:
    1. Feature extraction at T0
    2. Cluster assignment with OOD detection
    3. Strategy scoring with active parameters
    4. BUY/SKIP decision with logging
    """
    
    def __init__(self, db_pool: asyncpg.Pool):
        self.db_pool = db_pool
        self.feature_extractor = FeatureSnapshot(db_pool)
        self.cluster_router = ClusterRouter(db_pool)
        
        # Cache for active strategies
        self._strategy_cache = {}
        self._cache_timestamp = None
        self._cache_ttl = 300  # 5 minutes
    
    async def generate_signal(self, message_id: str, mint_address: str) -> Dict[str, Any]:
        """
        Generate BUY/SKIP signal for an accepted call.
        
        Args:
            message_id: Discord message ID
            mint_address: Token mint address
            
        Returns:
            Signal generation result
        """
        logger.info(f"🎯 Generating signal for {mint_address}")
        
        try:
            # Step 1: Extract T0 features
            success = await self.feature_extractor.capture_and_store(message_id, mint_address)
            if not success:
                return {
                    "error": "Failed to extract features",
                    "message_id": message_id,
                    "mint_address": mint_address
                }
            
            # Step 2: Get features for scoring
            async with self.db_pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT features 
                    FROM features_snapshot 
                    WHERE message_id = $1
                """, message_id)
            
            if not row:
                return {"error": "Features not found"}
            
            features = row["features"]
            
            # Step 3: Assign cluster
            cluster_id, distance, is_ood = await self.cluster_router.assign_cluster(features)
            
            logger.info(f"📊 Cluster assignment: {cluster_id} (distance={distance:.3f}, OOD={is_ood})")
            
            # Step 4: Load active strategy for cluster
            strategy = await self._get_active_strategy(cluster_id)
            
            if not strategy:
                signal = "SKIP"
                score = 0.0
                reason = "No active strategy"
            else:
                # Step 5: Score with strategy
                score = self._score_with_strategy(features, strategy)
                
                # Step 6: Apply decision logic
                if is_ood and distance > 2.0:
                    signal = "SKIP"
                    reason = f"OOD (distance={distance:.2f})"
                elif score < 0:
                    signal = "SKIP"
                    reason = "Failed thresholds"
                else:
                    # Apply buy cutoff
                    buy_threshold = strategy["thresholds"]["buy_cutoff"] * 2.0  # Scale factor
                    
                    if score >= buy_threshold:
                        signal = "BUY"
                        reason = f"Score {score:.3f} ≥ threshold {buy_threshold:.3f}"
                    else:
                        signal = "SKIP"
                        reason = f"Score {score:.3f} < threshold {buy_threshold:.3f}"
            
            # Step 7: Store signal
            signal_id = await self._store_signal(
                message_id,
                mint_address,
                cluster_id,
                strategy.get("id") if strategy else None,
                signal,
                score,
                {
                    "distance": distance,
                    "is_ood": is_ood,
                    "reason": reason
                }
            )
            
            # Step 8: Log result
            log_level = logging.WARNING if signal == "BUY" else logging.INFO
            logger.log(log_level, f"🎯 SIGNAL: {signal} for {mint_address} (score={score:.3f})")
            
            return {
                "signal_id": signal_id,
                "message_id": message_id,
                "mint_address": mint_address,
                "signal": signal,
                "score": score,
                "cluster_id": cluster_id,
                "strategy_id": strategy.get("id") if strategy else None,
                "reason": reason,
                "is_ood": is_ood
            }
            
        except Exception as e:
            logger.error(f"❌ Signal generation failed for {message_id}: {e}")
            return {
                "error": str(e),
                "message_id": message_id,
                "mint_address": mint_address
            }
    
    async def _get_active_strategy(self, cluster_id: int) -> Optional[Dict[str, Any]]:
        """Get active strategy for cluster with caching."""
        cache_key = f"cluster_{cluster_id}"
        
        # Check cache
        if (self._strategy_cache.get(cache_key) and 
            self._cache_timestamp and
            (datetime.utcnow() - self._cache_timestamp).total_seconds() < self._cache_ttl):
            return self._strategy_cache[cache_key]
        
        # Load from database
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT id, thresholds, weights, metrics
                FROM strategy_params
                WHERE cluster_id = $1 AND active = true
                LIMIT 1
            """, cluster_id)
        
        if not row:
            logger.warning(f"No active strategy for cluster {cluster_id}")
            return None
        
        strategy = {
            "id": row["id"],
            "thresholds": row["thresholds"],
            "weights": row["weights"],
            "metrics": row["metrics"]
        }
        
        # Update cache
        self._strategy_cache[cache_key] = strategy
        self._cache_timestamp = datetime.utcnow()
        
        return strategy
    
    def _score_with_strategy(self, features: Dict[str, Any], strategy: Dict[str, Any]) -> float:
        """Score features using strategy parameters."""
        thresholds = strategy["thresholds"]
        weights = strategy["weights"]
        
        # Apply thresholds
        liq_pct = features.get("liquidity_usd_pct", 0.5)
        vol_pct = features.get("volume_24h_usd_pct", 0.5)
        holder_pct = features.get("holder_count_pct", 0.5)
        
        if (liq_pct < thresholds.get("liquidity_threshold", 0.5) or
            vol_pct < thresholds.get("volume_threshold", 0.5) or
            holder_pct < thresholds.get("holder_threshold", 0.5)):
            return -1.0  # Fail thresholds
        
        # Calculate weighted score
        score = (
            weights.get("liquidity_weight", 1.0) * liq_pct +
            weights.get("volume_weight", 1.0) * vol_pct +
            weights.get("holder_weight", 1.0) * holder_pct
        )
        
        return score
    
    async def _store_signal(
        self,
        message_id: str,
        mint_address: str,
        cluster_id: int,
        strategy_id: Optional[str],
        signal: str,
        score: float,
        metadata: Dict[str, Any]
    ) -> int:
        """Store signal in database (matches existing schema)."""
        async with self.db_pool.acquire() as conn:
            signal_id = await conn.fetchval("""
                INSERT INTO signals (
                    message_id, cluster_id, strategy_id, signal, score, sent_at
                ) VALUES ($1, $2, $3, $4, $5, NOW())
                RETURNING id
            """,
                message_id,
                cluster_id,
                strategy_id,
                signal,
                score
            )
        
        return signal_id
    
    async def process_pending_signals(self):
        """Process accepted calls that need signals."""
        # Get accepted calls without signals
        query = """
            SELECT a.message_id, a.mint
            FROM acceptance_status a
            LEFT JOIN signals s ON a.message_id = s.message_id
            WHERE a.status = 'ACCEPT'
              AND s.id IS NULL
              AND a.first_seen >= NOW() - INTERVAL '24 hours'
            ORDER BY a.first_seen DESC
        """
        
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query)
        
        logger.info(f"📋 Found {len(rows)} calls needing signals")
        
        for row in rows:
            message_id = row["message_id"]
            mint_address = row["mint"]
            
            result = await self.generate_signal(message_id, mint_address)
            
            if "error" in result:
                logger.warning(f"⚠️ Signal error for {mint_address}: {result['error']}")
            
            # Rate limiting
            await asyncio.sleep(0.5)
    
    async def get_signal_stats(self) -> Dict[str, Any]:
        """Get signal generation statistics."""
        async with self.db_pool.acquire() as conn:
            # Overall stats
            overall = await conn.fetchrow("""
                SELECT 
                    COUNT(*) as total_signals,
                    COUNT(CASE WHEN signal = 'BUY' THEN 1 END) as buy_signals,
                    COUNT(CASE WHEN signal = 'SKIP' THEN 1 END) as skip_signals,
                    AVG(score) as avg_score
                FROM signals
                WHERE created_at >= NOW() - INTERVAL '7 days'
            """)
            
            # Recent signals
            recent = await conn.fetch("""
                SELECT 
                    s.message_id,
                    a.mint,
                    s.signal,
                    s.score,
                    s.cluster_id,
                    s.created_at,
                    o.win
                FROM signals s
                JOIN acceptance_status a ON s.message_id = a.message_id
                LEFT JOIN outcomes_24h o ON s.message_id = o.message_id
                WHERE s.created_at >= NOW() - INTERVAL '24 hours'
                ORDER BY s.created_at DESC
                LIMIT 10
            """)
        
        return {
            "overall_stats": dict(overall) if overall else {},
            "recent_signals": [dict(row) for row in recent]
        }


async def main():
    """Example usage and testing."""
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format=settings.LOG_FORMAT
    )
    
    # Create database pool
    pool = await asyncpg.create_pool(settings.DATABASE_URL)
    
    try:
        service = SignalService(pool)
        
        # Process pending signals
        await service.process_pending_signals()
        
        # Show stats
        stats = await service.get_signal_stats()
        
        print(f"\n🎯 Signal Generation Stats:")
        overall = stats['overall_stats']
        if overall.get('total_signals', 0) > 0:
            print(f"Total signals (7d): {overall['total_signals']}")
            print(f"BUY signals: {overall['buy_signals']}")
            print(f"SKIP signals: {overall['skip_signals']}")
            print(f"Buy rate: {overall['buy_signals']/overall['total_signals']*100:.1f}%")
            print(f"Avg score: {overall.get('avg_score', 0):.3f}")
        
        # Show recent signals
        recent = stats['recent_signals']
        if recent:
            print(f"\n📋 Recent Signals (24h):")
            for signal in recent[:5]:
                outcome = "🏆 WIN" if signal.get('win') else "❓ TBD" if signal['win'] is None else "❌ LOSS"
                print(f"  {signal['signal']} {signal['mint'][:8]}... (score: {signal['score']:.3f}) {outcome}")
    
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
