"""
Production-ready rate limiting - SIMPLIFIED VERSION
Works without flask_limiter.storage module
"""
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Production-ready limiter with in-memory storage (simple but works)
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["1000 per hour", "100 per minute"],  # Global limits
    headers_enabled=True,  # Return X-RateLimit-* headers
    swallow_errors=True,  # Don't crash app if rate limiting fails
)

# Custom rate limit decorators for specific use cases
def strict_rate_limit():
    """Very strict limit for sensitive endpoints (propose, vote)"""
    return limiter.limit("10 per hour, 2 per minute")

def moderate_rate_limit():
    """Moderate limit for authenticated endpoints"""
    return limiter.limit("100 per hour, 20 per minute")

def lenient_rate_limit():
    """Lenient limit for public read endpoints"""
    return limiter.limit("500 per hour, 50 per minute")