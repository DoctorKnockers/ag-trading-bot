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
            try:
                self.analyzer = pipeline(
                    "sentiment-analysis",
                    model=model_name,
                    device=device,
                    truncation=True,
                    max_length=512
                )
                self.logger.info("CryptoBERT initialized successfully")
            except Exception as e:
                self.logger.error(f"Failed to load model: {e}")
                try:
                    # Fallback to CPU if GPU fails
                    self.analyzer = pipeline(
                        "sentiment-analysis",
                        model=model_name,
                        device=-1,
                        truncation=True,
                        max_length=512
                    )
                    self.logger.info("CryptoBERT initialized on CPU fallback")
                except Exception as e2:
                    self.logger.error(f"All model loading failed: {e2}")
                    self.analyzer = None
            
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
    
    def score_description(self, text: str) -> Dict[str, float]:
        """
        Generate multiple sentiment signals from token description.
        
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
        
        # Use your existing comprehensive metrics parser
        return self._objective_parser.parse_message_metrics(embed_data)


# ============================================
# PART 3: Database Integration
# ============================================

def add_sentiment_columns_to_db(connection):
    """
    Add sentiment columns to your existing database schema.
    Run this once to update your database.
    
    Note: Your schema uses JSONB in features_snapshot table, so no schema changes needed!
    The sentiment features will be automatically included in the features JSONB column.
    This function is provided for compatibility but is not required for your setup.
    """
    print("✅ No database schema changes needed!")
    print("Your features_snapshot table uses JSONB which automatically handles sentiment features.")
    print("The EnhancedMetricsParser will include sentiment data in the features JSON.")


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