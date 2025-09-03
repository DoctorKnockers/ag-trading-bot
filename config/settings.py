"""
AG-Trading-Bot Configuration Settings
Source: spec.md - Tunables and environment configuration
"""

import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database Configuration
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://localhost/ag_trading_bot')
DB_POOL_MIN_SIZE = int(os.getenv('DB_POOL_MIN_SIZE', '2'))
DB_POOL_MAX_SIZE = int(os.getenv('DB_POOL_MAX_SIZE', '10'))

# Discord Configuration - WEB SCRAPING ONLY  
# NO WEBHOOKS, NO BOTS, NO TOKENS - Only credential-based web scraping
DISCORD_USERNAME = os.getenv('DISCORD_USERNAME')  # Discord email for web login
DISCORD_PASSWORD = os.getenv('DISCORD_PASSWORD')  # Discord password for web login
DISCORD_CHANNEL_ID = os.getenv('DISCORD_CHANNEL_ID')  # Alpha Gardeners #launchpads channel
DISCORD_GUILD_ID = os.getenv('DISCORD_GUILD_ID')  # Alpha Gardeners guild ID

# Solana RPC Configuration
HELIUS_API_KEY = os.getenv('HELIUS_API_KEY')
HELIUS_RPC_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
BACKUP_RPC_URL = os.getenv('BACKUP_RPC_URL', 'https://api.mainnet-beta.solana.com')

# External API Keys
BIRDEYE_API_KEY = os.getenv('BIRDEYE_API_KEY')
DEXSCREENER_API_KEY = os.getenv('DEXSCREENER_API_KEY')  # Optional
JUPITER_API_URL = 'https://quote-api.jup.ag/v6'

# Outcome Labeling Parameters (from spec.md)
MULTIPLE = 10  # 10x multiple for winner
T_DWELL_SEC = 180  # 180 seconds sustained duration
Q_TEST_SOL = 0.5  # 0.5 SOL for slippage test
S_MAX = 0.15  # 15% max slippage
POOL_WAIT_TIMEOUT_SEC = 1800  # 30 minutes for pool creation
MAX_EFFECTIVE_FEE = 0.40  # 40% max fee/impact

# Feature Extraction Parameters
FEATURE_VERSION = 'v1'
PERCENTILE_WINDOW_HOURS = 24  # Rolling window for percentile normalization

# Training Parameters
K_CLUSTERS = 3  # Number of clusters for K-means
MIN_TRAINING_SAMPLES = 100  # Minimum samples before training
GA_POPULATION_SIZE = 100
GA_GENERATIONS = 50
GA_CROSSOVER_PROB = 0.7
GA_MUTATION_PROB = 0.2
CV_FOLDS = 5  # Temporal blocked cross-validation folds
MIN_HOLDOUT_PICKS = 30  # Minimum picks for promotion
MIN_BUY_PRECISION = 0.60  # 60% minimum BUY win-rate for promotion
TARGET_BUY_RATE_MIN = 0.05  # 5% minimum buy rate
TARGET_BUY_RATE_MAX = 0.20  # 20% maximum buy rate

# Shadow Mode Duration
SHADOW_DAYS = 2  # Days in shadow mode before full activation

# Rate Limiting
HELIUS_RATE_LIMIT = 100  # Requests per second
BIRDEYE_RATE_LIMIT = 10  # Requests per second
JUPITER_RATE_LIMIT = 20  # Requests per second
DEXSCREENER_RATE_LIMIT = 5  # Requests per second

# Retry Configuration
MAX_RETRIES = 3
RETRY_DELAY_SEC = 1
RETRY_BACKOFF_FACTOR = 2

# Logging Configuration
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_FILE = os.getenv('LOG_FILE', 'ag_trading_bot.log')

# Processing Configuration
BATCH_SIZE = 10  # Messages to process in batch
PROCESSING_INTERVAL_SEC = 5  # Check for new messages every 5 seconds
OUTCOME_CHECK_INTERVAL_MIN = 5  # Check outcomes every 5 minutes

# Known SPL Token Program IDs
SPL_TOKEN_PROGRAM_ID = 'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA'
SPL_TOKEN_2022_PROGRAM_ID = 'TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb'

# Validation Thresholds
MIN_LIQUIDITY_USD = 100  # Minimum liquidity to consider
MIN_HOLDERS = 10  # Minimum holder count
MAX_TOP10_CONCENTRATION = 0.80  # Max 80% held by top 10

# Feature Names (for consistency)
FEATURE_NAMES = [
    'liquidity_usd',
    'volume_24h_usd',
    'holder_count',
    'top10_concentration',
    'smart_money_count',
    'age_minutes',
    'volume_to_mcap_ratio',
    'price_change_5m',
    'buy_sell_ratio',
    'unique_wallets_24h'
]

# Cluster Labels
CLUSTER_LABELS = {
    0: 'high_liquidity',
    1: 'early_momentum',
    2: 'smart_money',
    3: 'community_driven'
}

def validate_config() -> bool:
    """Validate required configuration."""
    required = [
        ('DISCORD_USERNAME', DISCORD_USERNAME),
        ('DISCORD_PASSWORD', DISCORD_PASSWORD), 
        ('DISCORD_CHANNEL_ID', DISCORD_CHANNEL_ID),
        ('HELIUS_API_KEY', HELIUS_API_KEY),
        ('BIRDEYE_API_KEY', BIRDEYE_API_KEY),
    ]
    
    missing = []
    for name, value in required:
        if not value:
            missing.append(name)
    
    if missing:
        print(f"❌ Missing required configuration: {', '.join(missing)}")
        print("Please set these in your .env file")
        return False
    
    return True

# Export all settings
__all__ = [
    'DATABASE_URL', 'DB_POOL_MIN_SIZE', 'DB_POOL_MAX_SIZE',
    'DISCORD_USERNAME', 'DISCORD_PASSWORD', 'DISCORD_CHANNEL_ID', 'DISCORD_GUILD_ID',
    'HELIUS_API_KEY', 'HELIUS_RPC_URL', 'BACKUP_RPC_URL',
    'BIRDEYE_API_KEY', 'DEXSCREENER_API_KEY', 'JUPITER_API_URL',
    'MULTIPLE', 'T_DWELL_SEC', 'Q_TEST_SOL', 'S_MAX',
    'POOL_WAIT_TIMEOUT_SEC', 'MAX_EFFECTIVE_FEE',
    'FEATURE_VERSION', 'PERCENTILE_WINDOW_HOURS',
    'K_CLUSTERS', 'MIN_TRAINING_SAMPLES', 'GA_POPULATION_SIZE',
    'GA_GENERATIONS', 'GA_CROSSOVER_PROB', 'GA_MUTATION_PROB',
    'CV_FOLDS', 'MIN_HOLDOUT_PICKS', 'MIN_BUY_PRECISION',
    'TARGET_BUY_RATE_MIN', 'TARGET_BUY_RATE_MAX',
    'SHADOW_DAYS', 'LOG_LEVEL', 'LOG_FORMAT', 'LOG_FILE',
    'BATCH_SIZE', 'PROCESSING_INTERVAL_SEC', 'OUTCOME_CHECK_INTERVAL_MIN',
    'SPL_TOKEN_PROGRAM_ID', 'SPL_TOKEN_2022_PROGRAM_ID',
    'MIN_LIQUIDITY_USD', 'MIN_HOLDERS', 'MAX_TOP10_CONCENTRATION',
    'FEATURE_NAMES', 'CLUSTER_LABELS', 'validate_config'
]
