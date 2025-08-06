from django.urls import path
from .views import StartParseView, ParseStatusView

urlpatterns = [
    path("start/", StartParseView.as_view()),
    path("status/<int:pk>/", ParseStatusView.as_view()),
]
