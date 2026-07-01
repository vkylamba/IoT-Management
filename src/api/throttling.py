"""
API rate limiting with Redis-backed moving window implementation.
Provides configurable throttling per user and per device for data ingestion.
"""
import time
from collections import OrderedDict

from django.conf import settings
from django.core.cache import cache
from rest_framework.throttling import BaseThrottle
from rest_framework.response import Response


class MovingWindowRateLimiter:
    """
    Moving window rate limiter using Redis for fast, distributed rate limiting.
    
    Tracks request timestamps in a moving window. When a new request arrives,
    it checks how many requests fall within the window and decides to allow or deny.
    """
    
    def __init__(self, window_seconds, max_requests):
        """
        Args:
            window_seconds: Time window in seconds
            max_requests: Maximum requests allowed within the window
        """
        self.window = window_seconds
        self.max_requests = max_requests
    
    def is_allowed(self, key):
        """
        Check if request is allowed within the moving window.
        
        Args:
            key: Unique identifier (e.g., "user:1" or "device:123")
            
        Returns:
            tuple: (allowed: bool, count: int, reset_in: int)
        """
        current_time = time.time()
        window_start = current_time - self.window
        
        # Get all timestamps from cache
        cache_key = f"rate_limit:{key}"
        timestamps = cache.get(cache_key, [])
        
        # Remove timestamps outside the window
        timestamps = [ts for ts in timestamps if ts > window_start]
        
        # Check if limit exceeded
        allowed = len(timestamps) < self.max_requests
        
        if allowed:
            # Add current timestamp
            timestamps.append(current_time)
        
        # Store updated timestamps (TTL = window size + 10s buffer)
        cache.set(cache_key, timestamps, self.window + 10)
        
        # Calculate time until oldest request exits the window
        reset_in = int((timestamps[0] - window_start) + 1) if timestamps else self.window
        
        return allowed, len(timestamps), reset_in


class DataIngestionUserThrottle(BaseThrottle):
    """
    Throttle for user-level rate limiting on data ingestion.
    Default: 10 requests per minute per user.
    Configurable via RATE_LIMIT_USER_REQUESTS and RATE_LIMIT_USER_WINDOW_SECONDS in settings.
    """
    
    def __init__(self):
        max_requests = getattr(
            settings, 
            'RATE_LIMIT_USER_REQUESTS', 
            10
        )
        window_seconds = getattr(
            settings, 
            'RATE_LIMIT_USER_WINDOW_SECONDS', 
            60
        )
        self.limiter = MovingWindowRateLimiter(window_seconds, max_requests)
        self.throttle_message = f"User rate limit exceeded: {max_requests} requests per {window_seconds}s"
    
    def get_ident(self, request):
        """Get user identifier from request."""
        user = getattr(request, 'user', None)
        if user and user.is_authenticated:
            return f"user:{user.id}"
        
        # For device-based auth, use IP + User-Agent
        return f"anon:{self._get_client_ip(request)}"
    
    def _get_client_ip(self, request):
        """Extract client IP from request."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    def throttle_success(self, request):
        """Called when request should be allowed."""
        return True
    
    def throttle_failure(self, request):
        """Called when throttle is triggered."""
        return False
    
    def allow_request(self, request):
        """Determine if the request should be throttled."""
        ident = self.get_ident(request)
        allowed, count, reset_in = self.limiter.is_allowed(ident)
        
        if not allowed:
            self.wait_seconds = reset_in
            return self.throttle_failure(request)
        
        return self.throttle_success(request)
    
    def throttle_success(self, request):
        return True
    
    def throttle_failure(self, request):
        return False


class DataIngestionDeviceThrottle(BaseThrottle):
    """
    Throttle for device-level rate limiting on data ingestion.
    Default: 1 request per minute per device.
    Configurable via RATE_LIMIT_DEVICE_REQUESTS and RATE_LIMIT_DEVICE_WINDOW_SECONDS in settings.
    """
    
    def __init__(self):
        max_requests = getattr(
            settings, 
            'RATE_LIMIT_DEVICE_REQUESTS', 
            1
        )
        window_seconds = getattr(
            settings, 
            'RATE_LIMIT_DEVICE_WINDOW_SECONDS', 
            60
        )
        self.limiter = MovingWindowRateLimiter(window_seconds, max_requests)
        self.throttle_message = f"Device rate limit exceeded: {max_requests} request per {window_seconds}s"
    
    def allow_request(self, request):
        """Determine if the request should be throttled."""
        # Get device from request
        device = getattr(request, 'device', None)
        if not device:
            # If no device, don't throttle at device level
            return True
        
        ident = f"device:{device.id}"
        allowed, count, reset_in = self.limiter.is_allowed(ident)
        
        if not allowed:
            self.wait_seconds = reset_in
            return False
        
        return True


class CompositeDataIngestionThrottle(BaseThrottle):
    """
    Composite throttle that applies both user-level and device-level rate limiting.
    Both user and device limits must be satisfied for request to be allowed.
    """
    
    def __init__(self):
        self.user_throttle = DataIngestionUserThrottle()
        self.device_throttle = DataIngestionDeviceThrottle()
        self.throttle_message = None
    
    def allow_request(self, request):
        """Check both user and device limits."""
        # Check user limit
        if not self.user_throttle.allow_request(request):
            self.throttle_message = self.user_throttle.throttle_message
            self.wait_seconds = getattr(self.user_throttle, 'wait_seconds', 60)
            return False
        
        # Check device limit
        if not self.device_throttle.allow_request(request):
            self.throttle_message = self.device_throttle.throttle_message
            self.wait_seconds = getattr(self.device_throttle, 'wait_seconds', 60)
            return False
        
        return True
    
    def throttle_success(self, request):
        return True
    
    def throttle_failure(self, request):
        return False
