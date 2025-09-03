"""
Cluster Router - K-means clustering for strategy routing.
Source: spec.md - Nightly k-means K=3–4; store centroids & covariance; implement runtime assigner.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score
import asyncpg

from config import settings

logger = logging.getLogger(__name__)


class ClusterRouter:
    """
    Manages feature clustering and runtime cluster assignment.
    
    Implements nightly K-means clustering with K=3-4 clusters.
    Provides runtime cluster assignment with OOD detection.
    """
    
    def __init__(self, db_pool: asyncpg.Pool):
        self.db_pool = db_pool
        self.k_clusters = settings.K_CLUSTERS
        self.feature_names = settings.FEATURE_NAMES
        
        # Cluster state
        self.scaler = None
        self.cluster_centers = None
        self.cluster_labels = None
    
    async def load_training_data(self, days_back: int = 30) -> Tuple[np.ndarray, List[str]]:
        """
        Load recent feature data for clustering.
        
        Args:
            days_back: Days of data to include
            
        Returns:
            Tuple of (feature_matrix, message_ids)
        """
        query = """
            SELECT fs.message_id, fs.features
            FROM features_snapshot fs
            INNER JOIN acceptance_status a ON fs.message_id = a.message_id
            WHERE a.status = 'ACCEPT'
              AND fs.snapped_at >= NOW() - INTERVAL '{} days'
              AND fs.feature_version = '{}'
            ORDER BY fs.snapped_at DESC
        """.format(days_back, settings.FEATURE_VERSION)
        
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query)
        
        if len(rows) < settings.MIN_TRAINING_SAMPLES:
            raise ValueError(f"Insufficient training data: {len(rows)} samples (need {settings.MIN_TRAINING_SAMPLES})")
        
        # Extract feature matrix
        feature_matrix = []
        message_ids = []
        
        for row in rows:
            features = row["features"]
            message_ids.append(row["message_id"])
            
            # Extract normalized feature values
            feature_vector = []
            for feature_name in self.feature_names:
                pct_name = f"{feature_name}_pct"
                if pct_name in features:
                    feature_vector.append(float(features[pct_name]))
                else:
                    feature_vector.append(0.5)  # Default to median
            
            feature_matrix.append(feature_vector)
        
        return np.array(feature_matrix), message_ids
    
    async def train_clusters(self) -> Dict[str, Any]:
        """
        Train K-means clusters on recent feature data.
        
        Returns:
            Training results and cluster information
        """
        logger.info(f"🧠 Training {self.k_clusters} clusters...")
        
        # Load training data
        X, message_ids = await self.load_training_data()
        
        logger.info(f"📊 Loaded {len(X)} samples with {X.shape[1]} features")
        
        # Standardize features
        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)
        
        # Try different K values and pick best
        best_k = self.k_clusters
        best_score = -1
        best_model = None
        
        for k in range(max(2, self.k_clusters - 1), self.k_clusters + 2):
            if k >= len(X):
                continue
                
            kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
            labels = kmeans.fit_predict(X_scaled)
            
            # Calculate silhouette score
            if len(np.unique(labels)) > 1:
                score = silhouette_score(X_scaled, labels)
                
                if score > best_score:
                    best_score = score
                    best_k = k
                    best_model = kmeans
        
        if best_model is None:
            raise ValueError("Failed to train any clusters")
        
        # Use best model
        self.k_clusters = best_k
        kmeans = best_model
        labels = kmeans.labels_
        self.cluster_centers = kmeans.cluster_centers_
        
        # Calculate cluster statistics
        cluster_info = []
        
        for cluster_id in range(self.k_clusters):
            mask = labels == cluster_id
            cluster_samples = X_scaled[mask]
            
            # Calculate covariance for OOD detection
            if len(cluster_samples) > 1:
                cov_matrix = np.cov(cluster_samples.T)
                
                # Calculate distance threshold (95th percentile)
                distances = []
                for sample in cluster_samples:
                    dist = np.linalg.norm(sample - self.cluster_centers[cluster_id])
                    distances.append(dist)
                
                distance_threshold = np.percentile(distances, 95)
            else:
                cov_matrix = np.eye(len(self.feature_names))
                distance_threshold = 1.0
            
            cluster_info.append({
                "cluster_id": cluster_id,
                "label": settings.CLUSTER_LABELS.get(cluster_id, f"cluster_{cluster_id}"),
                "size": int(np.sum(mask)),
                "centroid": self.cluster_centers[cluster_id].tolist(),
                "covariance": cov_matrix.tolist(),
                "distance_threshold": float(distance_threshold)
            })
        
        # Store clusters in database
        await self._store_clusters(cluster_info)
        
        logger.info(f"✅ Trained {self.k_clusters} clusters (silhouette: {best_score:.3f})")
        
        return {
            "n_clusters": self.k_clusters,
            "n_samples": len(X),
            "silhouette_score": best_score,
            "clusters": cluster_info
        }
    
    async def _store_clusters(self, cluster_info: List[Dict[str, Any]]):
        """Store cluster definitions in database."""
        async with self.db_pool.acquire() as conn:
            # Clear existing clusters
            await conn.execute("DELETE FROM strategy_clusters")
            
            # Insert new clusters
            for cluster in cluster_info:
                centroid_data = {
                    "centroid": cluster["centroid"],
                    "feature_names": self.feature_names,
                    "scaler_mean": self.scaler.mean_.tolist(),
                    "scaler_scale": self.scaler.scale_.tolist()
                }
                
                covariance_data = {
                    "covariance": cluster["covariance"],
                    "distance_threshold": cluster["distance_threshold"]
                }
                
                await conn.execute("""
                    INSERT INTO strategy_clusters (id, label, centroid, covariance)
                    VALUES ($1, $2, $3, $4)
                """,
                    cluster["cluster_id"],
                    cluster["label"],
                    json.dumps(centroid_data),
                    json.dumps(covariance_data)
                )
    
    async def assign_cluster(self, features: Dict[str, Any]) -> Tuple[int, float, bool]:
        """
        Assign features to nearest cluster with OOD detection.
        
        Args:
            features: Feature dictionary (normalized)
            
        Returns:
            Tuple of (cluster_id, distance, is_ood)
        """
        # Load clusters if not cached
        if self.cluster_centers is None:
            await self._load_clusters()
        
        # Extract feature vector
        feature_vector = []
        for feature_name in self.feature_names:
            pct_name = f"{feature_name}_pct"
            if pct_name in features:
                feature_vector.append(float(features[pct_name]))
            else:
                feature_vector.append(0.5)  # Default
        
        feature_vector = np.array(feature_vector).reshape(1, -1)
        
        # Standardize using saved scaler
        feature_scaled = self.scaler.transform(feature_vector)[0]
        
        # Find nearest cluster
        distances = []
        for center in self.cluster_centers:
            dist = np.linalg.norm(feature_scaled - center)
            distances.append(dist)
        
        nearest_cluster = int(np.argmin(distances))
        min_distance = float(distances[nearest_cluster])
        
        # Check if OOD
        cluster_threshold = await self._get_cluster_threshold(nearest_cluster)
        is_ood = min_distance > cluster_threshold
        
        return nearest_cluster, min_distance, is_ood
    
    async def _load_clusters(self):
        """Load cluster definitions from database."""
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, centroid, covariance
                FROM strategy_clusters
                ORDER BY id
            """)
        
        if not rows:
            raise ValueError("No clusters found. Train clusters first.")
        
        # Reconstruct cluster centers and scaler
        centroids = []
        
        for row in rows:
            centroid_data = row["centroid"]
            centroids.append(centroid_data["centroid"])
            
            # Reconstruct scaler from first cluster
            if self.scaler is None:
                self.scaler = StandardScaler()
                self.scaler.mean_ = np.array(centroid_data["scaler_mean"])
                self.scaler.scale_ = np.array(centroid_data["scaler_scale"])
        
        self.cluster_centers = np.array(centroids)
    
    async def _get_cluster_threshold(self, cluster_id: int) -> float:
        """Get distance threshold for OOD detection."""
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT covariance
                FROM strategy_clusters
                WHERE id = $1
            """, cluster_id)
        
        if row:
            covariance_data = row["covariance"]
            return float(covariance_data.get("distance_threshold", 1.0))
        
        return 1.0  # Default threshold


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
        router = ClusterRouter(pool)
        
        # Train clusters
        result = await router.train_clusters()
        
        print(f"\n🧠 Clustering Results:")
        print(f"Clusters: {result['n_clusters']}")
        print(f"Samples: {result['n_samples']}")
        print(f"Silhouette score: {result['silhouette_score']:.3f}")
        
        for cluster in result['clusters']:
            print(f"  Cluster {cluster['cluster_id']} ({cluster['label']}): {cluster['size']} samples")
    
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
