from django_clickhouse import migrations
from device.clickhouse_models.data import (
    MeterData,
    WeatherData,
    DerivedData
)

class Migration(migrations.Migration):
    operations = [
        migrations.CreateTable(MeterData),
        migrations.CreateTable(WeatherData),
        migrations.CreateTable(DerivedData)
    ]
