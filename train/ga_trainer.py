"""
GA Trainer - Genetic Algorithm optimization for trading strategies.
Source: ga.md - DEAP GA per cluster with temporal blocked CV; worst-fold aggregation; holdout eval.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
import numpy as np
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import precision_score, recall_score
import asyncpg

from config import settings

logger = logging.getLogger(__name__)


class GATrainer:
    """
    Genetic Algorithm trainer for strategy optimization.
    
    Uses DEAP for evolving trading strategies with temporal blocked CV.
    Fitness maximizes BUY precision with buy-rate constraints.
    """
    
    def __init__(self, db_pool: asyncpg.Pool, cluster_id: int):
        self.db_pool = db_pool
        self.cluster_id = cluster_id
        
        # GA parameters
        self.population_size = settings.GA_POPULATION_SIZE
        self.generations = settings.GA_GENERATIONS
        self.crossover_prob = settings.GA_CROSSOVER_PROB
        self.mutation_prob = settings.GA_MUTATION_PROB
        self.cv_folds = settings.CV_FOLDS
        
        # Fitness targets
        self.min_buy_precision = settings.MIN_BUY_PRECISION
        self.target_buy_rate_min = settings.TARGET_BUY_RATE_MIN
        self.target_buy_rate_max = settings.TARGET_BUY_RATE_MAX
        
        # Feature names
        self.feature_names = settings.FEATURE_NAMES
    
    async def load_cluster_training_data(self) -> List[Dict[str, Any]]:
        """Load training data for the specific cluster."""
        # For now, load all accepted data
        # In full implementation, this would filter by cluster assignment
        query = """
            SELECT 
                fs.message_id,
                fs.features,
                fs.snapped_at,
                o.win,
                o.sustained_10x,
                DATE(fs.snapped_at) as date
            FROM features_snapshot fs
            INNER JOIN acceptance_status a ON fs.message_id = a.message_id
            LEFT JOIN outcomes_24h o ON fs.message_id = o.message_id
            WHERE a.status = 'ACCEPT'
              AND o.win IS NOT NULL
              AND fs.snapped_at >= NOW() - INTERVAL '60 days'
            ORDER BY fs.snapped_at
        """
        
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query)
        
        return [dict(row) for row in rows]
    
    def create_individual(self) -> List[float]:
        """Create a random individual (strategy parameters)."""
        # Simplified strategy genome:
        # [threshold_liquidity, threshold_volume, threshold_holders, 
        #  weight_liquidity, weight_volume, weight_holders, buy_cutoff]
        
        individual = [
            np.random.uniform(0.1, 0.9),  # liquidity_threshold
            np.random.uniform(0.1, 0.9),  # volume_threshold  
            np.random.uniform(0.1, 0.9),  # holder_threshold
            np.random.uniform(0.0, 2.0),  # liquidity_weight
            np.random.uniform(0.0, 2.0),  # volume_weight
            np.random.uniform(0.0, 2.0),  # holder_weight
            np.random.uniform(0.5, 0.95)  # buy_cutoff
        ]
        
        return individual
    
    def evaluate_strategy(self, individual: List[float], training_data: List[Dict[str, Any]]) -> Tuple[float, float, float]:
        """
        Evaluate strategy using temporal blocked cross-validation.
        
        Args:
            individual: Strategy parameters
            training_data: Training dataset
            
        Returns:
            Tuple of (buy_precision, buy_rate_penalty, picks_per_day)
        """
        if len(training_data) < 50:
            return (0.0, 1.0, 0.0)  # Not enough data
        
        # Extract parameters
        liq_thresh, vol_thresh, holder_thresh = individual[:3]
        liq_weight, vol_weight, holder_weight = individual[3:6]
        buy_cutoff = individual[6]
        
        # Group by date for temporal CV
        data_by_date = {}
        for sample in training_data:
            date = sample["date"]
            if date not in data_by_date:
                data_by_date[date] = []
            data_by_date[date].append(sample)
        
        dates = sorted(data_by_date.keys())
        
        if len(dates) < self.cv_folds:
            # Not enough dates for CV
            return (0.0, 1.0, 0.0)
        
        # Temporal cross-validation
        tscv = TimeSeriesSplit(n_splits=min(self.cv_folds, len(dates) - 1))
        
        fold_scores = []
        
        # Convert to arrays for sklearn
        date_indices = list(range(len(dates)))
        
        for train_idx, test_idx in tscv.split(date_indices):
            # Get train/test dates
            train_dates = [dates[i] for i in train_idx]
            test_dates = [dates[i] for i in test_idx]
            
            # Gather samples
            test_samples = []
            for date in test_dates:
                test_samples.extend(data_by_date[date])
            
            if len(test_samples) < 10:
                continue
            
            # Score each test sample
            scores = []
            for sample in test_samples:
                score = self._score_sample(sample, individual)
                scores.append({
                    "score": score,
                    "win": sample.get("win", False)
                })
            
            # Apply buy cutoff
            scores.sort(key=lambda x: x["score"], reverse=True)
            
            if not scores or scores[0]["score"] <= 0:
                fold_scores.append((0.0, 0.0, 0.0))
                continue
            
            # Determine buy threshold
            max_score = scores[0]["score"]
            buy_threshold = max_score * buy_cutoff
            
            # Calculate metrics
            buys = [s for s in scores if s["score"] >= buy_threshold]
            
            if len(buys) == 0:
                buy_precision = 0.0
                buy_rate = 0.0
            else:
                buy_wins = sum(1 for s in buys if s["win"])
                buy_precision = buy_wins / len(buys)
                buy_rate = len(buys) / len(scores)
            
            picks_per_day = len(buys) / max(len(test_dates), 1)
            
            fold_scores.append((buy_precision, buy_rate, picks_per_day))
        
        if not fold_scores:
            return (0.0, 1.0, 0.0)
        
        # Aggregate by worst fold (robust evaluation)
        precisions = [s[0] for s in fold_scores]
        buy_rates = [s[1] for s in fold_scores]
        picks_per_days = [s[2] for s in fold_scores]
        
        worst_precision = np.min(precisions)
        median_buy_rate = np.median(buy_rates)
        median_picks = np.median(picks_per_days)
        
        # Calculate buy rate penalty
        if self.target_buy_rate_min <= median_buy_rate <= self.target_buy_rate_max:
            buy_rate_penalty = 0.0
        else:
            if median_buy_rate < self.target_buy_rate_min:
                buy_rate_penalty = self.target_buy_rate_min - median_buy_rate
            else:
                buy_rate_penalty = median_buy_rate - self.target_buy_rate_max
        
        return (worst_precision, buy_rate_penalty, median_picks)
    
    def _score_sample(self, sample: Dict[str, Any], individual: List[float]) -> float:
        """Score a single sample using strategy parameters."""
        features = sample.get("features", {})
        
        # Extract parameters
        liq_thresh, vol_thresh, holder_thresh = individual[:3]
        liq_weight, vol_weight, holder_weight = individual[3:6]
        
        # Apply thresholds
        liq_pct = features.get("liquidity_usd_pct", 0.5)
        vol_pct = features.get("volume_24h_usd_pct", 0.5)
        holder_pct = features.get("holder_count_pct", 0.5)
        
        if liq_pct < liq_thresh or vol_pct < vol_thresh or holder_pct < holder_thresh:
            return -1.0  # Fail thresholds
        
        # Calculate weighted score
        score = (
            liq_weight * liq_pct +
            vol_weight * vol_pct +
            holder_weight * holder_pct
        )
        
        return score
    
    async def save_strategy(self, individual: List[float], metrics: Dict[str, Any]) -> str:
        """Save trained strategy to database."""
        strategy_id = f"ga_{self.cluster_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        
        # Convert individual to strategy parameters
        thresholds = {
            "liquidity_threshold": individual[0],
            "volume_threshold": individual[1], 
            "holder_threshold": individual[2],
            "buy_cutoff": individual[6]
        }
        
        weights = {
            "liquidity_weight": individual[3],
            "volume_weight": individual[4],
            "holder_weight": individual[5]
        }
        
        async with self.db_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO strategy_params (
                    id, cluster_id, thresholds, weights, metrics, active, algo_version
                ) VALUES ($1, $2, $3, $4, $5, false, 1)
            """,
                strategy_id,
                self.cluster_id,
                json.dumps(thresholds),
                json.dumps(weights),
                json.dumps(metrics)
            )
        
        logger.info(f"💾 Saved strategy {strategy_id}")
        return strategy_id


async def main():
    """Example usage and testing."""
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format=settings.LOG_FORMAT
    )
    
    # Create database pool
    pool = await asyncpg.create_pool(settings.DATABASE_URL)
    
    try:
        # Train for cluster 0
        trainer = GATrainer(pool, cluster_id=0)
        
        # Load training data
        training_data = await trainer.load_cluster_training_data()
        
        if len(training_data) >= settings.MIN_TRAINING_SAMPLES:
            print(f"📊 Loaded {len(training_data)} training samples")
            
            # Test strategy evaluation
            test_individual = trainer.create_individual()
            precision, penalty, picks = trainer.evaluate_strategy(test_individual, training_data)
            
            print(f"🧪 Test strategy evaluation:")
            print(f"  Precision: {precision:.3f}")
            print(f"  Buy rate penalty: {penalty:.3f}")
            print(f"  Picks per day: {picks:.1f}")
            
            # Save test strategy
            metrics = {
                "buy_precision": precision,
                "buy_rate_penalty": penalty,
                "picks_per_day": picks,
                "trained_at": datetime.utcnow().isoformat()
            }
            
            strategy_id = await trainer.save_strategy(test_individual, metrics)
            print(f"💾 Saved test strategy: {strategy_id}")
        else:
            print(f"❌ Insufficient training data: {len(training_data)} samples")
    
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
