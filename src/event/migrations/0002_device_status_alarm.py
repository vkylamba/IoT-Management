# Generated manually for device status alarms

from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("event", "0001_initial"),
        ("device", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="DeviceStatusAlarm",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(blank=True, max_length=255, null=True)),
                ("status_key", models.CharField(max_length=255)),
                (
                    "operator",
                    models.CharField(
                        choices=[
                            ("eq", "Equals"),
                            ("neq", "Not Equals"),
                            ("gt", "Greater Than"),
                            ("gte", "Greater Than or Equals"),
                            ("lt", "Less Than"),
                            ("lte", "Less Than or Equals"),
                            ("contains", "Contains"),
                        ],
                        default="eq",
                        max_length=16,
                    ),
                ),
                ("target_value", models.CharField(max_length=255)),
                ("channels", models.JSONField(blank=True, default=list)),
                ("emails", models.TextField(blank=True, null=True)),
                ("telegram_chat_ids", models.TextField(blank=True, null=True)),
                ("active", models.BooleanField(default=True)),
                ("last_evaluation_match", models.BooleanField(default=False)),
                ("last_trigger_time", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "device",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="status_alarms",
                        to="device.device",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="status_alarms",
                        to="device.user",
                    ),
                ),
            ],
            options={"verbose_name_plural": "Device status alarms"},
        ),
        migrations.CreateModel(
            name="DeviceStatusAlarmHistory",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("triggered_at", models.DateTimeField(auto_now_add=True)),
                ("status_value", models.CharField(blank=True, max_length=255, null=True)),
                ("status_snapshot", models.JSONField(blank=True, null=True)),
                ("channels", models.JSONField(blank=True, default=list)),
                ("message", models.TextField(blank=True, null=True)),
                (
                    "alarm",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="history",
                        to="event.devicestatusalarm",
                    ),
                ),
                (
                    "device",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="status_alarm_history",
                        to="device.device",
                    ),
                ),
            ],
            options={"verbose_name_plural": "Device status alarm history"},
        ),
    ]
