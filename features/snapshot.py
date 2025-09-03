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
    
    async def extract_t0_features(self, message_id: str, mint_address: str) -> Dict[str, Any]:
        """
        Extract raw features at T0 for a given mint.
        
        Args:
            message_id: Discord message ID for T0 calculation
            mint_address: Token mint address
            
        Returns:
            Raw feature dictionary
        """
        t0 = get_entry_timestamp(message_id)
        
        logger.info(f"📸 Extracting T0 features for {mint_address} at {t0}")
        
        # Initialize features with defaults
        features = {
            "message_id": message_id,
            "mint_address": mint_address,
            "t0_timestamp": t0.isoformat(),
            "feature_version": self.feature_version
        }
        
        # 1. Liquidity and routing features
        liquidity_status, liquidity_data = await check_token_liquidity(mint_address)
        
        if liquidity_status == "LIQUIDITY_OK":
            features.update({
                "liquidity_usd": liquidity_data.get("liquidity_estimate_usd", 0),
                "buy_routes": liquidity_data.get("buy_routes", 0),
                "sell_routes": liquidity_data.get("sell_routes", 0),
                "max_price_impact": liquidity_data.get("max_impact", 1.0),
                "route_diversity": min(liquidity_data.get("buy_routes", 0), liquidity_data.get("sell_routes", 0))
            })
        else:
            features.update({
                "liquidity_usd": 0,
                "buy_routes": 0,
                "sell_routes": 0,
                "max_price_impact": 1.0,
                "route_diversity": 0
            })
        
        # 2. Market data from Birdeye
        async with BirdeyeClient() as birdeye:
            # Token overview
            try:
                url = f"{birdeye.base_url}/defi/token_overview"
                params = {"address": mint_address}
                
                async with birdeye.session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("success") and data.get("data"):
                            market_data = data["data"]
                            
                            features.update({
                                "volume_24h_usd": float(market_data.get("v24hUSD", 0)),
                                "volume_1h_usd": float(market_data.get("v1hUSD", 0)),
                                "market_cap_usd": float(market_data.get("mc", 0)),
                                "price_change_24h": float(market_data.get("v24hChangePercent", 0)),
                                "unique_wallets_24h": int(market_data.get("uniqueWallet24h", 0)),
                                "current_price": float(market_data.get("price", 0))
                            })
            except Exception as e:
                logger.warning(f"Failed to get market data: {e}")
            
            # Token security data
            try:
                url = f"{birdeye.base_url}/defi/token_security"
                params = {"address": mint_address}
                
                async with birdeye.session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("success") and data.get("data"):
                            security_data = data["data"]
                            
                            features.update({
                                "holder_count": int(security_data.get("holder", 0)),
                                "top10_concentration": float(security_data.get("top10HolderPercent", 0)) / 100,
                                "creator_percentage": float(security_data.get("creatorPercent", 0)) / 100
                            })
                            
                            # Calculate age
                            created_at = security_data.get("createdAt")
                            if created_at:
                                created_time = datetime.fromtimestamp(created_at / 1000)
                                age_minutes = (t0.replace(tzinfo=None) - created_time).total_seconds() / 60
                                features["age_minutes"] = max(0, age_minutes)
                            else:
                                features["age_minutes"] = 0
            except Exception as e:
                logger.warning(f"Failed to get security data: {e}")
        
        # 3. On-chain token data
        try:
            supply = await get_token_supply(mint_address)
            decimals = await get_token_decimals(mint_address)
            
            if supply is not None:
                features["total_supply"] = supply
            if decimals is not None:
                features["decimals"] = decimals
                
        except Exception as e:
            logger.warning(f"Failed to get token data: {e}")
        
        # 4. Derived features
        # Volume to market cap ratio
        volume_24h = features.get("volume_24h_usd", 0)
        market_cap = features.get("market_cap_usd", 0)
        
        if market_cap > 0:
            features["volume_to_mcap_ratio"] = volume_24h / market_cap
        else:
            features["volume_to_mcap_ratio"] = 0
        
        # Buy/sell pressure (placeholder - would need transaction analysis)
        features["buy_sell_ratio"] = 0.5  # Neutral default
        
        # Smart money score (placeholder - would need wallet analysis)
        features["smart_money_count"] = 0
        
        # Fill defaults for missing features
        for feature_name in self.feature_names:
            if feature_name not in features:
                features[feature_name] = 0
        
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
        
        # Get percentile stats for each feature over the lookback window
        lookback_hours = settings.PERCENTILE_WINDOW_HOURS
        
        for feature_name in self.feature_names:
            if feature_name in raw_features:
                raw_value = raw_features[feature_name]
                
                if isinstance(raw_value, (int, float)):
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
