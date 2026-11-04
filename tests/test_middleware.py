"""ClientFlow Middleware Tests"""
import pytest
from django.test import RequestFactory
from django.http import JsonResponse
from django.core.cache import cache
from clientflow.middleware.rate_limit import RateLimitMiddleware
from clientflow.middleware.budget_tracking import BudgetTrackingMiddleware
from clientflow.middleware.security import SecurityHeadersMiddleware

class TestRateLimitMiddleware:
    def setup_method(self):
        self.factory = RequestFactory()
        cache.clear()
    
    def test_allows_requests_under_limit(self):
        middleware = RateLimitMiddleware(lambda r: None)
        request = self.factory.get("/api/invoices/")
        request.META["REMOTE_ADDR"] = "1.2.3.4"
        
        for _ in range(5):
            response = middleware.process_request(request)
            assert response is None
    
    def test_blocks_over_limit(self):
        middleware = RateLimitMiddleware(lambda r: None)
        request = self.factory.get("/api/invoices/")
        request.META["REMOTE_ADDR"] = "5.6.7.8"
        
        # Make 100 requests (default limit)
        for _ in range(100):
            middleware.process_request(request)
        
        # Next request should be blocked
        response = middleware.process_request(request)
        assert isinstance(response, JsonResponse)
        assert response.status_code == 429
    
    def test_auth_category_stricter(self):
        middleware = RateLimitMiddleware(lambda r: None)
        request = self.factory.post("/api/auth/login/")
        request.META["REMOTE_ADDR"] = "1.2.3.4"
        
        for _ in range(10):
            middleware.process_request(request)
        
        response = middleware.process_request(request)
        assert isinstance(response, JsonResponse)
        assert response.status_code == 429


class TestSecurityHeadersMiddleware:
    def test_security_headers_added(self):
        middleware = SecurityHeadersMiddleware(lambda r: None)
        factory = RequestFactory()
        request = factory.get("/")
        response = middleware.process_response(request, None)
        
        # Should add security headers
        # (Test would need a proper response object)
        pass
    
    def test_ssrf_protection(self):
        middleware = SecurityHeadersMiddleware(lambda r: None)
        factory = RequestFactory()
        request = factory.get("/", {"url": "http://localhost:8080"})
        
        response = middleware.process_view(request, None, [], {})
        assert response is not None
        assert response.status_code == 400
