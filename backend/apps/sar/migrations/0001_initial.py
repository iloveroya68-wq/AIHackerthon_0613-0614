import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies: list = []

    operations = [
        migrations.CreateModel(
            name="Prediction",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("vessel_id", models.CharField(blank=True, max_length=100, null=True)),
                ("last_lon", models.FloatField()),
                ("last_lat", models.FloatField()),
                ("last_seen_at", models.DateTimeField()),
                ("vessel_type", models.CharField(max_length=50)),
                ("tonnage_tons", models.FloatField(blank=True, null=True)),
                ("simulation_hours", models.IntegerField(default=6)),
                ("notes", models.TextField(blank=True, null=True)),
                ("engine_result", models.JSONField(blank=True, null=True)),
                ("engine_version", models.CharField(default="mock-1.0", max_length=50)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"db_table": "sar_prediction", "ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="Briefing",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                (
                    "prediction",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="briefing",
                        to="sar.prediction",
                    ),
                ),
                ("briefing_result", models.JSONField()),
                ("pdf_url", models.URLField(blank=True, max_length=2000, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"db_table": "sar_briefing"},
        ),
    ]
