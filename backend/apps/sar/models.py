"""
Django ORM models for DRIFT backend.

GeoJSON is stored as JSONField (MVP).
P2: migrate to PostGIS GeometryField for spatial queries.
"""

import uuid

from django.db import models


class Prediction(models.Model):
    """One distress event → one Prediction record."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # ── Input fields (mirror PredictionRequest)
    vessel_id = models.CharField(max_length=100, null=True, blank=True)
    last_lon = models.FloatField()
    last_lat = models.FloatField()
    last_seen_at = models.DateTimeField()
    vessel_type = models.CharField(max_length=50)
    tonnage_tons = models.FloatField(null=True, blank=True)
    simulation_hours = models.IntegerField(default=6)
    notes = models.TextField(blank=True, null=True)

    # ── Engine output — full EnginePredictionResult JSON
    # P2: extract search_zones → PostGIS MultiPolygon
    engine_result = models.JSONField(null=True, blank=True)
    engine_version = models.CharField(max_length=50, default="mock-1.0")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "sar_prediction"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Prediction({self.vessel_id or 'unknown'} @ {self.created_at:%Y-%m-%d %H:%M})"


class Briefing(models.Model):
    """One-to-one extension of Prediction with the LLM briefing."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    prediction = models.OneToOneField(
        Prediction, on_delete=models.CASCADE, related_name="briefing"
    )
    briefing_result = models.JSONField()
    pdf_url = models.URLField(max_length=2000, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "sar_briefing"

    def __str__(self) -> str:
        return f"Briefing({self.prediction_id})"
