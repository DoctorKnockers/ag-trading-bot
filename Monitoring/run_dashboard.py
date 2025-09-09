#!/usr/bin/env python3
"""
Run the Rich dashboard for real-time monitoring.
"""

import asyncio
import logging
import signal
import sys
from dotenv import load_dotenv
import asyncpg

from config import settings
from monitoring.rich_dashboard import TradingDashboard

load_dotenv()

# Setup logging (minimal for dashboard)
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


async def main():
    """Main dashboard runner."""
    print("Starting AG Trading Bot Dashboard...")
    
    # Create database pool
    db_pool = await asyncpg.create_pool(
        settings.DATABASE_URL,
        min_size=2,
        max_size=5
    )
    
    # Create dashboard
    dashboard = TradingDashboard(db_pool)
    
    # Handle graceful shutdown
    def signal_handler(sig, frame):
        print("\nShutting down dashboard...")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        # Run dashboard
        await dashboard.run()
    finally:
        await db_pool.close()


if __name__ == "__main__":
    asyncio.run(main())