from django_clickhouse import migrations
from device.clickhouse_models.data import (
    Meter,
    MeterLoad,
    DerivedData
)

class Migration(migrations.Migration):
    operations = [
        migrations.AlterTable(MeterLoad),
        migrations.AlterTable(Meter),
        migrations.AlterTable(DerivedData),
    ]
