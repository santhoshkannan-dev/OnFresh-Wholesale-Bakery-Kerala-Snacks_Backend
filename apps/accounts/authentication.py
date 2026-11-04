from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, AuthenticationFailed
from django.conf import settings


class CookieJWTAuthentication(JWTAuthentication):
    """
    Custom JWT Authentication that supports:
    1. Standard 'Authorization: Bearer <token>' headers (ideal for external APIs and tests).
    2. Secure HttpOnly cookies (ideal for Next.js browser sessions).
    """

    def authenticate(self, request):
        # 1. Try standard Authorization header first
        header = self.get_header(request)
        if header is not None:
            raw_token = self.get_raw_token(header)
            if raw_token is not None:
                validated_token = self.get_validated_token(raw_token)
                return self.get_user(validated_token), validated_token

        # 2. Fall back to HttpOnly cookie
        cookie_name = getattr(settings, 'JWT_AUTH_COOKIE', 'onfresh_access_token')
        raw_token = request.COOKIES.get(cookie_name)

        if raw_token is None:
            return None

        try:
            validated_token = self.get_validated_token(raw_token)
            return self.get_user(validated_token), validated_token
        except (InvalidToken, AuthenticationFailed):
            # If the cookie has expired or is invalid, return None so AllowAny views work,
            # or raise so protected views return 401
            return None

