"""
Parallel Token Validation Module
Runs multiple security checks concurrently with ThreadPoolExecutor
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, Optional, List, Tuple
from functools import lru_cache
from datetime import datetime, timedelta
import aiohttp
import json
import base58

from config import settings
from utils.jupiter_helpers import test_token_executability
from utils.solana_helpers import validate_spl_mint
from utils.price_helpers import get_current_price

logger = logging.getLogger(__name__)


class ParallelValidator:
    """
    Parallel validation for token security checks.
    Runs honeypot, liquidity, smart wallet, and holder checks concurrently.
    """
    
    def __init__(self, max_workers: int = 4):
        """
        Initialize parallel validator.
        
        Args:
            max_workers: Maximum concurrent validation threads
        """
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.session = None
        
        # Cache for repeated checks
        self.honeypot_cache = {}
        self.cache_ttl = 300  # 5 minutes
        
        # Smart wallet tracking
        self.smart_wallets = self._load_smart_wallets()
        
        # API endpoints
        self.jupiter_api = "https://quote-api.jup.ag/v6"
        self.helius_rpc = settings.HELIUS_RPC_URL
        
        logger.info(f"✅ Parallel validator initialized with {max_workers} workers")
    
    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
        self.executor.shutdown(wait=False)
    
    def _load_smart_wallets(self) -> Dict[str, Dict]:
        """Load known smart wallet addresses and their stats."""
        # In production, load from database
        # For now, return sample data
        return {
            "SmartWallet1...": {"win_rate": 0.75, "total_trades": 150},
            "SmartWallet2...": {"win_rate": 0.68, "total_trades": 89},
            # Add more from your database
        }
    
    @lru_cache(maxsize=128)
    def check_honeypot_sync(self, mint_address: str) -> Dict[str, Any]:
        """
        Synchronous honeypot check with caching.
        Uses Jupiter Quote API to detect honeypot tokens.
        
        Args:
            mint_address: Token mint address
            
        Returns:
            Honeypot check results
        """
        # Check cache first
        cache_key = f"honeypot:{mint_address}"
        if cache_key in self.honeypot_cache:
            cached = self.honeypot_cache[cache_key]
            if (datetime.now() - cached["timestamp"]).seconds < self.cache_ttl:
                return cached["result"]
        
        try:
            import requests
            
            # Test small buy quote
            buy_params = {
                "inputMint": "So11111111111111111111111111111111111111112",  # SOL
                "outputMint": mint_address,
                "amount": str(int(0.01 * 1e9)),  # 0.01 SOL in lamports
                "slippageBps": "50"
            }
            
            buy_response = requests.get(f"{self.jupiter_api}/quote", params=buy_params)
            
            if buy_response.status_code != 200:
                return {
                    "is_honeypot": True,
                    "reason": "No buy route",
                    "confidence": 0.9
                }
            
            buy_data = buy_response.json()
            out_amount = int(buy_data.get("outAmount", 0))
            
            if out_amount == 0:
                return {
                    "is_honeypot": True,
                    "reason": "Zero output amount",
                    "confidence": 0.95
                }
            
            # Test sell quote with received amount
            sell_params = {
                "inputMint": mint_address,
                "outputMint": "So11111111111111111111111111111111111111112",  # SOL
                "amount": str(out_amount),
                "slippageBps": "50"
            }
            
            sell_response = requests.get(f"{self.jupiter_api}/quote", params=sell_params)
            
            if sell_response.status_code != 200:
                return {
                    "is_honeypot": True,
                    "reason": "No sell route",
                    "confidence": 0.95
                }
            
            sell_data = sell_response.json()
            sell_amount = int(sell_data.get("outAmount", 0))
            
            # Calculate effective tax
            expected_sell = int(0.01 * 1e9 * 0.95)  # Account for 5% slippage
            actual_loss = (expected_sell - sell_amount) / expected_sell if expected_sell > 0 else 1.0
            
            # Determine if honeypot based on loss
            is_honeypot = actual_loss > 0.5  # More than 50% loss is honeypot
            
            result = {
                "is_honeypot": is_honeypot,
                "buy_tax": max(0, actual_loss * 50),  # Estimate buy tax
                "sell_tax": max(0, actual_loss * 50),  # Estimate sell tax
                "effective_tax": actual_loss * 100,
                "can_sell": sell_amount > 0,
                "confidence": 0.85
            }
            
            # Cache result
            self.honeypot_cache[cache_key] = {
                "result": result,
                "timestamp": datetime.now()
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Honeypot check failed for {mint_address}: {e}")
            return {
                "is_honeypot": True,
                "error": str(e),
                "confidence": 0.0
            }
    
    def check_liquidity_sync(self, mint_address: str) -> Dict[str, Any]:
        """
        Synchronous liquidity check.
        Queries pool information from DEXs.
        
        Args:
            mint_address: Token mint address
            
        Returns:
            Liquidity check results
        """
        try:
            import requests
            
            # Check Jupiter price API for liquidity info
            response = requests.get(
                f"https://price.jup.ag/v4/price",
                params={"ids": mint_address}
            )
            
            if response.status_code == 200:
                data = response.json()
                token_data = data.get("data", {}).get(mint_address, {})
                
                if token_data:
                    return {
                        "has_liquidity": True,
                        "liquidity_usd": float(token_data.get("liquidity", 0)),
                        "price": float(token_data.get("price", 0)),
                        "confidence": 0.9,
                        "pools": []  # Would need additional queries for pool details
                    }
            
            # Fallback: assume low liquidity if not found
            return {
                "has_liquidity": False,
                "liquidity_usd": 0,
                "reason": "Not found in price feeds",
                "confidence": 0.7
            }
            
        except Exception as e:
            logger.error(f"Liquidity check failed: {e}")
            return {
                "has_liquidity": False,
                "error": str(e),
                "confidence": 0.0
            }
    
    def analyze_smart_wallets_sync(self, mint_address: str) -> Dict[str, Any]:
        """
        Synchronous smart wallet analysis.
        Checks if known profitable wallets hold the token.
        
        Args:
            mint_address: Token mint address
            
        Returns:
            Smart wallet analysis results
        """
        try:
            import requests
            
            # Get token holders via Helius API
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTokenLargestAccounts",
                "params": [mint_address]
            }
            
            response = requests.post(self.helius_rpc, json=payload)
            
            if response.status_code != 200:
                return {
                    "smart_wallets_count": 0,
                    "error": "Failed to get holders",
                    "confidence": 0.0
                }
            
            data = response.json()
            holders = data.get("result", {}).get("value", [])
            
            # Check holders against smart wallet list
            smart_holders = []
            total_smart_balance = 0
            
            for holder in holders[:50]:  # Check top 50 holders
                address = holder.get("address")
                amount = float(holder.get("amount", 0))
                
                if address in self.smart_wallets:
                    wallet_stats = self.smart_wallets[address]
                    if wallet_stats["win_rate"] > 0.65:
                        smart_holders.append({
                            "wallet": address,
                            "win_rate": wallet_stats["win_rate"],
                            "balance": amount
                        })
                        total_smart_balance += amount
            
            return {
                "smart_wallets_count": len(smart_holders),
                "smart_wallets": smart_holders[:10],  # Top 10
                "smart_money_balance": total_smart_balance,
                "confidence": 0.7 if len(smart_holders) > 0 else 0.3
            }
            
        except Exception as e:
            logger.error(f"Smart wallet analysis failed: {e}")
            return {
                "smart_wallets_count": 0,
                "error": str(e),
                "confidence": 0.0
            }
    
    def check_holder_distribution_sync(self, mint_address: str) -> Dict[str, Any]:
        """
        Synchronous holder distribution check.
        Analyzes token concentration among holders.
        
        Args:
            mint_address: Token mint address
            
        Returns:
            Holder distribution results
        """
        try:
            import requests
            import numpy as np
            
            # Get token holders
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTokenLargestAccounts",
                "params": [mint_address]
            }
            
            response = requests.post(self.helius_rpc, json=payload)
            
            if response.status_code != 200:
                return {
                    "total_holders": 0,
                    "error": "Failed to get holders",
                    "confidence": 0.0
                }
            
            data = response.json()
            holders = data.get("result", {}).get("value", [])
            
            if not holders:
                return {
                    "total_holders": 0,
                    "top10_percentage": 100,
                    "top20_percentage": 100,
                    "distribution_score": 0,
                    "confidence": 0.5
                }
            
            # Calculate holder statistics
            balances = [float(h.get("amount", 0)) for h in holders]
            total_supply = sum(balances)
            
            if total_supply == 0:
                return {
                    "total_holders": len(holders),
                    "error": "Zero total supply",
                    "confidence": 0.0
                }
            
            # Calculate concentration metrics
            sorted_balances = sorted(balances, reverse=True)
            
            top10_balance = sum(sorted_balances[:10])
            top20_balance = sum(sorted_balances[:20])
            
            top10_pct = (top10_balance / total_supply) * 100
            top20_pct = (top20_balance / total_supply) * 100
            
            # Calculate Gini coefficient
            def gini_coefficient(balances):
                sorted_balances = sorted(balances)
                n = len(balances)
                cumsum = np.cumsum(sorted_balances)
                return (2 * np.sum((np.arange(1, n+1) * sorted_balances))) / (n * cumsum[-1]) - (n + 1) / n
            
            gini = gini_coefficient(balances) if len(balances) > 1 else 1.0
            
            # Calculate distribution score (0-1, higher is better)
            distribution_score = max(0, 1 - gini) * (1 - top10_pct/100)
            
            # Count whales (holders with >2% of supply)
            whale_threshold = total_supply * 0.02
            whale_count = sum(1 for b in balances if b > whale_threshold)
            
            return {
                "total_holders": len(holders),
                "top10_percentage": top10_pct,
                "top20_percentage": top20_pct,
                "whale_count": whale_count,
                "distribution_score": distribution_score,
                "gini_coefficient": gini,
                "confidence": 0.8
            }
            
        except Exception as e:
            logger.error(f"Holder distribution check failed: {e}")
            return {
                "total_holders": 0,
                "error": str(e),
                "confidence": 0.0
            }
    
    async def validate_token(self, mint_address: str, timeout: float = 5.0) -> Dict[str, Any]:
        """
        Run all validation checks in parallel.
        
        Args:
            mint_address: Token mint address
            timeout: Maximum time for all checks
            
        Returns:
            Combined validation results
        """
        loop = asyncio.get_event_loop()
        
        # Schedule all synchronous checks in parallel
        futures = {
            'honeypot': loop.run_in_executor(self.executor, self.check_honeypot_sync, mint_address),
            'liquidity': loop.run_in_executor(self.executor, self.check_liquidity_sync, mint_address),
            'smart_wallets': loop.run_in_executor(self.executor, self.analyze_smart_wallets_sync, mint_address),
            'holders': loop.run_in_executor(self.executor, self.check_holder_distribution_sync, mint_address)
        }
        
        # Also run async checks
        async_futures = {
            'spl_validation': self._async_spl_check(mint_address),
            'executability': self._async_executability_check(mint_address)
        }
        
        # Combine all futures
        all_futures = {**futures, **async_futures}
        
        results = {}
        for key, future in all_futures.items():
            try:
                results[key] = await asyncio.wait_for(future, timeout=timeout)
            except asyncio.TimeoutError:
                logger.warning(f"Validation timeout for {key}")
                results[key] = {'status': 'timeout', 'valid': False}
            except Exception as e:
                logger.error(f"Validation error for {key}: {e}")
                results[key] = {'status': 'error', 'valid': False, 'error': str(e)}
        
        # Calculate overall validation score
        results['overall'] = self._calculate_validation_score(results)
        results['timestamp'] = datetime.now().isoformat()
        results['mint_address'] = mint_address
        
        return results
    
    async def _async_spl_check(self, mint_address: str) -> Dict[str, Any]:
        """Async SPL validation check."""
        try:
            is_valid, status, info = await validate_spl_mint(mint_address)
            return {
                'is_valid': is_valid,
                'status': status,
                'info': info
            }
        except Exception as e:
            return {
                'is_valid': False,
                'error': str(e)
            }
    
    async def _async_executability_check(self, mint_address: str) -> Dict[str, Any]:
        """Async executability check."""
        try:
            is_executable, results = await test_token_executability(
                mint_address,
                test_amount_sol=0.1,  # Small test amount
                max_slippage=0.15  # 15% max slippage
            )
            return {
                'is_executable': is_executable,
                'results': results
            }
        except Exception as e:
            return {
                'is_executable': False,
                'error': str(e)
            }
    
    def _calculate_validation_score(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate overall validation score from individual checks.
        
        Args:
            results: Individual validation results
            
        Returns:
            Overall validation assessment
        """
        score = 0.0
        max_score = 0.0
        flags = []
        
        # Honeypot check (critical - 30 points)
        if 'honeypot' in results and not results['honeypot'].get('error'):
            max_score += 30
            if not results['honeypot'].get('is_honeypot', True):
                score += 30
            else:
                flags.append("HONEYPOT_DETECTED")
        
        # Liquidity check (important - 25 points)
        if 'liquidity' in results and not results['liquidity'].get('error'):
            max_score += 25
            liq_usd = results['liquidity'].get('liquidity_usd', 0)
            if liq_usd > 10000:
                score += 25
            elif liq_usd > 5000:
                score += 15
            elif liq_usd > 1000:
                score += 5
            
            if liq_usd < 5000:
                flags.append("LOW_LIQUIDITY")
        
        # Smart wallet analysis (valuable signal - 20 points)
        if 'smart_wallets' in results and not results['smart_wallets'].get('error'):
            max_score += 20
            smart_count = results['smart_wallets'].get('smart_wallets_count', 0)
            if smart_count >= 5:
                score += 20
                flags.append("SMART_MONEY_DETECTED")
            elif smart_count >= 3:
                score += 12
            elif smart_count >= 1:
                score += 5
        
        # Holder distribution (risk factor - 15 points)
        if 'holders' in results and not results['holders'].get('error'):
            max_score += 15
            top10_pct = results['holders'].get('top10_percentage', 100)
            if top10_pct < 40:
                score += 15
            elif top10_pct < 60:
                score += 8
            elif top10_pct < 80:
                score += 3
            
            if top10_pct > 70:
                flags.append("HIGH_CONCENTRATION")
        
        # SPL validation (mandatory - 10 points)
        if 'spl_validation' in results:
            max_score += 10
            if results['spl_validation'].get('is_valid'):
                score += 10
            else:
                flags.append("INVALID_SPL")
                flags.append(results['spl_validation'].get('status', 'UNKNOWN'))
        
        # Calculate final score
        final_score = score / max_score if max_score > 0 else 0
        
        # Determine verdict
        if final_score >= 0.7 and not any(f in flags for f in ["HONEYPOT_DETECTED", "INVALID_SPL"]):
            verdict = "PASS"
        elif final_score >= 0.5 and "HONEYPOT_DETECTED" not in flags:
            verdict = "RISKY"
        else:
            verdict = "FAIL"
        
        return {
            'score': final_score,
            'verdict': verdict,
            'flags': flags,
            'details': {
                'raw_score': score,
                'max_score': max_score,
                'breakdown': {
                    'honeypot': score if 'honeypot' in results else 0,
                    'liquidity': score if 'liquidity' in results else 0,
                    'smart_wallets': score if 'smart_wallets' in results else 0,
                    'holders': score if 'holders' in results else 0,
                    'spl': score if 'spl_validation' in results else 0
                }
            }
        }
    
    async def validate_batch(self, mint_addresses: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Validate multiple tokens in parallel.
        
        Args:
            mint_addresses: List of token mint addresses
            
        Returns:
            Dict mapping mint addresses to validation results
        """
        tasks = []
        for mint in mint_addresses:
            tasks.append(self.validate_token(mint))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        return {
            mint: result if not isinstance(result, Exception) else {'error': str(result), 'overall': {'verdict': 'ERROR'}}
            for mint, result in zip(mint_addresses, results)
        }


# Example usage
if __name__ == "__main__":
    async def test():
        async with ParallelValidator(max_workers=4) as validator:
            # Test single validation
            result = await validator.validate_token("7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr")
            print(f"Validation result: {result['overall']['verdict']}")
            print(f"Score: {result['overall']['score']:.2%}")
            print(f"Flags: {result['overall']['flags']}")
            
            # Print detailed breakdown
            print("\nDetailed Results:")
            for check, data in result.items():
                if check != 'overall' and check != 'timestamp' and check != 'mint_address':
                    print(f"  {check}: {data}")
            
            # Test batch validation
            mints = [
                "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr",
                "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY2QrkX6R"
            ]
            batch_results = await validator.validate_batch(mints)
            print("\nBatch Validation:")
            for mint, result in batch_results.items():
                verdict = result.get('overall', {}).get('verdict', 'ERROR')
                score = result.get('overall', {}).get('score', 0)
                print(f"  {mint[:8]}...: {verdict} (score: {score:.2%})")
    
    asyncio.run(test())