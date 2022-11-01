from django.core.management.base import BaseCommand

from device.models import (
    Meter as MeterModelPostgres,
    MeterData as MeterDataModelPostgres
)


# from device.clickhouse_models.data import (
#     Meter as MeterModelClickhouse,
#     MeterData as MeterDataModelClickhouse
# )

# from django_clickhouse.tasks import sync_clickhouse_model, clickhouse_auto_sync


class Command(BaseCommand):

    def handle(self, *args, **kwargs):
        # data = MeterModelPostgres.objects.all()[0]
        # for i in range(0, 10):
        #     data.pk = None
        #     data.save()


        data = MeterDataModelPostgres.objects.all()[0]
        for i in range(0, 1):
            data.pk = None
            data.save()
        # sync_clickhouse_model(MeterDataModelClickhouse)
        # sync_clickhouse_model.delay(MeterDataModelClickhouse)

        # clickhouse_auto_sync()
        # res = clickhouse_auto_sync.delay()
        pass
