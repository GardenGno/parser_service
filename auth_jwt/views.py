from datetime import datetime, timezone as dt_tz
from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken, AccessToken
from rest_framework_simplejwt.views import TokenRefreshView
from .serializers import ExternalTokenObtainPairSerializer
from .models import UserToken

class CustomTokenObtainPairView(APIView):
    permission_classes = [permissions.AllowAny]
    def post(self, request):
        ser = ExternalTokenObtainPairSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        return Response(ser.validated_data, status=200)

class CustomTokenRefreshView(TokenRefreshView):
    permission_classes = [permissions.AllowAny]
    def post(self, request, *args, **kwargs):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response({"detail": "refresh token required"}, status=400)

        try:
            rt = RefreshToken(refresh_token)
            jti = str(rt["jti"])
            user_id = int(rt["user_id"])
            token_obj = UserToken.objects.filter(jti=jti, token_type="refresh", revoked=False).first()
            if not token_obj:
                return Response({"detail": "refresh token revoked or not found"}, status=401)
            if token_obj.expires_at < datetime.now(dt_tz.utc):
                return Response({"detail": "refresh token expired"}, status=401)
        except Exception:
            return Response({"detail": "invalid refresh token"}, status=400)

        UserToken.objects.filter(user_id=user_id, token_type="access").delete()
        response = super().post(request, *args, **kwargs)

        if response.status_code == 200 and "access" in response.data:
            new_access = AccessToken(response.data["access"])
            UserToken.objects.create(
                user_id=user_id,
                jti=str(new_access["jti"]),
                token_type="access",
                expires_at=datetime.fromtimestamp(int(new_access["exp"]), dt_tz.utc),
            )
        return response

class LogoutView(APIView):
    permission_classes = (permissions.IsAuthenticated,)
    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response({"detail": "refresh token required"}, status=400)
        try:
            rt = RefreshToken(refresh_token)
            jti = str(rt["jti"])
            user_id = int(rt["user_id"])

            UserToken.objects.filter(jti=jti, token_type="refresh").update(revoked=True)
            UserToken.objects.filter(user_id=user_id, token_type="access", revoked=False).update(revoked=True)

            # на всякий случай — отзовём access из заголовка
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                try:
                    access_jti = str(AccessToken(auth_header.split(" ")[1])["jti"])
                    UserToken.objects.filter(jti=access_jti).update(revoked=True)
                except Exception:
                    pass
            return Response(status=204)
        except Exception:
            return Response({"detail": "invalid token"}, status=400)