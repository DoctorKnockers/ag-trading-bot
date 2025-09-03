"""
Solana blockchain utilities and RPC helpers.
Source: spec.md - SPL validation and authority checks
"""

import asyncio
import logging
from typing import Dict, Any, Optional, Tuple
import aiohttp
import base58

from config import settings

logger = logging.getLogger(__name__)


class SolanaRPCClient:
    """Async Solana RPC client for mint validation."""
    
    def __init__(self):
        self.rpc_url = settings.HELIUS_RPC_URL
        self.backup_url = settings.BACKUP_RPC_URL
        self.session = None
    
    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
    
    async def get_account_info(self, address: str, encoding: str = "jsonParsed") -> Optional[Dict[str, Any]]:
        """
        Get account info from Solana RPC.
        
        Args:
            address: Solana account address
            encoding: Response encoding ('jsonParsed' recommended)
            
        Returns:
            Account info or None if error
        """
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getAccountInfo",
            "params": [address, {"encoding": encoding}]
        }
        
        # Try primary RPC first
        result = await self._make_rpc_call(self.rpc_url, payload)
        
        # Fallback to backup RPC if needed
        if not result and self.backup_url:
            result = await self._make_rpc_call(self.backup_url, payload)
        
        if result and "result" in result:
            return result["result"].get("value")
        
        return None
    
    async def _make_rpc_call(self, url: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Make RPC call with error handling."""
        try:
            headers = {"Content-Type": "application/json"}
            
            # Add auth header for Helius
            if "helius" in url and settings.HELIUS_API_KEY:
                headers["Authorization"] = f"Bearer {settings.HELIUS_API_KEY}"
            
            async with self.session.post(url, json=payload, headers=headers) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.warning(f"RPC error {response.status}: {await response.text()}")
                    
        except Exception as e:
            logger.error(f"RPC call failed: {e}")
        
        return None


async def validate_spl_mint(mint_address: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Validate if address is a valid SPL mint with no rug vectors.
    
    Args:
        mint_address: Solana mint address to validate
        
    Returns:
        Tuple of (is_valid, status_message, mint_info)
    """
    # Validate Base58 format
    try:
        decoded = base58.b58decode(mint_address)
        if len(decoded) != 32:
            return False, "INVALID_ADDRESS_LENGTH", None
    except Exception:
        return False, "INVALID_BASE58", None
    
    # Get account info via RPC
    async with SolanaRPCClient() as rpc:
        account_info = await rpc.get_account_info(mint_address)
        
        if not account_info:
            return False, "ACCOUNT_NOT_FOUND", None
        
        # Check owner program
        owner = account_info.get("owner")
        if owner not in [settings.SPL_TOKEN_PROGRAM_ID, settings.SPL_TOKEN_2022_PROGRAM_ID]:
            return False, f"INVALID_OWNER:{owner}", None
        
        # Check parsed data
        parsed = account_info.get("data", {}).get("parsed")
        if not parsed or parsed.get("type") != "mint":
            return False, "NOT_SPL_MINT", None
        
        # Extract mint info
        mint_info = parsed.get("info", {})
        
        # Check for rug vectors per spec.md
        
        # 1. INFINITE_MINT - mintAuthority present
        if mint_info.get("mintAuthority"):
            return False, "INFINITE_MINT", {
                "mintAuthority": mint_info["mintAuthority"],
                "supply": mint_info.get("supply", "0")
            }
        
        # 2. FREEZE_BACKDOOR - freezeAuthority present  
        if mint_info.get("freezeAuthority"):
            return False, "FREEZE_BACKDOOR", {
                "freezeAuthority": mint_info["freezeAuthority"]
            }
        
        # Valid SPL mint with no rug vectors
        return True, "VALID_SPL_MINT", {
            "supply": mint_info.get("supply", "0"),
            "decimals": mint_info.get("decimals", 0),
            "mintAuthority": None,
            "freezeAuthority": None,
            "owner": owner
        }


async def get_token_supply(mint_address: str) -> Optional[int]:
    """Get current token supply."""
    async with SolanaRPCClient() as rpc:
        account_info = await rpc.get_account_info(mint_address)
        
        if account_info:
            parsed = account_info.get("data", {}).get("parsed", {})
            mint_info = parsed.get("info", {})
            return int(mint_info.get("supply", 0))
    
    return None


async def get_token_decimals(mint_address: str) -> Optional[int]:
    """Get token decimals."""
    async with SolanaRPCClient() as rpc:
        account_info = await rpc.get_account_info(mint_address)
        
        if account_info:
            parsed = account_info.get("data", {}).get("parsed", {})
            mint_info = parsed.get("info", {})
            return mint_info.get("decimals", 0)
    
    return None
