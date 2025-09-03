"""
Mint Resolver Module
Source: selectors.md - URL & Selector Rules
Extracts and validates Solana SPL mints from Discord messages
"""

import re
import json
import logging
import asyncio
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timezone
import aiohttp
import asyncpg
import base58

from config import settings

logger = logging.getLogger(__name__)


class MintResolver:
    """
    Resolves Solana mint addresses from Discord messages.
    Implements patterns from selectors.md.
    """
    
    # URL patterns for known platforms (from selectors.md)
    URL_PATTERNS = {
        'solscan': re.compile(r'solscan\.io/token/([1-9A-HJ-NP-Za-km-z]{32,44})'),
        'birdeye': re.compile(r'birdeye\.so/token/(?:SOLANA/)?([1-9A-HJ-NP-Za-km-z]{32,44})'),
        'pump_fun': re.compile(r'pump\.fun/coin/([1-9A-HJ-NP-Za-km-z]{32,44})'),
        'dexscreener': re.compile(r'dexscreener\.com/solana/([1-9A-HJ-NP-Za-km-z]{32,44})'),
    }
    
    # Base58 pattern for last resort scraping
    BASE58_PATTERN = re.compile(r'[1-9A-HJ-NP-Za-km-z]{32,44}')
    
    # Query parameter patterns
    QUERY_PATTERNS = [
        re.compile(r'[?&](token|address|mint)=([1-9A-HJ-NP-Za-km-z]{32,44})'),
    ]
    
    def __init__(self, db_pool: asyncpg.Pool):
        self.db_pool = db_pool
        self.session = None
        
    async def setup(self):
        """Initialize HTTP session."""
        if not self.session:
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(timeout=timeout)
    
    async def cleanup(self):
        """Cleanup resources."""
        if self.session:
            await self.session.close()
    
    async def resolve_message(self, message_id: str) -> Dict[str, Any]:
        """
        Resolve mint from a Discord message.
        
        Args:
            message_id: Discord message snowflake ID
            
        Returns:
            Dict with resolution results
        """
        try:
            # Get message from database
            async with self.db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT payload FROM discord_raw WHERE message_id = $1",
                    message_id
                )
                
                if not row:
                    return {
                        'resolved': False,
                        'error': 'Message not found'
                    }
                
                payload = row['payload']
            
            # Try to extract mint from various sources
            mint_candidates = []
            
            # 1. Check embeds (highest priority)
            if 'embeds' in payload:
                for embed in payload['embeds']:
                    candidates = await self._extract_from_embed(embed)
                    mint_candidates.extend(candidates)
            
            # 2. Check button components
            if 'components' in payload:
                candidates = self._extract_from_components(payload['components'])
                mint_candidates.extend(candidates)
            
            # 3. Check message content (fallback)
            if 'content' in payload and payload['content']:
                candidates = self._extract_from_content(payload['content'])
                mint_candidates.extend(candidates)
            
            # Validate and rank candidates
            if mint_candidates:
                mint, source_url, source_type, confidence = await self._validate_and_rank(mint_candidates)
                
                if mint:
                    # Store resolution
                    await self._store_resolution(
                        message_id, mint, source_url, source_type, confidence
                    )
                    
                    return {
                        'resolved': True,
                        'mint': mint,
                        'source_url': source_url,
                        'source_type': source_type,
                        'confidence': confidence
                    }
            
            # No valid mint found
            await self._store_resolution(
                message_id, None, None, None, 0.0,
                error='No valid mint found in message'
            )
            
            return {
                'resolved': False,
                'error': 'No valid mint found'
            }
            
        except Exception as e:
            logger.error(f"Error resolving mint for {message_id}: {e}")
            return {
                'resolved': False,
                'error': str(e)
            }
    
    async def _extract_from_embed(self, embed: Dict) -> List[Tuple[str, str, str, float]]:
        """
        Extract mint candidates from Discord embed.
        Returns list of (mint, source_url, source_type, confidence) tuples.
        """
        candidates = []
        
        # Check embed URL
        if 'url' in embed:
            url = embed['url']
            mint = self._extract_mint_from_url(url)
            if mint:
                candidates.append((mint, url, 'embed_url', 0.9))
        
        # Check embed title and description
        for field in ['title', 'description']:
            if field in embed and embed[field]:
                text = embed[field]
                # Look for URLs in text
                urls = re.findall(r'https?://[^\s]+', text)
                for url in urls:
                    mint = self._extract_mint_from_url(url)
                    if mint:
                        candidates.append((mint, url, f'embed_{field}', 0.8))
        
        # Check embed fields
        if 'fields' in embed:
            for field in embed['fields']:
                for key in ['name', 'value']:
                    if key in field and field[key]:
                        text = field[key]
                        urls = re.findall(r'https?://[^\s]+', text)
                        for url in urls:
                            mint = self._extract_mint_from_url(url)
                            if mint:
                                candidates.append((mint, url, 'embed_field', 0.7))
        
        # Check footer
        if 'footer' in embed and 'text' in embed['footer']:
            text = embed['footer']['text']
            mint = self._extract_base58_from_text(text)
            if mint:
                candidates.append((mint, None, 'embed_footer', 0.6))
        
        return candidates
    
    def _extract_from_components(self, components: List) -> List[Tuple[str, str, str, float]]:
        """Extract mint candidates from Discord components (buttons)."""
        candidates = []
        
        for row in components:
            if 'components' in row:
                for component in row['components']:
                    if 'url' in component:
                        url = component['url']
                        mint = self._extract_mint_from_url(url)
                        if mint:
                            candidates.append((mint, url, 'button', 0.85))
        
        return candidates
    
    def _extract_from_content(self, content: str) -> List[Tuple[str, str, str, float]]:
        """Extract mint candidates from message content."""
        candidates = []
        
        # Look for URLs
        urls = re.findall(r'https?://[^\s]+', content)
        for url in urls:
            mint = self._extract_mint_from_url(url)
            if mint:
                candidates.append((mint, url, 'content_url', 0.5))
        
        # Last resort: base58 scraping
        if not candidates:
            mint = self._extract_base58_from_text(content)
            if mint:
                candidates.append((mint, None, 'base58_scrape', 0.3))
        
        return candidates
    
    def _extract_mint_from_url(self, url: str) -> Optional[str]:
        """Extract mint address from a URL using known patterns."""
        # Clean URL
        url = url.strip().rstrip('/')
        
        # Try each pattern
        for platform, pattern in self.URL_PATTERNS.items():
            match = pattern.search(url)
            if match:
                potential_mint = match.group(1)
                
                # Special handling for dexscreener (might be pair address)
                if platform == 'dexscreener':
                    # Will need to resolve via API if it's a pair
                    return potential_mint  # Return for now, validate later
                
                return potential_mint
        
        # Check query parameters
        for pattern in self.QUERY_PATTERNS:
            match = pattern.search(url)
            if match:
                return match.group(2)
        
        return None
    
    def _extract_base58_from_text(self, text: str) -> Optional[str]:
        """Extract potential base58 mint address from text."""
        matches = self.BASE58_PATTERN.findall(text)
        
        # Return the first valid-looking match
        for match in matches:
            if 32 <= len(match) <= 44:
                try:
                    # Try to decode to verify it's valid base58
                    base58.b58decode(match)
                    return match
                except:
                    continue
        
        return None
    
    async def _validate_and_rank(self, candidates: List[Tuple[str, str, str, float]]) -> Tuple[Optional[str], Optional[str], Optional[str], float]:
        """
        Validate mint candidates via RPC and return the best one.
        
        Returns:
            Tuple of (mint, source_url, source_type, confidence)
        """
        # Sort by confidence
        candidates.sort(key=lambda x: x[3], reverse=True)
        
        for mint_candidate, source_url, source_type, confidence in candidates:
            # Check if it's a dexscreener pair that needs resolution
            if source_url and 'dexscreener.com' in source_url:
                resolved_mint = await self._resolve_dexscreener_pair(mint_candidate)
                if resolved_mint:
                    mint_candidate = resolved_mint
            
            # Validate via RPC
            if await self._validate_mint_rpc(mint_candidate):
                return mint_candidate, source_url, source_type, confidence
        
        return None, None, None, 0.0
    
    async def _resolve_dexscreener_pair(self, pair_or_mint: str) -> Optional[str]:
        """
        Resolve Dexscreener pair address to mint address.
        If it's already a mint, return as-is.
        """
        try:
            if not self.session:
                await self.setup()
            
            # First check if it's already a valid mint
            if await self._validate_mint_rpc(pair_or_mint):
                return pair_or_mint
            
            # Try to get pair info from Dexscreener API
            url = f"https://api.dexscreener.com/latest/dex/pairs/solana/{pair_or_mint}"
            
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if 'pair' in data:
                        pair = data['pair']
                        # Get the base token (not quote token like USDC/SOL)
                        base_token = pair.get('baseToken', {})
                        if 'address' in base_token:
                            return base_token['address']
            
            return None
            
        except Exception as e:
            logger.warning(f"Failed to resolve Dexscreener pair {pair_or_mint}: {e}")
            return None
    
    async def _validate_mint_rpc(self, mint_address: str) -> bool:
        """
        Validate mint address via Solana RPC.
        Checks that it's a valid SPL token mint.
        """
        try:
            if not self.session:
                await self.setup()
            
            # Prepare RPC request
            rpc_url = settings.HELIUS_RPC_URL
            
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getAccountInfo",
                "params": [
                    mint_address,
                    {
                        "encoding": "jsonParsed"
                    }
                ]
            }
            
            async with self.session.post(rpc_url, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if 'result' in data and data['result']:
                        account = data['result']
                        
                        # Check if it's owned by SPL Token program
                        owner = account.get('owner')
                        if owner in [settings.SPL_TOKEN_PROGRAM_ID, settings.SPL_TOKEN_2022_PROGRAM_ID]:
                            # Check if it's a mint account
                            parsed = account.get('data', {}).get('parsed', {})
                            if parsed.get('type') == 'mint':
                                return True
            
            return False
            
        except Exception as e:
            logger.warning(f"RPC validation failed for {mint_address}: {e}")
            return False
    
    async def _store_resolution(self, message_id: str, mint: Optional[str], 
                               source_url: Optional[str], source_type: Optional[str],
                               confidence: float, error: Optional[str] = None):
        """Store mint resolution result in database."""
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO mint_resolution 
                    (message_id, resolved, mint, source_url, source_type, confidence, error)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (message_id) 
                    DO UPDATE SET
                        resolved = EXCLUDED.resolved,
                        mint = EXCLUDED.mint,
                        source_url = EXCLUDED.source_url,
                        source_type = EXCLUDED.source_type,
                        confidence = EXCLUDED.confidence,
                        error = EXCLUDED.error,
                        resolved_at = NOW()
                """, message_id, mint is not None, mint, source_url, source_type, confidence, error)
                
                logger.info(f"Stored resolution for {message_id}: mint={mint}, confidence={confidence}")
                
        except Exception as e:
            logger.error(f"Failed to store resolution for {message_id}: {e}")
    
    async def process_pending_messages(self, batch_size: int = 10):
        """
        Process messages that haven't been resolved yet.
        
        Args:
            batch_size: Number of messages to process in one batch
        """
        try:
            async with self.db_pool.acquire() as conn:
                # Get unprocessed messages
                rows = await conn.fetch("""
                    SELECT dr.message_id 
                    FROM discord_raw dr
                    LEFT JOIN mint_resolution mr ON dr.message_id = mr.message_id
                    WHERE mr.message_id IS NULL
                    ORDER BY dr.posted_at DESC
                    LIMIT $1
                """, batch_size)
                
                if not rows:
                    return
                
                logger.info(f"Processing {len(rows)} pending messages for mint resolution")
                
                for row in rows:
                    message_id = row['message_id']
                    result = await self.resolve_message(message_id)
                    
                    if result['resolved']:
                        logger.info(f"✅ Resolved mint for {message_id}: {result['mint']}")
                    else:
                        logger.warning(f"❌ Could not resolve mint for {message_id}: {result.get('error')}")
                    
                    # Small delay to avoid rate limits
                    await asyncio.sleep(0.1)
                    
        except Exception as e:
            logger.error(f"Error processing pending messages: {e}")


async def main():
    """Test the mint resolver."""
    import asyncpg
    
    # Connect to database
    pool = await asyncpg.create_pool(settings.DATABASE_URL)
    
    resolver = MintResolver(pool)
    await resolver.setup()
    
    try:
        # Process any pending messages
        await resolver.process_pending_messages()
    finally:
        await resolver.cleanup()
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
