"""
Jupiter API utilities for routing and executability testing.
Source: spec.md - Execution simulation and route validation
"""

import asyncio
import logging
from typing import Dict, Any, Optional, Tuple
import aiohttp

from config import settings

logger = logging.getLogger(__name__)

# SOL mint address (wrapped SOL)
WSOL_MINT = "So11111111111111111111111111111111111111112"


class JupiterQuoteClient:
    """Async Jupiter quote client for route testing."""
    
    def __init__(self):
        self.quote_url = settings.JUPITER_API_URL + "/quote"
        self.session = None
    
    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
    
    async def get_quote(
        self,
        input_mint: str,
        output_mint: str,
        amount: int,
        slippage_bps: int = 50
    ) -> Optional[Dict[str, Any]]:
        """
        Get quote from Jupiter API.
        
        Args:
            input_mint: Input token mint address
            output_mint: Output token mint address
            amount: Amount in smallest unit (lamports for SOL, token units for others)
            slippage_bps: Slippage tolerance in basis points
            
        Returns:
            Quote data or None if no route
        """
        params = {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": str(amount),
            "slippageBps": str(slippage_bps),
            "onlyDirectRoutes": "false"
        }
        
        try:
            async with self.session.get(self.quote_url, params=params) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.warning(f"Jupiter quote error {response.status}: {await response.text()}")
                    
        except Exception as e:
            logger.error(f"Jupiter quote failed: {e}")
        
        return None


async def test_token_executability(
    mint_address: str,
    test_amount_sol: float = None,
    max_slippage: float = None
) -> Tuple[bool, Dict[str, Any]]:
    """
    Test token executability per SUSTAINED_10X requirements.
    
    Implements the execution simulation from labels.md:
    - Step 1: Quote buy Q_TEST_SOL WSOL→MINT
    - Step 2: Quote sell MINT→WSOL using outAmount from step 1
    - Check effective slippage ≤ S_MAX
    
    Args:
        mint_address: Token mint to test
        test_amount_sol: SOL amount for test (default Q_TEST_SOL)
        max_slippage: Max slippage allowed (default S_MAX)
        
    Returns:
        Tuple of (is_executable, test_results)
    """
    if test_amount_sol is None:
        test_amount_sol = settings.Q_TEST_SOL
    if max_slippage is None:
        max_slippage = settings.S_MAX
    
    test_lamports = int(test_amount_sol * 1_000_000_000)
    
    logger.info(f"🧪 Testing executability for {mint_address} ({test_amount_sol} SOL)")
    
    async with JupiterQuoteClient() as jupiter:
        # Step 1: Quote buy (WSOL → MINT)
        buy_quote = await jupiter.get_quote(
            WSOL_MINT,
            mint_address,
            test_lamports
        )
        
        if not buy_quote:
            return False, {
                "error": "No buy route available",
                "test_amount_sol": test_amount_sol
            }
        
        out_amount = int(buy_quote.get("outAmount", 0))
        buy_impact_pct = float(buy_quote.get("priceImpactPct", 100.0))
        
        if out_amount == 0:
            return False, {
                "error": "Buy quote returned zero tokens",
                "buy_quote": buy_quote
            }
        
        # Step 2: Quote sell (MINT → WSOL) using exact outAmount
        sell_quote = await jupiter.get_quote(
            mint_address,
            WSOL_MINT,
            out_amount
        )
        
        if not sell_quote:
            return False, {
                "error": "No sell route available",
                "tokens_to_sell": out_amount
            }
        
        sell_impact_pct = float(sell_quote.get("priceImpactPct", 100.0))
        
        # Calculate effective slippage (max of buy/sell impacts)
        effective_slippage = max(buy_impact_pct, sell_impact_pct) / 100.0
        
        # Check against threshold
        is_executable = effective_slippage <= max_slippage
        
        results = {
            "is_executable": is_executable,
            "test_amount_sol": test_amount_sol,
            "buy_impact_pct": buy_impact_pct,
            "sell_impact_pct": sell_impact_pct,
            "effective_slippage": effective_slippage,
            "max_slippage_allowed": max_slippage,
            "tokens_received": out_amount,
            "buy_routes": len(buy_quote.get("routePlan", [])),
            "sell_routes": len(sell_quote.get("routePlan", [])),
            "buy_quote": buy_quote,
            "sell_quote": sell_quote
        }
        
        logger.info(f"📊 Executability: {is_executable} (slippage: {effective_slippage:.1%})")
        
        return is_executable, results


async def check_token_liquidity(mint_address: str) -> Tuple[str, Dict[str, Any]]:
    """
    Check token liquidity and routing availability.
    
    Args:
        mint_address: Token mint to check
        
    Returns:
        Tuple of (status_code, evidence)
    """
    # Test with small amount first
    test_amount = int(0.1 * 1_000_000_000)  # 0.1 SOL
    
    async with JupiterQuoteClient() as jupiter:
        # Test buy route
        buy_quote = await jupiter.get_quote(WSOL_MINT, mint_address, test_amount)
        
        if not buy_quote:
            return "NO_BUY_ROUTE", {"error": "No buy route found"}
        
        out_amount = int(buy_quote.get("outAmount", 0))
        if out_amount == 0:
            return "ZERO_OUTPUT", {"error": "Buy quote returned zero tokens"}
        
        # Test sell route
        sell_quote = await jupiter.get_quote(mint_address, WSOL_MINT, out_amount)
        
        if not sell_quote:
            return "NO_SELL_ROUTE", {"error": "No sell route found"}
        
        # Calculate metrics
        buy_impact = float(buy_quote.get("priceImpactPct", 0))
        sell_impact = float(sell_quote.get("priceImpactPct", 0))
        max_impact = max(buy_impact, sell_impact) / 100.0
        
        # Check against confiscatory fee threshold
        if max_impact > settings.MAX_EFFECTIVE_FEE:
            return "CONFISCATORY_FEE", {
                "buy_impact_pct": buy_impact,
                "sell_impact_pct": sell_impact,
                "max_impact": max_impact,
                "threshold": settings.MAX_EFFECTIVE_FEE
            }
        
        # Estimate liquidity from price impact
        liquidity_estimate = min(1_000_000, 10_000 / (max_impact + 0.001))
        
        return "LIQUIDITY_OK", {
            "buy_impact_pct": buy_impact,
            "sell_impact_pct": sell_impact,
            "max_impact": max_impact,
            "buy_routes": len(buy_quote.get("routePlan", [])),
            "sell_routes": len(sell_quote.get("routePlan", [])),
            "liquidity_estimate_usd": liquidity_estimate
        }


def is_valid_solana_address(address: str) -> bool:
    """
    Validate Solana address format.
    
    Args:
        address: Address string to validate
        
    Returns:
        True if valid Solana address format
    """
    try:
        decoded = base58.b58decode(address)
        return len(decoded) == 32
    except Exception:
        return False
