"""Security Headers Middleware - SSRF protection, CSP, etc."""
from django.utils.deprecation import MiddlewareMixin
from django.http import JsonResponse
from urllib.parse import urlparse

class SecurityHeadersMiddleware(MiddlewareMixin):
    """Add security headers and SSRF protection."""
    
    BLOCKED_HOSTS = {
        "localhost", "127.0.0.1", "0.0.0.0",
        "169.254.169.254", "metadata.google.internal", "metadata.azure.com",
    }
    
    BLOCKED_PREFIXES = (
        "10.", "192.168.", "172.16.", "172.17.", "172.18.", "172.19.",
        "172.20.", "172.21.", "172.22.", "172.23.", "172.24.", "172.25.",
        "172.26.", "172.27.", "172.28.", "172.29.", "172.30.", "172.31.",
        "192.168.", "10.", "127.", "0.0.0.0", "::1", "fe80::",
    )
    
    def process_response(self, request, response):
        # Security headers
        response["X-Content-Type-Options"] = "nosniff"
        response["X-Frame-Options"] = "DENY"
        response["X-XSS-Protection"] = "1; mode=block"
        response["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        )
        response["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        return response
    
    def process_view(self, request, view_func, view_args, view_kwargs):
        # Check for SSRF in URL parameters
        for key, value in request.GET.items():
            if key.lower() in ('url', 'redirect', 'next', 'callback', 'webhook', 'endpoint'):
                if self._is_blocked_url(value):
                    return JsonResponse({
                        "error": "Invalid URL: blocked for security"
                    }, status=400)
        return None
    
    def _is_blocked_url(self, url: str) -> bool:
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            hostname = parsed.hostname or ""
            
            if hostname in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
                return True
            
            for prefix in ("10.", "192.168.", "172.16.", "172.17.", "172.18.", 
                          "172.19.", "172.20.", "172.21.", "172.22.", "172.23.",
                          "172.24.", "172.25.", "172.26.", "172.27.", "172.28.",
                          "172.29.", "172.30.", "172.31.", "192.168.", "10.",
                          "127.", "0.0.0.0", "::1", "fe80::"):
                if hostname.startswith(prefix):
                    return True
            
            if hostname in ("169.254.169.254", "metadata.google.internal", 
                           "metadata.azure.com", "metadata"):
                return True
            
            return False
        except Exception:
            return True  # Block on parse error
