from django.utils.cache import patch_cache_control

# Answers from these paths are about someone's data right now (and the login
# one holds a token), so phones and proxies must never keep a copy (SO/BE14).
NO_STORE_PATHS = ('/api/', '/api-auth/')


class NoStoreApiMiddleware:
    """Add `Cache-Control: no-store` to every API answer, errors included.
    Static files are served by WhiteNoise before this and keep their caching."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith(NO_STORE_PATHS):
            patch_cache_control(response, no_store=True)
        return response
