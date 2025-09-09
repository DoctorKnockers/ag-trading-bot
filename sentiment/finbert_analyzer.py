"""
FinBERT-BiLSTM Sentiment Analysis
Specialized sentiment analysis for crypto token descriptions using FinTwitBERT
"""

import logging
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from typing import Dict, List, Optional, Tuple
import numpy as np
import asyncio
import aiohttp
from datetime import datetime

logger = logging.getLogger(__name__)


class FinBERTAnalyzer:
    """
    FinBERT-based sentiment analyzer for crypto token descriptions.
    Uses StephanAkkerman/FinTwitBERT-sentiment for domain-specific analysis.
    """
    
    def __init__(self, model_name: str = "StephanAkkerman/FinTwitBERT-sentiment"):
        """
        Initialize FinBERT analyzer.
        
        Args:
            model_name: HuggingFace model name for FinBERT sentiment
        """
        self.model_name = model_name
        self.tokenizer = None
        self.model = None
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        
        # Sentiment labels mapping
        self.label_mapping = {
            0: "bearish",
            1: "neutral", 
            2: "bullish"
        }
        
        logger.info(f"🧠 FinBERT analyzer initialized with model: {model_name}")
        logger.info(f"📱 Using device: {self.device}")
    
    async def load_model(self):
        """Load FinBERT model and tokenizer."""
        if self.model is not None:
            return
        
        logger.info(f"📥 Loading FinBERT model: {self.model_name}")
        
        try:
            # Load tokenizer and model
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self.model = AutoModelForSequenceClassification.from_pretrained(self.model_name)
            self.model.to(self.device)
            self.model.eval()
            
            logger.info("✅ FinBERT model loaded successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to load FinBERT model: {e}")
            raise
    
    def preprocess_text(self, text: str) -> str:
        """
        Preprocess text for sentiment analysis.
        
        Args:
            text: Raw text to analyze
            
        Returns:
            Cleaned text
        """
        if not text:
            return ""
        
        # Basic cleaning
        text = text.strip()
        
        # Remove excessive whitespace
        text = ' '.join(text.split())
        
        # Truncate if too long (BERT has 512 token limit)
        if len(text) > 500:
            text = text[:500]
        
        return text
    
    def analyze_sentiment(self, text: str) -> Dict[str, float]:
        """
        Analyze sentiment of a single text.
        
        Args:
            text: Text to analyze
            
        Returns:
            Dict with sentiment scores and prediction
        """
        if not text or not text.strip():
            return {
                'sentiment': 'neutral',
                'confidence': 0.0,
                'scores': {'bearish': 0.33, 'neutral': 0.34, 'bullish': 0.33}
            }
        
        # Preprocess text
        clean_text = self.preprocess_text(text)
        
        # Tokenize
        inputs = self.tokenizer(
            clean_text,
            return_tensors="pt",
            truncation=True,
            padding=True,
            max_length=512
        )
        
        # Move to device
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        
        # Get predictions
        with torch.no_grad():
            outputs = self.model(**inputs)
            predictions = torch.nn.functional.softmax(outputs.logits, dim=-1)
        
        # Convert to numpy
        scores = predictions.cpu().numpy()[0]
        
        # Get predicted class
        predicted_class = np.argmax(scores)
        sentiment = self.label_mapping[predicted_class]
        confidence = float(scores[predicted_class])
        
        return {
            'sentiment': sentiment,
            'confidence': confidence,
            'scores': {
                'bearish': float(scores[0]),
                'neutral': float(scores[1]),
                'bullish': float(scores[2])
            }
        }
    
    def analyze_batch(self, texts: List[str], batch_size: int = 8) -> List[Dict[str, float]]:
        """
        Analyze sentiment for multiple texts in batches.
        
        Args:
            texts: List of texts to analyze
            batch_size: Batch size for processing
            
        Returns:
            List of sentiment analysis results
        """
        results = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            batch_results = []
            
            for text in batch:
                result = self.analyze_sentiment(text)
                batch_results.append(result)
            
            results.extend(batch_results)
            
            # Log progress
            if len(texts) > batch_size:
                logger.debug(f"📊 Processed {min(i + batch_size, len(texts))}/{len(texts)} texts")
        
        return results
    
    def extract_sentiment_features(self, text: str) -> Dict[str, float]:
        """
        Extract sentiment features for use in trading signals.
        
        Args:
            text: Text to analyze (token description)
            
        Returns:
            Dict with sentiment features
        """
        result = self.analyze_sentiment(text)
        
        # Calculate sentiment score (-1 to 1)
        bullish_score = result['scores']['bullish']
        bearish_score = result['scores']['bearish']
        sentiment_score = bullish_score - bearish_score  # Range: -1 to 1
        
        # Normalize to 0-1 for consistency with other features
        sentiment_normalized = (sentiment_score + 1) / 2
        
        return {
            'sentiment_score': sentiment_normalized,
            'sentiment_confidence': result['confidence'],
            'sentiment_label': result['sentiment'],
            'bullish_probability': bullish_score,
            'bearish_probability': bearish_score,
            'neutral_probability': result['scores']['neutral']
        }
    
    async def analyze_token_description(self, description: str) -> Dict[str, float]:
        """
        Analyze sentiment of token description asynchronously.
        
        Args:
            description: Token description text
            
        Returns:
            Sentiment features dict
        """
        # Ensure model is loaded
        await self.load_model()
        
        # Run analysis in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, 
            self.extract_sentiment_features, 
            description
        )
        
        return result


# Singleton instance
_analyzer = None


async def get_analyzer() -> FinBERTAnalyzer:
    """
    Get or create FinBERT analyzer instance.
    
    Returns:
        FinBERTAnalyzer instance
    """
    global _analyzer
    
    if _analyzer is None:
        _analyzer = FinBERTAnalyzer()
        await _analyzer.load_model()
    
    return _analyzer


# Example usage
if __name__ == "__main__":
    async def test():
        analyzer = await get_analyzer()
        
        # Test descriptions
        test_texts = [
            "Revolutionary DeFi protocol with massive potential for 100x gains!",
            "Another worthless meme coin that will dump to zero",
            "Solid fundamentals and experienced team behind this project",
            "Rug pull incoming, avoid at all costs",
            "Neutral description of a standard ERC-20 token"
        ]
        
        print("\n🧠 FinBERT Sentiment Analysis Test")
        print("=" * 50)
        
        for text in test_texts:
            result = await analyzer.analyze_token_description(text)
            
            print(f"\nText: {text[:60]}...")
            print(f"Sentiment: {result['sentiment_label']} ({result['sentiment_confidence']:.2f})")
            print(f"Score: {result['sentiment_score']:.3f}")
            print(f"Bullish: {result['bullish_probability']:.3f}")
            print(f"Bearish: {result['bearish_probability']:.3f}")
    
    asyncio.run(test())
