from django.contrib import admin
from django.urls import path, include
from auth_jwt.views import CustomTokenObtainPairView, CustomTokenRefreshView, LogoutView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/parsing/', include('parsing.urls')),
    path('api/auth/token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/auth/token/refresh/', CustomTokenRefreshView.as_view(), name='token_refresh'),
    path('api/auth/logout/', LogoutView.as_view(), name='logout'),
]