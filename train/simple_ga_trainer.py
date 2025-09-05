#!/usr/bin/env python3
"""
Simple GA trainer that works around macOS signal/multiprocessing issues.
Implements basic genetic algorithm for strategy optimization.
"""

import json
import random
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import List, Dict, Any, Tuple
from datetime import datetime, timezone
import uuid
from dotenv import load_dotenv

from config import settings

load_dotenv()


class SimpleGATrainer:
    """Simple genetic algorithm trainer for strategy optimization."""
    
    def __init__(self, cluster_id: int):
        self.cluster_id = cluster_id
        self.population_size = 50  # Smaller for simple implementation
        self.generations = 20
        self.mutation_rate = 0.1
        self.crossover_rate = 0.7
        
        # Strategy parameters (simplified)
        self.param_ranges = {
            "min_market_cap": (1000, 100000),
            "min_liquidity": (500, 50000), 
            "min_ag_score": (1, 10),
            "max_bundled_pct": (1, 50),
            "min_holders": (5, 100),
            "min_win_prediction": (1, 30),
            "buy_threshold": (0.5, 0.95)
        }
    
    def create_individual(self) -> List[float]:
        """Create random individual (strategy)."""
        individual = []
        for param, (min_val, max_val) in self.param_ranges.items():
            value = random.uniform(min_val, max_val)
            individual.append(value)
        
        return individual
    
    def decode_individual(self, individual: List[float]) -> Dict[str, float]:
        """Decode individual to strategy parameters."""
        params = {}
        for i, (param_name, _) in enumerate(self.param_ranges.items()):
            params[param_name] = individual[i]
        
        return params
    
    def evaluate_fitness(self, individual: List[float], training_data: List[Dict]) -> Tuple[float, float, float]:
        """
        Evaluate strategy fitness.
        
        Returns:
            Tuple of (buy_precision, buy_rate, total_picks)
        """
        if not training_data:
            return (0.0, 0.0, 0.0)
        
        strategy = self.decode_individual(individual)
        
        # Score each sample
        scores = []
        for sample in training_data:
            features = sample['features']
            win = sample['win']
            
            score = self._score_sample(features, strategy)
            scores.append({"score": score, "win": win})
        
        # Sort by score (highest first)
        scores.sort(key=lambda x: x["score"], reverse=True)
        
        # Apply buy threshold
        buy_threshold = strategy["buy_threshold"]
        
        if not scores or scores[0]["score"] <= 0:
            return (0.0, 0.0, 0.0)
        
        # Determine buy cutoff
        max_score = scores[0]["score"]
        cutoff_score = max_score * buy_threshold
        
        # Calculate metrics
        buys = [s for s in scores if s["score"] >= cutoff_score]
        
        if not buys:
            return (0.0, 0.0, 0.0)
        
        buy_wins = sum(1 for s in buys if s["win"])
        buy_precision = buy_wins / len(buys)
        buy_rate = len(buys) / len(scores)
        total_picks = len(buys)
        
        return (buy_precision, buy_rate, total_picks)
    
    def _score_sample(self, features: Dict[str, Any], strategy: Dict[str, float]) -> float:
        """Score a sample using strategy parameters."""
        # Apply thresholds
        market_cap = features.get("market_cap_usd", 0)
        liquidity = features.get("liquidity_usd", 0)
        ag_score = features.get("ag_score", 0)
        bundled_pct = features.get("bundled_pct", 100)
        holders = features.get("holders_count", 0)
        win_pred = features.get("win_prediction_pct", 0)
        
        # Threshold checks
        if market_cap < strategy["min_market_cap"]:
            return -1.0
        if liquidity < strategy["min_liquidity"]:
            return -1.0
        if ag_score < strategy["min_ag_score"]:
            return -1.0
        if bundled_pct > strategy["max_bundled_pct"]:
            return -1.0
        if holders < strategy["min_holders"]:
            return -1.0
        if win_pred < strategy["min_win_prediction"]:
            return -1.0
        
        # Calculate weighted score
        score = (
            (market_cap / 100000) * 0.2 +
            (liquidity / 50000) * 0.2 +
            (ag_score / 10) * 0.3 +
            (1 - bundled_pct / 100) * 0.1 +
            (holders / 100) * 0.1 +
            (win_pred / 100) * 0.1
        )
        
        return score
    
    def crossover(self, parent1: List[float], parent2: List[float]) -> Tuple[List[float], List[float]]:
        """Simple crossover operation."""
        if random.random() > self.crossover_rate:
            return parent1[:], parent2[:]
        
        # Single-point crossover
        crossover_point = random.randint(1, len(parent1) - 1)
        
        child1 = parent1[:crossover_point] + parent2[crossover_point:]
        child2 = parent2[:crossover_point] + parent1[crossover_point:]
        
        return child1, child2
    
    def mutate(self, individual: List[float]) -> List[float]:
        """Simple mutation operation."""
        mutated = individual[:]
        
        for i in range(len(mutated)):
            if random.random() < self.mutation_rate:
                param_name = list(self.param_ranges.keys())[i]
                min_val, max_val = self.param_ranges[param_name]
                
                # Gaussian mutation
                sigma = (max_val - min_val) * 0.1
                mutated[i] += random.gauss(0, sigma)
                mutated[i] = max(min_val, min(max_val, mutated[i]))
        
        return mutated
    
    def train_strategy(self) -> Dict[str, Any]:
        """Train strategy using simple GA."""
        print(f"🎯 Training strategy for cluster {self.cluster_id}")
        
        # Load training data
        try:
            conn = psycopg2.connect(settings.DATABASE_URL, cursor_factory=RealDictCursor)
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 
                        fs.message_id,
                        fs.features,
                        o.win
                    FROM features_snapshot fs
                    JOIN acceptance_status a ON fs.message_id = a.message_id
                    JOIN outcomes_24h o ON fs.message_id = o.message_id
                    WHERE a.status = 'ACCEPT'
                      AND o.win IS NOT NULL
                """)
                
                training_data = [dict(row) for row in cur.fetchall()]
            conn.close()
            
        except Exception as e:
            return {"error": f"Failed to load training data: {e}"}
        
        if len(training_data) < 20:
            return {"error": f"Insufficient training data: {len(training_data)} samples"}
        
        print(f"📊 Training on {len(training_data)} samples")
        
        # Initialize population
        population = [self.create_individual() for _ in range(self.population_size)]
        
        best_fitness = (0.0, 1.0, 0.0)  # (precision, buy_rate_penalty, picks)
        best_individual = None
        
        # Evolution loop
        for generation in range(self.generations):
            # Evaluate fitness
            fitness_scores = []
            for individual in population:
                precision, buy_rate, picks = self.evaluate_fitness(individual, training_data)
                
                # Fitness combines precision and buy rate penalty
                buy_rate_penalty = abs(buy_rate - 0.1) if buy_rate != 0 else 1.0  # Target 10% buy rate
                
                fitness = precision - buy_rate_penalty * 0.5
                fitness_scores.append((fitness, precision, buy_rate, picks, individual))
            
            # Sort by fitness (highest first)
            fitness_scores.sort(key=lambda x: x[0], reverse=True)
            
            # Track best
            current_best = fitness_scores[0]
            if current_best[1] > best_fitness[0]:  # Better precision
                best_fitness = (current_best[1], current_best[2], current_best[3])
                best_individual = current_best[4][:]
            
            # Selection and reproduction
            # Keep top 50%
            survivors = [fs[4] for fs in fitness_scores[:self.population_size // 2]]
            
            # Create new population
            new_population = survivors[:]
            
            while len(new_population) < self.population_size:
                # Tournament selection
                parent1 = random.choice(survivors)
                parent2 = random.choice(survivors)
                
                # Crossover
                child1, child2 = self.crossover(parent1, parent2)
                
                # Mutation
                child1 = self.mutate(child1)
                child2 = self.mutate(child2)
                
                new_population.extend([child1, child2])
            
            population = new_population[:self.population_size]
            
            if generation % 5 == 0:
                print(f"  Generation {generation}: Best precision = {best_fitness[0]:.3f}")
        
        # Save best strategy
        if best_individual:
            strategy_id = str(uuid.uuid4())
            best_params = self.decode_individual(best_individual)
            
            metrics = {
                "buy_precision": best_fitness[0],
                "buy_rate": best_fitness[1], 
                "picks": best_fitness[2],
                "generations": self.generations,
                "trained_at": datetime.now(timezone.utc).isoformat()
            }
            
            try:
                conn = psycopg2.connect(settings.DATABASE_URL)
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO strategy_params (
                            id, cluster_id, created_at, thresholds, weights, metrics, active, algo_version
                        ) VALUES (%s, %s, NOW(), %s, %s, %s, %s, %s)
                    """, (
                        strategy_id,
                        self.cluster_id,
                        json.dumps(best_params),
                        json.dumps({"feature_weights": [1.0] * len(self.feature_keys)}),
                        json.dumps(metrics),
                        False,  # Not active yet
                        1
                    ))
                    
                    conn.commit()
                conn.close()
                
                print(f"💾 Saved strategy {strategy_id}")
                
            except Exception as e:
                print(f"❌ Failed to save strategy: {e}")
        
        return {
            "cluster_id": self.cluster_id,
            "best_fitness": best_fitness,
            "strategy_id": strategy_id if best_individual else None,
            "training_samples": len(training_data)
        }


def main():
    """Test simple GA training."""
    trainer = SimpleGATrainer(cluster_id=1)  # Train for cluster 1
    result = trainer.train_strategy()
    
    if "error" in result:
        print(f"❌ Training failed: {result['error']}")
    else:
        print(f"🎉 Training complete!")
        print(f"  Best precision: {result['best_fitness'][0]:.3f}")
        print(f"  Buy rate: {result['best_fitness'][1]:.3f}")
        print(f"  Strategy ID: {result['strategy_id']}")


if __name__ == "__main__":
    main()
