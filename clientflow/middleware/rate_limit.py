"""Rate Limiting Middleware - Per-tenant adaptive rate limiting"""
import time
from collections import defaultdict
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin
from django.core.cache import cache

class RateLimitMiddleware(MiddlewareMixin):
    """Adaptive rate limiting per tenant/user."""
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.default_limits = {
            "default": (100, 60),      # 100 req/min
            "api": (200, 60),          # 200 req/min for API
            "auth": (10, 60),          # 10 req/min for auth
            "webhook": (50, 60),       # 50 req/min for webhooks
        }
        super().__init__(get_response)
    
    def process_request(self, request):
        # Determine limit category
        category = self._get_category(request)
        max_requests, window = self.default_limits.get(category, (100, 60))
        
        # Get client identifier
        identifier = self._get_identifier(request)
        cache_key = f"ratelimit:{category}:{identifier}"
        
        # Get current count
        current = cache.get(cache_key, 0)
        
        if current >= self.default_limits[category][0]:
            return JsonResponse({
                "error": "Rate limit exceeded",
                "limit": self.default_limits[category][0],
                "window_seconds": 60,
                "retry_after": 60,
            }, status=429)
        
        # Increment counter
        cache.set(cache_key, current + 1, 60)
        return None
    
    def _get_category(self, request):
        path = request.path
        if path.startswith("/api/auth/"):
            return "auth"
        elif path.startswith("/api/webhooks/"):
            return "webhook"
        elif path.startswith("/api/"):
            return "api"
        return "default"
    
    def _get_identifier(self, request):
        # Use API key if present, else IP
        auth = request.META.get("HTTP_AUTHORIZATION", "")
        if auth.startswith("Bearer "):
            return f"token:{auth[7:20]}"  # First 13 chars of token
        return f"ip:{request.META.get('REMOTE_ADDR', 'unknown')}"
