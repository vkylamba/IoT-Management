from datetime import datetime
from uuid import UUID, uuid4

from django.conf import settings
from django.db import models
from django_clickhouse.clickhouse_models import (ClickHouseModel,
                                                 ClickHouseModelMeta)
from django_clickhouse.engines import MergeTree
from infi.clickhouse_orm import fields
from infi.clickhouse_orm.utils import escape


class ForeignKeyField(fields.Field):
    class_default = UUID(int=0)

    min_value = 0
    max_value = 2**64 - 1

    __related_model = None

    def __init__(self, model: ClickHouseModel, *args, **kwargs):
        self.__related_model = model
        if isinstance(self.__related_model, ClickHouseModelMeta):
            self.db_type = 'UUID'
        else:
            self.db_type = 'UInt64'
        super(ForeignKeyField, self).__init__(*args, **kwargs)

    def to_python(self, value, timezone_in_use):

        if isinstance(value, ClickHouseModel):
            return value.id
        if isinstance(value, models.Model):
            return value.pk

        if isinstance(self.__related_model, ClickHouseModelMeta):
            return self.to_python_uuid(value, timezone_in_use)

        return super(ForeignKeyField, self).to_python(value, timezone_in_use)

    def to_python_uuid(self, value, timezone_in_use):
        if isinstance(value, UUID):
            return value
        elif isinstance(value, bytes):
            return UUID(bytes=value)
        elif isinstance(value, str):
            return UUID(value)
        elif isinstance(value, int):
            return UUID(int=value)
        elif isinstance(value, tuple):
            return UUID(fields=value)
        else:
            raise ValueError('Invalid value for UUIDField: %r' % value)

    def to_db_string(self, value, quote=True):
        '''
            Returns the field's value prepared for writing to the database.
            When quote is true, strings are surrounded by single quotes.
        '''
        if isinstance(self.__related_model, ClickHouseModelMeta):
            return escape(str(value), quote)
        return escape(value, quote)

    def get_sql(self, with_default_expression=True, db=None):
        '''
        Returns an SQL expression describing the field (e.g. for CREATE TABLE).
        - `with_default_expression`: If True, adds default value to sql.
            It doesn't affect fields with alias and materialized values.
        - `db`: Database, used for checking supported features.
        '''
        sql = self.db_type
        return sql

class RawData(ClickHouseModel):
    """
        Model to store raw data received from device.
    """

    id = fields.UUIDField()
    device = ForeignKeyField('Device')
    data_arrival_time = fields.DateTimeField()
    data = fields.StringField()

    engine = MergeTree('data_arrival_time', ('device', ))


class Meter(ClickHouseModel):
    """
        Meter model.
    """
    AC_METER = 'AC_METER'
    DC_METER = 'DC_METER'
    HOUSEHOLD_AC_METER = 'HOUSEHOLD_AC_METER'
    LOAD_AC_METER = 'LOAD_AC_METER'
    LOAD_DC_METER = 'LOAD_DC_METER'
    INVERTER_AC_METER = 'INVERTER_AC_METER'
    INVERTER_DC_METER = 'INVERTER_DC_METER'
    WEATHER_METER = 'WEATHER_METER'
    IMPORT_ENERGY_METER = 'IMPORT_ENERGY_METER'
    EXPORT_ENERGY_METER = 'EXPORT_ENERGY_METER'

    id = fields.UUIDField()
    name = fields.StringField()
    device = ForeignKeyField('Device')
    meter_type = fields.StringField()

    engine = MergeTree(partition_key=('name', ), order_by=('device', 'name'))

class MeterData(ClickHouseModel):
    """
        Model to store data from devices.
    """

    id = fields.UUIDField()
    # Device to which this data belongs to
    meter = ForeignKeyField(Meter)
    data_arrival_time = fields.DateTimeField()
    voltage = fields.Float64Field()
    current = fields.Float64Field()
    power = fields.Float64Field()
    frequency = fields.Float64Field()
    energy = fields.Float64Field()
    # Run time seconds
    runtime = fields.Int64Field()
    humidity = fields.Float64Field()
    temperature = fields.Float64Field()
    latitude = fields.StringField()
    longitude = fields.StringField()

    state = fields.Int32Field()

    more_data = fields.StringField()

    cpu_temperature = fields.Float64Field()

    engine = MergeTree('data_arrival_time', ('meter', ))

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "meter": str(self.meter),
            "data_arrival_time": self.data_arrival_time.strftime(settings.TIME_FORMAT_STRING),
            "voltage": round(self.voltage, 2) if self.voltage is not None else None,
            "current": round(self.current, 2) if self.current is not None else None,
            "power": round(self.power, 2) if self.power is not None else None,
            "frequency": round(self.frequency, 2) if self.frequency is not None else None,
            "energy": round(self.energy, 2) if self.energy is not None else None,
            "runtime": self.runtime,
            "humidity": round(self.humidity, 2) if self.humidity is not None else None,
            "temperature": round(self.temperature, 2) if self.temperature is not None else None,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "state": self.state,
            "more_data": self.more_data,
            "cpu_temperature": round(self.cpu_temperature, 2) if self.cpu_temperature is not None else None
        }

class WeatherData(ClickHouseModel):
    """
        Model to store other data related to device.
    """
    id = fields.UUIDField()
    device = ForeignKeyField('Device')
    data_arrival_time = fields.DateTimeField()
    temperature = fields.Int32Field()
    humidity = fields.Int32Field()
    wind_speed = fields.Int32Field()
    more_data = fields.StringField()

    engine = MergeTree('data_arrival_time', ('device', ))


class DerivedData(ClickHouseModel):
    """
        Model to store definitions of user derived data.
    """
    id = fields.UUIDField()
    # Device to which this variable belongs to
    device = ForeignKeyField('Device')
    name = fields.StringField()
    dependent1 = fields.StringField()
    cofficient = fields.DecimalField(precision=8, scale=3)
    offset = fields.DecimalField(precision=8, scale=3)

    engine = MergeTree(partition_key=('device', ), order_by=('device', 'name'))


class MeterLoad(ClickHouseModel):
    """
        Model to store loads running on the device.
    """
    equipment = ForeignKeyField('DeviceEquipment')
    equipment_name = fields.StringField()
    device = ForeignKeyField('Device')
    data_point = ForeignKeyField(MeterData)
    count = fields.Int32Field()
    power = fields.DecimalField(precision=8, scale=3)
    data_arrival_time = fields.DateTimeField()

    engine = MergeTree('data_arrival_time')


def create_model_instance(model: ClickHouseModel, data):
    """
        Method to create model instances
    """
    if 'id' not in data:
        data['id'] = str(uuid4())
    return model.objects.create(**data)
