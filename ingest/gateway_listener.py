"""
Gateway Listener Module - COMPLIANT VERSION
Source: spec.md - Discord Message Ingestion
Passively scrapes Discord messages from Alpha Gardeners #launchpads channel
NO WEBHOOKS, NO BOTS - Only passive read-only scraping via user session
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
import asyncpg
import discord
from discord.ext import commands

from config import settings

logger = logging.getLogger(__name__)


class DiscordMessageScraper:
    """
    Passive Discord message scraper for Alpha Gardeners #launchpads channel.
    
    COMPLIANCE NOTES:
    - Uses discord.py in USER MODE (not bot mode)
    - Read-only passive scraping - no posting, no interactions
    - No webhooks, no bot tokens, no integrations
    - Stores raw message payloads for processing
    """
    
    def __init__(self, db_pool: asyncpg.Pool):
        """
        Initialize the Discord scraper.
        
        Args:
            db_pool: PostgreSQL connection pool
        """
        self.db_pool = db_pool
        
        # Create Discord client in user mode (not bot)
        # This requires a user token for passive scraping
        intents = discord.Intents.default()
        intents.message_content = True
        intents.messages = True
        intents.guilds = True
        
        self.client = discord.Client(intents=intents)
        
        # Register event handlers
        self.client.event(self.on_ready)
        self.client.event(self.on_message)
        
        # Target channel configuration
        self.target_guild_id = settings.DISCORD_GUILD_ID  # Alpha Gardeners guild
        self.target_channel_id = settings.DISCORD_CHANNEL_ID  # #launchpads channel
        
        self.is_ready = False
    
    async def on_ready(self):
        """Called when Discord client is ready."""
        logger.info(f"Discord scraper connected as {self.client.user}")
        
        # Verify we can access the target channel
        guild = self.client.get_guild(self.target_guild_id)
        if not guild:
            logger.error(f"Cannot access guild {self.target_guild_id}")
            return
        
        channel = guild.get_channel(self.target_channel_id)
        if not channel:
            logger.error(f"Cannot access channel {self.target_channel_id}")
            return
        
        logger.info(f"✅ Monitoring {guild.name} → #{channel.name}")
        self.is_ready = True
        
        # Optionally fetch recent message history on startup
        await self.fetch_recent_messages(channel)
    
    async def on_message(self, message: discord.Message):
        """
        Handle incoming Discord messages.
        Only processes messages from the target channel.
        
        Args:
            message: Discord message object
        """
        # Only process messages from target channel
        if message.channel.id != self.target_channel_id:
            return
        
        # Convert to raw payload format
        raw_payload = self._message_to_payload(message)
        
        # Store in database
        await self.store_message(raw_payload)
        
        # Log for monitoring
        logger.info(f"📨 Scraped message {message.id} from {message.author.name}")
        
        # Display key information
        self._log_message_details(raw_payload)
    
    def _message_to_payload(self, message: discord.Message) -> Dict[str, Any]:
        """
        Convert Discord.py message object to raw payload format.
        Matches the structure Discord webhooks would provide.
        
        Args:
            message: Discord message object
            
        Returns:
            Raw message payload as dict
        """
        payload = {
            "id": str(message.id),
            "type": message.type.value,
            "content": message.content,
            "channel_id": str(message.channel.id),
            "guild_id": str(message.guild.id) if message.guild else None,
            "timestamp": message.created_at.isoformat(),
            "edited_timestamp": message.edited_at.isoformat() if message.edited_at else None,
            "tts": message.tts,
            "mention_everyone": message.mention_everyone,
            "pinned": message.pinned,
            
            # Author information
            "author": {
                "id": str(message.author.id),
                "username": message.author.name,
                "discriminator": message.author.discriminator,
                "avatar": str(message.author.avatar) if message.author.avatar else None,
                "bot": message.author.bot,
            },
            
            # Embeds
            "embeds": [self._embed_to_dict(embed) for embed in message.embeds],
            
            # Attachments
            "attachments": [
                {
                    "id": str(att.id),
                    "filename": att.filename,
                    "size": att.size,
                    "url": att.url,
                    "proxy_url": att.proxy_url,
                    "content_type": att.content_type,
                }
                for att in message.attachments
            ],
            
            # Components (buttons, etc.)
            "components": self._components_to_dict(message.components) if hasattr(message, 'components') else [],
            
            # Reactions
            "reactions": [
                {
                    "emoji": str(reaction.emoji),
                    "count": reaction.count,
                    "me": reaction.me,
                }
                for reaction in message.reactions
            ] if message.reactions else [],
        }
        
        return payload
    
    def _embed_to_dict(self, embed: discord.Embed) -> Dict[str, Any]:
        """Convert Discord embed to dictionary."""
        embed_dict = {
            "type": embed.type,
            "title": embed.title,
            "description": embed.description,
            "url": embed.url,
            "color": embed.color.value if embed.color else None,
            "timestamp": embed.timestamp.isoformat() if embed.timestamp else None,
        }
        
        if embed.footer:
            embed_dict["footer"] = {
                "text": embed.footer.text,
                "icon_url": embed.footer.icon_url,
            }
        
        if embed.author:
            embed_dict["author"] = {
                "name": embed.author.name,
                "url": embed.author.url,
                "icon_url": embed.author.icon_url,
            }
        
        if embed.fields:
            embed_dict["fields"] = [
                {
                    "name": field.name,
                    "value": field.value,
                    "inline": field.inline,
                }
                for field in embed.fields
            ]
        
        if embed.image:
            embed_dict["image"] = {"url": embed.image.url}
        
        if embed.thumbnail:
            embed_dict["thumbnail"] = {"url": embed.thumbnail.url}
        
        return embed_dict
    
    def _components_to_dict(self, components: List) -> List[Dict[str, Any]]:
        """Convert Discord components (buttons, etc.) to dictionary."""
        result = []
        
        for action_row in components:
            row_dict = {
                "type": 1,  # ACTION_ROW
                "components": []
            }
            
            for component in action_row.children:
                if isinstance(component, discord.Button):
                    comp_dict = {
                        "type": 2,  # BUTTON
                        "style": component.style.value,
                        "label": component.label,
                        "emoji": str(component.emoji) if component.emoji else None,
                        "custom_id": component.custom_id,
                        "url": component.url,
                        "disabled": component.disabled,
                    }
                    row_dict["components"].append(comp_dict)
            
            result.append(row_dict)
        
        return result
    
    def _log_message_details(self, payload: Dict[str, Any]):
        """Log important details from scraped message."""
        # Extract key information
        content = payload.get('content', '')
        author = payload.get('author', {}).get('username', 'Unknown')
        
        # Check for embeds with URLs
        for embed in payload.get('embeds', []):
            if url := embed.get('url'):
                logger.info(f"  📎 Embed URL: {url}")
        
        # Check for button components with URLs
        for row in payload.get('components', []):
            for comp in row.get('components', []):
                if comp.get('type') == 2 and comp.get('url'):  # Button with URL
                    logger.info(f"  🔘 Button: {comp.get('label')} → {comp.get('url')}")
    
    async def store_message(self, payload: Dict[str, Any]):
        """
        Store raw Discord message payload in database.
        
        Args:
            payload: Raw message payload
        """
        try:
            message_id = payload['id']
            channel_id = payload['channel_id']
            guild_id = payload['guild_id']
            author_id = payload['author']['id']
            posted_at = datetime.fromisoformat(payload['timestamp'])
            
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
            logger.error(f"Failed to store message {payload.get('id')}: {e}")
    
    async def fetch_recent_messages(self, channel: discord.TextChannel, limit: int = 100):
        """
        Fetch recent message history from channel on startup.
        
        Args:
            channel: Discord channel object
            limit: Number of messages to fetch
        """
        try:
            logger.info(f"Fetching last {limit} messages from #{channel.name}")
            
            async for message in channel.history(limit=limit):
                # Convert and store each message
                payload = self._message_to_payload(message)
                await self.store_message(payload)
            
            logger.info(f"✅ Fetched and stored recent message history")
            
        except Exception as e:
            logger.error(f"Failed to fetch message history: {e}")
    
    async def start(self):
        """Start the Discord scraper."""
        try:
            # Note: In production, use a secure method to provide the user token
            # Never commit tokens to version control
            token = settings.DISCORD_USER_TOKEN
            
            if not token:
                raise ValueError("DISCORD_USER_TOKEN not configured")
            
            logger.info("Starting Discord message scraper...")
            await self.client.start(token, bot=False)  # bot=False for user mode
            
        except Exception as e:
            logger.error(f"Failed to start Discord scraper: {e}")
            raise
    
    async def stop(self):
        """Stop the Discord scraper."""
        if self.client:
            await self.client.close()
            logger.info("Discord scraper stopped")


async def main():
    """Main entry point for the gateway listener."""
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create database pool
    pool = await asyncpg.create_pool(settings.DATABASE_URL)
    
    # Create and start scraper
    scraper = DiscordMessageScraper(pool)
    
    try:
        await scraper.start()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        await scraper.stop()
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
