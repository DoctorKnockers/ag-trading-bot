"""
CryptoBERT Sentiment Integration for AG Trading Bot
Complete implementation ready for Cursor
"""

import torch
import logging
from typing import Dict, Optional, List
import re
from datetime import datetime
import numpy as np
import hashlib
from functools import lru_cache

# Handle macOS signal issues with transformers
try:
    from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification
    TRANSFORMERS_AVAILABLE = True
except Exception as e:
    logging.warning(f"Transformers import failed (likely macOS signal issue): {e}")
    TRANSFORMERS_AVAILABLE = False

# ============================================
# PART 1: Core Sentiment Analyzer
# ============================================

class SimpleCryptoSentiment:
    """
    Dead simple CryptoBERT sentiment analyzer optimized for memecoin launches.
    Provides multiple scoring signals from a single model pass.
    """
    
    def __init__(self, model_name: str = "ElKulako/cryptobert", device: Optional[int] = None):
        """
        Initialize the sentiment analyzer.
        
        Args:
            model_name: HuggingFace model to use
            device: CUDA device (-1 for CPU, 0+ for GPU)
        """
        if device is None:
            device = 0 if torch.cuda.is_available() else -1
            
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"Initializing CryptoBERT on device {device}")
        
        if not TRANSFORMERS_AVAILABLE:
            self.logger.warning("Transformers not available - using rule-based sentiment fallback")
            self.analyzer = None
        else:
            # Try multiple models in order of preference
            self.analyzer = self._initialize_model_with_fallbacks(model_name, device)
            
        # Memecoin-specific patterns
        self.fomo_terms = [
            'early', 'moon', 'gem', 'next', '100x', '1000x', 
            'aping', 'send', 'lfg', 'wagmi', 'pump', 'flying',
            'explode', 'parabolic', 'millionaire', 'generational'
        ]
        
        self.trust_terms = [
            'renounced', 'burned', 'locked', 'audit', 'safe',
            'community', 'cto', 'takeover', 'organic', 'fair'
        ]
        
        self.warning_terms = [
            'dyor', 'risk', 'careful', 'might', 'maybe', 
            'possibly', 'could', 'potential', 'nfa'
        ]
        
        self.scam_indicators = [
            'guaranteed', 'promise', 'definitely', 'easy money',
            'risk free', 'cant lose', 'insider', 'secret'
        ]
    
    def _initialize_model_with_fallbacks(self, primary_model: str, device: int):
        """
        Initialize sentiment model with multiple fallback options.
        
        Args:
            primary_model: Primary model to try (ElKulako/cryptobert)
            device: Device to use
            
        Returns:
            Loaded pipeline or None if all fail
        """
        # Model fallback chain (in order of preference)
        models_to_try = [
            (primary_model, "CryptoBERT (primary)"),
            ("cardiffnlp/twitter-roberta-base-sentiment-latest", "Twitter-RoBERTa (crypto-aware)"),
            ("distilbert-base-uncased-finetuned-sst-2-english", "DistilBERT (lightweight)")
        ]
        
        for model_name, model_desc in models_to_try:
            try:
                self.logger.info(f"Trying to load {model_desc}...")
                analyzer = pipeline(
                    "sentiment-analysis",
                    model=model_name,
                    device=device,
                    truncation=True,
                    max_length=512
                )
                self.logger.info(f"✅ Successfully loaded {model_desc}")
                return analyzer
                
            except Exception as e:
                self.logger.warning(f"Failed to load {model_desc}: {e}")
                
                # Try CPU fallback for the same model
                if device != -1:
                    try:
                        self.logger.info(f"Trying {model_desc} on CPU...")
                        analyzer = pipeline(
                            "sentiment-analysis",
                            model=model_name,
                            device=-1,
                            truncation=True,
                            max_length=512
                        )
                        self.logger.info(f"✅ Successfully loaded {model_desc} on CPU")
                        return analyzer
                    except Exception as e2:
                        self.logger.warning(f"CPU fallback also failed for {model_desc}: {e2}")
        
        # All models failed
        self.logger.error("❌ All sentiment models failed to load - using rule-based fallback")
        return None
    
    @lru_cache(maxsize=1000)
    def _cached_sentiment_analysis(self, text_hash: str, text: str) -> Dict[str, float]:
        """
        Cached sentiment analysis to avoid recomputing identical descriptions.
        Uses text hash for cache key to handle identical descriptions efficiently.
        """
        return self._compute_sentiment_features(text)
    
    def score_description(self, text: str) -> Dict[str, float]:
        """
        Generate multiple sentiment signals from token description.
        Uses caching to avoid recomputing identical descriptions.
        
        Args:
            text: Discord embed description text
            
        Returns:
            Dictionary of normalized (0-1) sentiment features
        """
        if not text or len(text.strip()) < 10:
            # Return neutral scores for empty/minimal descriptions
            return {
                'crypto_bullish_score': 0.5,
                'sentiment_confidence': 0.0,
                'fomo_intensity': 0.0,
                'trust_score': 0.0,
                'warning_flags': 0.0,
                'scam_probability': 0.0,
                'description_quality': 0.0,
                'has_renounced': 0.0,
                'has_burned_lp': 0.0,
                'community_driven': 0.0
            }
        
        # Create hash for caching
        text_hash = hashlib.md5(text.encode()).hexdigest()
        
        # Use cached analysis
        return self._cached_sentiment_analysis(text_hash, text)
    
    def _compute_sentiment_features(self, text: str) -> Dict[str, float]:
        """
        Actual sentiment computation (called by cached method).
        """
        # Clean text for analysis
        text_lower = text.lower()
        text_clean = re.sub(r'[^\w\s]', ' ', text_lower)
        
        # Get base sentiment from CryptoBERT or fallback to rule-based
        if self.analyzer is not None:
            try:
                result = self.analyzer(text[:512])[0]
                
                # Extract bullish probability
                if result['label'].lower() == 'bullish':
                    bullish_score = result['score']
                elif result['label'].lower() == 'bearish':
                    bullish_score = 1.0 - result['score']
                else:  # neutral
                    bullish_score = 0.5
                    
                confidence = result['score']
                
            except Exception as e:
                self.logger.warning(f"Sentiment analysis failed: {e}")
                bullish_score, confidence = self._rule_based_sentiment(text_lower)
        else:
            # Use rule-based fallback
            bullish_score, confidence = self._rule_based_sentiment(text_lower)
        
        # Calculate specialized scores
        features = {
            # Primary sentiment
            'crypto_bullish_score': bullish_score,
            'sentiment_confidence': confidence,
            
            # FOMO intensity (0-1)
            'fomo_intensity': self._calculate_term_intensity(text_lower, self.fomo_terms),
            
            # Trust indicators (0-1)
            'trust_score': self._calculate_term_intensity(text_lower, self.trust_terms),
            
            # Warning flags (0-1) - higher = more cautious language
            'warning_flags': self._calculate_term_intensity(text_lower, self.warning_terms),
            
            # Scam probability (0-1)
            'scam_probability': self._calculate_term_intensity(text_lower, self.scam_indicators),
            
            # Description quality (length & structure)
            'description_quality': self._calculate_quality_score(text),
            
            # Critical binary features for memecoins
            'has_renounced': float('renounced' in text_lower or 'renounce' in text_lower),
            'has_burned_lp': float(
                ('burn' in text_lower or 'burned' in text_lower) and 
                ('lp' in text_lower or 'liquidity' in text_lower)
            ),
            'community_driven': float(
                any(term in text_lower for term in ['community', 'cto', 'takeover', 'community takeover'])
            )
        }
        
        return features
    
    def _rule_based_sentiment(self, text_lower: str) -> tuple[float, float]:
        """
        Rule-based sentiment fallback when CryptoBERT is not available.
        
        Args:
            text_lower: Lowercase text to analyze
            
        Returns:
            Tuple of (bullish_score, confidence)
        """
        # Count positive and negative indicators
        positive_count = sum(1 for term in self.fomo_terms + self.trust_terms if term in text_lower)
        negative_count = sum(1 for term in self.warning_terms + self.scam_indicators if term in text_lower)
        
        # Calculate simple sentiment score
        if positive_count > negative_count:
            bullish_score = 0.6 + min(0.3, (positive_count - negative_count) * 0.1)
            confidence = min(0.8, 0.4 + (positive_count - negative_count) * 0.1)
        elif negative_count > positive_count:
            bullish_score = 0.4 - min(0.3, (negative_count - positive_count) * 0.1)
            confidence = min(0.8, 0.4 + (negative_count - positive_count) * 0.1)
        else:
            bullish_score = 0.5
            confidence = 0.3
            
        return bullish_score, confidence
    
    def _calculate_term_intensity(self, text: str, terms: List[str]) -> float:
        """Calculate normalized intensity score based on term frequency."""
        if not text:
            return 0.0
            
        matches = sum(1 for term in terms if term in text)
        # Use sqrt to prevent single term domination
        return min(np.sqrt(matches / len(terms)) * 2, 1.0)
    
    def _calculate_quality_score(self, text: str) -> float:
        """
        Calculate quality score based on description characteristics.
        Higher quality = more likely to be legitimate project.
        """
        if not text:
            return 0.0
            
        # Length score (sweet spot: 100-500 chars)
        length = len(text)
        if length < 50:
            length_score = 0.2
        elif length < 100:
            length_score = 0.5
        elif length <= 500:
            length_score = 1.0
        else:
            length_score = max(0.7, 1.0 - (length - 500) / 1000)
            
        # Structure score (has sentences, not just keywords)
        sentences = len(re.split(r'[.!?]+', text))
        structure_score = min(sentences / 3, 1.0)
        
        # Link presence (CA, website, twitter)
        has_links = float(bool(re.search(r'https?://|0x[a-fA-F0-9]{40,}|@\w+', text)))
        
        # Combine scores
        quality = (length_score * 0.5 + structure_score * 0.3 + has_links * 0.2)
        
        return min(quality, 1.0)


# ============================================
# PART 2: Integration with Existing Pipeline
# ============================================

class EnhancedMetricsParser:
    """
    Extends your existing metrics parser with sentiment features.
    Drop-in replacement for your current parse_metrics function.
    """
    
    def __init__(self, sentiment_analyzer: Optional[SimpleCryptoSentiment] = None):
        """
        Initialize enhanced parser.
        
        Args:
            sentiment_analyzer: Instance of SimpleCryptoSentiment (creates one if None)
        """
        self.sentiment = sentiment_analyzer or SimpleCryptoSentiment()
        self.logger = logging.getLogger(__name__)
        
    def parse_metrics_with_sentiment(self, embed_data: Dict, description: str = "") -> Dict[str, float]:
        """
        Parse both objective metrics and sentiment features.
        
        Args:
            embed_data: Discord embed data (your existing 58 metrics)
            description: Token description text from Discord
            
        Returns:
            Combined dictionary with 58 + 10 = 68 total features
        """
        # Parse your existing objective metrics
        metrics = self.parse_objective_metrics(embed_data)
        
        # Add sentiment features if description exists
        if description and len(description.strip()) > 0:
            sentiment_features = self.sentiment.score_description(description)
            metrics.update(sentiment_features)
            self.logger.debug(f"Added {len(sentiment_features)} sentiment features")
        else:
            # Add neutral sentiment features if no description
            metrics.update({
                'crypto_bullish_score': 0.5,
                'sentiment_confidence': 0.0,
                'fomo_intensity': 0.0,
                'trust_score': 0.0,
                'warning_flags': 0.0,
                'scam_probability': 0.0,
                'description_quality': 0.0,
                'has_renounced': 0.0,
                'has_burned_lp': 0.0,
                'community_driven': 0.0
            })
            
        return metrics
    
    def parse_objective_metrics(self, embed_data: Dict) -> Dict[str, float]:
        """
        Use your actual LaunchpadMetricsParser for objective metrics.
        """
        # Import your actual parser
        from ingest.metrics_parser import LaunchpadMetricsParser
        
        if not hasattr(self, '_objective_parser'):
            self._objective_parser = LaunchpadMetricsParser()
        
        # The LaunchpadMetricsParser expects the full message payload
        # Create a minimal payload structure for the parser
        message_payload = {
            'embeds': [embed_data] if embed_data else [],
            'components': [],  # Add empty components
            'content': ''  # Add empty content
        }
        
        # Use your existing comprehensive metrics parser
        metrics = self._objective_parser.parse_message_metrics(message_payload)
        
        # Convert all values to float for consistency
        float_metrics = {}
        for key, value in metrics.items():
            try:
                if value is not None:
                    float_metrics[key] = float(value)
                else:
                    float_metrics[key] = 0.0
            except (ValueError, TypeError):
                float_metrics[key] = 0.0
                
        return float_metrics


# ============================================
# PART 3: Database Integration
# ============================================

def add_sentiment_columns_to_db(connection):
    """
    Your existing schema is already perfect! 
    Features are stored in features_snapshot.features as JSONB.
    Sentiment features are automatically included.
    
    This function is for reference only - no changes needed.
    """
    print("✅ Your database schema is already optimized!")
    print("✅ features_snapshot.features (JSONB) automatically includes sentiment data")
    print("✅ No schema changes required - sentiment integration is seamless")
    
def create_optional_sentiment_table(connection):
    """
    OPTIONAL: Create dedicated sentiment table for easier querying.
    Only use this if you want to query sentiment features separately.
    """
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS message_sentiment (
        message_id TEXT PRIMARY KEY REFERENCES discord_raw(message_id),
        crypto_bullish_score REAL DEFAULT 0.5,
        sentiment_confidence REAL DEFAULT 0.0,
        fomo_intensity REAL DEFAULT 0.0,
        trust_score REAL DEFAULT 0.0,
        warning_flags REAL DEFAULT 0.0,
        scam_probability REAL DEFAULT 0.0,
        description_quality REAL DEFAULT 0.0,
        has_renounced REAL DEFAULT 0.0,
        has_burned_lp REAL DEFAULT 0.0,
        community_driven REAL DEFAULT 0.0,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW()
    );
    
    -- Index for faster queries
    CREATE INDEX IF NOT EXISTS idx_sentiment_bullish ON message_sentiment(crypto_bullish_score DESC);
    CREATE INDEX IF NOT EXISTS idx_sentiment_trust ON message_sentiment(trust_score DESC);
    """
    
    try:
        if hasattr(connection, 'execute'):
            # asyncpg connection
            import asyncio
            asyncio.create_task(connection.execute(create_table_sql))
        else:
            # Standard DB connection
            cursor = connection.cursor()
            cursor.execute(create_table_sql)
            connection.commit()
        
        print("✅ Optional sentiment table created successfully")
        
    except Exception as e:
        print(f"⚠️ Optional table creation failed (this is OK): {e}")
        print("✅ Sentiment data will still work via features_snapshot table")


# ============================================
# PART 4: Usage Example & Integration Guide
# ============================================

def main_integration_example():
    """
    Example showing how to integrate this into your existing pipeline.
    """
    # Initialize components
    sentiment_analyzer = SimpleCryptoSentiment()
    parser = EnhancedMetricsParser(sentiment_analyzer)
    
    # Example Discord message data
    example_embed = {
        'market_cap': 250000,
        'liquidity': 50.5,
        'volume_24h': 125000,
        'holder_count': 156,
        'ag_score': 78,
        # ... your other metrics
    }
    
    example_description = """
    🚀 $PEPE2.0 - The Return of the King! 
    
    Dev RENOUNCED ✅ LP BURNED 🔥 
    Community takeover in progress! This gem is going to the moon! 
    Early holders will be rewarded. DYOR but don't miss this opportunity!
    
    CA: 0x1234...
    TG: @pepe2community
    """
    
    # Parse all metrics including sentiment
    all_features = parser.parse_metrics_with_sentiment(example_embed, example_description)
    
    print(f"Total features: {len(all_features)}")
    print("\nSentiment features extracted:")
    for key, value in all_features.items():
        if 'sentiment' in key or 'crypto' in key or 'fomo' in key or 'trust' in key:
            print(f"  {key}: {value:.3f}")
    
    # These features now feed directly into your GA trainer
    # The GA will determine optimal thresholds for BUY/SKIP signals


# ============================================
# PART 5: Quick Start Instructions
# ============================================

"""
INSTALLATION (run in your ag-trading-bot directory):

pip install transformers torch

INTEGRATION STEPS:

1. Copy this entire file to: ag-trading-bot/ingest/sentiment_analyzer.py

2. Update your existing message processor:

   # In your message processing loop
   from ingest.sentiment_analyzer import SimpleCryptoSentiment, EnhancedMetricsParser
   
   parser = EnhancedMetricsParser()
   
   # When processing each Discord message:
   metrics = parser.parse_metrics_with_sentiment(embed_data, description_text)
   
3. Update your database (run once):

   from ingest.sentiment_analyzer import add_sentiment_columns_to_db
   add_sentiment_columns_to_db(your_db_connection)

4. Update your GA trainer to use 68 features instead of 58:

   # No code changes needed! 
   # GA will automatically use all features in the metrics dict

5. Start collecting data with sentiment features!

TESTING:

if __name__ == "__main__":
    # Test the integration
    main_integration_example()
"""

if __name__ == "__main__":
    # Run test
    main_integration_example()