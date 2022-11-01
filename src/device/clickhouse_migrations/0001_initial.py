from django_clickhouse import migrations
from device.clickhouse_models.data import (
    RawData,
    Meter,
    MeterData,
    WeatherData,
    DerivedData
)

class Migration(migrations.Migration):
    operations = [
        migrations.CreateTable(RawData),
        migrations.CreateTable(Meter),
        migrations.CreateTable(MeterData),
        migrations.CreateTable(WeatherData),
        migrations.CreateTable(DerivedData)
    ]
