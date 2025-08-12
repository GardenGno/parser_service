# auth_jwt/authentication.py
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken
from .models import UserToken, ExternalUser

class DBJWTAuthentication(JWTAuthentication):
    def get_validated_token(self, raw_token):
        token = super().get_validated_token(raw_token)
        jti = token.get("jti")
        if not jti:
            raise InvalidToken("Token missing jti")
        if not UserToken.objects.filter(jti=jti, revoked=False).exists():
            raise AuthenticationFailed("Token revoked or not found")
        return token

    def get_user(self, validated_token):
        user_id = validated_token.get("user_id")
        if user_id is None:
            raise InvalidToken("Token missing user_id")

        try:
            user = ExternalUser.objects.get(pk=int(user_id))
        except ExternalUser.DoesNotExist:
            raise AuthenticationFailed("User not found")

        return user