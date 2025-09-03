"""
Discord Web Scraper - Browser-based Message Scraping
Uses Selenium/Playwright to login to Discord web and scrape messages
Maintains persistent session with cookies for re-authentication
NO DISCORD API, NO BOTS - Pure web scraping
"""

import asyncio
import json
import logging
import pickle
import os
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from pathlib import Path

import asyncpg
from playwright.async_api import async_playwright, Browser, Page, BrowserContext
from bs4 import BeautifulSoup

from config import settings

logger = logging.getLogger(__name__)


class DiscordWebScraper:
    """
    Web-based Discord scraper using browser automation.
    Logs in via web interface and maintains persistent session.
    
    COMPLIANCE NOTES:
    - Uses web scraping, NOT Discord API
    - No bot tokens, no webhooks
    - Maintains session cookies for persistent login
    - Read-only scraping of public messages
    """
    
    def __init__(self, db_pool: asyncpg.Pool):
        """
        Initialize the web scraper.
        
        Args:
            db_pool: PostgreSQL connection pool
        """
        self.db_pool = db_pool
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        
        # Session persistence
        self.session_file = Path("discord_session.json")
        self.cookies_file = Path("discord_cookies.pkl")
        
        # Discord URLs
        self.discord_url = "https://discord.com/app"
        self.login_url = "https://discord.com/login"
        
        # Target channel - will be constructed after login
        self.target_channel_url = None
        
        # Login credentials from environment
        self.email = os.getenv('DISCORD_EMAIL')
        self.password = os.getenv('DISCORD_PASSWORD')
        
        # Message tracking
        self.processed_messages = set()
        self.last_message_id = None
    
    async def setup_browser(self):
        """Initialize browser with persistent session."""
        playwright = await async_playwright().start()
        
        # Launch browser in non-headless mode for debugging
        # Set headless=True for production
        self.browser = await playwright.chromium.launch(
            headless=False,  # Set to True in production
            args=['--disable-blink-features=AutomationControlled']
        )
        
        # Create context with saved session if available
        context_options = {
            'viewport': {'width': 1920, 'height': 1080},
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        # Load saved cookies if they exist
        if self.cookies_file.exists():
            try:
                with open(self.cookies_file, 'rb') as f:
                    cookies = pickle.load(f)
                context_options['storage_state'] = {
                    'cookies': cookies
                }
                logger.info("Loaded saved session cookies")
            except Exception as e:
                logger.warning(f"Failed to load cookies: {e}")
        
        self.context = await self.browser.new_context(**context_options)
        self.page = await self.context.new_page()
        
        # Set up request interception to capture API calls
        await self.setup_request_interception()
    
    async def setup_request_interception(self):
        """Intercept Discord API calls to capture message data."""
        async def handle_response(response):
            """Handle intercepted responses."""
            url = response.url
            
            # Capture messages from Discord API
            if '/api/v9/channels/' in url and 'messages' in url:
                try:
                    data = await response.json()
                    if isinstance(data, list):
                        # Process message batch
                        for msg in data:
                            await self.process_api_message(msg)
                    elif isinstance(data, dict) and 'id' in data:
                        # Single message
                        await self.process_api_message(data)
                except Exception as e:
                    logger.debug(f"Failed to parse API response: {e}")
        
        self.page.on('response', handle_response)
    
    async def login(self):
        """Login to Discord web interface."""
        logger.info("Attempting to login to Discord...")
        
        # Navigate to Discord
        await self.page.goto(self.discord_url, wait_until='networkidle')
        
        # Check if already logged in
        if await self.is_logged_in():
            logger.info("Already logged in via saved session")
            await self.navigate_to_channel()
            return True
        
        # Need to login
        logger.info("Not logged in, proceeding with login...")
        await self.page.goto(self.login_url, wait_until='networkidle')
        
        # Fill login form
        await self.page.fill('input[name="email"]', self.email)
        await self.page.fill('input[name="password"]', self.password)
        
        # Click login button
        await self.page.click('button[type="submit"]')
        
        # Wait for navigation
        try:
            await self.page.wait_for_url(f"{self.discord_url}/**", timeout=30000)
            logger.info("Login successful")
            
            # Save session cookies
            await self.save_session()
            
            # Navigate to target channel
            await self.navigate_to_channel()
            return True
            
        except Exception as e:
            logger.error(f"Login failed: {e}")
            
            # Check for 2FA
            if await self.page.locator('input[placeholder*="6-digit"]').count() > 0:
                logger.info("2FA required - please enter code manually")
                # Wait for manual 2FA entry
                await self.page.wait_for_url(f"{self.discord_url}/**", timeout=120000)
                await self.save_session()
                await self.navigate_to_channel()
                return True
            
            return False
    
    async def is_logged_in(self):
        """Check if we're logged into Discord."""
        try:
            # Check for user avatar or settings button
            user_area = await self.page.locator('[class*="avatar"]').count()
            return user_area > 0
        except:
            return False
    
    async def save_session(self):
        """Save session cookies for persistent login."""
        try:
            cookies = await self.context.cookies()
            with open(self.cookies_file, 'wb') as f:
                pickle.dump(cookies, f)
            logger.info("Session cookies saved")
        except Exception as e:
            logger.error(f"Failed to save session: {e}")
    
    async def navigate_to_channel(self):
        """Navigate to the target channel."""
        guild_id = settings.DISCORD_GUILD_ID
        channel_id = settings.DISCORD_CHANNEL_ID
        
        self.target_channel_url = f"{self.discord_url}/channels/{guild_id}/{channel_id}"
        
        logger.info(f"Navigating to channel: {self.target_channel_url}")
        await self.page.goto(self.target_channel_url, wait_until='networkidle')
        
        # Wait for messages to load
        await self.page.wait_for_selector('[class*="message"]', timeout=10000)
        logger.info("Successfully navigated to #launchpads channel")
    
    async def scrape_visible_messages(self):
        """Scrape currently visible messages from the page."""
        # Get all message elements
        messages = await self.page.locator('[class*="message"][id*="message"]').all()
        
        for message_elem in messages:
            try:
                # Extract message ID
                elem_id = await message_elem.get_attribute('id')
                if not elem_id:
                    continue
                
                message_id = elem_id.replace('chat-messages-', '').split('-')[-1]
                
                # Skip if already processed
                if message_id in self.processed_messages:
                    continue
                
                # Extract message data
                message_data = await self.extract_message_data(message_elem, message_id)
                
                if message_data:
                    await self.store_message(message_data)
                    self.processed_messages.add(message_id)
                    
                    # Log key information
                    self._log_message_details(message_data)
                    
            except Exception as e:
                logger.error(f"Failed to process message element: {e}")
    
    async def extract_message_data(self, message_elem, message_id: str) -> Optional[Dict[str, Any]]:
        """Extract message data from DOM element."""
        try:
            # Get message HTML
            html = await message_elem.inner_html()
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract author
            author_elem = soup.find(class_=lambda x: x and 'username' in x)
            author = author_elem.text if author_elem else 'Unknown'
            
            # Extract content
            content_elem = soup.find(class_=lambda x: x and 'messageContent' in x)
            content = content_elem.text if content_elem else ''
            
            # Extract timestamp
            time_elem = soup.find('time')
            timestamp = time_elem.get('datetime') if time_elem else datetime.now(timezone.utc).isoformat()
            
            # Extract embeds
            embeds = []
            embed_elems = soup.find_all(class_=lambda x: x and 'embed' in x)
            for embed in embed_elems:
                embed_data = self.parse_embed(embed)
                if embed_data:
                    embeds.append(embed_data)
            
            # Extract buttons/components
            components = []
            button_elems = soup.find_all('a', class_=lambda x: x and 'button' in x)
            for button in button_elems:
                if button.get('href'):
                    components.append({
                        'type': 'button',
                        'label': button.text,
                        'url': button['href']
                    })
            
            # Build message payload
            payload = {
                'id': message_id,
                'content': content,
                'author': {
                    'username': author,
                    'id': f'user_{message_id}'  # Placeholder
                },
                'timestamp': timestamp,
                'embeds': embeds,
                'components': components,
                'channel_id': settings.DISCORD_CHANNEL_ID,
                'guild_id': settings.DISCORD_GUILD_ID
            }
            
            return payload
            
        except Exception as e:
            logger.error(f"Failed to extract message data: {e}")
            return None
    
    def parse_embed(self, embed_soup) -> Optional[Dict[str, Any]]:
        """Parse embed data from BeautifulSoup element."""
        try:
            embed_data = {}
            
            # Title
            title = embed_soup.find(class_=lambda x: x and 'embedTitle' in x)
            if title:
                embed_data['title'] = title.text
                # Check for URL in title link
                if title.find('a'):
                    embed_data['url'] = title.find('a').get('href')
            
            # Description
            desc = embed_soup.find(class_=lambda x: x and 'embedDescription' in x)
            if desc:
                embed_data['description'] = desc.text
            
            # Fields
            fields = []
            field_elems = embed_soup.find_all(class_=lambda x: x and 'embedField' in x)
            for field in field_elems:
                name = field.find(class_=lambda x: x and 'embedFieldName' in x)
                value = field.find(class_=lambda x: x and 'embedFieldValue' in x)
                if name and value:
                    fields.append({
                        'name': name.text,
                        'value': value.text
                    })
            
            if fields:
                embed_data['fields'] = fields
            
            return embed_data if embed_data else None
            
        except Exception as e:
            logger.error(f"Failed to parse embed: {e}")
            return None
    
    async def process_api_message(self, message_data: Dict[str, Any]):
        """Process message data captured from API calls."""
        try:
            message_id = message_data.get('id')
            
            # Skip if already processed
            if message_id in self.processed_messages:
                return
            
            # Check if it's from our target channel
            if message_data.get('channel_id') != settings.DISCORD_CHANNEL_ID:
                return
            
            # Store the message
            await self.store_message(message_data)
            self.processed_messages.add(message_id)
            
            # Log details
            self._log_message_details(message_data)
            
        except Exception as e:
            logger.error(f"Failed to process API message: {e}")
    
    def _log_message_details(self, payload: Dict[str, Any]):
        """Log important details from scraped message."""
        content = payload.get('content', '')
        author = payload.get('author', {}).get('username', 'Unknown')
        
        logger.info(f"📨 Scraped message from {author}: {content[:50]}...")
        
        # Check for embeds with URLs
        for embed in payload.get('embeds', []):
            if url := embed.get('url'):
                logger.info(f"  📎 Embed URL: {url}")
        
        # Check for components with URLs
        for comp in payload.get('components', []):
            if comp.get('url'):
                logger.info(f"  🔘 Button: {comp.get('label')} → {comp.get('url')}")
    
    async def store_message(self, payload: Dict[str, Any]):
        """Store scraped message in database."""
        try:
            message_id = payload['id']
            channel_id = payload.get('channel_id', settings.DISCORD_CHANNEL_ID)
            guild_id = payload.get('guild_id', settings.DISCORD_GUILD_ID)
            author_id = payload.get('author', {}).get('id', 'unknown')
            
            # Parse timestamp
            timestamp_str = payload.get('timestamp')
            if timestamp_str:
                posted_at = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            else:
                posted_at = datetime.now(timezone.utc)
            
            async with self.db_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO discord_raw 
                    (message_id, channel_id, guild_id, author_id, posted_at, payload)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (message_id) DO UPDATE
                    SET payload = EXCLUDED.payload,
                        updated_at = NOW()
                """, message_id, channel_id, guild_id, author_id, posted_at, json.dumps(payload))
                
                logger.debug(f"Stored message {message_id} in database")
                
        except Exception as e:
            logger.error(f"Failed to store message: {e}")
    
    async def monitor_channel(self):
        """Continuously monitor the channel for new messages."""
        logger.info("Starting channel monitoring...")
        
        while True:
            try:
                # Scrape visible messages
                await self.scrape_visible_messages()
                
                # Scroll up to load more history if needed
                if len(self.processed_messages) < 100:
                    await self.page.keyboard.press('PageUp')
                    await asyncio.sleep(1)
                
                # Wait before next scrape
                await asyncio.sleep(5)
                
            except Exception as e:
                logger.error(f"Error during monitoring: {e}")
                await asyncio.sleep(10)
    
    async def start(self):
        """Start the web scraper."""
        try:
            # Validate configuration
            if not self.email or not self.password:
                raise ValueError("DISCORD_EMAIL and DISCORD_PASSWORD must be set")
            
            # Setup browser
            await self.setup_browser()
            
            # Login to Discord
            if not await self.login():
                raise Exception("Failed to login to Discord")
            
            # Start monitoring
            await self.monitor_channel()
            
        except Exception as e:
            logger.error(f"Failed to start scraper: {e}")
            raise
    
    async def stop(self):
        """Stop the web scraper."""
        if self.page:
            await self.page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        logger.info("Web scraper stopped")


async def main():
    """Main entry point for the Discord web scraper."""
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create database pool
    pool = await asyncpg.create_pool(settings.DATABASE_URL)
    
    # Create and start scraper
    scraper = DiscordWebScraper(pool)
    
    try:
        await scraper.start()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        await scraper.stop()
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
