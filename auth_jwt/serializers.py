# auth_jwt/serializers.py
from types import SimpleNamespace
from datetime import datetime, timezone as dt_tz
from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.tokens import RefreshToken
from .models import UserToken, ExternalUser
from .utils import verify_laravel_password

class ExternalTokenObtainPairSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        email = attrs["email"]
        password = attrs["password"]

        user = ExternalUser.objects.filter(email=email).only("id", "password").first()
        if not user or not verify_laravel_password(password, user.password):
            raise AuthenticationFailed("Invalid credentials")

        # Можно использовать сам ORM-объект — SimpleJWT возьмёт user.id
        refresh = RefreshToken.for_user(user)
        access = refresh.access_token

        with transaction.atomic():
            # Чистим старые access
            UserToken.objects.filter(user_id=user.id, token_type="access").delete()

            # Пишем новые токены
            UserToken.objects.create(
                user_id=user.id,
                jti=str(refresh["jti"]),
                token_type="refresh",
                expires_at=datetime.fromtimestamp(int(refresh["exp"]), dt_tz.utc),
            )
            UserToken.objects.create(
                user_id=user.id,
                jti=str(access["jti"]),
                token_type="access",
                expires_at=datetime.fromtimestamp(int(access["exp"]), dt_tz.utc),
            )

        return {"refresh": str(refresh), "access": str(access)}