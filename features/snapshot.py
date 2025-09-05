"""
Feature Snapshot - T0 feature extraction with normalized percentiles.
Source: spec.md - T0 features (normalized per-day percentiles). No leakage from future data.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import asyncpg

from config import settings
from utils.time_utils import get_entry_timestamp
from utils.price_helpers import BirdeyeClient, get_current_price
from utils.jupiter_helpers import check_token_liquidity
from utils.solana_helpers import get_token_supply, get_token_decimals
from ingest.metrics_parser import LaunchpadMetricsParser

logger = logging.getLogger(__name__)


class FeatureSnapshot:
    """
    Extracts T0 feature snapshots for accepted calls.
    
    Features are normalized to per-day percentiles to avoid temporal leakage.
    All features represent the state at T0 (entry time) only.
    """
    
    def __init__(self, db_pool: asyncpg.Pool):
        self.db_pool = db_pool
        self.feature_version = settings.FEATURE_VERSION
        
        # Feature names from settings
        self.feature_names = settings.FEATURE_NAMES
        
        # Metrics parser for Discord messages
        self.metrics_parser = LaunchpadMetricsParser()
    
    async def extract_t0_features(self, message_id: str, mint_address: str) -> Dict[str, Any]:
        """
        Extract raw features at T0 for a given mint.
        
        Args:
            message_id: Discord message ID for T0 calculation
            mint_address: Token mint address
            
        Returns:
            Raw feature dictionary with all Discord metrics + external API data
        """
        t0 = get_entry_timestamp(message_id)
        
        logger.info(f"📸 Extracting T0 features for {mint_address} at {t0}")
        
        # Step 1: Get original Discord message payload
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT payload FROM discord_raw WHERE message_id = $1
            """, message_id)
        
        if not row:
            raise ValueError(f"Discord message {message_id} not found")
        
        message_payload = row["payload"]
        
        # Step 2: Parse all metrics from Discord message
        discord_metrics = self.metrics_parser.parse_message_metrics(message_payload)
        validated_metrics = self.metrics_parser.validate_parsed_metrics(discord_metrics)
        
        # Step 3: Initialize features with Discord metrics + metadata
        features = {
            "message_id": message_id,
            "mint_address": mint_address,
            "t0_timestamp": t0.isoformat(),
            "feature_version": self.feature_version,
            
            # All Discord metrics
            **validated_metrics
        }
        
        # Step 4: Supplement with external API data (if Discord metrics are missing)
        # Only fetch external data for metrics not already captured from Discord
        
        if not features.get("liquidity_usd"):
            # Get Jupiter routing data as fallback
            liquidity_status, liquidity_data = await check_token_liquidity(mint_address)
            
            if liquidity_status == "LIQUIDITY_OK":
                features.update({
                    "external_liquidity_usd": liquidity_data.get("liquidity_estimate_usd", 0),
                    "external_buy_routes": liquidity_data.get("buy_routes", 0),
                    "external_sell_routes": liquidity_data.get("sell_routes", 0),
                    "external_max_price_impact": liquidity_data.get("max_impact", 1.0)
                })
        
        # Supplement with Birdeye data only if not in Discord metrics
        if not features.get("market_cap_usd") or not features.get("holders_count"):
            try:
                async with BirdeyeClient() as birdeye:
                    # Get additional market data
                    url = f"{birdeye.base_url}/defi/token_overview"
                    params = {"address": mint_address}
                    
                    async with birdeye.session.get(url, params=params) as response:
                        if response.status == 200:
                            data = await response.json()
                            if data.get("success") and data.get("data"):
                                market_data = data["data"]
                                
                                # Only update if not already from Discord
                                if not features.get("market_cap_usd"):
                                    features["external_market_cap_usd"] = float(market_data.get("mc", 0))
                                
                                if not features.get("volume_1m_total_usd"):
                                    features["external_volume_24h_usd"] = float(market_data.get("v24hUSD", 0))
                                
                                features["external_current_price"] = float(market_data.get("price", 0))
            except Exception as e:
                logger.warning(f"Failed to get external market data: {e}")
        
        # Step 5: Calculate derived features using Discord metrics as primary source
        # Use Discord metrics first, fallback to external
        primary_mc = features.get("market_cap_usd") or features.get("external_market_cap_usd", 0)
        primary_volume = features.get("volume_1m_total_usd") or features.get("external_volume_24h_usd", 0)
        
        if primary_mc > 0 and primary_volume > 0:
            features["derived_vol_to_mc_ratio"] = primary_volume / primary_mc
        else:
            features["derived_vol_to_mc_ratio"] = features.get("volume_1m_to_mc_pct", 0) / 100
        
        # Risk score based on Discord metrics
        risk_factors = []
        if features.get("mint_authority_flag"):
            risk_factors.append("mint_authority")
        if features.get("freeze_authority_flag"):
            risk_factors.append("freeze_authority")
        if features.get("creator_drained_count", 0) > 0:
            risk_factors.append("creator_drained")
        if features.get("bundled_pct", 0) > 50:
            risk_factors.append("high_bundled")
        
        features["risk_factors"] = risk_factors
        features["risk_score"] = len(risk_factors) / 4.0  # Normalize to 0-1
        
        return features
    
    async def normalize_features(self, raw_features: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize features to per-day percentiles to avoid temporal leakage.
        
        Args:
            raw_features: Raw feature values
            
        Returns:
            Normalized features with percentile values
        """
        normalized = raw_features.copy()
        
        # Get percentile stats for numeric features over the lookback window
        lookback_hours = settings.PERCENTILE_WINDOW_HOURS
        
        # Define which features to normalize (numeric only)
        numeric_features = [
            "win_prediction_pct", "market_cap_usd", "liquidity_usd", "liquidity_pct",
            "token_age_sec", "top10_holders_pct", "top20_holders_pct", "holders_count",
            "swaps_f_count", "swaps_kyc_count", "swaps_unique_count", "swaps_sm_count",
            "volume_1m_total_usd", "volume_1m_buy_pct", "volume_1m_sell_pct", "volume_1m_to_mc_pct",
            "ag_score", "bundled_pct", "creator_pct", "funding_age_min",
            "creator_drained_count", "creator_drained_total", "risk_score"
        ]
        
        for feature_name in numeric_features:
            if feature_name in raw_features:
                raw_value = raw_features[feature_name]
                
                if isinstance(raw_value, (int, float)) and raw_value is not None:
                    percentile = await self._get_feature_percentile(feature_name, raw_value, lookback_hours)
                    normalized[f"{feature_name}_pct"] = percentile
        
        # Also normalize legacy feature names for compatibility
        for feature_name in self.feature_names:
            if feature_name in raw_features:
                raw_value = raw_features[feature_name]
                
                if isinstance(raw_value, (int, float)) and raw_value is not None:
                    percentile = await self._get_feature_percentile(feature_name, raw_value, lookback_hours)
                    normalized[f"{feature_name}_pct"] = percentile
        
        return normalized
    
    async def _get_feature_percentile(
        self,
        feature_name: str,
        value: float,
        lookback_hours: int
    ) -> float:
        """
        Calculate percentile rank of a feature value within recent history.
        
        Args:
            feature_name: Name of the feature
            value: Current feature value
            lookback_hours: Hours to look back for percentile calculation
            
        Returns:
            Percentile rank (0.0 to 1.0)
        """
        query = """
            WITH recent_values AS (
                SELECT (features->>{})::float AS val
                FROM features_snapshot
                WHERE snapped_at >= NOW() - INTERVAL '{} hours'
                  AND features ? '{}'
                  AND (features->>{})::float IS NOT NULL
            )
            SELECT 
                COUNT(CASE WHEN val < {} THEN 1 END)::float / NULLIF(COUNT(*), 0) AS percentile
            FROM recent_values
        """.format(feature_name, lookback_hours, feature_name, feature_name, value)
        
        try:
            async with self.db_pool.acquire() as conn:
                result = await conn.fetchval(query)
                return float(result) if result is not None else 0.5
        except Exception as e:
            logger.warning(f"Percentile calculation failed for {feature_name}: {e}")
            return 0.5  # Default to median
    
    async def capture_and_store(self, message_id: str, mint_address: str) -> bool:
        """
        Capture T0 features and store in features_snapshot table.
        
        Args:
            message_id: Discord message ID
            mint_address: Token mint address
            
        Returns:
            Success status
        """
        try:
            # Check if already exists
            async with self.db_pool.acquire() as conn:
                exists = await conn.fetchval(
                    "SELECT 1 FROM features_snapshot WHERE message_id = $1",
                    message_id
                )
                
                if exists:
                    logger.info(f"Features already captured for {message_id}")
                    return True
            
            # Extract raw features
            raw_features = await self.extract_t0_features(message_id, mint_address)
            
            # Normalize features
            normalized_features = await self.normalize_features(raw_features)
            
            # Store in database
            t0 = get_entry_timestamp(message_id)
            
            async with self.db_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO features_snapshot (
                        message_id, snapped_at, features, feature_version
                    ) VALUES ($1, $2, $3, $4)
                    ON CONFLICT (message_id) DO UPDATE SET
                        features = $3,
                        feature_version = $4
                """,
                    message_id,
                    t0,
                    json.dumps(normalized_features),
                    int(self.feature_version.replace('v', '')) if isinstance(self.feature_version, str) else self.feature_version
                )
            
            logger.info(f"✅ Features captured for {message_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to capture features for {message_id}: {e}")
            return False
    
    async def process_pending_features(self):
        """Process accepted calls that need feature snapshots."""
        # Get accepted calls without features
        query = """
            SELECT a.message_id, a.mint
            FROM acceptance_status a
            LEFT JOIN features_snapshot f ON a.message_id = f.message_id
            WHERE a.status = 'ACCEPT'
              AND f.message_id IS NULL
              AND a.first_seen >= NOW() - INTERVAL '7 days'
            ORDER BY a.first_seen DESC
        """
        
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query)
        
        logger.info(f"📋 Found {len(rows)} calls needing feature extraction")
        
        success_count = 0
        
        for row in rows:
            message_id = row["message_id"]
            mint_address = row["mint"]
            
            if await self.capture_and_store(message_id, mint_address):
                success_count += 1
            
            # Rate limiting
            await asyncio.sleep(1)
        
        logger.info(f"✅ Captured features for {success_count}/{len(rows)} calls")


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
        snapshot = FeatureSnapshot(pool)
        
        # Process pending features
        await snapshot.process_pending_features()
        
        # Show stats
        async with pool.acquire() as conn:
            stats = await conn.fetchrow("""
                SELECT 
                    COUNT(*) as total_features,
                    COUNT(CASE WHEN snapped_at >= NOW() - INTERVAL '24 hours' THEN 1 END) as features_24h
                FROM features_snapshot
            """)
        
        print(f"\n📊 Feature Snapshot Stats:")
        print(f"Total features: {stats['total_features']}")
        print(f"Features (24h): {stats['features_24h']}")
    
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
