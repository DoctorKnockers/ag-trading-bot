#!/usr/bin/env python3
"""
Real Discord Scraper - Robust Alpha Gardeners message collection.
Uses Playwright with synchronous approach to avoid async/signal issues.
ONLY processes real Alpha Gardeners Discord messages.
"""

import json
import logging
import os
import time
import pickle
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
import psycopg2
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

from config import settings
from ingest.metrics_parser import LaunchpadMetricsParser
from utils.time_utils import get_entry_timestamp, datetime_to_epoch_ms

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class RealDiscordScraper:
    """
    Real Discord scraper for Alpha Gardeners #launchpads channel.
    Uses synchronous Playwright to avoid async issues.
    ONLY processes authentic Alpha Gardeners messages.
    """
    
    def __init__(self):
        self.username = settings.DISCORD_USERNAME
        self.password = settings.DISCORD_PASSWORD
        self.channel_id = settings.DISCORD_CHANNEL_ID
        self.guild_id = settings.DISCORD_GUILD_ID
        
        # Validation
        if not all([self.username, self.password, self.channel_id, self.guild_id]):
            raise ValueError("Missing Discord configuration")
        
        # Session persistence
        self.cookies_file = Path("discord_cookies.pkl")
        self.session_file = Path("discord_session.json")
        
        # Playwright objects
        self.playwright = None
        self.browser = None
        self.page = None
        
        # Metrics parser
        self.metrics_parser = LaunchpadMetricsParser()
        
        # Message tracking
        self.processed_messages = set()
        self.last_scrape_time = None
        
        # Alpha Gardeners validation
        self.valid_authors = [
            "Launchpads Bot",
            "AlphaGardeners", 
            "Alpha Gardeners",
            "AG Bot"
        ]
        
        self.valid_content_patterns = [
            "@launchpads",
            "Fomo called",
            "FOMO called", 
            "Alpha call",
            "ALPHA CALL"
        ]
    
    def setup_browser(self):
        """Setup Playwright browser with session persistence."""
        logger.info("🌐 Setting up browser for Discord scraping...")
        
        self.playwright = sync_playwright().start()
        
        # Launch browser
        self.browser = self.playwright.chromium.launch(
            headless=False,  # Set to True for production
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox'
            ]
        )
        
        # Create context with saved session
        context_options = {
            'viewport': {'width': 1920, 'height': 1080},
            'user_agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        # Load saved cookies if available
        if self.cookies_file.exists():
            try:
                with open(self.cookies_file, 'rb') as f:
                    cookies = pickle.load(f)
                context_options['storage_state'] = {'cookies': cookies}
                logger.info("📂 Loaded saved session cookies")
            except Exception as e:
                logger.warning(f"Failed to load cookies: {e}")
        
        self.context = self.browser.new_context(**context_options)
        self.page = self.context.new_page()
        
        logger.info("✅ Browser setup complete")
    
    def login_to_discord(self) -> bool:
        """Login to Discord web interface."""
        logger.info("🔐 Logging into Discord...")
        
        try:
            # Navigate to Discord
            self.page.goto("https://discord.com/app", wait_until='networkidle')
            
            # Check if already logged in
            if self.is_logged_in():
                logger.info("✅ Already logged in via saved session")
                return True
            
            # Need to login
            logger.info("🔑 Performing login...")
            self.page.goto("https://discord.com/login", wait_until='networkidle')
            
            # Fill login form
            self.page.fill('input[name="email"]', self.username)
            self.page.fill('input[name="password"]', self.password)
            
            # Click login
            self.page.click('button[type="submit"]')
            
            # Wait for navigation or 2FA
            try:
                self.page.wait_for_url("https://discord.com/channels/**", timeout=30000)
                logger.info("✅ Login successful")
                
                # Save session
                self.save_session()
                return True
                
            except Exception:
                # Check for 2FA
                if self.page.locator('input[placeholder*="6-digit"]').count() > 0:
                    logger.info("🔐 2FA required - please enter code manually in browser")
                    
                    # Wait for manual 2FA entry
                    self.page.wait_for_url("https://discord.com/channels/**", timeout=120000)
                    logger.info("✅ 2FA completed")
                    
                    self.save_session()
                    return True
                else:
                    logger.error("❌ Login failed")
                    return False
                    
        except Exception as e:
            logger.error(f"❌ Login error: {e}")
            return False
    
    def is_logged_in(self) -> bool:
        """Check if logged into Discord."""
        try:
            # Look for user avatar or settings
            return self.page.locator('[class*="avatar"]').count() > 0
        except:
            return False
    
    def save_session(self):
        """Save session cookies for persistence."""
        try:
            cookies = self.context.cookies()
            with open(self.cookies_file, 'wb') as f:
                pickle.dump(cookies, f)
            logger.info("💾 Session cookies saved")
        except Exception as e:
            logger.error(f"Failed to save session: {e}")
    
    def navigate_to_alpha_gardeners(self) -> bool:
        """Navigate to Alpha Gardeners #launchpads channel."""
        target_url = f"https://discord.com/channels/{self.guild_id}/{self.channel_id}"
        
        logger.info(f"🎯 Navigating to Alpha Gardeners: {target_url}")
        
        try:
            self.page.goto(target_url, wait_until='networkidle')
            
            # Wait for messages to load
            self.page.wait_for_selector('[class*="message"]', timeout=10000)
            
            logger.info("✅ Successfully navigated to #launchpads channel")
            return True
            
        except Exception as e:
            logger.error(f"❌ Navigation failed: {e}")
            return False
    
    def is_valid_alpha_gardeners_message(self, message_data: Dict[str, Any]) -> bool:
        """
        Validate that this is a real Alpha Gardeners launchpad message.
        NO synthetic data allowed.
        """
        # Check author
        author_name = message_data.get('author', {}).get('username', '')
        if not any(valid_author.lower() in author_name.lower() for valid_author in self.valid_authors):
            logger.debug(f"❌ Invalid author: {author_name}")
            return False
        
        # Check content patterns
        content = message_data.get('content', '')
        if not any(pattern.lower() in content.lower() for pattern in self.valid_content_patterns):
            logger.debug(f"❌ Invalid content pattern: {content[:50]}")
            return False
        
        # Check for embeds (Alpha Gardeners always uses rich embeds)
        if not message_data.get('embeds'):
            logger.debug("❌ No embeds found")
            return False
        
        # Check for launchpad-specific fields
        embed = message_data['embeds'][0]
        embed_text = f"{embed.get('title', '')} {embed.get('description', '')}"
        
        # Must contain typical Alpha Gardeners metrics
        required_indicators = ['MC:', 'Liq:', 'AG Score:', 'Holders:']
        has_indicators = sum(1 for indicator in required_indicators if indicator in embed_text)
        
        if has_indicators < 2:
            logger.debug(f"❌ Missing launchpad indicators: {embed_text[:100]}")
            return False
        
        logger.info(f"✅ Valid Alpha Gardeners message: {message_data['id']}")
        return True
    
    def scrape_visible_messages(self) -> List[Dict[str, Any]]:
        """Scrape currently visible messages from Alpha Gardeners channel."""
        logger.info("📥 Scraping visible messages...")
        
        messages = []
        
        try:
            # Get all message elements
            message_elements = self.page.locator('[class*="message"][id*="message"]').all()
            
            logger.info(f"🔍 Found {len(message_elements)} message elements")
            
            for i, message_elem in enumerate(message_elements):
                try:
                    # Extract message ID
                    elem_id = message_elem.get_attribute('id')
                    if not elem_id:
                        continue
                    
                    # Parse message ID from element
                    message_id = elem_id.split('-')[-1]
                    
                    # Skip if already processed
                    if message_id in self.processed_messages:
                        continue
                    
                    # Extract message data
                    message_data = self.extract_message_from_element(message_elem, message_id)
                    
                    if message_data and self.is_valid_alpha_gardeners_message(message_data):
                        messages.append(message_data)
                        self.processed_messages.add(message_id)
                        logger.info(f"📞 Scraped Alpha Gardeners message: {message_id}")
                    
                except Exception as e:
                    logger.warning(f"Failed to process message element {i}: {e}")
            
            logger.info(f"✅ Scraped {len(messages)} valid Alpha Gardeners messages")
            return messages
            
        except Exception as e:
            logger.error(f"❌ Message scraping failed: {e}")
            return []
    
    def extract_message_from_element(self, message_elem, message_id: str) -> Dict[str, Any]:
        """Extract message data from DOM element."""
        try:
            # Get HTML content
            html = message_elem.inner_html()
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract author
            author_elem = soup.find(class_=lambda x: x and 'username' in str(x))
            author = author_elem.get_text(strip=True) if author_elem else 'Unknown'
            
            # Extract content
            content_elem = soup.find(class_=lambda x: x and 'messageContent' in str(x))
            content = content_elem.get_text(strip=True) if content_elem else ''
            
            # Extract timestamp
            time_elem = soup.find('time')
            timestamp = time_elem.get('datetime') if time_elem else datetime.now(timezone.utc).isoformat()
            
            # Extract embeds (simplified - real Discord embeds are complex)
            embeds = []
            embed_elems = soup.find_all(class_=lambda x: x and 'embed' in str(x))
            
            for embed_elem in embed_elems:
                embed_data = self.parse_embed_element(embed_elem)
                if embed_data:
                    embeds.append(embed_data)
            
            # Extract buttons/links
            components = []
            link_elems = soup.find_all('a', href=True)
            
            for link in link_elems:
                if link.get('href') and 'http' in link.get('href'):
                    components.append({
                        'type': 'button',
                        'label': link.get_text(strip=True),
                        'url': link['href']
                    })
            
            # Build message data
            message_data = {
                'id': message_id,
                'channel_id': self.channel_id,
                'content': content,
                'author': {
                    'username': author,
                    'id': f'scraped_{message_id}'
                },
                'timestamp': timestamp,
                'embeds': embeds,
                'components': [{'type': 1, 'components': components}] if components else [],
                'scraped_at': datetime.now(timezone.utc).isoformat()
            }
            
            return message_data
            
        except Exception as e:
            logger.error(f"Failed to extract message data: {e}")
            return None
    
    def parse_embed_element(self, embed_elem) -> Dict[str, Any]:
        """Parse embed data from BeautifulSoup element."""
        try:
            embed_data = {}
            
            # Title
            title_elem = embed_elem.find(class_=lambda x: x and 'embedTitle' in str(x))
            if title_elem:
                embed_data['title'] = title_elem.get_text(strip=True)
            
            # Description
            desc_elem = embed_elem.find(class_=lambda x: x and 'embedDescription' in str(x))
            if desc_elem:
                embed_data['description'] = desc_elem.get_text(strip=True)
            
            # Fields (this is where Alpha Gardeners metrics are)
            fields = []
            field_elems = embed_elem.find_all(class_=lambda x: x and 'embedField' in str(x))
            
            for field_elem in field_elems:
                name_elem = field_elem.find(class_=lambda x: x and 'embedFieldName' in str(x))
                value_elem = field_elem.find(class_=lambda x: x and 'embedFieldValue' in str(x))
                
                if name_elem and value_elem:
                    fields.append({
                        'name': name_elem.get_text(strip=True),
                        'value': value_elem.get_text(strip=True)
                    })
            
            if fields:
                embed_data['fields'] = fields
            
            return embed_data if embed_data else None
            
        except Exception as e:
            logger.error(f"Failed to parse embed: {e}")
            return None
    
    def store_real_message(self, message_data: Dict[str, Any]) -> bool:
        """Store real Alpha Gardeners message in database."""
        try:
            message_id = message_data['id']
            
            # Get T0 from snowflake
            t0 = get_entry_timestamp(message_id)
            epoch_ms = datetime_to_epoch_ms(t0)
            
            conn = psycopg2.connect(settings.DATABASE_URL)
            
            with conn.cursor() as cur:
                # Store in discord_raw
                cur.execute("""
                    INSERT INTO discord_raw (
                        channel_id, message_id, posted_at, posted_at_epoch_ms,
                        author_id, payload, inserted_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (message_id) DO NOTHING
                """, (
                    self.channel_id,
                    message_id,
                    t0,
                    epoch_ms,
                    message_data['author']['id'],
                    json.dumps(message_data)
                ))
                
                rows_inserted = cur.rowcount
                conn.commit()
            
            conn.close()
            
            if rows_inserted > 0:
                logger.info(f"💾 Stored real Alpha Gardeners message: {message_id}")
                
                # Immediately process through pipeline
                self.process_message_pipeline(message_id, message_data)
                
            return rows_inserted > 0
            
        except Exception as e:
            logger.error(f"❌ Failed to store message {message_data.get('id')}: {e}")
            return False
    
    def process_message_pipeline(self, message_id: str, message_data: Dict[str, Any]):
        """Process message through the complete pipeline."""
        logger.info(f"🔄 Processing {message_id} through pipeline...")
        
        try:
            # Step 1: Resolve mint
            mint_address = self.resolve_mint_from_message(message_data)
            
            if not mint_address:
                logger.warning(f"⚠️ No mint found in {message_id}")
                return
            
            # Step 2: Store mint resolution
            self.store_mint_resolution(message_id, mint_address, message_data)
            
            # Step 3: Validate acceptance (simplified for now)
            self.store_acceptance_status(message_id, mint_address)
            
            # Step 4: Extract comprehensive features
            self.extract_and_store_features(message_id, message_data)
            
            logger.info(f"✅ Pipeline processing complete for {message_id}")
            
        except Exception as e:
            logger.error(f"❌ Pipeline processing failed for {message_id}: {e}")
    
    def resolve_mint_from_message(self, message_data: Dict[str, Any]) -> str:
        """Resolve mint address from real Alpha Gardeners message."""
        # Check embeds for URLs
        for embed in message_data.get('embeds', []):
            if url := embed.get('url'):
                mint = self.extract_mint_from_url(url)
                if mint:
                    return mint
        
        # Check components for URLs
        for comp_row in message_data.get('components', []):
            for comp in comp_row.get('components', []):
                if url := comp.get('url'):
                    mint = self.extract_mint_from_url(url)
                    if mint:
                        return mint
        
        return None
    
    def extract_mint_from_url(self, url: str) -> str:
        """Extract mint from URL."""
        if 'pump.fun' in url:
            parts = url.split('/')
            if len(parts) > 3:
                return parts[-1]
        elif 'jup.ag' in url and 'swap' in url:
            parts = url.split('/')
            if len(parts) > 3:
                pair = parts[-1]
                tokens = pair.split('-')
                for token in tokens:
                    if token != 'SOL' and len(token) > 30:
                        return token
        
        return None
    
    def store_mint_resolution(self, message_id: str, mint_address: str, message_data: Dict[str, Any]):
        """Store mint resolution."""
        try:
            conn = psycopg2.connect(settings.DATABASE_URL)
            
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO mint_resolution (
                        message_id, resolved, mint, source_url, confidence, resolved_at
                    ) VALUES (%s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (message_id) DO NOTHING
                """, (
                    message_id, True, mint_address, 'alpha_gardeners_embed', 0.95
                ))
                
                conn.commit()
            
            conn.close()
            logger.info(f"✅ Mint resolved: {mint_address}")
            
        except Exception as e:
            logger.error(f"❌ Mint resolution storage failed: {e}")
    
    def store_acceptance_status(self, message_id: str, mint_address: str):
        """Store acceptance status (simplified - accept all for now)."""
        try:
            conn = psycopg2.connect(settings.DATABASE_URL)
            
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO acceptance_status (
                        message_id, mint, first_seen, status, reason_code, evidence, pool_deadline, last_checked
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (message_id) DO NOTHING
                """, (
                    message_id, mint_address, datetime.now(timezone.utc),
                    'ACCEPT', None,
                    json.dumps({"source": "real_alpha_gardeners", "auto_accepted": True}),
                    datetime.now(timezone.utc)
                ))
                
                conn.commit()
            
            conn.close()
            logger.info(f"✅ Accepted: {mint_address}")
            
        except Exception as e:
            logger.error(f"❌ Acceptance storage failed: {e}")
    
    def extract_and_store_features(self, message_id: str, message_data: Dict[str, Any]):
        """Extract and store comprehensive Alpha Gardeners features."""
        try:
            # Parse comprehensive metrics
            discord_metrics = self.metrics_parser.parse_message_metrics(message_data)
            validated_metrics = self.metrics_parser.validate_parsed_metrics(discord_metrics)
            
            # Add metadata
            validated_metrics.update({
                "message_id": message_id,
                "t0_timestamp": get_entry_timestamp(message_id).isoformat(),
                "feature_version": 1,
                "source": "real_alpha_gardeners_discord",
                "scraped_at": datetime.now(timezone.utc).isoformat()
            })
            
            conn = psycopg2.connect(settings.DATABASE_URL)
            
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO features_snapshot (
                        message_id, snapped_at, features, feature_version
                    ) VALUES (%s, %s, %s, %s)
                    ON CONFLICT (message_id) DO UPDATE SET
                        features = %s,
                        feature_version = %s
                """, (
                    message_id,
                    get_entry_timestamp(message_id),
                    json.dumps(validated_metrics),
                    1,
                    json.dumps(validated_metrics),
                    1
                ))
                
                conn.commit()
            
            conn.close()
            
            # Log key metrics extracted
            key_metrics = {
                "market_cap": validated_metrics.get("market_cap_usd"),
                "ag_score": validated_metrics.get("ag_score"),
                "win_prediction": validated_metrics.get("win_prediction_pct"),
                "bundled_pct": validated_metrics.get("bundled_pct")
            }
            
            logger.info(f"📊 Features extracted: {key_metrics}")
            
        except Exception as e:
            logger.error(f"❌ Feature extraction failed for {message_id}: {e}")
    
    def start_continuous_scraping(self):
        """Start continuous scraping of Alpha Gardeners channel."""
        logger.info("🚀 Starting continuous Alpha Gardeners scraping...")
        
        try:
            # Setup
            self.setup_browser()
            
            # Login
            if not self.login_to_discord():
                raise Exception("Discord login failed")
            
            # Navigate to channel
            if not self.navigate_to_alpha_gardeners():
                raise Exception("Failed to navigate to Alpha Gardeners channel")
            
            # Continuous scraping loop
            logger.info("🔄 Starting continuous monitoring...")
            
            while True:
                try:
                    # Scrape current messages
                    messages = self.scrape_visible_messages()
                    
                    # Store each valid message
                    for message in messages:
                        self.store_real_message(message)
                    
                    # Scroll up to load more history (occasionally)
                    if len(self.processed_messages) < 50:
                        self.page.keyboard.press('PageUp')
                        time.sleep(1)
                    
                    # Wait before next scrape
                    time.sleep(10)  # Check every 10 seconds for new messages
                    
                except Exception as e:
                    logger.error(f"❌ Scraping iteration failed: {e}")
                    time.sleep(30)  # Wait longer on errors
            
        except KeyboardInterrupt:
            logger.info("🛑 Scraping stopped by user")
        except Exception as e:
            logger.error(f"❌ Scraping failed: {e}")
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Cleanup browser resources."""
        try:
            if self.page:
                self.page.close()
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
            
            logger.info("🧹 Browser cleanup complete")
        except Exception as e:
            logger.error(f"Cleanup error: {e}")


def main():
    """Start real Alpha Gardeners Discord scraping."""
    print("🎯 Real Alpha Gardeners Discord Scraper")
    print("=" * 50)
    print("⚠️ REAL DATA ONLY - No synthetic messages")
    print(f"🎯 Target: Alpha Gardeners #launchpads")
    print(f"📧 Login: {settings.DISCORD_USERNAME}")
    
    scraper = RealDiscordScraper()
    
    try:
        scraper.start_continuous_scraping()
    except Exception as e:
        print(f"❌ Scraper failed: {e}")
        logger.error(f"Main scraper error: {e}")


if __name__ == "__main__":
    main()
