"""
AEON NEXUS - File-Based Rate Limiting
======================================
Persistent rate limiting using file-based storage.

Features:
- File-based storage (survives restarts)
- Thread-safe operations
- Automatic cleanup
- Per-IP rate limiting
- Configurable limits and windows

Version: 1.0.0
Author: AEON NEXUS Collective
"""

import os
import json
import time
import threading
from pathlib import Path
from typing import Dict, Tuple, Optional
from datetime import datetime, timedelta


class FileBasedRateLimiter:
    """
    File-based rate limiter with persistent storage.
    
    Each IP address gets its own JSON file storing request count and reset time.
    Thread-safe with file locking.
    """
    
    def __init__(self, storage_dir: str):
        """
        Initialize rate limiter.
        
        Args:
            storage_dir: Directory to store rate limit files
        """
        if storage_dir is None:
            raise ValueError("storage_dir cannot be None")
        
        self.storage_dir = Path(storage_dir)
        self.lock = threading.Lock()
        
        # Create storage directory if it doesn't exist
        try:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            print(f"Warning: Could not create rate limit directory: {e}")
    
    def _get_file_path(self, identifier: str) -> Path:
        """
        Get file path for identifier.
        
        Args:
            identifier: Unique identifier (e.g., IP address)
            
        Returns:
            Path object for the rate limit file
        """
        # Sanitize identifier for filename (replace dots with underscores)
        safe_identifier = identifier.replace('.', '_').replace(':', '_')
        return self.storage_dir / f"{safe_identifier}.json"
    
    def _read_counter(self, file_path: Path) -> Dict:
        """
        Read counter from file.
        
        Args:
            file_path: Path to counter file
            
        Returns:
            Dictionary with count and reset_time
        """
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
                return {
                    'count': data.get('count', 0),
                    'reset_time': data.get('reset_time', 0)
                }
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            return {'count': 0, 'reset_time': 0}
    
    def _write_counter(self, file_path: Path, count: int, reset_time: int):
        """
        Write counter to file.
        
        Args:
            file_path: Path to counter file
            count: Request count
            reset_time: Reset timestamp
        """
        try:
            with open(file_path, 'w') as f:
                json.dump({
                    'count': count,
                    'reset_time': reset_time
                }, f)
        except OSError as e:
            print(f"Warning: Could not write rate limit file: {e}")
    
    def increment(self, identifier: str, limit: int, window: int) -> Dict:
        """
        Increment counter for identifier and check if limit exceeded.
        
        Args:
            identifier: Unique identifier (e.g., IP address)
            limit: Maximum requests allowed
            window: Time window in seconds
            
        Returns:
            Dictionary with:
                - allowed: bool (whether request is allowed)
                - count: int (current request count)
                - remaining: int (requests remaining)
                - reset_time: int (timestamp when counter resets)
        """
        with self.lock:
            file_path = self._get_file_path(identifier)
            now = int(time.time())
            
            # Read current counter
            data = self._read_counter(file_path)
            count = data['count']
            reset_time = data['reset_time']
            
            # Check if window has expired
            if now >= reset_time:
                # Reset counter
                count = 1
                reset_time = now + window
            else:
                # Increment counter
                count += 1
            
            # Write updated counter
            self._write_counter(file_path, count, reset_time)
            
            # Check if limit exceeded
            allowed = count <= limit
            remaining = max(0, limit - count)
            
            return {
                'allowed': allowed,
                'count': count,
                'remaining': remaining,
                'reset_time': reset_time
            }
    
    def check(self, identifier: str, limit: int, window: int) -> Dict:
        """
        Check rate limit without incrementing.
        
        Args:
            identifier: Unique identifier
            limit: Maximum requests allowed
            window: Time window in seconds
            
        Returns:
            Dictionary with current status
        """
        with self.lock:
            file_path = self._get_file_path(identifier)
            now = int(time.time())
            
            # Read current counter
            data = self._read_counter(file_path)
            count = data['count']
            reset_time = data['reset_time']
            
            # Check if window has expired
            if now >= reset_time:
                count = 0
                reset_time = now + window
            
            allowed = count < limit
            remaining = max(0, limit - count)
            
            return {
                'allowed': allowed,
                'count': count,
                'remaining': remaining,
                'reset_time': reset_time
            }
    
    def reset(self, identifier: str):
        """
        Reset counter for identifier.
        
        Args:
            identifier: Unique identifier to reset
        """
        with self.lock:
            file_path = self._get_file_path(identifier)
            if file_path.exists():
                try:
                    file_path.unlink()
                except OSError:
                    pass
    
    def cleanup(self, max_age: int = 3600):
        """
        Remove old rate limit files.
        
        Args:
            max_age: Maximum age in seconds (default 1 hour)
        """
        with self.lock:
            now = time.time()
            
            for file_path in self.storage_dir.glob('*.json'):
                try:
                    # Check file modification time
                    if now - file_path.stat().st_mtime > max_age:
                        file_path.unlink()
                except OSError:
                    pass
    
    def get_stats(self) -> Dict:
        """
        Get statistics about rate limiting.
        
        Returns:
            Dictionary with stats
        """
        with self.lock:
            files = list(self.storage_dir.glob('*.json'))
            
            total_files = len(files)
            total_requests = 0
            active_limiters = 0
            
            now = int(time.time())
            
            for file_path in files:
                try:
                    data = self._read_counter(file_path)
                    if data['reset_time'] > now:
                        active_limiters += 1
                        total_requests += data['count']
                except:
                    pass
            
            return {
                'total_files': total_files,
                'active_limiters': active_limiters,
                'total_requests': total_requests,
                'storage_dir': str(self.storage_dir)
            }


# =============================================================================
# GLOBAL RATE LIMITER INSTANCE
# =============================================================================

_rate_limiter = None


def get_rate_limiter():
    """
    Get or create the global rate limiter instance.
    Falls back to default storage directory if not configured.
    """
    global _rate_limiter
    
    if _rate_limiter is None:
        # Try to get storage directory from Config
        storage_dir = None
        
        try:
            from config import Config
            storage_dir = getattr(Config, 'RATE_LIMIT_STORAGE_DIR', None)
        except ImportError:
            pass
        
        # Fallback to default directory
        if storage_dir is None:
            storage_dir = '/home/superral/aeon_nexus/data/rate_limits'
        
        # Ensure directory exists
        try:
            os.makedirs(storage_dir, exist_ok=True)
        except OSError as e:
            print(f"Warning: Could not create rate limit directory {storage_dir}: {e}")
        
        # Create rate limiter
        _rate_limiter = FileBasedRateLimiter(storage_dir)
    
    return _rate_limiter


def check_rate_limit(identifier: str, limit: int, window: int) -> Tuple[bool, Dict]:
    """
    Check if request is within rate limits.
    
    This is the main function to use for rate limiting in Flask routes.
    
    Args:
        identifier: Unique identifier (e.g., IP address)
        limit: Maximum requests allowed
        window: Time window in seconds
        
    Returns:
        Tuple of (allowed: bool, headers: dict)
        
    Example:
        allowed, headers = check_rate_limit(request.remote_addr, 10, 3600)
        if not allowed:
            response = jsonify({'error': 'Rate limit exceeded'})
            for key, value in headers.items():
                response.headers[key] = value
            return response, 429
    """
    limiter = get_rate_limiter()
    result = limiter.increment(identifier, limit, window)
    
    headers = {
        'X-RateLimit-Limit': str(limit),
        'X-RateLimit-Remaining': str(result['remaining']),
        'X-RateLimit-Reset': str(result['reset_time'])
    }
    
    return result['allowed'], headers


def check_rate_limit_no_increment(identifier: str, limit: int, window: int) -> Tuple[bool, Dict]:
    """
    Check rate limit without incrementing counter.
    
    Useful for checking limits before performing expensive operations.
    
    Args:
        identifier: Unique identifier
        limit: Maximum requests allowed
        window: Time window in seconds
        
    Returns:
        Tuple of (allowed: bool, headers: dict)
    """
    limiter = get_rate_limiter()
    result = limiter.check(identifier, limit, window)
    
    headers = {
        'X-RateLimit-Limit': str(limit),
        'X-RateLimit-Remaining': str(result['remaining']),
        'X-RateLimit-Reset': str(result['reset_time'])
    }
    
    return result['allowed'], headers


def reset_rate_limit(identifier: str):
    """
    Reset rate limit for identifier.
    
    Args:
        identifier: Unique identifier to reset
    """
    limiter = get_rate_limiter()
    limiter.reset(identifier)


def cleanup_rate_limits(max_age: int = 3600):
    """
    Clean up old rate limit files.
    
    Args:
        max_age: Maximum age in seconds (default 1 hour)
    """
    limiter = get_rate_limiter()
    limiter.cleanup(max_age)


def get_rate_limit_stats() -> Dict:
    """
    Get rate limiting statistics.
    
    Returns:
        Dictionary with statistics
    """
    limiter = get_rate_limiter()
    return limiter.get_stats()


# =============================================================================
# FLASK INTEGRATION HELPERS
# =============================================================================

def rate_limit_decorator(limit: int, window: int):
    """
    Decorator for Flask routes to apply rate limiting.
    
    Args:
        limit: Maximum requests allowed
        window: Time window in seconds
        
    Example:
        @app.route('/api/endpoint')
        @rate_limit_decorator(10, 3600)
        def my_endpoint():
            return jsonify({'status': 'ok'})
    """
    from functools import wraps
    from flask import request, jsonify
    
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            allowed, headers = check_rate_limit(
                request.remote_addr,
                limit,
                window
            )
            
            if not allowed:
                response = jsonify({
                    'status': 'RATE_LIMITED',
                    'error': f'Rate limit exceeded. Max {limit} requests per {window} seconds.'
                })
                for key, value in headers.items():
                    response.headers[key] = value
                return response, 429
            
            # Call the actual route
            response = f(*args, **kwargs)
            
            # Add rate limit headers to response
            if hasattr(response, 'headers'):
                for key, value in headers.items():
                    response.headers[key] = value
            
            return response
        
        return decorated_function
    return decorator


# =============================================================================
# CLEANUP SCHEDULER (Optional)
# =============================================================================

def start_cleanup_scheduler(interval: int = 3600):
    """
    Start background thread to periodically clean up old rate limit files.
    
    Args:
        interval: Cleanup interval in seconds (default 1 hour)
    """
    import threading
    
    def cleanup_worker():
        while True:
            time.sleep(interval)
            try:
                cleanup_rate_limits()
            except Exception as e:
                print(f"Rate limit cleanup error: {e}")
    
    thread = threading.Thread(target=cleanup_worker, daemon=True)
    thread.start()


# =============================================================================
# EXAMPLE USAGE
# =============================================================================

if __name__ == '__main__':
    """
    Example usage and testing
    """
    
    # Create test limiter
    limiter = FileBasedRateLimiter('/tmp/test_rate_limits')
    
    # Test rate limiting
    print("Testing rate limiter...")
    
    for i in range(15):
        result = limiter.increment('test_ip', 10, 60)
        status = "✓ ALLOWED" if result['allowed'] else "✗ BLOCKED"
        print(f"Request {i+1}: {status} (count: {result['count']}, remaining: {result['remaining']})")
    
    # Get stats
    stats = limiter.get_stats()
    print(f"\nStatistics: {stats}")
    
    # Cleanup
    limiter.cleanup(0)
    print("\nCleanup complete!")