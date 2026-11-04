"""Budget Tracking Middleware - Token usage per request"""
import json
import time
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin
from django.core.cache import cache

class BudgetTrackingMiddleware(MiddlewareMixin):
    """Track token usage per API request for budgeting."""
    
    def __init__(self, get_response):
        self.get_response = get_response
        super().__init__(get_response)
    
    def process_request(self, request):
        request._budget_start = time.time()
        return None
    
    def process_response(self, request, response):
        if not request.path.startswith("/api/"):
            return response
        
        # Estimate tokens in response
        content = response.content.decode('utf-8') if response.content else ""
        estimated_tokens = len(content) // 4  # Rough estimate
        
        # Track per user/tenant
        user_id = getattr(request.user, 'id', 'anonymous')
        cache_key = f"budget:{request.user.id if request.user.is_authenticated else 'anon'}"
        
        # Store in cache for budget tracking
        current = cache.get(cache_key, {"total": 0, "requests": 0})
        current["total"] += len(content) // 4
        current["requests"] += 1
        cache.set(cache_key, current, 3600)
        
        # Add budget headers
        response["X-Budget-Tokens"] = str(len(content) // 4)
        response["X-Budget-Total"] = str(cache.get(cache_key, {}).get("total", 0))
        
        return response
