"""
Discord Launchpad Metrics Parser
Extracts all structured metrics from Alpha Gardeners Discord launchpad messages.
Maps Discord embed content to standardized feature schema.
"""

import re
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class LaunchpadMetricsParser:
    """
    Parses all metrics from Discord launchpad message embeds.
    
    Handles the rich structured data shown in Alpha Gardeners bot messages
    including market cap, liquidity, holder stats, swap data, etc.
    """
    
    def __init__(self):
        # Regex patterns for metric extraction
        self.patterns = {
            # Market metrics
            'market_cap': re.compile(r'MC:\s*\$?([\d,]+\.?\d*[KMB]?)', re.IGNORECASE),
            'liquidity': re.compile(r'Liq:\s*\$?([\d,]+\.?\d*[KMB]?)\s*\(?([\d.]+)%?\)?', re.IGNORECASE),
            'token_age': re.compile(r'Token Age:\s*(.+?)(?:\n|$)', re.IGNORECASE),
            'top_holders': re.compile(r'Top (\d+):\s*([\d.]+)%', re.IGNORECASE),
            'holders_count': re.compile(r'Holders:\s*(\d+)', re.IGNORECASE),
            
            # Volume metrics
            'volume_1m': re.compile(r'1m Volume:.*?Total:\s*([\d.]+[KMB]?)\s*B:\s*([\d.]+)%\s*S:\s*([\d.]+)%', re.IGNORECASE | re.DOTALL),
            'vol2mc': re.compile(r'Vol2MC:\s*([\d.]+)%', re.IGNORECASE),
            
            # Swap metrics
            'swaps_f': re.compile(r'F:\s*(\d+)', re.IGNORECASE),
            'swaps_kyc': re.compile(r'KYC:\s*(\d+)', re.IGNORECASE),
            'swaps_unq': re.compile(r'Unq:\s*(\d+)', re.IGNORECASE),
            'swaps_sm': re.compile(r'SM:\s*(\d+)', re.IGNORECASE),
            
            # Creator/Security metrics
            'ag_score': re.compile(r'AG Score:\s*(\d+)/10', re.IGNORECASE),
            'mint_flag': re.compile(r'Mint:\s*(No|Yes)', re.IGNORECASE),
            'freeze_flag': re.compile(r'Freeze:\s*(No|Yes)', re.IGNORECASE),
            'mut_flag': re.compile(r'Mut:\s*(No|Yes)', re.IGNORECASE),
            'chg_flag': re.compile(r'Chg:\s*(No|Yes)', re.IGNORECASE),
            'bundled_pct': re.compile(r'Bundled:\s*([\d.]+)%', re.IGNORECASE),
            'ds_paid': re.compile(r'DS paid:\s*(No|Yes)', re.IGNORECASE),
            
            # Funding/Creator info
            'funding_info': re.compile(r'Funding:\s*(.+?)(?:\n|$)', re.IGNORECASE),
            'drained_info': re.compile(r'Drained\s*(\d+)\s*of\s*(\d+)', re.IGNORECASE),
            'airdropped_pct': re.compile(r'Airdropped:\s*([\d.]+)%', re.IGNORECASE),
            
            # Win prediction
            'win_prediction': re.compile(r'Win Prediction:\s*([\d.]+)%', re.IGNORECASE),
            
            # First alert info
            'first_alert': re.compile(r'First Alerted.*?(\d+\.?\d*)\s*SOL.*?([\d.]+[KMB]?)', re.IGNORECASE | re.DOTALL),
            'price_change': re.compile(r'([\d.]+[KMB]?)\s*→\s*([\d.]+[KMB]?)\s*Δ\s*([\d.]+)x', re.IGNORECASE),
        }
    
    def parse_message_metrics(self, message_payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse all metrics from a Discord launchpad message.
        
        Args:
            message_payload: Full Discord message payload
            
        Returns:
            Structured metrics dictionary
        """
        metrics = {
            # Initialize all metrics with defaults
            "win_prediction_pct": None,
            "market_cap_usd": None,
            "ath_market_cap_usd": None,
            "liquidity_usd": None,
            "liquidity_pct": None,
            "source_platform": None,
            "token_age_sec": None,
            "top10_holders_pct": None,
            "top20_holders_pct": None,
            "holders_count": None,
            "swaps_f_count": None,
            "swaps_d_count": None,
            "swaps_kyc_count": None,
            "swaps_unique_count": None,
            "swaps_sm_count": None,
            "volume_1m_total_usd": None,
            "volume_1m_buy_pct": None,
            "volume_1m_sell_pct": None,
            "volume_1m_to_mc_pct": None,
            "links_web_url": None,
            "links_x_url": None,
            "ag_score": None,
            "bundled_pct": None,
            "ds_paid_flag": None,
            "creator_wallet": None,
            "creator_pct": None,
            "creator_sol_change": None,
            "funding_wallet": None,
            "funding_age_min": None,
            "creator_drained_count": None,
            "creator_drained_total": None,
            "creator_drained_tags": None,
            "token_description": None,
            "first_alert_epoch_ms": None,
            "recent_swaps_time_sec": None,
            "recent_swaps_exch": None,
            "recent_swaps_amount": None,
            "recent_swaps_volume": None,
            "min_liquidity_threshold_usd": None,
            "max_liquidity_threshold_usd": None,
            "min_market_cap_threshold_usd": None,
            "max_market_cap_threshold_usd": None,
            "min_token_age_sec": None,
            "max_token_age_sec": None,
            "min_ag_score": None,
            "max_ag_score": None,
            "min_bundled_pct": None,
            "max_bundled_pct": None,
            "max_drained_pct": None,
            "max_drained_count": None,
            "skip_duplicates_flag": None,
            "fresh_deployer_flag": None,
            "has_description_flag": None,
            
            # Meta information
            "parsed_at": datetime.now(timezone.utc).isoformat(),
            "parser_version": "1.0"
        }
        
        # Extract all text content from the message
        all_text = self._extract_all_text(message_payload)
        
        # Parse each metric category
        self._parse_market_metrics(all_text, metrics)
        self._parse_holder_metrics(all_text, metrics)
        self._parse_volume_metrics(all_text, metrics)
        self._parse_swap_metrics(all_text, metrics)
        self._parse_security_metrics(all_text, metrics)
        self._parse_creator_metrics(all_text, metrics)
        self._parse_platform_metrics(all_text, metrics)
        self._parse_links(message_payload, metrics)
        
        # Parse description
        metrics["token_description"] = self._extract_description(message_payload)
        metrics["has_description_flag"] = bool(metrics["token_description"])
        
        # Determine source platform
        metrics["source_platform"] = self._determine_platform(all_text, message_payload)
        
        logger.info(f"📊 Parsed {sum(1 for v in metrics.values() if v is not None)} metrics from message")
        
        return metrics
    
    def _extract_all_text(self, payload: Dict[str, Any]) -> str:
        """Extract all text content from message payload."""
        text_parts = []
        
        # Main content
        if content := payload.get('content'):
            text_parts.append(content)
        
        # Embed content
        for embed in payload.get('embeds', []):
            if title := embed.get('title'):
                text_parts.append(title)
            if desc := embed.get('description'):
                text_parts.append(desc)
            
            # Embed fields
            for field in embed.get('fields', []):
                if name := field.get('name'):
                    text_parts.append(name)
                if value := field.get('value'):
                    text_parts.append(value)
            
            # Footer
            if footer := embed.get('footer'):
                if text := footer.get('text'):
                    text_parts.append(text)
        
        return '\n'.join(text_parts)
    
    def _parse_market_metrics(self, text: str, metrics: Dict[str, Any]):
        """Parse market cap, liquidity, and related metrics."""
        # Market cap
        if match := self.patterns['market_cap'].search(text):
            mc_str = match.group(1)
            metrics["market_cap_usd"] = self._parse_currency_value(mc_str)
        
        # Liquidity with percentage
        if match := self.patterns['liquidity'].search(text):
            liq_str = match.group(1)
            metrics["liquidity_usd"] = self._parse_currency_value(liq_str)
            
            if len(match.groups()) > 1 and match.group(2):
                metrics["liquidity_pct"] = float(match.group(2))
        
        # Vol2MC
        if match := self.patterns['vol2mc'].search(text):
            metrics["volume_1m_to_mc_pct"] = float(match.group(1))
    
    def _parse_holder_metrics(self, text: str, metrics: Dict[str, Any]):
        """Parse holder-related metrics."""
        # Holders count
        if match := self.patterns['holders_count'].search(text):
            metrics["holders_count"] = int(match.group(1))
        
        # Top holder percentages
        for match in self.patterns['top_holders'].finditer(text):
            top_n = int(match.group(1))
            percentage = float(match.group(2))
            
            if top_n == 10:
                metrics["top10_holders_pct"] = percentage
            elif top_n == 20:
                metrics["top20_holders_pct"] = percentage
    
    def _parse_volume_metrics(self, text: str, metrics: Dict[str, Any]):
        """Parse volume-related metrics."""
        # 1m Volume breakdown
        if match := self.patterns['volume_1m'].search(text):
            total_str = match.group(1)
            buy_pct = float(match.group(2))
            sell_pct = float(match.group(3))
            
            metrics["volume_1m_total_usd"] = self._parse_currency_value(total_str)
            metrics["volume_1m_buy_pct"] = buy_pct
            metrics["volume_1m_sell_pct"] = sell_pct
    
    def _parse_swap_metrics(self, text: str, metrics: Dict[str, Any]):
        """Parse swap count metrics."""
        # Recent swaps counts
        if match := self.patterns['swaps_f'].search(text):
            metrics["swaps_f_count"] = int(match.group(1))
        
        if match := self.patterns['swaps_kyc'].search(text):
            metrics["swaps_kyc_count"] = int(match.group(1))
        
        if match := self.patterns['swaps_unq'].search(text):
            metrics["swaps_unique_count"] = int(match.group(1))
        
        if match := self.patterns['swaps_sm'].search(text):
            metrics["swaps_sm_count"] = int(match.group(1))
    
    def _parse_security_metrics(self, text: str, metrics: Dict[str, Any]):
        """Parse security and risk metrics."""
        # AG Score
        if match := self.patterns['ag_score'].search(text):
            metrics["ag_score"] = int(match.group(1))
        
        # Security flags
        if match := self.patterns['mint_flag'].search(text):
            metrics["mint_authority_flag"] = match.group(1).lower() == 'yes'
        
        if match := self.patterns['freeze_flag'].search(text):
            metrics["freeze_authority_flag"] = match.group(1).lower() == 'yes'
        
        if match := self.patterns['mut_flag'].search(text):
            metrics["mutable_flag"] = match.group(1).lower() == 'yes'
        
        if match := self.patterns['chg_flag'].search(text):
            metrics["changeable_flag"] = match.group(1).lower() == 'yes'
        
        # Bundled percentage
        if match := self.patterns['bundled_pct'].search(text):
            metrics["bundled_pct"] = float(match.group(1))
        
        # DS paid flag
        if match := self.patterns['ds_paid'].search(text):
            metrics["ds_paid_flag"] = match.group(1).lower() == 'yes'
        
        # Win prediction
        if match := self.patterns['win_prediction'].search(text):
            metrics["win_prediction_pct"] = float(match.group(1))
    
    def _parse_creator_metrics(self, text: str, metrics: Dict[str, Any]):
        """Parse creator and funding metrics."""
        # Funding info
        if match := self.patterns['funding_info'].search(text):
            funding_text = match.group(1)
            
            # Extract wallet and timing
            wallet_match = re.search(r'([A-Za-z0-9]{32,44})', funding_text)
            if wallet_match:
                metrics["funding_wallet"] = wallet_match.group(1)
            
            # Extract timing
            time_match = re.search(r'@\s*(\d+)([mh])', funding_text)
            if time_match:
                value = int(time_match.group(1))
                unit = time_match.group(2)
                
                if unit == 'm':
                    metrics["funding_age_min"] = value
                elif unit == 'h':
                    metrics["funding_age_min"] = value * 60
        
        # Drained info
        if match := self.patterns['drained_info'].search(text):
            drained_count = int(match.group(1))
            drained_total = int(match.group(2))
            
            metrics["creator_drained_count"] = drained_count
            metrics["creator_drained_total"] = drained_total
            
            if drained_total > 0:
                metrics["max_drained_pct"] = (drained_count / drained_total) * 100
        
        # Airdropped percentage
        if match := self.patterns['airdropped_pct'].search(text):
            metrics["airdropped_pct"] = float(match.group(1))
    
    def _parse_platform_metrics(self, text: str, metrics: Dict[str, Any]):
        """Parse platform and launch metrics."""
        # Token age parsing
        if match := self.patterns['token_age'].search(text):
            age_text = match.group(1).strip()
            metrics["token_age_sec"] = self._parse_time_to_seconds(age_text)
        
        # First alert info
        if match := self.patterns['first_alert'].search(text):
            sol_amount = float(match.group(1))
            market_cap = self._parse_currency_value(match.group(2))
            
            metrics["first_alert_sol_amount"] = sol_amount
            metrics["first_alert_market_cap"] = market_cap
        
        # Price change info
        if match := self.patterns['price_change'].search(text):
            from_price = self._parse_currency_value(match.group(1))
            to_price = self._parse_currency_value(match.group(2))
            multiple = float(match.group(3))
            
            metrics["price_from"] = from_price
            metrics["price_to"] = to_price
            metrics["price_multiple"] = multiple
    
    def _parse_links(self, payload: Dict[str, Any], metrics: Dict[str, Any]):
        """Parse links from message components and embeds."""
        links = []
        
        # Extract from embeds
        for embed in payload.get('embeds', []):
            if url := embed.get('url'):
                links.append(url)
        
        # Extract from components (buttons)
        for comp_row in payload.get('components', []):
            for comp in comp_row.get('components', []):
                if url := comp.get('url'):
                    links.append(url)
        
        # Categorize links
        for link in links:
            if 'twitter.com' in link or 'x.com' in link:
                metrics["links_x_url"] = link
            elif any(platform in link for platform in ['pump.fun', 'birdeye.so', 'dexscreener.com']):
                metrics["links_web_url"] = link
    
    def _extract_description(self, payload: Dict[str, Any]) -> Optional[str]:
        """Extract token description from embed."""
        for embed in payload.get('embeds', []):
            # Look for description field
            if desc := embed.get('description'):
                # Skip if it's just stats
                if not any(stat in desc.lower() for stat in ['mc:', 'liq:', 'holders:', 'volume:']):
                    return desc.strip()
            
            # Look in fields for description
            for field in embed.get('fields', []):
                if 'description' in field.get('name', '').lower():
                    return field.get('value', '').strip()
        
        return None
    
    def _determine_platform(self, text: str, payload: Dict[str, Any]) -> str:
        """Determine source platform from message content."""
        text_lower = text.lower()
        
        if 'pump.fun' in text_lower or 'pumpfun' in text_lower:
            return "pumpfun"
        elif 'launchpad' in text_lower:
            return "launchpad"
        elif 'raydium' in text_lower:
            return "raydium"
        elif 'meteora' in text_lower:
            return "meteora"
        else:
            return "unknown"
    
    def _parse_currency_value(self, value_str: str) -> Optional[float]:
        """Parse currency string like '$15,090' or '4.1K' to float."""
        if not value_str:
            return None
        
        # Clean the string
        clean = re.sub(r'[,$]', '', value_str.strip())
        
        # Handle K/M/B suffixes
        multiplier = 1
        if clean.endswith('K'):
            multiplier = 1_000
            clean = clean[:-1]
        elif clean.endswith('M'):
            multiplier = 1_000_000
            clean = clean[:-1]
        elif clean.endswith('B'):
            multiplier = 1_000_000_000
            clean = clean[:-1]
        
        try:
            return float(clean) * multiplier
        except ValueError:
            return None
    
    def _parse_time_to_seconds(self, time_str: str) -> Optional[int]:
        """Parse time string like 'a day ago' or '2 hours ago' to seconds."""
        time_lower = time_str.lower()
        
        # Extract number and unit
        time_match = re.search(r'(\d+)\s*(second|minute|hour|day|week)', time_lower)
        
        if time_match:
            value = int(time_match.group(1))
            unit = time_match.group(2)
            
            multipliers = {
                'second': 1,
                'minute': 60,
                'hour': 3600,
                'day': 86400,
                'week': 604800
            }
            
            return value * multipliers.get(unit, 1)
        
        # Handle relative terms
        if 'a day ago' in time_lower:
            return 86400
        elif 'an hour ago' in time_lower:
            return 3600
        elif 'a minute ago' in time_lower:
            return 60
        
        return None
    
    def validate_parsed_metrics(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate and clean parsed metrics.
        
        Args:
            metrics: Raw parsed metrics
            
        Returns:
            Validated and cleaned metrics
        """
        validated = metrics.copy()
        
        # Ensure percentages are in valid range
        percentage_fields = [
            'win_prediction_pct', 'liquidity_pct', 'top10_holders_pct', 'top20_holders_pct',
            'volume_1m_buy_pct', 'volume_1m_sell_pct', 'volume_1m_to_mc_pct',
            'bundled_pct', 'creator_pct', 'airdropped_pct'
        ]
        
        for field in percentage_fields:
            if validated.get(field) is not None:
                validated[field] = max(0, min(100, validated[field]))
        
        # Ensure counts are non-negative
        count_fields = [
            'holders_count', 'swaps_f_count', 'swaps_d_count', 'swaps_kyc_count',
            'swaps_unique_count', 'swaps_sm_count', 'creator_drained_count', 'creator_drained_total'
        ]
        
        for field in count_fields:
            if validated.get(field) is not None:
                validated[field] = max(0, validated[field])
        
        # Ensure currency values are positive
        currency_fields = [
            'market_cap_usd', 'ath_market_cap_usd', 'liquidity_usd', 'volume_1m_total_usd',
            'first_alert_market_cap', 'price_from', 'price_to'
        ]
        
        for field in currency_fields:
            if validated.get(field) is not None and isinstance(validated[field], (int, float)):
                validated[field] = max(0, validated[field])
        
        # Set derived flags with null safety
        drained_count = validated.get("creator_drained_count") or 0
        funding_age = validated.get("funding_age_min") or 0
        
        validated["fresh_deployer_flag"] = (
            drained_count == 0 and funding_age < 60  # Less than 1 hour
        )
        
        validated["skip_duplicates_flag"] = (
            drained_count > 2  # Creator has drained multiple tokens
        )
        
        return validated


def test_parser():
    """Test the metrics parser with sample data."""
    # Sample Discord message payload (based on screenshots)
    sample_payload = {
        "id": "1234567890",
        "content": "🚀 ALPHA CALL - NEW PUMP.FUN LAUNCH DETECTED",
        "embeds": [
            {
                "title": "FOMO called DYNGE",
                "description": "4SQQe...bonk 📄 Copy • 🔮 Win Prediction: 14%",
                "fields": [
                    {
                        "name": "Stats DYNGE",
                        "value": "💰 MC: $15,090\n💧 Liq: $4,333 (51.54%)\n🚀 Via: LAUNCHPAD\n⏰ Token Age: a day ago\n👥 Top 20: 42.81%\n📊 Holders: 47"
                    },
                    {
                        "name": "Stats Creator", 
                        "value": "🎯 AG Score: 7/10\n🎭 Mint: No 🟢 Freeze: No 🟢\n🔧 Mut: No 🟢 Chg: No 🟢\n💼 Bundled: 3.35%\n🏛️ DS paid: No 🔴"
                    },
                    {
                        "name": "Recent Swaps",
                        "value": "F: 7 KYC: 0 Unq: 6 SM: 0"
                    },
                    {
                        "name": "1m Volume",
                        "value": "Total: 4.1K B: 40% S: 60%\nVol2MC: 27%"
                    }
                ]
            }
        ],
        "components": [
            {
                "type": 1,
                "components": [
                    {
                        "type": 2,
                        "style": 5,
                        "label": "Insta Buy",
                        "url": "https://pump.fun/coin/4SQQeXXXXbonk"
                    }
                ]
            }
        ]
    }
    
    parser = LaunchpadMetricsParser()
    metrics = parser.parse_message_metrics(sample_payload)
    
    print("🧪 Parser Test Results:")
    for key, value in metrics.items():
        if value is not None:
            print(f"  {key}: {value}")
    
    return metrics


if __name__ == "__main__":
    test_parser()
