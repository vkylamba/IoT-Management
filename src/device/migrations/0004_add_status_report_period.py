from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('device', '0003_create_devicestatus_timeseries'),
    ]

    operations = [
        migrations.AddField(
            model_name='statustype',
            name='report_period',
            field=models.CharField(blank=True, choices=[('yesterday', 'yesterday'), ('week', 'week'), ('month', 'month')], max_length=255, null=True),
        ),
    ]