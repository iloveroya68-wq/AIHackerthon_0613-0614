from django.urls import path

from .views import (
    ChatView,
    HealthView,
    PredictionBriefingView,
    PredictionCreateView,
    PredictionDetailView,
    RiskForecastView,
)

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("chat/", ChatView.as_view(), name="chat"),
    path("predictions/", PredictionCreateView.as_view(), name="prediction-create"),
    path("predictions/<str:pk>/", PredictionDetailView.as_view(), name="prediction-detail"),
    path("predictions/<str:pk>/briefing/", PredictionBriefingView.as_view(), name="prediction-briefing"),
    path("risk/forecast/", RiskForecastView.as_view(), name="risk-forecast"),
]
