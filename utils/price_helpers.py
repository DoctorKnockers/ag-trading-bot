"""
Price data utilities for market data and entry price calculation.
Source: labels.md - Entry price calculation and outcome tracking
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import aiohttp

from config import settings
from .time_utils import get_entry_timestamp

logger = logging.getLogger(__name__)


class BirdeyeClient:
    """Async Birdeye API client for price data."""
    
    def __init__(self):
        self.base_url = "https://public-api.birdeye.so"
        self.api_key = settings.BIRDEYE_API_KEY
        self.session = None
    
    async def __aenter__(self):
        """Async context manager entry."""
        headers = {}
        if self.api_key:
            headers["X-API-KEY"] = self.api_key
        
        self.session = aiohttp.ClientSession(headers=headers)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
    
    async def get_token_price(self, mint_address: str) -> Optional[float]:
        """Get current token price in USD."""
        try:
            url = f"{self.base_url}/defi/price"
            params = {"address": mint_address}
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("success"):
                        return float(data.get("data", {}).get("value", 0))
                        
        except Exception as e:
            logger.error(f"Birdeye price error: {e}")
        
        return None
    
    async def get_ohlcv_data(
        self,
        mint_address: str,
        start_time: int,
        end_time: int,
        interval: str = "1m"
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Get OHLCV candle data.
        
        Args:
            mint_address: Token mint address
            start_time: Unix timestamp start
            end_time: Unix timestamp end  
            interval: Candle interval (1m, 5m, 15m, 1h, 4h, 1d)
            
        Returns:
            List of OHLCV candles or None
        """
        try:
            url = f"{self.base_url}/defi/ohlcv"
            params = {
                "address": mint_address,
                "type": interval,
                "time_from": start_time,
                "time_to": end_time
            }
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("success"):
                        return data.get("data", {}).get("items", [])
                        
        except Exception as e:
            logger.error(f"Birdeye OHLCV error: {e}")
        
        return None


class DexscreenerClient:
    """Async Dexscreener client for fallback price data."""
    
    def __init__(self):
        self.base_url = "https://api.dexscreener.com/latest"
        self.session = None
    
    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
    
    async def get_token_price(self, mint_address: str) -> Optional[float]:
        """Get token price from Dexscreener as fallback."""
        try:
            url = f"{self.base_url}/dex/tokens/{mint_address}"
            
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    pairs = data.get("pairs", [])
                    
                    if pairs:
                        # Get highest liquidity pair
                        best_pair = max(pairs, key=lambda p: float(p.get("liquidity", {}).get("usd", 0)))
                        return float(best_pair.get("priceUsd", 0))
                        
        except Exception as e:
            logger.error(f"Dexscreener price error: {e}")
        
        return None


async def get_entry_price(message_id: str, mint_address: str) -> Optional[float]:
    """
    Get entry price at T0 per labels.md specification.
    
    Entry price = 1-min candle open that spans T0 (Birdeye preferred).
    If not available, use earliest reliable price after T0 (Dexscreener fallback).
    
    Args:
        message_id: Discord message ID for T0 calculation
        mint_address: Token mint address
        
    Returns:
        Entry price in USD or None
    """
    # Get T0 from message snowflake
    t0 = get_entry_timestamp(message_id)
    
    # Find the 1-minute candle that spans T0
    candle_start = t0.replace(second=0, microsecond=0)
    candle_end = candle_start + timedelta(minutes=1)
    
    logger.info(f"📈 Getting entry price for {mint_address} at T0={t0}")
    
    # Try Birdeye OHLCV first (preferred)
    async with BirdeyeClient() as birdeye:
        ohlcv_data = await birdeye.get_ohlcv_data(
            mint_address,
            int(candle_start.timestamp()),
            int(candle_end.timestamp()),
            "1m"
        )
        
        if ohlcv_data and len(ohlcv_data) > 0:
            # Use open price of the candle that spans T0
            entry_price = float(ohlcv_data[0].get("o", 0))
            logger.info(f"✅ Entry price from Birdeye: ${entry_price}")
            return entry_price
    
    # Fallback to Dexscreener (if within reasonable time window)
    time_since_t0 = (datetime.utcnow().replace(tzinfo=None) - t0.replace(tzinfo=None)).total_seconds()
    
    if time_since_t0 < 3600:  # Within 1 hour
        async with DexscreenerClient() as dexscreener:
            fallback_price = await dexscreener.get_token_price(mint_address)
            
            if fallback_price:
                logger.info(f"⚠️ Entry price from Dexscreener fallback: ${fallback_price}")
                return fallback_price
    
    logger.warning(f"❌ No entry price available for {mint_address}")
    return None


async def get_current_price(mint_address: str) -> Optional[float]:
    """Get current token price (Birdeye first, Dexscreener fallback)."""
    # Try Birdeye first
    async with BirdeyeClient() as birdeye:
        price = await birdeye.get_token_price(mint_address)
        if price:
            return price
    
    # Fallback to Dexscreener
    async with DexscreenerClient() as dexscreener:
        return await dexscreener.get_token_price(mint_address)


async def calculate_price_multiple(current_price: float, entry_price: float) -> float:
    """Calculate price multiple from entry."""
    if entry_price <= 0:
        return 0.0
    return current_price / entry_price
