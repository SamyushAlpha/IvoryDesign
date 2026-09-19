import hashlib
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import HttpResponsePermanentRedirect, JsonResponse
from django.utils import timezone


def client_fingerprint(request):
    """Return a non-reversible key suitable for abuse controls."""
    address = request.META.get("REMOTE_ADDR", "unknown")
    if settings.IVORY_TRUST_PROXY_HEADERS:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            address = forwarded.split(",", 1)[0].strip() or address
    return hashlib.sha256(address.encode()).hexdigest()


def rate_limited(request, scope, *, limit, window, identity=None):
    """Database-backed limiter shared by every application instance."""
    from .models import SecurityThrottle

    fingerprint = identity or client_fingerprint(request)
    digest = hashlib.sha256(fingerprint.encode()).hexdigest()
    key = f"{scope}:{digest}"
    now = timezone.now()
    window_ends = now + timedelta(seconds=window)
    for attempt in range(2):
        try:
            with transaction.atomic():
                throttle = SecurityThrottle.objects.select_for_update().filter(key=key).first()
                if throttle is None:
                    SecurityThrottle.objects.create(key=key, count=1, window_ends=window_ends)
                    return False
                if throttle.window_ends <= now:
                    throttle.count = 1
                    throttle.window_ends = window_ends
                else:
                    throttle.count += 1
                throttle.save(update_fields=("count", "window_ends"))
                return throttle.count > limit
        except IntegrityError:
            if attempt:
                return True
    return True


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.setdefault(
            "Permissions-Policy",
            "camera=(), geolocation=(), payment=(), usb=(), microphone=(self)",
        )
        response.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "base-uri 'self'; form-action 'self'; frame-ancestors 'none'; object-src 'none'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.tailwindcss.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com; "
            "font-src 'self' data: https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
            "img-src 'self' data: blob: https:; media-src 'self' blob: https:; "
            "connect-src 'self' https: wss:; worker-src 'self' blob:",
        )
        return response


class CanonicalHostMiddleware:
    """Consolidate the legacy indexed Vercel hostname under the public brand URL."""

    LEGACY_HOSTS = {"ivory-design.vercel.app", "www.ivory-design.vercel.app"}
    CANONICAL_ORIGIN = "https://ivoryarvena.vercel.app"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        hostname = request.get_host().split(":", 1)[0].lower()
        if hostname in self.LEGACY_HOSTS:
            return HttpResponsePermanentRedirect(
                f"{self.CANONICAL_ORIGIN}{request.get_full_path()}"
            )
        return self.get_response(request)


class AdminLoginRateLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == "/my-lo/login/" and request.method == "POST":
            if rate_limited(request, "admin-login", limit=8, window=900):
                response = JsonResponse(
                    {"error": "Too many sign-in attempts. Please wait 15 minutes."},
                    status=429,
                )
                response["Retry-After"] = "900"
                return response
        return self.get_response(request)
