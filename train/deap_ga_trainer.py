"""
DEAP Genetic Algorithm Trainer
Multi-objective optimization for trading strategy evolution
"""

import logging
import json
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple, Optional
import numpy as np
from deap import base, creator, tools, algorithms
import asyncpg
import random

from config import settings

logger = logging.getLogger(__name__)

# Define fitness and individual classes (must be at module level for DEAP)
if not hasattr(creator, "FitnessMulti"):
    creator.create("FitnessMulti", base.Fitness, weights=(1.0, 1.0, -1.0))  # win_rate, sharpe, -drawdown
if not hasattr(creator, "Individual"):
    creator.create("Individual", list, fitness=creator.FitnessMulti)


class DEAPGeneticAlgorithm:
    """
    DEAP-based genetic algorithm for strategy optimization.
    Uses mu+lambda evolution with multi-objective fitness.
    """
    
    def __init__(self, db_pool: asyncpg.Pool, cluster_id: int = 0):
        """
        Initialize DEAP GA trainer.
        
        Args:
            db_pool: Database connection pool
            cluster_id: Strategy cluster ID
        """
        self.db_pool = db_pool
        self.cluster_id = cluster_id
        
        # GA parameters
        self.population_size = 100
        self.generations = 50
        self.mutation_rate = 0.3
        self.crossover_rate = 0.7
        
        # Parameter bounds for strategy genome
        self.BOUNDS = [
            (0.01, 1.0),    # liquidity_threshold
            (0.1, 0.9),     # sentiment_threshold  
            (0.0, 100.0),   # volume_threshold
            (1, 50),        # smart_wallet_min
            (0.5, 0.95),    # confidence_threshold
            (0.0, 1.0),     # honeypot_weight
            (0.0, 1.0),     # liquidity_weight
            (0.0, 1.0),     # sentiment_weight
            (0.0, 1.0),     # smart_wallet_weight
            (0.0, 1.0),     # holder_weight
        ]
        
        # Setup DEAP toolbox
        self.toolbox = base.Toolbox()
        self.setup_ga()
        
        # Training data cache
        self.training_data = None
        
        logger.info(f"✅ DEAP GA initialized for cluster {cluster_id}")
    
    def setup_ga(self):
        """Setup DEAP genetic operators."""
        # Gene creation
        self.toolbox.register("gene", self.random_gene)
        
        # Individual creation
        self.toolbox.register("individual", tools.initIterate, 
                            creator.Individual, 
                            lambda: [self.random_gene(b) for b in self.BOUNDS])
        
        # Population creation
        self.toolbox.register("population", tools.initRepeat, 
                            list, self.toolbox.individual)
        
        # Genetic operators
        self.toolbox.register("mate", self.custom_crossover)
        self.toolbox.register("mutate", self.custom_mutation)
        self.toolbox.register("select", tools.selNSGA2)  # Multi-objective selection
        self.toolbox.register("evaluate", self.evaluate_strategy)
    
    def random_gene(self, bounds: Tuple) -> float:
        """Generate random gene value within bounds."""
        min_val, max_val = bounds
        if isinstance(min_val, int) and isinstance(max_val, int):
            return random.randint(min_val, max_val)
        else:
            return random.uniform(min_val, max_val)
    
    def custom_crossover(self, ind1: List, ind2: List) -> Tuple[List, List]:
        """Custom crossover respecting parameter bounds."""
        if random.random() < self.crossover_rate:
            # Uniform crossover
            for i in range(len(ind1)):
                if random.random() < 0.5:
                    ind1[i], ind2[i] = ind2[i], ind1[i]
            
            # Ensure bounds are respected
            self.enforce_bounds(ind1)
            self.enforce_bounds(ind2)
            
            # Invalidate fitness
            del ind1.fitness.values
            del ind2.fitness.values
        
        return ind1, ind2
    
    def custom_mutation(self, individual: List) -> Tuple[List]:
        """Custom mutation respecting parameter bounds."""
        for i in range(len(individual)):
            if random.random() < self.mutation_rate:
                min_val, max_val = self.BOUNDS[i]
                
                # Gaussian mutation
                if isinstance(min_val, int):
                    # Integer parameter
                    delta = random.randint(-5, 5)
                    individual[i] = max(min_val, min(max_val, individual[i] + delta))
                else:
                    # Float parameter
                    sigma = (max_val - min_val) * 0.1
                    individual[i] += random.gauss(0, sigma)
                    individual[i] = max(min_val, min(max_val, individual[i]))
        
        # Invalidate fitness
        del individual.fitness.values
        
        return individual,
    
    def enforce_bounds(self, individual: List):
        """Ensure all genes are within bounds."""
        for i in range(len(individual)):
            min_val, max_val = self.BOUNDS[i]
            individual[i] = max(min_val, min(max_val, individual[i]))
    
    async def load_training_data(self) -> List[Dict[str, Any]]:
        """Load training data from database."""
        if self.training_data is not None:
            return self.training_data
        
        query = """
            SELECT 
                fs.message_id,
                fs.features,
                o.win,
                o.entry_price_usd,
                o.max_24h_price_usd,
                o.sustained_10x
            FROM features_snapshot fs
            JOIN acceptance_status a ON fs.message_id = a.message_id
            JOIN outcomes_24h o ON fs.message_id = o.message_id
            WHERE a.status = 'ACCEPT'
              AND o.win IS NOT NULL
              AND fs.snapped_at >= NOW() - INTERVAL '30 days'
            ORDER BY fs.snapped_at
        """
        
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query)
        
        self.training_data = [dict(row) for row in rows]
        logger.info(f"📊 Loaded {len(self.training_data)} training samples")
        
        return self.training_data
    
    def evaluate_strategy(self, individual: List) -> Tuple[float, float, float]:
        """
        Evaluate strategy fitness (multi-objective).
        
        Args:
            individual: Strategy parameters
            
        Returns:
            Tuple of (win_rate, sharpe_ratio, -max_drawdown)
        """
        if not self.training_data:
            return (0.0, 0.0, 0.0)
        
        # Extract parameters
        params = self.decode_individual(individual)
        
        # Simulate trading with these parameters
        trades = []
        returns = []
        
        for sample in self.training_data:
            signal = self.generate_signal(sample['features'], params)
            
            if signal == 'BUY':
                # Calculate return
                entry = sample['entry_price_usd']
                exit = sample['max_24h_price_usd']
                
                if entry > 0:
                    ret = (exit - entry) / entry
                    trades.append({
                        'return': ret,
                        'win': sample['win']
                    })
                    returns.append(ret)
        
        if not trades:
            return (0.0, 0.0, -1.0)  # No trades = worst fitness
        
        # Calculate fitness metrics
        wins = sum(1 for t in trades if t['win'])
        win_rate = wins / len(trades)
        
        # Sharpe ratio (simplified)
        if returns:
            avg_return = np.mean(returns)
            std_return = np.std(returns) if len(returns) > 1 else 1.0
            sharpe = avg_return / std_return if std_return > 0 else 0.0
        else:
            sharpe = 0.0
        
        # Max drawdown
        cumulative = np.cumsum(returns)
        running_max = np.maximum.accumulate(cumulative)
        drawdown = cumulative - running_max
        max_drawdown = np.min(drawdown) if len(drawdown) > 0 else 0.0
        
        return (win_rate, sharpe, -max_drawdown)
    
    def decode_individual(self, individual: List) -> Dict[str, Any]:
        """Decode individual to strategy parameters."""
        return {
            'liquidity_threshold': individual[0],
            'sentiment_threshold': individual[1],
            'volume_threshold': individual[2],
            'smart_wallet_min': int(individual[3]),
            'confidence_threshold': individual[4],
            'honeypot_weight': individual[5],
            'liquidity_weight': individual[6],
            'sentiment_weight': individual[7],
            'smart_wallet_weight': individual[8],
            'holder_weight': individual[9],
        }
    
    def generate_signal(self, features: Dict[str, Any], params: Dict[str, Any]) -> str:
        """
        Generate trading signal based on features and parameters.
        
        Args:
            features: Token features
            params: Strategy parameters
            
        Returns:
            'BUY' or 'SKIP'
        """
        score = 0.0
        weights_sum = 0.0
        
        # Check thresholds
        liquidity = features.get('liquidity_usd', 0)
        if liquidity < params['liquidity_threshold'] * 100000:  # Scale threshold
            return 'SKIP'
        
        # Calculate weighted score
        components = {
            'honeypot': 1.0 if not features.get('honeypot_detected', False) else 0.0,
            'liquidity': min(1.0, liquidity / 100000),
            'sentiment': features.get('sentiment_score', 0.5),
            'smart_wallet': min(1.0, features.get('smart_wallet_count', 0) / params['smart_wallet_min']),
            'holder': 1.0 - features.get('top10_holders_pct', 100) / 100
        }
        
        for key, value in components.items():
            weight = params.get(f'{key}_weight', 1.0)
            score += value * weight
            weights_sum += weight
        
        # Normalize score
        if weights_sum > 0:
            score /= weights_sum
        
        # Apply confidence threshold
        return 'BUY' if score >= params['confidence_threshold'] else 'SKIP'
    
    async def evolve(self) -> Dict[str, Any]:
        """
        Run evolution to find optimal strategy.
        
        Returns:
            Best strategy and evolution statistics
        """
        # Load training data
        await self.load_training_data()
        
        if len(self.training_data) < 20:
            logger.warning(f"Insufficient training data: {len(self.training_data)}")
            return None
        
        logger.info(f"🧬 Starting evolution: {self.population_size} pop, {self.generations} gen")
        
        # Create initial population
        population = self.toolbox.population(n=self.population_size)
        
        # Statistics
        stats = tools.Statistics(lambda ind: ind.fitness.values)
        stats.register("avg", np.mean, axis=0)
        stats.register("std", np.std, axis=0)
        stats.register("min", np.min, axis=0)
        stats.register("max", np.max, axis=0)
        
        # Hall of fame (best individuals)
        hof = tools.ParetoFront()
        
        # Run evolution with mu+lambda
        population, logbook = algorithms.eaMuPlusLambda(
            population, self.toolbox,
            mu=self.population_size,
            lambda_=self.population_size * 2,
            cxpb=self.crossover_rate,
            mutpb=self.mutation_rate,
            ngen=self.generations,
            stats=stats,
            halloffame=hof,
            verbose=True
        )
        
        # Get best individual
        best_individual = hof[0] if hof else tools.selBest(population, k=1)[0]
        
        # Decode best strategy
        best_strategy = self.decode_individual(best_individual)
        best_fitness = best_individual.fitness.values
        
        logger.info(f"🏆 Best strategy found:")
        logger.info(f"  Win Rate: {best_fitness[0]:.2%}")
        logger.info(f"  Sharpe: {best_fitness[1]:.3f}")
        logger.info(f"  Max Drawdown: {-best_fitness[2]:.2%}")
        
        # Save to database
        await self.save_strategy(best_individual, best_strategy, best_fitness, logbook)
        
        return {
            'strategy': best_strategy,
            'fitness': {
                'win_rate': best_fitness[0],
                'sharpe_ratio': best_fitness[1],
                'max_drawdown': -best_fitness[2]
            },
            'evolution_history': logbook,
            'population_final': len(population),
            'generations_completed': self.generations
        }
    
    async def save_strategy(self, individual: List, strategy: Dict, fitness: Tuple, logbook: Any):
        """Save evolved strategy to database."""
        strategy_id = str(uuid.uuid4())
        
        metrics = {
            'win_rate': fitness[0],
            'sharpe_ratio': fitness[1],
            'max_drawdown': -fitness[2],
            'training_samples': len(self.training_data),
            'generations': self.generations,
            'population_size': self.population_size,
            'evolved_at': datetime.now(timezone.utc).isoformat()
        }
        
        # Extract evolution history
        history = []
        for record in logbook:
            gen_stats = {
                'generation': record['gen'],
                'evaluations': record['nevals'],
                'avg_fitness': record['avg'].tolist() if hasattr(record['avg'], 'tolist') else record['avg'],
                'max_fitness': record['max'].tolist() if hasattr(record['max'], 'tolist') else record['max'],
            }
            history.append(gen_stats)
        
        async with self.db_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO strategy_params (
                    id, cluster_id, created_at, thresholds, weights, metrics, active, algo_version
                ) VALUES ($1, $2, NOW(), $3, $4, $5, $6, $7)
            """,
                strategy_id,
                self.cluster_id,
                json.dumps({
                    'liquidity_threshold': strategy['liquidity_threshold'],
                    'sentiment_threshold': strategy['sentiment_threshold'],
                    'volume_threshold': strategy['volume_threshold'],
                    'smart_wallet_min': strategy['smart_wallet_min'],
                    'confidence_threshold': strategy['confidence_threshold']
                }),
                json.dumps({
                    'honeypot_weight': strategy['honeypot_weight'],
                    'liquidity_weight': strategy['liquidity_weight'],
                    'sentiment_weight': strategy['sentiment_weight'],
                    'smart_wallet_weight': strategy['smart_wallet_weight'],
                    'holder_weight': strategy['holder_weight']
                }),
                json.dumps({**metrics, 'evolution_history': history}),
                False,  # Not active yet (needs testing)
                2  # Version 2 with DEAP
            )
        
        logger.info(f"💾 Saved strategy {strategy_id} to database")


# Singleton instance management
_trainer_instances = {}


async def get_trainer(db_pool: asyncpg.Pool, cluster_id: int = 0) -> DEAPGeneticAlgorithm:
    """
    Get or create trainer instance for cluster.
    
    Args:
        db_pool: Database connection pool
        cluster_id: Cluster ID
        
    Returns:
        DEAPGeneticAlgorithm instance
    """
    if cluster_id not in _trainer_instances:
        _trainer_instances[cluster_id] = DEAPGeneticAlgorithm(db_pool, cluster_id)
    return _trainer_instances[cluster_id]


# Example usage
if __name__ == "__main__":
    import asyncio
    
    async def test():
        # Create mock DB pool
        db_pool = await asyncpg.create_pool(settings.DATABASE_URL)
        
        try:
            # Get trainer
            trainer = await get_trainer(db_pool, cluster_id=0)
            
            # Run evolution
            result = await trainer.evolve()
            
            if result:
                print(f"\n🎯 Evolution complete!")
                print(f"Best strategy: {result['strategy']}")
                print(f"Fitness: {result['fitness']}")
            else:
                print("Evolution failed - insufficient data")
                
        finally:
            await db_pool.close()
    
    asyncio.run(test())