from django.contrib import admin

from .models import Briefing, Prediction


@admin.register(Prediction)
class PredictionAdmin(admin.ModelAdmin):
    list_display = ("id", "vessel_id", "vessel_type", "last_lon", "last_lat", "simulation_hours", "created_at")
    list_filter = ("vessel_type",)
    search_fields = ("vessel_id",)
    readonly_fields = ("id", "created_at", "engine_result")


@admin.register(Briefing)
class BriefingAdmin(admin.ModelAdmin):
    list_display = ("id", "prediction", "created_at")
    readonly_fields = ("id", "created_at", "briefing_result")
