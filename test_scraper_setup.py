#!/usr/bin/env python3
"""
Test script to verify Discord web scraper setup.
Tests configuration, database connectivity, and scraper initialization.
"""

import asyncio
import logging
from pathlib import Path
import asyncpg

from config import settings
from ingest.discord_web_scraper import DiscordWebScraper

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_configuration():
    """Test configuration settings."""
    print("🔧 Testing Configuration...")
    
    # Check required settings
    required_settings = [
        ('DISCORD_USERNAME', settings.DISCORD_USERNAME),
        ('DISCORD_PASSWORD', settings.DISCORD_PASSWORD),
        ('DISCORD_CHANNEL_ID', settings.DISCORD_CHANNEL_ID),
        ('DISCORD_GUILD_ID', settings.DISCORD_GUILD_ID),
        ('DATABASE_URL', settings.DATABASE_URL),
        ('HELIUS_API_KEY', settings.HELIUS_API_KEY),
        ('BIRDEYE_API_KEY', settings.BIRDEYE_API_KEY)
    ]
    
    for name, value in required_settings:
        if value:
            if 'PASSWORD' in name or 'KEY' in name or 'URL' in name:
                print(f"  ✅ {name}: {'*' * 8}...")
            else:
                print(f"  ✅ {name}: {value}")
        else:
            print(f"  ❌ {name}: NOT SET")
    
    # Overall validation
    is_valid = settings.validate_config()
    print(f"\n📋 Configuration validation: {'✅ PASS' if is_valid else '❌ FAIL'}")
    
    return is_valid


async def test_database_connection():
    """Test database connectivity."""
    print("\n🗄️ Testing Database Connection...")
    
    try:
        # Test connection
        pool = await asyncpg.create_pool(
            settings.DATABASE_URL,
            min_size=1,
            max_size=2
        )
        
        async with pool.acquire() as conn:
            # Test basic query
            result = await conn.fetchval("SELECT 1")
            print(f"  ✅ Database connection: OK (test query returned {result})")
            
            # Check tables exist
            tables = await conn.fetch("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                  AND table_type = 'BASE TABLE'
                ORDER BY table_name
            """)
            
            table_names = [row['table_name'] for row in tables]
            print(f"  ✅ Tables found: {len(table_names)}")
            
            required_tables = [
                'discord_raw', 'mint_resolution', 'acceptance_status',
                'outcomes_24h', 'features_snapshot', 'strategy_clusters',
                'strategy_params', 'signals'
            ]
            
            missing_tables = [t for t in required_tables if t not in table_names]
            
            if missing_tables:
                print(f"  ❌ Missing tables: {missing_tables}")
                return False
            else:
                print(f"  ✅ All required tables exist")
        
        await pool.close()
        return True
        
    except Exception as e:
        print(f"  ❌ Database connection failed: {e}")
        return False


async def test_scraper_initialization():
    """Test Discord scraper initialization."""
    print("\n📡 Testing Discord Scraper Initialization...")
    
    try:
        # Create database pool
        pool = await asyncpg.create_pool(settings.DATABASE_URL, min_size=1, max_size=2)
        
        # Create scraper instance
        scraper = DiscordWebScraper(pool)
        print("  ✅ DiscordWebScraper instance created")
        
        # Check credentials
        if scraper.email and scraper.password:
            print(f"  ✅ Login credentials configured: {scraper.email}")
        else:
            print("  ❌ Login credentials missing")
            return False
        
        # Check session files
        session_file = Path("discord_session.json")
        cookies_file = Path("discord_cookies.pkl")
        
        print(f"  📁 Session file exists: {session_file.exists()}")
        print(f"  📁 Cookies file exists: {cookies_file.exists()}")
        
        # Check target URLs
        target_url = f"https://discord.com/channels/{settings.DISCORD_GUILD_ID}/{settings.DISCORD_CHANNEL_ID}"
        print(f"  🎯 Target channel: {target_url}")
        
        await pool.close()
        return True
        
    except Exception as e:
        print(f"  ❌ Scraper initialization failed: {e}")
        return False


async def main():
    """Run all tests."""
    print("🧪 AG-Trading-Bot Setup Verification")
    print("=" * 50)
    
    # Run tests
    config_ok = await test_configuration()
    db_ok = await test_database_connection()
    scraper_ok = await test_scraper_initialization()
    
    print("\n" + "=" * 50)
    print("📊 FINAL RESULTS:")
    print(f"  Configuration: {'✅ PASS' if config_ok else '❌ FAIL'}")
    print(f"  Database: {'✅ PASS' if db_ok else '❌ FAIL'}")
    print(f"  Scraper Setup: {'✅ PASS' if scraper_ok else '❌ FAIL'}")
    
    overall_status = config_ok and db_ok and scraper_ok
    print(f"\n🎯 OVERALL STATUS: {'✅ READY TO SCRAPE' if overall_status else '❌ NEEDS ATTENTION'}")
    
    if overall_status:
        print("\n🚀 Next Steps:")
        print("1. Run: python ingest/discord_web_scraper.py")
        print("2. Browser will open and login to Discord")
        print("3. Navigate to Alpha Gardeners #launchpads")
        print("4. Watch console for scraped messages")
        print("5. Check database for stored messages")
    
    return overall_status


if __name__ == "__main__":
    asyncio.run(main())
