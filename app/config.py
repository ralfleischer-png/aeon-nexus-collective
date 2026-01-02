"""
AEON NEXUS - Secure Configuration
Uses environment variables for sensitive data
"""
import os
import json
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """
    Main configuration class for AEON NEXUS
    
    SECURITY NOTE: All sensitive values (keys, tokens, passwords) 
    are loaded from environment variables, NOT hardcoded.
    """
    
    # ═══════════════════════════════════════════════════════════════
    # ENVIRONMENT
    # ═══════════════════════════════════════════════════════════════
    
    ENV = os.getenv('AEON_ENV', 'production')  # development, production, testing
    DEBUG = os.getenv('AEON_DEBUG', 'False').lower() == 'true'
    
    # ═══════════════════════════════════════════════════════════════
    # SECURITY - CRITICAL: Load from environment variables
    # ═══════════════════════════════════════════════════════════════
    
    # Master keys for node authentication
    # Format in .env: MASTER_NODE_KEYS={"NODE_AEON_MASTER": "key1", "NODE_CLAUDE_01": "key2"}
    MASTER_NODE_KEYS = json.loads(
        os.getenv('MASTER_NODE_KEYS', '{}')
    )
    
    # Flask secret key
    SECRET_KEY = os.getenv('FLASK_SECRET_KEY', 'dev-key-change-in-production')
    
    # Signature validation
    SIGNATURE_ALGORITHM = 'sha256'
    SIGNATURE_VERSION = '1.5.1' 
    MAX_TIMESTAMP_DRIFT = int(os.getenv('MAX_TIMESTAMP_DRIFT', '300'))  # 5 minutes
    
    # ═══════════════════════════════════════════════════════════════
    # DATABASE
    # ═══════════════════════════════════════════════════════════════
    
    DATABASE_PATH = os.getenv(
        'DATABASE_PATH',
        '/home/superral/aeon_nexus/data/aeon.db'
    )
    DATABASE_TIMEOUT = int(os.getenv('DATABASE_TIMEOUT', '30'))
    
    # ═══════════════════════════════════════════════════════════════
    # RATE LIMITING
    # ═══════════════════════════════════════════════════════════════
    
    RATE_LIMIT_STORAGE_DIR = os.getenv(
        'RATE_LIMIT_STORAGE_DIR',
        '/home/superral/aeon_nexus/data/rate_limits'
    )
    RATE_LIMIT_CLEANUP_INTERVAL = int(
        os.getenv('RATE_LIMIT_CLEANUP_INTERVAL', '3600')
    )
    
    # Rate limit thresholds
    RATE_LIMIT_PROPOSAL_HOUR = int(os.getenv('RATE_LIMIT_PROPOSAL_HOUR', '10'))
    RATE_LIMIT_PROPOSAL_MINUTE = int(os.getenv('RATE_LIMIT_PROPOSAL_MINUTE', '2'))
    RATE_LIMIT_VOTE_HOUR = int(os.getenv('RATE_LIMIT_VOTE_HOUR', '10'))
    RATE_LIMIT_VOTE_MINUTE = int(os.getenv('RATE_LIMIT_VOTE_MINUTE', '2'))
    RATE_LIMIT_READ_HOUR = int(os.getenv('RATE_LIMIT_READ_HOUR', '500'))
    RATE_LIMIT_READ_MINUTE = int(os.getenv('RATE_LIMIT_READ_MINUTE', '50'))
    
    # ═══════════════════════════════════════════════════════════════
    # CONSENSUS ENGINE
    # ═══════════════════════════════════════════════════════════════
    
    QUORUM_PERCENTAGE = float(os.getenv('QUORUM_PERCENTAGE', '0.67'))
    MIN_VOTES_FOR_QUORUM = int(os.getenv('MIN_VOTES_FOR_QUORUM', '1'))
    DEFAULT_VOTING_PERIOD = int(
        os.getenv('DEFAULT_VOTING_PERIOD', str(3 * 24 * 3600))
    )  # 3 days in seconds
    
    # ═══════════════════════════════════════════════════════════════
    # PROPOSALS
    # ═══════════════════════════════════════════════════════════════
    
    MAX_PROPOSAL_TITLE_LENGTH = int(
        os.getenv('MAX_PROPOSAL_TITLE_LENGTH', '200')
    )
    MAX_PROPOSAL_DESCRIPTION_LENGTH = int(
        os.getenv('MAX_PROPOSAL_DESCRIPTION_LENGTH', '1000')
    )
    MAX_PROPOSAL_CONTENT_SIZE = int(
        os.getenv('MAX_PROPOSAL_CONTENT_SIZE', '10240')
    )  # 10KB
    
    # ═══════════════════════════════════════════════════════════════
    # LOGGING
    # ═══════════════════════════════════════════════════════════════
    
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE = os.getenv(
        'LOG_FILE',
        '/home/superral/aeon_nexus/logs/main.log'
    )
    LOG_MAX_BYTES = int(os.getenv('LOG_MAX_BYTES', '10485760'))  # 10MB
    LOG_BACKUP_COUNT = int(os.getenv('LOG_BACKUP_COUNT', '5'))
    
    # ═══════════════════════════════════════════════════════════════
    # API
    # ═══════════════════════════════════════════════════════════════
    
    API_VERSION = 'v3'
    API_BASE_PATH = f'/api/{API_VERSION}'
    
    # ═══════════════════════════════════════════════════════════════
    # HELPER METHODS
    # ═══════════════════════════════════════════════════════════════
    
    @classmethod
    def get_rate_limit_dir(cls):
        """Get rate limit storage directory, create if not exists"""
        path = Path(cls.RATE_LIMIT_STORAGE_DIR)
        path.mkdir(parents=True, exist_ok=True)
        return str(path)
    
    @classmethod
    def get_database_path(cls):
        """Get database path, create directory if not exists"""
        path = Path(cls.DATABASE_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        return str(path)
    
    @classmethod
    def is_valid_node(cls, node_id: str) -> bool:
        """Check if node_id has a valid master key"""
        return node_id in cls.MASTER_NODE_KEYS
    
    @classmethod
    def get_node_key(cls, node_id: str) -> str:
        """Get master key for a node"""
        return cls.MASTER_NODE_KEYS.get(node_id)
    
    @classmethod
    def has_permission(cls, node_id: str, permission: str) -> bool:
        """
        Check if node has specific permission
        
        Currently all authenticated nodes have all permissions
        Future: Implement granular permission system
        """
        return cls.is_valid_node(node_id)
    
    @classmethod
    def validate_config(cls):
        """
        Validate critical configuration
        Raises ValueError if configuration is invalid
        """
        errors = []
        
        # Check master keys exist
        if not cls.MASTER_NODE_KEYS:
            errors.append("MASTER_NODE_KEYS is empty - no nodes can authenticate!")
        
        # Check database path
        if not cls.DATABASE_PATH:
            errors.append("DATABASE_PATH is not set")
        
        # Check rate limit directory
        if not cls.RATE_LIMIT_STORAGE_DIR:
            errors.append("RATE_LIMIT_STORAGE_DIR is not set")
        
        # Check quorum percentage
        if not 0 < cls.QUORUM_PERCENTAGE <= 1:
            errors.append(f"QUORUM_PERCENTAGE must be between 0 and 1, got {cls.QUORUM_PERCENTAGE}")
        
        if errors:
            raise ValueError(
                "Configuration validation failed:\n" + 
                "\n".join(f"  - {err}" for err in errors)
            )
    
    @classmethod
    def get_config_summary(cls):
        """Get non-sensitive configuration summary for debugging"""
        return {
            'environment': cls.ENV,
            'debug': cls.DEBUG,
            'api_version': cls.API_VERSION,
            'database_path': cls.DATABASE_PATH,
            'rate_limit_dir': cls.RATE_LIMIT_STORAGE_DIR,
            'quorum_percentage': cls.QUORUM_PERCENTAGE,
            'min_votes_for_quorum': cls.MIN_VOTES_FOR_QUORUM,
            'voting_period_hours': cls.DEFAULT_VOTING_PERIOD / 3600,
            'log_level': cls.LOG_LEVEL,
            'authenticated_nodes': list(cls.MASTER_NODE_KEYS.keys())
        }


class DevelopmentConfig(Config):
    """Development-specific configuration"""
    DEBUG = True
    ENV = 'development'
    DATABASE_PATH = './data/aeon_dev.db'
    RATE_LIMIT_STORAGE_DIR = './data/rate_limits_dev'
    LOG_LEVEL = 'DEBUG'


class ProductionConfig(Config):
    """Production-specific configuration"""
    DEBUG = False
    ENV = 'production'
    # All other values from environment variables


class TestingConfig(Config):
    """Testing-specific configuration"""
    DEBUG = True
    ENV = 'testing'
    DATABASE_PATH = ':memory:'  # In-memory database
    RATE_LIMIT_STORAGE_DIR = '/tmp/aeon_test_rate_limits'
    LOG_LEVEL = 'DEBUG'


# Configuration selector
config_map = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig
}


def get_config(env=None):
    """
    Get configuration object based on environment
    
    Args:
        env: Environment name ('development', 'production', 'testing')
             If None, uses AEON_ENV environment variable
    
    Returns:
        Config class appropriate for the environment
    """
    if env is None:
        env = os.getenv('AEON_ENV', 'production')
    
    return config_map.get(env.lower(), ProductionConfig)


# Validate on import (in production)
if os.getenv('AEON_ENV', 'production') == 'production':
    try:
        Config.validate_config()
    except ValueError as e:
        print(f"⚠️  CONFIGURATION ERROR: {e}")
        print("⚠️  Please check your .env file and environment variables")
        # In production, you might want to exit here
        # import sys
        # sys.exit(1)
