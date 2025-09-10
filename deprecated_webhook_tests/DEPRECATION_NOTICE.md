"""
Async Discord Scraper with optimized architecture
Replaces synchronous real_discord_scraper.py
"""

import asyncio
import json
import logging
import pickle
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Set
from playwright.async_api import async_playwright, Browser, Page, BrowserContext
import aiofiles
import asyncpg

from config import settings
from ingest.metrics_parser import LaunchpadMetricsParser
from utils.time_utils import get_entry_timestamp, datetime_to_epoch_ms

logger = logging.getLogger(__name__)


class AsyncDiscordScraper:
    """
    Optimized async Discord scraper for Alpha Gardeners.
    Uses async Playwright for better performance.
    """
    
    def __init__(self, db_pool: asyncpg.Pool):
        self.db_pool = db_pool
        self.username = settings.DISCORD_USERNAME
        self.password = settings.DISCORD_PASSWORD
        self.channel_id = settings.DISCORD_CHANNEL_ID
        self.guild_id = settings.DISCORD_GUILD_ID
        
        # Session persistence
        self.cookies_file = Path("discord_cookies.pkl")
        self.session_file = Path("discord_session.json")
        
        # Playwright objects
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        
        # Metrics parser
        self.metrics_parser = LaunchpadMetricsParser()
        
        # Message tracking with deduplication
        self.processed_messages: Set[str] = set()
        self.message_cache_size = 1000  # Keep last 1000 message IDs
        
        # Scraping interval
        self.polling_interval = 5  # seconds
        
        # Alpha Gardeners validation
        self.valid_authors = {
            "launchpads bot", "alphagardeners", "alpha gardeners", "ag bot"
        }
        
        self.valid_patterns = {
            "@launchpads", "fomo called", "alpha call"
        }
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.setup_browser()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager cleanup."""
        await self.cleanup()
    
    async def setup_browser(self):
        """Setup Playwright browser with session persistence."""
        logger.info("🌐 Setting up async browser...")
        
        self.playwright = await async_playwright().start()
        
        # Launch with optimized settings
        self.browser = await self.playwright.chromium.launch(
            headless=True,  # Run headless in production
            args=[
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process'
            ]
        )
        
        # Load saved session if exists
        storage_state = None
        if self.session_file.exists():
            try:
                async with aiofiles.open(self.session_file, 'r') as f:
                    storage_state = json.loads(await f.read())
                logger.info("📂 Loaded saved session")
            except Exception as e:
                logger.warning(f"Failed to load session: {e}")
        
        # Create context
        self.context = await self.browser.new_context(
            storage_state=storage_state,
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        
        self.page = await self.context.new_page()
        
        # Setup request interception for API monitoring
        self.page.on('response', self._handle_response)
        
        logger.info("✅ Browser setup complete")
    
    async def _handle_response(self, response):
        """Intercept Discord API responses for faster data capture."""
        if '/api/v9/channels/' in response.url and 'messages' in response.url:
            try:
                data = await response.json()
                if isinstance(data, list):
                    for msg in data:
                        await self._process_api_message(msg)
            except:
                pass  # Ignore parsing errors
    
    async def _process_api_message(self, msg: Dict[str, Any]):
        """Process message from intercepted API call."""
        if msg.get('channel_id') == self.channel_id:
            if msg['id'] not in self.processed_messages:
                if self._is_valid_alpha_message(msg):
                    await self._store_and_process_message(msg)
    
    async def login(self) -> bool:
        """Async Discord login."""
        logger.info("🔐 Logging into Discord...")
        
        try:
            await self.page.goto("https://discord.com/app", wait_until='networkidle')
            
            # Check if already logged in
            if await self._is_logged_in():
                logger.info("✅ Already logged in")
                await self._save_session()
                return True
            
            # Perform login
            await self.page.goto("https://discord.com/login", wait_until='networkidle')
            await self.page.fill('input[name="email"]', self.username)
            await self.page.fill('input[name="password"]', self.password)
            await self.page.click('button[type="submit"]')
            
            # Wait for navigation
            try:
                await self.page.wait_for_url("https://discord.com/channels/**", timeout=30000)
                logger.info("✅ Login successful")
                await self._save_session()
                return True
            except:
                # Check for 2FA
                if await self.page.locator('input[placeholder*="6-digit"]').count() > 0:
                    logger.info("🔐 2FA required - waiting for manual entry...")
                    await self.page.wait_for_url("https://discord.com/channels/**", timeout=120000)
                    await self._save_session()
                    return True
                return False
                
        except Exception as e:
            logger.error(f"❌ Login failed: {e}")
            return False
    
    async def _is_logged_in(self) -> bool:
        """Check login status."""
        return await self.page.locator('[class*="avatar"]').count() > 0
    
    async def _save_session(self):
        """Save session for persistence."""
        try:
            storage_state = await self.context.storage_state()
            async with aiofiles.open(self.session_file, 'w') as f:
                await f.write(json.dumps(storage_state))
            logger.info("💾 Session saved")
        except Exception as e:
            logger.error(f"Failed to save session: {e}")
    
    async def navigate_to_channel(self) -> bool:
        """Navigate to Alpha Gardeners channel."""
        target_url = f"https://discord.com/channels/{self.guild_id}/{self.channel_id}"
        
        try:
            await self.page.goto(target_url, wait_until='networkidle')
            await self.page.wait_for_selector('[class*="message"]', timeout=10000)
            logger.info("✅ Navigated to #launchpads")
            return True
        except Exception as e:
            logger.error(f"❌ Navigation failed: {e}")
            return False
    
    def _is_valid_alpha_message(self, msg: Dict[str, Any]) -> bool:
        """Validate Alpha Gardeners message."""
        # Check author
        author = msg.get('author', {}).get('username', '').lower()
        if not any(valid in author for valid in self.valid_authors):
            return False
        
        # Check content patterns
        content = msg.get('content', '').lower()
        if not any(pattern in content for pattern in self.valid_patterns):
            return False
        
        # Must have embeds
        if not msg.get('embeds'):
            return False
        
        # Check for metrics in embeds
        embed_text = str(msg['embeds'][0]) if msg['embeds'] else ''
        required_indicators = ['MC:', 'Liq:', 'AG Score:']
        
        return sum(indicator in embed_text for indicator in required_indicators) >= 2
    
    async def _store_and_process_message(self, msg: Dict[str, Any]):
        """Store message and trigger pipeline processing."""
        message_id = msg['id']
        
        if message_id in self.processed_messages:
            return
        
        # Add to processed set with size limit
        self.processed_messages.add(message_id)
        if len(self.processed_messages) > self.message_cache_size:
            # Remove oldest (first) item
            self.processed_messages.pop()
        
        try:
            # Store in database
            t0 = get_entry_timestamp(message_id)
            
            async with self.db_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO discord_raw (
                        channel_id, message_id, posted_at, posted_at_epoch_ms,
                        author_id, payload, inserted_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, NOW())
                    ON CONFLICT (message_id) DO NOTHING
                """, (
                    self.channel_id,
                    message_id,
                    t0,
                    datetime_to_epoch_ms(t0),
                    msg['author']['id'],
                    json.dumps(msg)
                ))
            
            logger.info(f"📥 Stored message {message_id}")
            
            # Trigger async pipeline processing
            asyncio.create_task(self._process_pipeline(message_id, msg))
            
        except Exception as e:
            logger.error(f"Failed to store message: {e}")
    
    async def _process_pipeline(self, message_id: str, msg: Dict[str, Any]):
        """Async pipeline processing for new message."""
        try:
            # Extract mint
            mint = self._extract_mint(msg)
            if not mint:
                return
            
            # Store mint resolution
            async with self.db_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO mint_resolution (
                        message_id, resolved, mint, confidence, resolved_at
                    ) VALUES ($1, $2, $3, $4, NOW())
                    ON CONFLICT (message_id) DO NOTHING
                """, (message_id, True, mint, 0.95))
            
            # Extract and store features
            metrics = self.metrics_parser.parse_message_metrics(msg)
            validated = self.metrics_parser.validate_parsed_metrics(metrics)
            
            async with self.db_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO features_snapshot (
                        message_id, snapped_at, features, feature_version
                    ) VALUES ($1, $2, $3, $4)
                    ON CONFLICT (message_id) DO UPDATE SET
                        features = $3
                """, (
                    message_id,
                    get_entry_timestamp(message_id),
                    json.dumps(validated),
                    1
                ))
            
            logger.info(f"✅ Pipeline processed for {message_id}")
            
        except Exception as e:
            logger.error(f"Pipeline processing failed: {e}")
    
    def _extract_mint(self, msg: Dict[str, Any]) -> Optional[str]:
        """Extract mint address from message."""
        # Check embeds for URLs
        for embed in msg.get('embeds', []):
            if url := embed.get('url'):
                if 'pump.fun' in url:
                    parts = url.split('/')
                    if len(parts) > 3:
                        return parts[-1]
        
        # Check components
        for row in msg.get('components', []):
            for comp in row.get('components', []):
                if url := comp.get('url'):
                    if 'pump.fun' in url:
                        return url.split('/')[-1]
        
        return None
    
    async def start_monitoring(self):
        """Start continuous monitoring loop."""
        logger.info("🚀 Starting async monitoring...")
        
        if not await self.login():
            raise Exception("Login failed")
        
        if not await self.navigate_to_channel():
            raise Exception("Navigation failed")
        
        # Continuous monitoring
        while True:
            try:
                # Scroll to trigger message loading
                await self.page.evaluate('window.scrollBy(0, -500)')
                
                # Wait for polling interval
                await asyncio.sleep(self.polling_interval)
                
            except Exception as e:
                logger.error(f"Monitoring error: {e}")
                await asyncio.sleep(30)
    
    async def cleanup(self):
        """Cleanup resources."""
        if self.page:
            await self.page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()


async def main():
    """Main entry point for async scraper."""
    logging.basicConfig(level=logging.INFO)
    
    # Create database pool
    pool = await asyncpg.create_pool(settings.DATABASE_URL)
    
    try:
        async with AsyncDiscordScraper(pool) as scraper:
            await scraper.start_monitoring()
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())