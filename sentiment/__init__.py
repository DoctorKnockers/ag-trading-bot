"""
Sentiment Analysis Module
CryptoBERT sentiment analysis for crypto token descriptions
"""

from .finbert_analyzer import SimpleCryptoSentiment, EnhancedMetricsParser, add_sentiment_columns_to_db

# Backward compatibility alias
FinBERTAnalyzer = SimpleCryptoSentiment

__all__ = [
    'SimpleCryptoSentiment',
    'EnhancedMetricsParser', 
    'FinBERTAnalyzer',
    'add_sentiment_columns_to_db'
]
