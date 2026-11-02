# Require CSRF protection for guest mutations even when no user is logged in.
from rest_framework.authentication import SessionAuthentication


class GuestSessionCSRF(SessionAuthentication):
    """SessionAuthentication normally skips CSRF for anonymous users; we don't."""
    def authenticate(self, request):
        self.enforce_csrf(request)
        return None  # Ownership comes from the server-side guest session, not login.
