from types import SimpleNamespace
from datetime import datetime, timezone as dt_tz
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.tokens import RefreshToken
from .utils import get_user_by_email, verify_laravel_password
from .models import UserToken

class ExternalTokenObtainPairSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        user = get_user_by_email(attrs["email"])
        if not user or not verify_laravel_password(attrs["password"], user["password"]):
            raise AuthenticationFailed("Invalid credentials")

        # объект-заглушка с полем id — достаточно для SimpleJWT
        stub = SimpleNamespace(id=user["id"])
        refresh = RefreshToken.for_user(stub)
        access = refresh.access_token

        # Чистим старые access
        UserToken.objects.filter(user_id=user["id"], token_type="access").delete()

        # Пишем новые токены
        UserToken.objects.create(
            user_id=user["id"],
            jti=str(refresh["jti"]),
            token_type="refresh",
            expires_at=datetime.fromtimestamp(int(refresh["exp"]), dt_tz.utc),
        )
        UserToken.objects.create(
            user_id=user["id"],
            jti=str(access["jti"]),
            token_type="access",
            expires_at=datetime.fromtimestamp(int(access["exp"]), dt_tz.utc),
        )

        return {"refresh": str(refresh), "access": str(access)}