# Generated manually for alarm refactor to EventType + DeviceEvent

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("event", "0002_device_status_alarm"),
    ]

    operations = [
        migrations.AddField(
            model_name="eventtype",
            name="is_alarm_type",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="eventtype",
            name="status_key",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="eventtype",
            name="operator",
            field=models.CharField(blank=True, max_length=16, null=True),
        ),
        migrations.AddField(
            model_name="eventtype",
            name="target_value",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="deviceevent",
            name="actions_config",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="deviceevent",
            name="last_evaluation_match",
            field=models.BooleanField(default=False),
        ),
        migrations.DeleteModel(name="DeviceStatusAlarmHistory"),
        migrations.DeleteModel(name="DeviceStatusAlarm"),
    ]
