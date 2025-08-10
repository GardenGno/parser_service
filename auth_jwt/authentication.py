from dataclasses import dataclass
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken
from .models import UserToken
from .utils import get_user_by_id

@dataclass
class ExternalAuthUser:
    id: int
    email: str = ""
    name: str = ""
    @property
    def is_authenticated(self): return True
    @property
    def is_anonymous(self): return False

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
        user = get_user_by_id(int(user_id))
        if not user:
            raise AuthenticationFailed("User not found")
        return ExternalAuthUser(id=user["id"], email=user["email"], name=user["name"])