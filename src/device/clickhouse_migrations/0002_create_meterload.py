from django_clickhouse import migrations
from device.clickhouse_models.data import (
    MeterLoad
)

class Migration(migrations.Migration):
    operations = [
        migrations.CreateTable(MeterLoad)
    ]
