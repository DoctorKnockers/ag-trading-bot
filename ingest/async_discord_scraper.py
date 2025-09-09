"""
Async Discord Web Scraper
Playwright-based async Discord scraping with API response interception
"""

import asyncio
import logging
import json
import pickle
import aiofiles
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set
from pathlib import Path
import asyncpg
from playwright.async_api import async_playwright, Browser, Page, Response
from collections import deque

from config import settings

logger = logging.getLogger(__name__)


class AsyncDiscordScraper:
    """
    Async Discord scraper using Playwright with API response interception.
    Provides 5-second polling with 1000 message deduplication cache.
    """
    
    def __init__(self, db_pool: asyncpg.Pool):
        """
        Initialize async Discord scraper.
        
        Args:
            db_pool: Database connection pool
        """
        self.db_pool = db_pool
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        
        # Message deduplication cache (last 1000 messages)
        self.message_cache: deque = deque(maxlen=1000)
        
        # Session persistence
        self.session_file = Path("discord_session.pkl")
        self.cookies_file = Path("discord_cookies.pkl")
        
        # Scraping state
        self.is_running = False
        self.last_message_id = None
        
        # Channel configuration
        self.channel_id = settings.DISCORD_CHANNEL_ID
        self.guild_id = settings.DISCORD_GUILD_ID
        
        logger.info(f"🤖 Async Discord scraper initialized")
        logger.info(f"📍 Target channel: {self.channel_id}")
    
    async def start_browser(self):
        """Start Playwright browser with session persistence."""
        playwright = await async_playwright().start()
        
        # Launch browser with persistence
        self.browser = await playwright.chromium.launch(
            headless=False,  # Set to True for production
            user_data_dir="./discord_browser_data"
        )
        
        # Create context with session
        context = await self.browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        
        # Load cookies if they exist
        if self.cookies_file.exists():
            try:
                with open(self.cookies_file, 'rb') as f:
                    cookies = pickle.load(f)
                await context.add_cookies(cookies)
                logger.info("🍪 Loaded saved cookies")
            except Exception as e:
                logger.warning(f"Failed to load cookies: {e}")
        
        self.page = await context.new_page()
        
        # Setup API response interception
        await self.setup_interception()
        
        logger.info("🌐 Browser started successfully")
    
    async def setup_interception(self):
        """Setup API response interception for faster message capture."""
        async def handle_response(response: Response):
            # Intercept Discord API calls for messages
            if "api/v9/channels" in response.url and "messages" in response.url:
                try:
                    if response.status == 200:
                        data = await response.json()
                        await self.process_intercepted_messages(data)
                except Exception as e:
                    logger.debug(f"Error processing intercepted response: {e}")
        
        self.page.on("response", handle_response)
        logger.info("🕸️ API interception setup complete")
    
    async def process_intercepted_messages(self, messages_data):
        """Process messages from intercepted API responses."""
        if not isinstance(messages_data, list):
            return
        
        for message_data in messages_data:
            if isinstance(message_data, dict) and 'id' in message_data:
                await self.process_message(message_data)
    
    async def login(self) -> bool:
        """Login to Discord with credentials."""
        try:
            await self.page.goto("https://discord.com/login")
            await self.page.wait_for_load_state("networkidle")
            
            # Check if already logged in
            if "channels" in self.page.url:
                logger.info("✅ Already logged in")
                return True
            
            # Fill login form
            await self.page.fill('input[name="email"]', settings.DISCORD_USERNAME)
            await self.page.fill('input[name="password"]', settings.DISCORD_PASSWORD)
            
            # Submit login
            await self.page.click('button[type="submit"]')
            
            # Wait for login to complete
            await self.page.wait_for_url("**/channels/**", timeout=30000)
            
            # Save cookies for future sessions
            cookies = await self.page.context.cookies()
            with open(self.cookies_file, 'wb') as f:
                pickle.dump(cookies, f)
            
            logger.info("✅ Login successful")
            return True
            
        except Exception as e:
            logger.error(f"❌ Login failed: {e}")
            return False
    
    async def navigate_to_channel(self) -> bool:
        """Navigate to the target Discord channel."""
        try:
            channel_url = f"https://discord.com/channels/{self.guild_id}/{self.channel_id}"
            await self.page.goto(channel_url)
            await self.page.wait_for_load_state("networkidle")
            
            # Wait for messages to load
            await self.page.wait_for_selector('[data-list-id="chat-messages"]', timeout=10000)
            
            logger.info(f"📍 Navigated to channel: {self.channel_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to navigate to channel: {e}")
            return False
    
    async def process_message(self, message_data: Dict):
        """Process a single Discord message."""
        try:
            message_id = message_data.get('id')
            if not message_id or message_id in self.message_cache:
                return  # Skip duplicates
            
            # Add to cache
            self.message_cache.append(message_id)
            
            # Extract message content
            content = message_data.get('content', '')
            embeds = message_data.get('embeds', [])
            author = message_data.get('author', {})
            timestamp = message_data.get('timestamp')
            
            # Skip if no embeds (we're looking for token announcements)
            if not embeds:
                return
            
            # Parse timestamp
            created_at = None
            if timestamp:
                try:
                    created_at = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                except:
                    created_at = datetime.now(timezone.utc)
            else:
                created_at = datetime.now(timezone.utc)
            
            # Store in database
            await self.store_message(
                message_id=message_id,
                content=content,
                embeds=embeds,
                author_id=author.get('id'),
                author_username=author.get('username'),
                created_at=created_at
            )
            
            logger.info(f"💬 Processed message: {message_id}")
            
        except Exception as e:
            logger.error(f"❌ Error processing message: {e}")
    
    async def store_message(self, message_id: str, content: str, embeds: List[Dict], 
                          author_id: str, author_username: str, created_at: datetime):
        """Store message in database."""
        async with self.db_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO discord_raw (
                    message_id, content, embeds, author_id, author_username, 
                    created_at, inserted_at
                ) VALUES ($1, $2, $3, $4, $5, $6, NOW())
                ON CONFLICT (message_id) DO NOTHING
            """,
                message_id,
                content,
                json.dumps(embeds),
                author_id,
                author_username,
                created_at
            )
    
    async def scroll_and_collect(self):
        """Scroll through messages and collect new ones."""
        try:
            # Scroll to load more messages
            await self.page.evaluate("window.scrollTo(0, 0)")  # Scroll to top for new messages
            await asyncio.sleep(1)
            
            # Get messages from DOM
            messages = await self.page.query_selector_all('[id^="chat-messages-"]')
            
            for message_element in messages[-10:]:  # Process last 10 visible messages
                try:
                    # Extract message data from DOM
                    message_id = await message_element.get_attribute('id')
                    if message_id:
                        message_id = message_id.replace('chat-messages-', '')
                        
                        if message_id not in self.message_cache:
                            # Get message content
                            content_element = await message_element.query_selector('[class*="messageContent"]')
                            content = await content_element.inner_text() if content_element else ""
                            
                            # Check for embeds
                            embed_elements = await message_element.query_selector_all('[class*="embed"]')
                            
                            if embed_elements:
                                # Process as potential token announcement
                                await self.process_dom_message(message_id, content, embed_elements)
                
                except Exception as e:
                    logger.debug(f"Error processing DOM message: {e}")
        
        except Exception as e:
            logger.error(f"❌ Error scrolling and collecting: {e}")
    
    async def process_dom_message(self, message_id: str, content: str, embed_elements):
        """Process message extracted from DOM."""
        try:
            # Extract embed data from DOM elements
            embeds = []
            for embed_element in embed_elements:
                embed_data = {}
                
                # Get title
                title_element = await embed_element.query_selector('[class*="embedTitle"]')
                if title_element:
                    embed_data['title'] = await title_element.inner_text()
                
                # Get description  
                desc_element = await embed_element.query_selector('[class*="embedDescription"]')
                if desc_element:
                    embed_data['description'] = await desc_element.inner_text()
                
                # Get fields
                field_elements = await embed_element.query_selector_all('[class*="embedField"]')
                fields = []
                for field_element in field_elements:
                    field_name_element = await field_element.query_selector('[class*="embedFieldName"]')
                    field_value_element = await field_element.query_selector('[class*="embedFieldValue"]')
                    
                    if field_name_element and field_value_element:
                        fields.append({
                            'name': await field_name_element.inner_text(),
                            'value': await field_value_element.inner_text(),
                            'inline': True
                        })
                
                embed_data['fields'] = fields
                embeds.append(embed_data)
            
            # Store message
            await self.store_message(
                message_id=message_id,
                content=content,
                embeds=embeds,
                author_id="unknown",
                author_username="unknown",
                created_at=datetime.now(timezone.utc)
            )
            
            logger.info(f"💬 Processed DOM message: {message_id}")
            
        except Exception as e:
            logger.error(f"❌ Error processing DOM message: {e}")
    
    async def run_scraping_loop(self):
        """Main scraping loop with 5-second polling."""
        self.is_running = True
        logger.info("🔄 Starting scraping loop (5-second interval)")
        
        while self.is_running:
            try:
                await self.scroll_and_collect()
                await asyncio.sleep(5)  # 5-second polling interval
                
            except Exception as e:
                logger.error(f"❌ Error in scraping loop: {e}")
                await asyncio.sleep(10)  # Longer delay on error
    
    async def start_scraping(self):
        """Start the complete scraping process."""
        try:
            # Start browser
            await self.start_browser()
            
            # Login
            if not await self.login():
                raise Exception("Login failed")
            
            # Navigate to channel
            if not await self.navigate_to_channel():
                raise Exception("Failed to navigate to channel")
            
            # Start scraping loop
            await self.run_scraping_loop()
            
        except Exception as e:
            logger.error(f"❌ Scraping failed: {e}")
        finally:
            await self.cleanup()
    
    async def stop_scraping(self):
        """Stop the scraping process."""
        self.is_running = False
        logger.info("🛑 Stopping scraper...")
    
    async def cleanup(self):
        """Cleanup browser resources."""
        if self.browser:
            await self.browser.close()
            logger.info("🧹 Browser cleaned up")


# Singleton instance
_scraper = None


async def get_scraper(db_pool: asyncpg.Pool) -> AsyncDiscordScraper:
    """
    Get or create async Discord scraper instance.
    
    Args:
        db_pool: Database connection pool
        
    Returns:
        AsyncDiscordScraper instance
    """
    global _scraper
    
    if _scraper is None:
        _scraper = AsyncDiscordScraper(db_pool)
    
    return _scraper


# Example usage
if __name__ == "__main__":
    async def test():
        # Create DB pool
        db_pool = await asyncpg.create_pool(settings.DATABASE_URL)
        
        try:
            # Get scraper
            scraper = await get_scraper(db_pool)
            
            # Start scraping
            await scraper.start_scraping()
            
        except KeyboardInterrupt:
            logger.info("🛑 Scraper stopped by user")
        finally:
            await db_pool.close()
    
    asyncio.run(test())
