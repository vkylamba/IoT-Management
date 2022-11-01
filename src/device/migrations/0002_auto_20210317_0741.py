# Generated by Django 2.2 on 2021-03-17 07:41

import django.contrib.postgres.fields.jsonb
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('device', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='devicetype',
            name='other_data',
            field=django.contrib.postgres.fields.jsonb.JSONField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='meter',
            name='meter_type',
            field=models.CharField(choices=[('AC_METER', 'AC_METER'), ('DC_METER', 'DC_METER'), ('HOUSEHOLD_AC_METER', 'HOUSEHOLD_AC_METER'), ('INVETER_AC_METER', 'INVETER_AC_METER'), ('INVETER_DC_METER', 'INVETER_DC_METER'), ('WEATHER_METER', 'WEATHER_METER')], max_length=50),
        ),
    ]
