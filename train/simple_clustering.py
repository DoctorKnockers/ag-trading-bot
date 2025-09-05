#!/usr/bin/env python3
"""
Simple clustering implementation that works around macOS signal issues.
Uses basic K-means without sklearn to avoid multiprocessing problems.
"""

import json
import math
import random
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import List, Dict, Any, Tuple
from dotenv import load_dotenv

from config import settings

load_dotenv()


class SimpleKMeans:
    """Simple K-means implementation without multiprocessing."""
    
    def __init__(self, k: int = 3, max_iters: int = 100):
        self.k = k
        self.max_iters = max_iters
        self.centroids = []
        self.labels = []
    
    def fit(self, data: List[List[float]]) -> List[int]:
        """Fit K-means to data."""
        if len(data) < self.k:
            raise ValueError(f"Not enough data points ({len(data)}) for {self.k} clusters")
        
        n_features = len(data[0])
        
        # Initialize centroids randomly
        self.centroids = []
        for _ in range(self.k):
            centroid = [random.uniform(0, 1) for _ in range(n_features)]
            self.centroids.append(centroid)
        
        # Iterate until convergence
        for iteration in range(self.max_iters):
            # Assign points to clusters
            new_labels = []
            for point in data:
                distances = []
                for centroid in self.centroids:
                    dist = self._euclidean_distance(point, centroid)
                    distances.append(dist)
                
                closest_cluster = distances.index(min(distances))
                new_labels.append(closest_cluster)
            
            # Update centroids
            new_centroids = []
            for cluster_id in range(self.k):
                cluster_points = [data[i] for i, label in enumerate(new_labels) if label == cluster_id]
                
                if cluster_points:
                    # Calculate mean
                    centroid = []
                    for feature_idx in range(n_features):
                        feature_mean = sum(point[feature_idx] for point in cluster_points) / len(cluster_points)
                        centroid.append(feature_mean)
                    new_centroids.append(centroid)
                else:
                    # Keep old centroid if no points assigned
                    new_centroids.append(self.centroids[cluster_id])
            
            # Check convergence
            converged = True
            for i, (old, new) in enumerate(zip(self.centroids, new_centroids)):
                if self._euclidean_distance(old, new) > 0.001:
                    converged = False
                    break
            
            self.centroids = new_centroids
            self.labels = new_labels
            
            if converged:
                print(f"  ✅ Converged after {iteration + 1} iterations")
                break
        
        return self.labels
    
    def _euclidean_distance(self, point1: List[float], point2: List[float]) -> float:
        """Calculate Euclidean distance between two points."""
        return math.sqrt(sum((a - b) ** 2 for a, b in zip(point1, point2)))
    
    def predict(self, point: List[float]) -> int:
        """Predict cluster for a new point."""
        distances = []
        for centroid in self.centroids:
            dist = self._euclidean_distance(point, centroid)
            distances.append(dist)
        
        return distances.index(min(distances))


class SimpleClustering:
    """Simple clustering for ag-trading-bot features."""
    
    def __init__(self):
        self.feature_keys = [
            "market_cap_usd", "liquidity_usd", "ag_score", "bundled_pct",
            "holders_count", "swaps_f_count", "volume_1m_to_mc_pct",
            "win_prediction_pct", "token_age_sec"
        ]
    
    def load_training_features(self) -> Tuple[List[List[float]], List[str], List[bool]]:
        """Load training features from database."""
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
                    ORDER BY fs.snapped_at
                """)
                
                records = cur.fetchall()
            
            conn.close()
            
            # Extract feature matrix
            feature_matrix = []
            message_ids = []
            outcomes = []
            
            for record in records:
                features = record['features']
                
                # Extract normalized feature vector
                feature_vector = []
                valid = True
                
                for key in self.feature_keys:
                    value = features.get(key)
                    
                    if value is not None:
                        # Normalize to 0-1 range
                        if key == "ag_score":
                            normalized = value / 10.0
                        elif key in ["market_cap_usd", "liquidity_usd", "volume_1m_total_usd"]:
                            # Log scale for currency values
                            normalized = min(1.0, math.log10(max(1, value)) / 6)  # Log scale up to 1M
                        elif key in ["bundled_pct", "liquidity_pct", "volume_1m_to_mc_pct", "win_prediction_pct"]:
                            normalized = value / 100.0
                        elif key == "token_age_sec":
                            normalized = min(1.0, value / 604800)  # Max 1 week
                        elif key in ["holders_count", "swaps_f_count"]:
                            normalized = min(1.0, value / 100)  # Max 100
                        else:
                            normalized = min(1.0, max(0.0, value))
                        
                        feature_vector.append(normalized)
                    else:
                        # Use median value for missing features
                        feature_vector.append(0.5)
                
                if len(feature_vector) == len(self.feature_keys):
                    feature_matrix.append(feature_vector)
                    message_ids.append(record['message_id'])
                    outcomes.append(record['win'])
            
            print(f"📊 Loaded {len(feature_matrix)} training samples with {len(self.feature_keys)} features")
            
            return feature_matrix, message_ids, outcomes
            
        except Exception as e:
            print(f"❌ Failed to load training features: {e}")
            return [], [], []
    
    def train_clusters(self) -> Dict[str, Any]:
        """Train simple K-means clusters."""
        print(f"🧠 Training {settings.K_CLUSTERS} clusters with simple K-means...")
        
        # Load training data
        feature_matrix, message_ids, outcomes = self.load_training_features()
        
        if len(feature_matrix) < settings.K_CLUSTERS:
            return {"error": f"Not enough samples ({len(feature_matrix)}) for {settings.K_CLUSTERS} clusters"}
        
        # Train K-means
        kmeans = SimpleKMeans(k=settings.K_CLUSTERS)
        labels = kmeans.fit(feature_matrix)
        
        # Analyze clusters
        cluster_analysis = []
        
        for cluster_id in range(settings.K_CLUSTERS):
            cluster_samples = [i for i, label in enumerate(labels) if label == cluster_id]
            cluster_outcomes = [outcomes[i] for i in cluster_samples]
            
            win_rate = sum(cluster_outcomes) / len(cluster_outcomes) if cluster_outcomes else 0
            
            cluster_info = {
                "cluster_id": cluster_id,
                "size": len(cluster_samples),
                "win_rate": win_rate,
                "centroid": kmeans.centroids[cluster_id]
            }
            
            cluster_analysis.append(cluster_info)
            
            print(f"  📊 Cluster {cluster_id}: {len(cluster_samples)} samples, {win_rate:.1%} win rate")
        
        # Store clusters in database
        try:
            conn = psycopg2.connect(settings.DATABASE_URL)
            with conn.cursor() as cur:
                # Clear existing clusters
                cur.execute("DELETE FROM strategy_clusters")
                
                # Insert new clusters
                for cluster in cluster_analysis:
                    centroid_data = {
                        "centroid": cluster["centroid"],
                        "feature_keys": self.feature_keys,
                        "size": cluster["size"],
                        "win_rate": cluster["win_rate"]
                    }
                    
                    cur.execute("""
                        INSERT INTO strategy_clusters (id, label, centroid, covariance, updated_at)
                        VALUES (%s, %s, %s, %s, NOW())
                    """, (
                        cluster["cluster_id"],
                        f"cluster_{cluster['cluster_id']}",
                        json.dumps(centroid_data),
                        json.dumps({"distance_threshold": 1.0})
                    ))
                
                conn.commit()
            conn.close()
            
            print(f"✅ Stored {len(cluster_analysis)} clusters in database")
            
        except Exception as e:
            print(f"❌ Failed to store clusters: {e}")
        
        return {
            "n_clusters": settings.K_CLUSTERS,
            "n_samples": len(feature_matrix),
            "clusters": cluster_analysis
        }


def main():
    """Test simple clustering."""
    print("🧠 Simple Clustering Test")
    print("=" * 40)
    
    clustering = SimpleClustering()
    result = clustering.train_clusters()
    
    if "error" in result:
        print(f"❌ Clustering failed: {result['error']}")
    else:
        print(f"\n🎉 Clustering successful!")
        print(f"  Clusters: {result['n_clusters']}")
        print(f"  Samples: {result['n_samples']}")
        
        for cluster in result['clusters']:
            print(f"    Cluster {cluster['cluster_id']}: {cluster['size']} samples ({cluster['win_rate']:.1%} wins)")


if __name__ == "__main__":
    main()
