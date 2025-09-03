"""
Outcome Tracker - 24h monitoring and SUSTAINED_10X labeling.
Source: labels.md - Winner definition and execution simulation
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
import asyncpg

from config import settings
from utils.time_utils import get_entry_timestamp
from utils.price_helpers import get_entry_price, get_current_price, BirdeyeClient
from utils.jupiter_helpers import test_token_executability

logger = logging.getLogger(__name__)


class OutcomeTracker:
    """
    Tracks 24-hour outcomes for accepted tokens.
    
    Implements SUSTAINED_10X labeling per labels.md:
    - Price ≥ 10× entry for ≥ 180s
    - AND simulated sell of Q_TEST_SOL shows effective slippage ≤ 15%
    """
    
    def __init__(self, db_pool: asyncpg.Pool):
        self.db_pool = db_pool
        
        # Tracking parameters from spec.md
        self.multiple = settings.MULTIPLE  # 10x
        self.dwell_seconds = settings.T_DWELL_SEC  # 180s
        self.test_sol_amount = settings.Q_TEST_SOL  # 0.5 SOL
        self.max_slippage = settings.S_MAX  # 15%
        
        # Price monitoring state
        self.active_monitors = {}  # message_id -> monitor state
    
    async def start_monitoring_accepted_call(self, message_id: str, mint_address: str):
        """
        Start 24-hour monitoring for an accepted call.
        
        Args:
            message_id: Discord message ID
            mint_address: Token mint to monitor
        """
        logger.info(f"🎯 Starting 24h monitoring: {message_id} → {mint_address}")
        
        # Get T0 and entry price
        t0 = get_entry_timestamp(message_id)
        entry_price = await get_entry_price(message_id, mint_address)
        
        if not entry_price or entry_price <= 0:
            logger.error(f"❌ No entry price for {mint_address} - cannot monitor")
            return
        
        target_price = entry_price * self.multiple
        
        logger.info(f"📊 Monitoring setup: entry=${entry_price:.6f}, target=${target_price:.6f}")
        
        # Initialize monitoring state
        monitor_state = {
            "message_id": message_id,
            "mint_address": mint_address,
            "t0": t0,
            "entry_price": entry_price,
            "target_price": target_price,
            "max_price": entry_price,
            "touch_10x": False,
            "sustained_10x": False,
            "first_10x_time": None,
            "sustained_start": None,
            "sustained_end": None,
            "executability_tested": False,
            "price_history": []
        }
        
        self.active_monitors[message_id] = monitor_state
        
        # Store initial monitor state
        await self._store_monitor_state(monitor_state)
        
        # Start monitoring task
        asyncio.create_task(self._monitor_token_24h(monitor_state))
    
    async def _monitor_token_24h(self, monitor_state: Dict[str, Any]):
        """Monitor a token for 24 hours."""
        message_id = monitor_state["message_id"]
        mint_address = monitor_state["mint_address"]
        t0 = monitor_state["t0"]
        
        end_time = t0 + timedelta(hours=24)
        
        logger.info(f"⏰ Starting 24h monitoring for {mint_address} until {end_time}")
        
        try:
            while datetime.utcnow().replace(tzinfo=None) < end_time.replace(tzinfo=None):
                # Get current price
                current_price = await get_current_price(mint_address)
                
                if current_price and current_price > 0:
                    await self._process_price_update(monitor_state, current_price)
                
                # Check every 30 seconds
                await asyncio.sleep(30)
            
            # 24h period complete
            logger.info(f"⏰ 24h monitoring complete for {mint_address}")
            await self._finalize_outcome(monitor_state)
            
        except Exception as e:
            logger.error(f"❌ Monitoring error for {mint_address}: {e}")
        finally:
            # Remove from active monitors
            if message_id in self.active_monitors:
                del self.active_monitors[message_id]
    
    async def _process_price_update(self, monitor_state: Dict[str, Any], current_price: float):
        """Process a price update and check for SUSTAINED_10X conditions."""
        mint_address = monitor_state["mint_address"]
        target_price = monitor_state["target_price"]
        
        # Update max price
        if current_price > monitor_state["max_price"]:
            monitor_state["max_price"] = current_price
        
        # Add to price history
        monitor_state["price_history"].append({
            "timestamp": datetime.utcnow(),
            "price": current_price,
            "multiple": current_price / monitor_state["entry_price"]
        })
        
        # Keep only recent history (last 10 minutes for dwell calculation)
        cutoff_time = datetime.utcnow() - timedelta(minutes=10)
        monitor_state["price_history"] = [
            p for p in monitor_state["price_history"] 
            if p["timestamp"] > cutoff_time
        ]
        
        # Check for 10x touch
        if current_price >= target_price:
            if not monitor_state["touch_10x"]:
                monitor_state["touch_10x"] = True
                monitor_state["first_10x_time"] = datetime.utcnow()
                logger.info(f"🎉 TOUCH_10X: {mint_address} hit {current_price/monitor_state['entry_price']:.1f}x")
            
            # Check for sustained 10x (≥ 180s above target)
            if not monitor_state["sustained_10x"]:
                # Find continuous period above target
                above_target_start = None
                
                for price_point in reversed(monitor_state["price_history"]):
                    if price_point["price"] >= target_price:
                        above_target_start = price_point["timestamp"]
                    else:
                        break
                
                if above_target_start:
                    duration_seconds = (datetime.utcnow() - above_target_start).total_seconds()
                    
                    if duration_seconds >= self.dwell_seconds:
                        # Sustained for required duration - test executability
                        logger.info(f"⏳ DWELL_MET: {mint_address} sustained for {duration_seconds:.0f}s")
                        
                        if not monitor_state["executability_tested"]:
                            is_executable, test_results = await test_token_executability(
                                mint_address,
                                self.test_sol_amount,
                                self.max_slippage
                            )
                            
                            monitor_state["executability_tested"] = True
                            monitor_state["executability_results"] = test_results
                            
                            if is_executable:
                                monitor_state["sustained_10x"] = True
                                monitor_state["sustained_start"] = above_target_start
                                logger.info(f"🏆 SUSTAINED_10X: {mint_address} - WINNER!")
                            else:
                                logger.info(f"❌ FAILED_EXECUTABILITY: {mint_address} - not executable")
        
        else:
            # Below target - reset sustained tracking if we had it
            if monitor_state.get("sustained_start") and not monitor_state["sustained_10x"]:
                # Was above target but dropped before executability test
                monitor_state["sustained_start"] = None
        
        # Store update every 5 minutes or on significant events
        should_store = (
            monitor_state["touch_10x"] or
            monitor_state["sustained_10x"] or
            len(monitor_state["price_history"]) % 10 == 0  # Every 10 price updates
        )
        
        if should_store:
            await self._store_monitor_state(monitor_state)
    
    async def _store_monitor_state(self, monitor_state: Dict[str, Any]):
        """Store/update monitor state in database (matches existing schema)."""
        try:
            async with self.db_pool.acquire() as conn:
                # Store in monitor_state table
                await conn.execute("""
                    INSERT INTO monitor_state (
                        message_id, mint, entry_price_usd, started_at, max_price_usd,
                        above_since, time_above_mult_s, size_ok, sustained, last_seen_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
                    ON CONFLICT (message_id) DO UPDATE SET
                        max_price_usd = GREATEST(monitor_state.max_price_usd, $5),
                        above_since = CASE 
                            WHEN $5 >= $3 * {} THEN COALESCE(monitor_state.above_since, NOW())
                            ELSE NULL 
                        END,
                        time_above_mult_s = CASE
                            WHEN $5 >= $3 * {} AND monitor_state.above_since IS NOT NULL
                            THEN EXTRACT(EPOCH FROM (NOW() - monitor_state.above_since))::INTEGER
                            ELSE 0
                        END,
                        size_ok = $8,
                        sustained = $9,
                        last_seen_at = NOW()
                """.format(self.multiple, self.multiple),
                    monitor_state["message_id"],
                    monitor_state["mint_address"],
                    monitor_state["entry_price"],
                    monitor_state["t0"],
                    monitor_state["max_price"],
                    monitor_state.get("sustained_start"),
                    monitor_state.get("sustained_duration", 0),
                    monitor_state.get("executability_tested", False),
                    monitor_state["sustained_10x"],
                )
                
        except Exception as e:
            logger.error(f"Failed to store monitor state: {e}")
    
    async def _finalize_outcome(self, monitor_state: Dict[str, Any]):
        """Finalize 24h outcome with complete data."""
        message_id = monitor_state["message_id"]
        mint_address = monitor_state["mint_address"]
        
        # Final outcome summary
        outcome_summary = {
            "message_id": message_id,
            "mint_address": mint_address,
            "entry_price": monitor_state["entry_price"],
            "max_price": monitor_state["max_price"],
            "max_multiple": monitor_state["max_price"] / monitor_state["entry_price"],
            "touch_10x": monitor_state["touch_10x"],
            "sustained_10x": monitor_state["sustained_10x"],
            "win": monitor_state["sustained_10x"],
            "first_10x_time": monitor_state.get("first_10x_time"),
            "sustained_duration": None,
            "executability_results": monitor_state.get("executability_results")
        }
        
        # Calculate sustained duration if applicable
        if monitor_state.get("sustained_start"):
            sustained_end = monitor_state.get("sustained_end", datetime.utcnow())
            duration = (sustained_end - monitor_state["sustained_start"]).total_seconds()
            outcome_summary["sustained_duration"] = duration
        
        # Store final outcome
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute("""
                    UPDATE outcomes_24h SET
                        max_24h_price_usd = $2,
                        touch_10x = $3,
                        sustained_10x = $4,
                        win = $5,
                        computed_at = NOW()
                    WHERE message_id = $1
                """,
                    message_id,
                    monitor_state["max_price"],
                    monitor_state["touch_10x"],
                    monitor_state["sustained_10x"],
                    monitor_state["sustained_10x"]
                )
                
                logger.info(f"📋 Final outcome stored for {mint_address}")
                
                # Log final result
                if outcome_summary["win"]:
                    logger.info(f"🏆 WINNER: {mint_address} - SUSTAINED_10X achieved!")
                elif outcome_summary["touch_10x"]:
                    logger.info(f"📈 TOUCH_10X: {mint_address} - touched {outcome_summary['max_multiple']:.1f}x but not sustained")
                else:
                    logger.info(f"📉 NO_10X: {mint_address} - max {outcome_summary['max_multiple']:.1f}x")
                    
        except Exception as e:
            logger.error(f"Failed to finalize outcome: {e}")
    
    async def process_pending_outcomes(self):
        """Process accepted calls that need outcome tracking."""
        # Get accepted calls from last 25 hours that don't have complete outcomes
        query = """
            SELECT a.message_id, a.mint, a.first_seen
            FROM acceptance_status a
            LEFT JOIN outcomes_24h o ON a.message_id = o.message_id
            WHERE a.status = 'ACCEPT'
              AND a.first_seen >= NOW() - INTERVAL '25 hours'
              AND (o.message_id IS NULL OR o.computed_at < NOW() - INTERVAL '5 minutes')
            ORDER BY a.first_seen DESC
        """
        
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query)
        
        logger.info(f"📋 Found {len(rows)} calls needing outcome tracking")
        
        for row in rows:
            message_id = row["message_id"]
            mint_address = row["mint"]
            
            # Skip if already monitoring
            if message_id in self.active_monitors:
                continue
            
            # Check if 24h period is complete
            t0 = get_entry_timestamp(message_id)
            hours_elapsed = (datetime.utcnow().replace(tzinfo=None) - t0.replace(tzinfo=None)).total_seconds() / 3600
            
            if hours_elapsed >= 24:
                # Complete 24h analysis
                await self._analyze_complete_24h(message_id, mint_address)
            else:
                # Start real-time monitoring
                await self.start_monitoring_accepted_call(message_id, mint_address)
    
    async def _analyze_complete_24h(self, message_id: str, mint_address: str):
        """Analyze complete 24h period using historical data."""
        logger.info(f"📊 Analyzing complete 24h for {mint_address}")
        
        # Get T0 and entry price
        t0 = get_entry_timestamp(message_id)
        entry_price = await get_entry_price(message_id, mint_address)
        
        if not entry_price:
            logger.warning(f"⚠️ No entry price for {mint_address}")
            return
        
        # Get 24h OHLCV data
        start_timestamp = int(t0.timestamp())
        end_timestamp = start_timestamp + (24 * 3600)  # 24 hours
        
        async with BirdeyeClient() as birdeye:
            ohlcv_data = await birdeye.get_ohlcv_data(
                mint_address,
                start_timestamp,
                end_timestamp,
                "1m"
            )
        
        if not ohlcv_data:
            logger.warning(f"⚠️ No OHLCV data for {mint_address}")
            return
        
        # Analyze price action
        target_price = entry_price * self.multiple
        max_price = entry_price
        touch_10x = False
        sustained_10x = False
        
        # Track periods above target
        above_target_periods = []
        current_period_start = None
        
        for candle in ohlcv_data:
            high = float(candle.get("h", 0))
            low = float(candle.get("l", 0))
            timestamp = candle.get("unixTime", 0)
            
            # Update max price
            if high > max_price:
                max_price = high
            
            # Check if touched 10x
            if high >= target_price:
                touch_10x = True
                
                # Track period start
                if current_period_start is None:
                    current_period_start = timestamp
            
            # Check if dropped below target
            if low < target_price and current_period_start is not None:
                # Period ended
                period_duration = timestamp - current_period_start
                above_target_periods.append({
                    "start": current_period_start,
                    "end": timestamp,
                    "duration": period_duration
                })
                current_period_start = None
        
        # Check for final period (if still above at end)
        if current_period_start is not None:
            final_duration = end_timestamp - current_period_start
            above_target_periods.append({
                "start": current_period_start,
                "end": end_timestamp,
                "duration": final_duration
            })
        
        # Check for sustained 10x
        for period in above_target_periods:
            if period["duration"] >= self.dwell_seconds:
                # Found sustained period - test executability
                logger.info(f"⏳ Found sustained period: {period['duration']}s")
                
                is_executable, test_results = await test_token_executability(
                    mint_address,
                    self.test_sol_amount,
                    self.max_slippage
                )
                
                if is_executable:
                    sustained_10x = True
                    logger.info(f"🏆 SUSTAINED_10X confirmed for {mint_address}")
                    break
                else:
                    logger.info(f"❌ Failed executability: {test_results.get('effective_slippage', 0):.1%} > {self.max_slippage:.1%}")
        
        # Store final outcome
        win = sustained_10x  # win = sustained_10x per spec
        
        async with self.db_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO outcomes_24h (
                    message_id, entry_price_usd, max_24h_price_usd,
                    touch_10x, sustained_10x, win, computed_at, outcomes_version
                ) VALUES ($1, $2, $3, $4, $5, $6, NOW(), 1)
                ON CONFLICT (message_id) DO UPDATE SET
                    entry_price_usd = $2,
                    max_24h_price_usd = $3,
                    touch_10x = $4,
                    sustained_10x = $5,
                    win = $6,
                    computed_at = NOW()
            """,
                message_id,
                entry_price,
                max_price,
                touch_10x,
                sustained_10x,
                win
            )
        
        # Log result summary
        multiple = max_price / entry_price
        logger.info(f"📊 {mint_address} outcome: {multiple:.1f}x max, touch_10x={touch_10x}, sustained_10x={sustained_10x}, WIN={win}")
    
    async def get_monitoring_stats(self) -> Dict[str, Any]:
        """Get current monitoring statistics."""
        async with self.db_pool.acquire() as conn:
            # Overall stats
            overall = await conn.fetchrow("""
                SELECT 
                    COUNT(*) as total_outcomes,
                    COUNT(CASE WHEN touch_10x THEN 1 END) as touch_10x_count,
                    COUNT(CASE WHEN sustained_10x THEN 1 END) as sustained_10x_count,
                    COUNT(CASE WHEN win THEN 1 END) as wins,
                    AVG(max_24h_price_usd / NULLIF(entry_price_usd, 0)) as avg_max_multiple
                FROM outcomes_24h
                WHERE computed_at >= NOW() - INTERVAL '7 days'
            """)
            
            # Recent outcomes
            recent = await conn.fetch("""
                SELECT 
                    o.message_id,
                    a.mint,
                    o.entry_price_usd,
                    o.max_24h_price_usd,
                    o.max_24h_price_usd / NULLIF(o.entry_price_usd, 0) as max_multiple,
                    o.touch_10x,
                    o.sustained_10x,
                    o.win,
                    o.computed_at
                FROM outcomes_24h o
                JOIN acceptance_status a ON o.message_id = a.message_id
                WHERE o.computed_at >= NOW() - INTERVAL '24 hours'
                ORDER BY o.computed_at DESC
                LIMIT 10
            """)
        
        return {
            "active_monitors": len(self.active_monitors),
            "overall_stats": dict(overall) if overall else {},
            "recent_outcomes": [dict(row) for row in recent]
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
        tracker = OutcomeTracker(pool)
        
        # Process any pending outcomes
        await tracker.process_pending_outcomes()
        
        # Show stats
        stats = await tracker.get_monitoring_stats()
        
        print(f"\n📊 Outcome Tracking Stats:")
        print(f"Active monitors: {stats['active_monitors']}")
        
        overall = stats['overall_stats']
        if overall.get('total_outcomes', 0) > 0:
            print(f"Total outcomes (7d): {overall['total_outcomes']}")
            print(f"Touch 10x: {overall['touch_10x_count']} ({overall['touch_10x_count']/overall['total_outcomes']*100:.1f}%)")
            print(f"Sustained 10x: {overall['sustained_10x_count']} ({overall['sustained_10x_count']/overall['total_outcomes']*100:.1f}%)")
            print(f"Winners: {overall['wins']} ({overall['wins']/overall['total_outcomes']*100:.1f}%)")
            print(f"Avg max multiple: {overall.get('avg_max_multiple', 0):.1f}x")
        
        # Show recent outcomes
        recent = stats['recent_outcomes']
        if recent:
            print(f"\n📋 Recent Outcomes (24h):")
            for outcome in recent[:5]:
                status = "🏆 WIN" if outcome['win'] else "📈 TOUCH" if outcome['touch_10x'] else "📉 MISS"
                print(f"  {status} {outcome['mint'][:8]}... {outcome['max_multiple']:.1f}x")
    
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
