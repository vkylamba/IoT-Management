from django_clickhouse import migrations
from device.clickhouse_models.data import (
    MeterData
)

class Migration(migrations.Migration):
    operations = [
        migrations.AlterTable(MeterData)
    ]
