#!/usr/bin/env python3
"""
Main pipeline runner for ag-trading-bot.
Orchestrates the complete pipeline from Discord scraping to signal generation.
"""

import asyncio
import logging
import argparse
from datetime import datetime
import asyncpg
from dotenv import load_dotenv

from config import settings
from ingest.discord_web_scraper import DiscordWebScraper
from ingest.mint_resolver import MintResolver
from outcomes.outcome_tracker import OutcomeTracker
from features.snapshot import FeatureSnapshot
from train.cluster_router import ClusterRouter
from train.ga_trainer import GATrainer
from signal.signal_service import SignalService

# Load environment
load_dotenv()

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format=settings.LOG_FORMAT
)
logger = logging.getLogger(__name__)


class AGTradingBotPipeline:
    """Main pipeline orchestrator for ag-trading-bot."""
    
    def __init__(self):
        self.db_pool = None
        
        # Pipeline components
        self.discord_scraper = None
        self.mint_resolver = None
        self.outcome_tracker = None
        self.feature_extractor = None
        self.cluster_router = None
        self.signal_service = None
    
    async def setup(self):
        """Initialize all pipeline components."""
        logger.info("🚀 Initializing AG-Trading-Bot pipeline...")
        
        # Validate configuration
        if not settings.validate_config():
            raise ValueError("Configuration validation failed")
        
        # Database connection
        self.db_pool = await asyncpg.create_pool(
            settings.DATABASE_URL,
            min_size=settings.DB_POOL_MIN_SIZE,
            max_size=settings.DB_POOL_MAX_SIZE
        )
        
        # Initialize components
        self.discord_scraper = DiscordWebScraper(self.db_pool)
        self.mint_resolver = MintResolver(self.db_pool)
        self.outcome_tracker = OutcomeTracker(self.db_pool)
        self.feature_extractor = FeatureSnapshot(self.db_pool)
        self.cluster_router = ClusterRouter(self.db_pool)
        self.signal_service = SignalService(self.db_pool)
        
        logger.info("✅ Pipeline components initialized")
    
    async def run_discord_scraper(self):
        """Run Discord message scraper."""
        logger.info("📡 Starting Discord message scraper...")
        await self.discord_scraper.start()
    
    async def process_mint_resolution(self):
        """Process pending mint resolutions."""
        logger.info("🔍 Processing mint resolutions...")
        await self.mint_resolver.process_pending()
    
    async def process_outcomes(self):
        """Process outcome tracking."""
        logger.info("📊 Processing outcome tracking...")
        await self.outcome_tracker.process_pending_outcomes()
    
    async def process_features(self):
        """Process feature extraction."""
        logger.info("📸 Processing feature extraction...")
        await self.feature_extractor.process_pending_features()
    
    async def train_clusters(self):
        """Train clustering model."""
        logger.info("🧠 Training clusters...")
        result = await self.cluster_router.train_clusters()
        logger.info(f"✅ Trained {result['n_clusters']} clusters")
        return result
    
    async def train_strategies(self):
        """Train strategies for all clusters."""
        logger.info("🎯 Training strategies...")
        
        # Get cluster count
        async with self.db_pool.acquire() as conn:
            cluster_count = await conn.fetchval("SELECT COUNT(*) FROM strategy_clusters")
        
        if cluster_count == 0:
            logger.warning("No clusters found - train clusters first")
            return
        
        # Train strategy for each cluster
        for cluster_id in range(cluster_count):
            logger.info(f"Training strategy for cluster {cluster_id}")
            trainer = GATrainer(self.db_pool, cluster_id)
            
            # For now, just create a simple test strategy
            individual = trainer.create_individual()
            training_data = await trainer.load_cluster_training_data()
            
            if len(training_data) >= 10:
                precision, penalty, picks = trainer.evaluate_strategy(individual, training_data)
                
                metrics = {
                    "buy_precision": precision,
                    "buy_rate_penalty": penalty,
                    "picks_per_day": picks,
                    "trained_at": datetime.utcnow().isoformat()
                }
                
                strategy_id = await trainer.save_strategy(individual, metrics)
                logger.info(f"💾 Saved strategy {strategy_id} for cluster {cluster_id}")
    
    async def generate_signals(self):
        """Generate trading signals."""
        logger.info("🎯 Generating trading signals...")
        await self.signal_service.process_pending_signals()
    
    async def run_full_pipeline(self):
        """Run the complete pipeline once."""
        logger.info("🔄 Running full pipeline...")
        
        # Process in order
        await self.process_mint_resolution()
        await self.process_outcomes() 
        await self.process_features()
        await self.generate_signals()
        
        logger.info("✅ Full pipeline complete")
    
    async def run_training_pipeline(self):
        """Run the nightly training pipeline."""
        logger.info("🌙 Running nightly training pipeline...")
        
        # Train clusters
        cluster_result = await self.train_clusters()
        
        # Train strategies
        await self.train_strategies()
        
        logger.info("✅ Training pipeline complete")
    
    async def get_pipeline_stats(self):
        """Get comprehensive pipeline statistics."""
        stats = {}
        
        # Message stats
        async with self.db_pool.acquire() as conn:
            message_stats = await conn.fetchrow("""
                SELECT 
                    COUNT(*) as total_messages,
                    COUNT(CASE WHEN payload->>'content' LIKE '%launch%' OR payload->>'content' LIKE '%🚀%' THEN 1 END) as potential_launches
                FROM discord_raw
                WHERE posted_at >= NOW() - INTERVAL '24 hours'
            """)
            stats["messages"] = dict(message_stats) if message_stats else {}
            
            # Resolution stats
            resolution_stats = await conn.fetchrow("""
                SELECT 
                    COUNT(*) as total_resolutions,
                    COUNT(CASE WHEN resolved = true THEN 1 END) as successful,
                    COUNT(CASE WHEN resolved = false THEN 1 END) as failed
                FROM mint_resolution
                WHERE resolved_at >= NOW() - INTERVAL '24 hours'
            """)
            stats["resolution"] = dict(resolution_stats) if resolution_stats else {}
            
            # Acceptance stats
            acceptance_stats = await conn.fetch("""
                SELECT status, COUNT(*) as count
                FROM acceptance_status
                WHERE first_seen >= NOW() - INTERVAL '24 hours'
                GROUP BY status
            """)
            stats["acceptance"] = {row["status"]: row["count"] for row in acceptance_stats}
            
            # Outcome stats
            outcome_stats = await conn.fetchrow("""
                SELECT 
                    COUNT(*) as total_outcomes,
                    COUNT(CASE WHEN touch_10x THEN 1 END) as touch_10x,
                    COUNT(CASE WHEN sustained_10x THEN 1 END) as sustained_10x,
                    COUNT(CASE WHEN win THEN 1 END) as wins
                FROM outcomes_24h
                WHERE computed_at >= NOW() - INTERVAL '7 days'
            """)
            stats["outcomes"] = dict(outcome_stats) if outcome_stats else {}
            
            # Signal stats
            signal_stats = await conn.fetchrow("""
                SELECT 
                    COUNT(*) as total_signals,
                    COUNT(CASE WHEN signal = 'BUY' THEN 1 END) as buy_signals,
                    COUNT(CASE WHEN signal = 'SKIP' THEN 1 END) as skip_signals
                FROM signals
                WHERE created_at >= NOW() - INTERVAL '24 hours'
            """)
            stats["signals"] = dict(signal_stats) if signal_stats else {}
        
        return stats
    
    async def cleanup(self):
        """Cleanup resources."""
        if self.discord_scraper:
            await self.discord_scraper.stop()
        if self.db_pool:
            await self.db_pool.close()


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="AG-Trading-Bot Pipeline")
    parser.add_argument("--mode", choices=[
        "scraper", "process", "train", "signals", "stats", "full"
    ], default="full", help="Pipeline mode")
    
    args = parser.parse_args()
    
    pipeline = AGTradingBotPipeline()
    
    try:
        await pipeline.setup()
        
        if args.mode == "scraper":
            await pipeline.run_discord_scraper()
        elif args.mode == "process":
            await pipeline.run_full_pipeline()
        elif args.mode == "train":
            await pipeline.run_training_pipeline()
        elif args.mode == "signals":
            await pipeline.generate_signals()
        elif args.mode == "stats":
            stats = await pipeline.get_pipeline_stats()
            
            print("\n📊 AG-Trading-Bot Pipeline Statistics:")
            print(f"Messages (24h): {stats['messages']}")
            print(f"Resolution (24h): {stats['resolution']}")
            print(f"Acceptance (24h): {stats['acceptance']}")
            print(f"Outcomes (7d): {stats['outcomes']}")
            print(f"Signals (24h): {stats['signals']}")
        elif args.mode == "full":
            # Run complete pipeline
            await pipeline.run_full_pipeline()
    
    finally:
        await pipeline.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
