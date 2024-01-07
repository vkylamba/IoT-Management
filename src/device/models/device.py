import binascii
import logging
import os
# import ssl
import uuid
from typing import Iterable

# import certifi
import pytz
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.cache import cache
from django.db import models
from django.utils import timezone
# from geoposition.fields import GeopositionField
# from geopy import geocoders
from timezonefinder import TimezoneFinder

from device.clickhouse_models import MeterData

# ctx = ssl.create_default_context(cafile=certifi.where())
# geocoders.options.default_ssl_context = ctx
# geolocator = geocoders.Nominatim(user_agent="iot_server")

logger = logging.getLogger('django')


def get_image_path(instance, filename):
    return os.path.join('photos', str(instance.pk), filename)


class Subnet(models.Model):
    """
    Model to store information about subnets.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    subnet_a = models.IntegerField(help_text='subnet_a')
    subnet_b = models.IntegerField(help_text='subnet_b')
    subnet_c = models.IntegerField(help_text='subnet_c')
    subnet_d = models.IntegerField(help_text='subnet_d')

    class Meta:
        app_label = "device"
        verbose_name = "Subnet"
        verbose_name_plural = "Subnets"
    
    @classmethod
    def get_next(cls):
        last_subnet = cls.objects.all().order_by('-created_at').first()
        if last_subnet is None:
            last_subnet = cls(
               subnet_a=192, 
               subnet_b=168, 
               subnet_c=1,
               subnet_d=0
            )
        else:
            if (last_subnet.subnet_c <= 254):
                last_subnet = cls(
                    subnet_a=last_subnet.subnet_a, 
                    subnet_b=last_subnet.subnet_b, 
                    subnet_c=last_subnet.subnet_c+1,
                    subnet_d=0
                )
            elif (last_subnet.subnet_c <= 254):
                last_subnet = cls(
                    subnet_a=last_subnet.subnet_a, 
                    subnet_b=last_subnet.subnet_b+1, 
                    subnet_c=0,
                    subnet_d=0
                )
            else:
                last_subnet = cls(
                    subnet_a=last_subnet.subnet_a + 1, 
                    subnet_b=0,
                    subnet_c=0,
                    subnet_d=0
                )

        last_subnet.save()
        default_len = 15
        return f"{last_subnet.subnet_a}.{last_subnet.subnet_b}.{last_subnet.subnet_c}.{last_subnet.subnet_d}/{default_len}"

    def __str__(self):
        return f"{self.subnet_a}.{self.subnet_b}.{self.subnet_c}.{self.subnet_d}"


class Operator(models.Model):
    """
    Model to store static information of the operator.

    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(
        max_length=100,
        help_text='Name of the branch'
    )
    address = models.CharField(
        max_length=500,
        help_text='Address of the branch'
    )
    pin_code = models.IntegerField(help_text='PIN code')
    contact_number = models.CharField(
        max_length=20,
        help_text='Contact number'
    )
    avatar = models.ImageField(
        upload_to=get_image_path,
        blank=True,
        null=True,
        help_text='Avatar of the operator'
    )
    
    class Meta:
        app_label = "device"
        verbose_name = "Device Operator"
        verbose_name_plural = "Device Operator"

    def __str__(self):
        return str(self.name) + ": " + str(self.contact_number)


DEVICE_TYPE_CHOICES = (
    ('Home', 'Home'),
    ('Charge Controller', 'Charge Controller'),
    ('DELTA-RPI Inverter', 'DELTA-RPI Inverter'),
    ('WEATHER_STATION', 'WEATHER STATION'),
    ('SOLAR HYBRID INVERTER', 'SOLAR HYBRID INVERTER'),
    ('IOT_GATEWAY', 'IOT_GATEWAY'),
    ('SOLAR_PUMP', 'SOLAR PUMP'),
    ('OTHER', 'OTHER'),
)

class DeviceType(models.Model):

    """
    Stores type information of the devices.
    """
    HOME = 'Home'
    CHARGE_CONTROLLER = 'Charge Controller'
    DELTA_RPI_INVERTER = 'DELTA-RPI Inverter'
    SOLAR_HYBRID_INVERTER = 'SOLAR HYBRID INVERTER'
    WEATHER_STATION = 'WEATHER STATION'
    IOT_GATEWAY = 'IOT_GATEWAY'
    SOLAR_PUMP = 'SOLAR PUMP'
    OTHER = 'OTHER'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(
        max_length=50,
        help_text='Type name'
    )
    details = models.TextField(blank=True, null=True)
    other_data = models.JSONField(blank=True, null=True)
    
    class Meta:
        app_label = "device"
        verbose_name = "Device Type"
        verbose_name_plural = "Device Types"

    def __str__(self):
        return self.name if self.name is not None else self.id


class Device(models.Model):
    """
        Stores static information about the device.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    numeric_id = models.BigIntegerField(blank=True, null=True)
    ip_address = models.CharField(
        unique=True,
        max_length=20,
        help_text='IP address of the device',
        blank=True,
        null=True
    )
    mac = models.CharField(
        max_length=255,
        help_text='Device MAC',
        blank=True,
        null=True
    )
    alias = models.CharField(
        max_length=255,
        help_text='Name of the device',
        blank=True,
        null=True
    )
    types = models.ManyToManyField(DeviceType, blank=True, null=True)
    device_type = models.ForeignKey('UserDeviceType', blank=True, null=True, on_delete=models.DO_NOTHING)
    installation_date = models.DateField(
        blank=True,
        null=True,
        help_text='Device\'s installation date'
    )
    operator = models.ForeignKey(
        Operator,
        blank=True,
        null=True,
        help_text='Operator of the device',
        on_delete=models.CASCADE
    )
    device_contact_number = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text='Contact number of the device.'
    )
    avatar = models.ImageField(
        upload_to=get_image_path,
        blank=True,
        null=True,
        help_text='Avatar of the device'
    )
    position = models.JSONField(
        blank=True,
        null=True
    )
    address = models.TextField(
        blank=True, null=True
    )
    commands = models.ManyToManyField('DevCommand', blank=True, null=True)

    # Access token for the device to push data
    access_token = models.CharField(max_length=40, blank=True, null=True)

    other_data = models.JSONField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    active = models.BooleanField(default=True, blank=True, null=True)

    class Meta:
        unique_together = ('ip_address', )
        app_label = "device"
        verbose_name = "Device"
        verbose_name_plural = "Devices"


    def __str__(self):
        if self.ip_address:
            return self.ip_address 
        if self.mac is not None:
            return self.mac
        if self.alias is not None:
            return self.alias
        return str(self.id)

    def generate_key(self):
        return binascii.hexlify(os.urandom(20)).decode()

    # Overriding save method to generate access token
    def save(self, *args, **kwargs):
        if not self.access_token:
            self.access_token = self.generate_key()
        # if not self.numeric_id:
        #     if self.ip_address:
        #         self.numeric_id = User.address_string_to_numeric(self.ip_address)
        # if self.position:
        #     try:
        #         location = geolocator.reverse("{}, {}".format(self.position.get("latitude"), self.position.get("longitude")))
        #     except Exception as e:
        #         logger.warning(e)
        #     else:
        #         self.address = location.address
        super(self.__class__, self).save(*args, **kwargs)

    def latitude(self):
        if self.position:
            return self.position.get("latitude")
        else:
            return ''

    def longitude(self):
        if self.position:
            return self.position.get("longitude")
        else:
            return ''

    @property
    def type(self):
        try:
            return self.device_type
        except Exception as ex:
            return None
    
    def get_local_time(self):
        """
            Method to return local time for the device.
        """
        device_timezone = self.get_timezone()
        if device_timezone is None:
            dt = timezone.now()
        else:
            dt = timezone.datetime.now(device_timezone)
        return dt

    def get_command(self):
        commands = Command.objects.filter(
            device=self,
            status="P"
        ).order_by("command_in_time")
        if len(commands) > 0:
            return commands[0]
        else:
            return None

    def get_latest_data(self, meter_type=None, split_by_meters=False):
        return self.get_last_data_point(meter_type=meter_type, split_by_meters=split_by_meters)

    def get_last_data_point(self, meter_type=None, split_by_meters=False):
        logger.debug("Fetching latest data point for device {}.".format(self.ip_address))

        if isinstance(meter_type, Iterable):
            cache_key = "{}-{}-{}-last_data_point".format(self.ip_address, '-'.join(meter_type), split_by_meters)
        else:
            cache_key = "{}-{}-{}-last_data_point".format(self.ip_address, meter_type, split_by_meters)

        data = cache.get(cache_key)
        if not data:
            logger.debug("Latest data for device {} not found in cache.".format(self.ip_address))
            meters = self.get_meters()

            if split_by_meters:
                data = {}
                for meter in meters:
                    try:
                        this_data = MeterData.objects.filter(
                            meter=str(meter.id)
                        ).order_by(
                            '-data_arrival_time'
                        )[0]
                        data[meter.name] = this_data.to_dict()
                    except StopIteration:
                        data[meter.name] = None
            else:
                data = MeterData.objects.filter(
                    meter__in=[str(x.id) for x in meters]
                )
                if meter_type is not None:
                    meter_ids = [str(x.id) for x in meters if x.meter_type in meter_type]
                else:
                    meter_ids = [str(x.id) for x in meters]

                if len(meter_ids) == 0:
                    return None

                try:
                    data = MeterData.objects.filter(
                        meter__in=[str(x.id) for x in meters]
                    ).order_by(
                        '-data_arrival_time'
                    )[0]
                except StopIteration:
                    return None
            cache.set(cache_key, data, 600)
        return data

    def get_meters(self):
        """
            Returns the list of meters related to the device.
        """
        meters = Meter.objects.filter(
            device=self.id
        )
        if meters.count() == 0:
            return []
        return meters

    def get_all_equipments(self, meter_id=None):
        """
            Method to return list of equipments of the device.
        """
        logger.debug("Fetching equipment list for device {}.".format(self.ip_address))
        equipments = cache.get("{}-equipments".format(self.ip_address))
        if not equipments:
            logger.debug("Equipment list for device {} not found in cache.".format(self.ip_address))
            equipments = DeviceEquipment.objects.filter(
                device=self
            )
            if meter_id is not None:
                equipments = equipments.filter(
                    meter_id=meter_id
                )

            equipments = equipments.order_by('-equipment__max_power')

            equipments = equipments.select_related('equipment')
            cache.set("{}-equipments".format(self.ip_address), equipments, settings.DEVICE_PROPERTY_UPDATE_DELAY_MINUTES * 60)
        return equipments

    def get_timezone(self):
        """
            Return device timezone.
        """
        timezone_str = cache.get("{}_timezone_str".format(self.ip_address))
        if timezone_str is None:
            if self.position is None:
                logger.warning("Position for the device {} is not defined.".format(self.ip_address))
                timezone_str = ''
            else:
                tf = TimezoneFinder()
                timezone_str = tf.timezone_at(
                    lat=float(self.position.get("latitude")),
                    lng=float(self.position.get("longitude"))
                )
            cache.set("{}_timezone_str".format(self.ip_address), timezone_str, 1 * 60 * 60)
        if timezone_str:
            timezone_obj = pytz.timezone(timezone_str)
        else:
            timezone_obj = None
        return timezone_obj

class DeviceProperty(models.Model):
    """
        Model to store device propertirs.
    """
    INT = 'I'
    FLOAT = 'F'
    STRING = 'S'
    VALUE_TYPES = (
        (INT, 'Int'),
        (FLOAT, 'Float'),
        (STRING, 'String')
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device = models.ForeignKey('Device', blank=True, null=True, on_delete=models.CASCADE)
    user = models.ForeignKey('User', blank=True, null=True, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    value = models.CharField(max_length=255)
    val_type = models.CharField(
        max_length=255, choices=VALUE_TYPES, default=STRING)

    class Meta:
        app_label = "device"
        verbose_name = "Device Property"
        verbose_name_plural = "Device Properties"

    def get_value(self):

        if self.val_type == DeviceProperty.INT:
            return int(self.value)
        elif self.val_type == DeviceProperty.FLOAT:
            return float(self.value)
        else:
            return self.value

    def __str__(self):
        return "{}-{}: {}".format(
            "{}-{}".format(self.user.user.username if self.user else '',
                           self.device.ip_address if self.device else ''),
            self.name,
            self.value
        )


class DeviceEquipment(models.Model):
    """
        Model to store list of equipments for the device.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device = models.ForeignKey('Device', on_delete=models.CASCADE)
    meter_id = models.CharField(max_length=1024, blank=True, null=True)
    equipment = models.ForeignKey('Equipment', on_delete=models.CASCADE)
    quantity = models.IntegerField()

    class Meta:
        app_label = "device"
        verbose_name = 'Device Equipment'
        verbose_name_plural = 'Device Equipments'

    def __str__(self):
        return "{}-{}-{}".format(self.device.ip_address, self.equipment.name, self.quantity)

    def save(self, *args, **kwargs):
        super(self.__class__, self).save(*args, **kwargs)
        cache.delete("{}-equipments".format(self.device.ip_address))


class Equipment(models.Model):
    """
        Class to store load equipments.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, help_text="Name of the equipment")
    max_power = models.IntegerField(
        help_text="Max power consumption of the equipment")
    min_power = models.IntegerField(
        help_text="Min power consumption of the equipment")

    class Meta:
        app_label = "device"
        verbose_name = 'Equipment'
        verbose_name_plural = 'Equipments'

    def __str__(self):
        return "{}".format(self.name)


class DevCommand(models.Model):
    """
        Model to store possible commands for device.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    command_name = models.CharField(
        max_length=255, help_text="Name of command.")
    command_code = models.CharField(max_length=20, help_text="Command code.")
    
    class Meta:
        app_label = "device"
        verbose_name = "Device Command"
        verbose_name_plural = "Device Commands"

    def __str__(self):
        return self.command_name


class Command(models.Model):
    """
    Model to store the remote commands to be executed by the devices
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device = models.ForeignKey(Device, on_delete=models.CASCADE)
    status = models.CharField(
        max_length=1, help_text="Command's status(E:Executed or P:Pending)")
    command_in_time = models.DateTimeField(help_text="Command arrival time")
    command_read_time = models.DateTimeField(
        help_text="Time when the command was read by the remote device", blank=True, null=True)
    command = models.CharField(max_length=20, help_text="Command")
    param = models.CharField(max_length=100, help_text="Command parameter")
    
    class Meta:
        app_label = "device"
        verbose_name = "Command"
        verbose_name_plural = "Commands"

    def __unicode__(self):
        return str(self.device) + ": " + str(self.command_in_time) + ", " + str(self.command) + ", " + str(self.param) + ", " + str(self.status)

    def send(self):
        param = ''
        if self.param is not None:
            param = self.param
        message = str(self.command) + ',' + param + ';'
        # ToDo: send command to device.


class User(AbstractUser):

    """
    Class defining users/owners of the devices

    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    city = models.CharField(max_length=255, blank=True, null=True)
    country = models.CharField(max_length=255, blank=True, null=True)
    phone = models.CharField(max_length=255, blank=True, null=True)
    postal_code = models.CharField(max_length=255, blank=True, null=True)
    description = models.CharField(
        max_length=500,
        help_text="Desc of the user"
    )
    subnet_mask = models.CharField(
        max_length=20,
        help_text="Subnet mask"
    )
    dev_image = models.ImageField(
        upload_to=get_image_path,
        blank=True,
        null=True,
        help_text='Avatar of the device'
    )
    device_data_token = models.CharField(max_length=40, blank=True, null=True)
    permissions = models.ManyToManyField('Permission')
    other_data = models.JSONField(blank=True, null=True)
    
    class Meta:
        app_label = "device"
        verbose_name = "User"
        verbose_name_plural = "Users"

    def generate_key(self):
        return binascii.hexlify(os.urandom(20)).decode()

    def save(self, *args, **kwargs):
        if not self.device_data_token:
            self.device_data_token = self.generate_key()
        super(self.__class__, self).save(*args, **kwargs)

    def __str__(self):
        return str(self.username) + " --> [" + self.subnet_mask + "]"

    @staticmethod
    def address_string_to_numeric(str_address):
        temp_address = str_address.split('.')
        num_address = 0
        i = 0
        while i < len(temp_address):
            num_address *= 256
            num_address += int(temp_address[i]) if temp_address[i] != '' else 0
            i += 1
        return num_address

    @staticmethod
    def address_numeric_to_string(num_address):
        address = [0, 0, 0, 0]
        i = 0
        while num_address > 0:
            address[i] = num_address % 256
            num_address //= 256
            i += 1
        return str(address[3]) + "."\
            + str(address[2]) + "."\
            + str(address[1]) + "."\
            + str(address[0])

    def device_list(self, return_objects=False, device_id=None, return_next_address=False):
        device_list = []
        dev_user = self
        if dev_user.is_superuser:
            max_address = 0
            subnet_end = 0
            device_list = Device.objects.all().select_related('operator')
            if device_id is not None:
                device_list = device_list.filter(ip_address=device_id).first()
            if not return_objects:
                device_list = [dev.ip_address for dev in device_list if dev.active is not False]
        else:
            subnet = dev_user.subnet_mask
            subnet = subnet.split('/')
            if len(subnet) > 1:
                subnet_start = User.address_string_to_numeric(subnet[0].strip())
                subnet_end = subnet_start + int(subnet[1].strip())
            else:
                subnet_start = subnet_end = 0

            if device_id:
                device_id = User.address_string_to_numeric(device_id)
            # Now figure out the devices which belongs to this user
            max_address = subnet_start
            for device in Device.objects.all().select_related('operator'):
                dev_address = device.ip_address
                if dev_address is None or device.active is False:
                    continue
                dev_address = User.address_string_to_numeric(dev_address)
                if subnet_start <= dev_address and dev_address < subnet_end:
                    # The device belongs to this user
                    if device_id is not None and dev_address == device_id:
                        return device
                    if return_objects:
                        device_list.append(device)
                    else:
                        device_list.append(device.ip_address)
                    if max_address is None or dev_address > max_address:
                        max_address = dev_address

        if return_next_address:
            return (
                device_list,
                User.address_numeric_to_string(
                    max_address + 1) if max_address + 1 < subnet_end else None
            )
        return device_list

    def has_permission(self, permission):
        if isinstance(permission, Permission):
            return self.permissions.filter(name=permission.name).exists()
        else:
            return self.permissions.filter(name=permission).exists()


class Permission(models.Model):
    """
        Permissions model for user.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    
    class Meta:
        app_label = "device"
        verbose_name = "Permission"
        verbose_name_plural = "Permissions"

    def __str__(self):
        return f"{self.name}"

class Document(models.Model):
    """
        model to store device documents.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device = models.ForeignKey(Device, blank=True, null=True, on_delete=models.CASCADE)
    user = models.ForeignKey(User, blank=True, null=True, on_delete=models.CASCADE)
    document = models.FileField(
        upload_to=get_image_path,
        blank=True,
        null=True,
    )
    description = models.CharField(
        max_length=1024,
        blank=True,
        null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        app_label = "device"
        verbose_name = "Device Document"
        verbose_name_plural = "Device Documents"

    def __str__(self):
        owner = ''
        if self.device is not None:
            owner += self.device.ip_address
        if self.user is not None:
            owner += ' - ' + self.user.username
        return f"{owner} - {self.description}"


DEVICE_STATUS_NAMES = (
    ('DAILY_STATUS', 'DAILY_STATUS'),
    ('LAST_DAY_REPORT', 'LAST_DAY_REPORT'),
    ('LAST_WEEK_REPORT', 'LAST_WEEK_REPORT'),
    ('LAST_MONTH_REPORT', 'LAST_MONTH_REPORT'),
)

class DeviceStatus(models.Model):
    """
        model to store device status.
    """
    DAILY_STATUS = 'DAILY_STATUS'
    LAST_DAY_REPORT = 'LAST_DAY_REPORT'
    LAST_WEEK_REPORT = 'LAST_WEEK_REPORT'
    LAST_MONTH_REPORT = 'LAST_MONTH_REPORT'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, blank=True, null=True)
    device = models.ForeignKey(Device, blank=True, null=True, on_delete=models.DO_NOTHING)
    user = models.ForeignKey('User', blank=True, null=True, on_delete=models.DO_NOTHING)
    created_at = models.DateTimeField(auto_now_add=True)

    status = models.JSONField(blank=True, null=True)

    class Meta:
        app_label = "device"
        verbose_name = "Device Status"
        verbose_name_plural = "Devices Status"

    def __str__(self):
        return f"{self.name} - {self.device.ip_address} - {self.created_at}"


METER_TYPE_CHOICES = (
    ('AC_METER', 'AC_METER'),
    ('DC_METER', 'DC_METER'),
    ('HOUSEHOLD_AC_METER', 'HOUSEHOLD_AC_METER'),
    ('LOAD_AC_METER', 'LOAD_AC_METER'),
    ('LOAD_DC_METER', 'LOAD_DC_METER'),
    ('INVERTER_AC_METER', 'INVERTER_AC_METER'),
    ('INVERTER_DC_METER', 'INVERTER_DC_METER'),
    ('WEATHER_METER', 'WEATHER_METER'),
    ('IMPORT_ENERGY_METER', 'IMPORT_ENERGY_METER'),
    ('EXPORT_ENERGY_METER', 'EXPORT_ENERGY_METER'),
)


class Meter(models.Model):
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

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=1024)
    device = models.ForeignKey('Device', on_delete=models.DO_NOTHING)
    meter_type = models.CharField(
        max_length=1024,
        choices=METER_TYPE_CHOICES,
        help_text='Meter type'
    )

    class Meta:
        app_label = "device"
        verbose_name = "Meter"
        verbose_name_plural = "Meters"

    def __str__(self) -> str:
        return f"{self.name}"


class RawData(models.Model):
    """
        Model to store raw data received from device.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device = models.ForeignKey('Device', on_delete=models.DO_NOTHING)
    channel = models.CharField(max_length=255, null=True, blank=True)
    data_type = models.CharField(max_length=255, null=True, blank=True)
    data_arrival_time = models.DateTimeField()
    data = models.JSONField()

    class Meta:
        app_label = "device"
        verbose_name = "RawData"
        verbose_name_plural = "RawData"

    def __str__(self) -> str:
        return f"{self.device.ip_address}-{self.data_arrival_time.strftime(settings.TIME_FORMAT_STRING)}"
