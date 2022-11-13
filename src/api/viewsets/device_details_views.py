
import logging
from datetime import datetime

import pytz
import simplejson as json
from api.permissions import IsDevice, IsDeviceUser
from dashboard.data_scripts.data_update_signal_receiver import \
    update_device_info_on_meter_data_update
from device.clickhouse_models import (DerivedData, MeterData,
                                      create_model_instance)
from device.models import (Command, Device, DeviceStatus, DeviceType, Meter,
                           RawData)
from device_schemas.device_types import IOT_GW_DEVICES
from device_schemas.schema import validate_data_schema
from django.conf import settings
from django.core.cache import cache
from django.core.files.storage import FileSystemStorage
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from utils import DataReports, detect_and_save_meter_loads
from utils.weather import get_weather_data_cached

PERMISSIONS_ADMIN = settings.PERMISSIONS_ADMIN

logger = logging.getLogger('application')

AVAILABLE_METER_DATA_FIELDS = {
        "voltage": float,
        "current": float,
        "power": float,
        "frequency": float,
        "energy": float,
        "runtime": int,
        "humidity": float,
        "temperature": float,
        "latitude": float,
        "longitude": float,
        "state": int,
        "cpu_temperature": float,
}

EXTRA_METER_DATA_FIELD = "more_data"


def get_latest_raw_data(device):
    try:
        raw_data = RawData.objects.filter(
            device=device
        ).order_by(
            '-data_arrival_time'
        )[0]
        return json.loads(raw_data.data)
    except Exception as ex:
        return None


def filter_meter_data(data, meter, data_arrival_time):
    meter_name = meter.name
    meter_data = {}
    extra_data = {}
    for key, val in data.get(meter_name, {}).items():
        if val is not None:
            if key in AVAILABLE_METER_DATA_FIELDS.keys(): # and isinstance(val, AVAILABLE_METER_DATA_FIELDS[key]):
                meter_data[key] = val
            else:
                extra_data["key"] = val

    if data_arrival_time is None:
        data_arrival_time = datetime.utcnow()

    meter_data['data_arrival_time'] = data_arrival_time
    meter_data['meter'] = meter

    if extra_data:
        meter_data[EXTRA_METER_DATA_FIELD] = json.dumps(extra_data)
    return meter_data


class HeartbeatViewSet(viewsets.ViewSet):
    """
        Viewset to get device heartbeat data
    """
    permission_classes = ()
    authentication_classes = ()

    def get(self, request, format=None):
        """
            Method to heartbeat data via get request.
        """
        logger.info(f"heartbeat data received: {request.query_params}")
        return Response("OK")

    def post(self, request, format=None):
        """
        Method to heartbeat data via get request.
        """
        logger.info(f"heartbeat data received: {request.data}")

        device_mac = request.data.get("mac")
        device = Device.objects.filter(
            mac=device_mac
        ).first()

        utc_timestamp = int(datetime.utcnow().timestamp())
        resp = f"HEARTBEAT_ACK [{utc_timestamp}]"
        time_to_sync = False
        try:
            if device:
                other_data = device.other_data
                if other_data is None:
                    other_data = {}

                last_datasync_time = other_data.get("last_data_sync_time")
                if last_datasync_time is None:
                    time_to_sync = True
                else:
                    last_datasync_time = datetime.strptime(last_datasync_time, settings.TIME_FORMAT_STRING)
                    time_to_sync = (datetime.utcnow() - last_datasync_time).total_seconds() >= settings.DEFAULT_SYNC_FREQUENCY_MINUTES * 60

                other_data["last_heartbeat_time"] = datetime.utcnow().strftime(settings.TIME_FORMAT_STRING)
                device.other_data = other_data
                device.save()
            elif device_mac:
                device = Device(
                    mac=device_mac,
                    other_data={
                        "last_heartbeat_time": datetime.utcnow().strftime(settings.TIME_FORMAT_STRING)
                    }
                )
                time_to_sync = True
                device.save()

            if time_to_sync:
                resp = "SYNC [0] {0}"
            elif device is not None:
                command = device.get_command()
                if command is not None:
                    command.status = 'E'
                    command.command_read_time = datetime.utcnow()
                    command.save()
                    resp = f"{command.command}{command.param}"

        except Exception as ex:
            logger.exception(ex)
            resp = "ERROR"
        return Response(resp)


class DataViewSet(viewsets.ViewSet):
    """
        Viewset to accept data from device.
    """
    permission_classes = (IsDevice,)
    authentication_classes = ()

    def create(self, request, format=None):
        """
            Method to accept data via post request.
        """
        device = request.device
        data = request.data

        config_data = data.get("config", {})
        dev_type = config_data.get("devType")

        if dev_type is None:
            dev_types = [x.name for x in device.types.all()]
            dev_type = dev_types[-1] if len(dev_types) > 0 else None
        logger.info(f"Data from {dev_type} device: {data}")

        # Save the raw data
        data_arrival_time = data.get("last_update_time")
        if data_arrival_time is not None:
            data_arrival_time = datetime.strptime(
                data_arrival_time,
                "%Y-%m-%dT%H:%M:%S%z"
            )
            data_arrival_time = data_arrival_time.astimezone(pytz.utc)
        else:
            data_arrival_time = datetime.utcnow()

        raw_data = RawData(
            device=device,
            data_arrival_time=data_arrival_time,
            data=data
        )
        raw_data.save()

        other_data = device.other_data
        if other_data is None:
            other_data = {}

        other_data["last_data_sync_time"] = data_arrival_time.strftime(settings.TIME_FORMAT_STRING)
        device.other_data = other_data
        device.save()

        if dev_type in IOT_GW_DEVICES:
            configured_schema_type = other_data.get("data_schema_type")
            if configured_schema_type is None:
                configured_schema_type = dev_type
            last_raw_data = get_latest_raw_data(device)
            validated_data = validate_data_schema(configured_schema_type, data, last_raw_data)
            if validated_data is None:
                return Response(status=status.HTTP_400_BAD_REQUEST)

            logger.info(f"Validated data is: {validated_data}")
            data = validated_data

        meters_and_data = []
        for meter_name in data:
            if 'meter' not in meter_name:
                continue
            if all(value == None for value in data.get(meter_name, {}).values()):
                continue
            meters = Meter.objects.filter(
                name=meter_name,
                device=device
            )
            if meters.count() == 0:
                meter = Meter(
                    name=meter_name,
                    device=device
                )
                meter.save()
            else:
                meter = meters[0]
            try:
                meter_data = filter_meter_data(data, meter, data_arrival_time)
                data_obj = create_model_instance(
                    MeterData,
                    meter_data
                )
                meters_and_data.append({
                    "meter": meter,
                    "data": meter_data
                })
            except TypeError as e:
                logger.exception(e)

        if other_data.get("device_load_detection_on", False):
            detect_and_save_meter_loads(
                device,
                meters_and_data,
                data_arrival_time
            )
        update_device_info_on_meter_data_update(device, meters_and_data)

        # invalidate static data cache
        cache.delete("device_static_data_{}".format(device.ip_address))

        return Response("OK")


class DeviceDetailsViewSet(viewsets.ViewSet):
    """
    ViewSet to return device info.
    """
    permission_classes = (IsAuthenticated, IsDeviceUser)

    def device_static_data(self, request, device_id):
        """
        The view should return static data of the device.
        """
        # Findout the user
        dev_user = request.user
        device = dev_user.device_list(return_objects=True, device_id=device_id)

        if isinstance(device, list):
            return Response(status=status.HTTP_404_NOT_FOUND)

        cached_data = None # cache.get("device_static_data_{}".format(device_id))

        if cached_data is not None:
            return Response(json.loads(cached_data))

        latest_status = DeviceStatus.objects.filter(
            device=device,
            name=DeviceStatus.DAILY_STATUS
        ).order_by('-created_at').first()
        
        data_report = DataReports(device)

        device_data = {
            'ip_address': device.ip_address,
            'alias': device.alias,
            'type': data_report.device_types,
            'installation_date': device.installation_date.strftime("%d-%b-%Y") if device.installation_date else None,
            'operator': {},
            'device_contact': device.device_contact_number,
            'avatar': device.avatar.url if device.avatar else None,
            'position': {
                'latitude': device.position.latitude if device.position else None,
                'longitude': device.position.longitude if device.position else None
            },
            'commands': [c.command_name for c in device.commands.all()],
            'properties': latest_status.status if latest_status else None,
            'address': device.address,
            'other_data': device.other_data
        }

        if device.operator:
            operator_data = {
                '_id': device.operator.id,
                'name': device.operator.name,
                'address': device.operator.address,
                'pincode': device.operator.pin_code,
                'contact': device.operator.contact_number,
                'avatar': device.operator.avatar.url if device.operator.avatar else None
            }
            device_data['operator'] = operator_data

        available_parameters = [
            "voltage", "current", "power",
            "frequency", "temperature",
            "energy", "state", "runtime",
            "latitude", "longitude",
        ]

        derived_data = DerivedData.objects.filter(device=str(device.id))
        for derived_dt in derived_data:
            available_parameters.append(derived_dt.name)

        device_data["data_parameters"] = available_parameters

        device_data['latest_data'] = data_report.get_latest_data()
        device_data['latest_weather_data'] = get_weather_data_cached(device)
        device_data['current_load'] = data_report.get_possible_equipment_list()
        device_data['tips'] = data_report.get_energy_saving_tips(
            device_data['current_load'])

        # ToDo: Remove data_today, and weather_data_today
        device_data['data_today'] = [x for x in data_report.get_current_day_data()]
        device_data['weather_data_today'] = [x for x in data_report.get_current_day_weather_data()]
        device_data['status_data_today'] = data_report.get_current_day_status_data()
        device_data['loads_today'] = data_report.get_appliances_current_day()

        device_data['alarms'] = data_report.get_alarms()

        device_data['available_meter_types'] = [x for x in Meter.__dict__ if '_METER' in x]
        device_data['meters'] = [{
            "id": str(device_meter.id),
            "name": device_meter.name,
            "meter_type": device_meter.meter_type,
        } for device_meter in device.get_meters()]

        cache.set("device_static_data_{}".format(device_id), json.dumps(device_data), 300)

        return Response(device_data)

    def update_static_data(self, request, device_id):

        data = request.data
        dev_user = request.user
        device = dev_user.device_list(return_objects=True, device_id=device_id)

        if device is None or isinstance(device, list):
            return Response(status=status.HTTP_404_NOT_FOUND)

        if not dev_user.is_superuser:
            return Response(status=status.HTTP_403_FORBIDDEN)

        for key in data:
            val = data[key]
            if hasattr(device, key):
                setattr(device, key, val)

        if 'type' in data:
            pass

        device_meters = device.get_meters()

        for meter_data in data.get('meters', []):
            meter = device_meters.filter(id=meter_data['id'])
            if meter.count() > 0:
                meter.update(meter_type=meter_data.get('meter_type'))

        properties_data = data.get('properties', {})
        latest_status = DeviceStatus.objects.filter(
            device=device,
            name=DeviceStatus.DAILY_STATUS
        ).order_by('-created_at').first()
        for property_name in properties_data:
            latest_status.status[property_name] = properties_data.get(property_name)
            new_status = DeviceStatus(
                device=device,
                name=DeviceStatus.DAILY_STATUS,
                status=latest_status.status
            )
            new_status.save()
            latest_status = new_status

        device.save()

        device_data = {
            'ip_address': device.ip_address,
            'alias': device.alias,
            'type': [x.name for x in device.types.all()],
            'installation_date': device.installation_date.strftime("%d-%b-%Y") if device.installation_date else None,
            'device_contact': device.device_contact_number,
            'avatar': device.avatar.url if device.avatar else None,
            'position': {
                'latitude': device.position.latitude if device.position else None,
                'longitude': device.position.longitude if device.position else None
            },
            'commands': [c.command_name for c in device.commands.all()],
            'properties': latest_status.status if latest_status else None,
            'address': device.address,
            'other_data': device.other_data
        }

        device_data['meters'] = [{
            "id": str(device_meter.id),
            "name": device_meter.name,
            "meter_type": device_meter.meter_type,
        } for device_meter in device.get_meters()]

        return Response(device_data)

    def get_dynamic_data(self, request, device_id):
        dynamic_data = {}

        dev_user = request.user
        device = dev_user.device_list(return_objects=True, device_id=device_id)

        try:
            start_time = request.GET["start_time"].strip()
            start_time = timezone.datetime.strptime(
                start_time, settings.TIME_FORMAT_STRING
            )
            end_time = request.GET["end_time"].strip()
            end_time = timezone.datetime.strptime(
                end_time, settings.TIME_FORMAT_STRING
            )
        except Exception as e:  # Start time and end time are not provided. So lets send latest data point
            logger.error(e)
            start_time = None
            end_time = None

        selected_x_params = request.GET["x_params"]
        selected_y_params = request.GET["y_params"]
        # aggregate_data = request.GET.get('aggregate', 'yes')

        data_report = DataReports(device)

        data = data_report.get_all_data(
            start_time,
            end_time,
            meter_type=[
                Meter.AC_METER, Meter.INVERTER_AC_METER,
                Meter.HOUSEHOLD_AC_METER, Meter.LOAD_AC_METER
            ]
        )
        # if end_time - start_time > timezone.timedelta(days=1) and aggregate_data == 'yes':
        #     data = data_report.get_all_data_aggregated(start_time, end_time)
        # else:
        #     data = data_report.get_all_data(start_time, end_time)
        x_params = selected_x_params.strip()
        y_params = selected_y_params.strip().split(',')

        params_list = ["time"]
        if(x_params != '' and x_params != 'time'):
            params_list += [x_params]
        for param in y_params:
            params_list += [param]

        for param in params_list:
            dynamic_data[param] = []

        for param in params_list:
            data_list = []
            for each_data in data:
                detum = data_report.get_data_dict(each_data)
                if(param == "time"):
                    if 'time' in detum:
                        logger.debug(
                            "The data dictionary keys are: {}".format(detum.keys()))
                        data_list.append(detum['time'])
                    else:
                        data_list.append(detum['data_arrival_time'])
                else:
                    data_list.append(detum[param])
            dynamic_data[param] = data_list
        data = {"error": "success", "dynamic_data": dynamic_data}
        return Response(data)

    def send_command(self, request, device_id):
        error = ''
        if not request.user.is_authenticated():
            error = "Not logged in"
        else:
            dev_user = request.user
            device = dev_user.device_list(
                return_objects=True, device_id=device_id)
            data = request.data
            command = data.get('command', '').strip()
            command_param = data.get("command_param")
            if command_param and isinstance(command_param, str):
                command_param = command_param.strip()
            method = str(data.get("method")).strip()

            # dev_contact = device.device_contact_number
            if command != "" and command_param != "":
                # Save the command into command model
                dev_command = device.commands.get(command_name=command)
                cmd = Command(
                    device=device,
                    status='P',
                    command_in_time=timezone.now(),
                    command=dev_command.command_code,
                    param=command_param
                )
                if method == '1':
                    cmd.save()
                    error = "success"
                else:
                    cmd.status = 'E'
                    status = cmd.send()
                    cmd.save()
                    if status:
                        error = "success"
                    else:
                        error = "Error sending sms"
        data = {"error": error}
        return Response(data)

    def get_report(self, request, device_id, report_type):
        """
            This will return weekly/monthly energy consumption data by day/week.
            This will return weekly/monthly energy consumption data by appliance.
            This will return weekly/monthly energy consumption data of last 3 weeks/months.
        """

        # Findout the user
        dev_user = request.user
        device = dev_user.device_list(return_objects=True, device_id=device_id)

        report_data = None
        report_name = None

        if report_type == 'yesterday':
            report_name = DeviceStatus.LAST_DAY_REPORT

        elif report_type == 'month':
            report_name = DeviceStatus.LAST_MONTH_REPORT

        elif report_type == 'week':
            report_name = DeviceStatus.LAST_WEEK_REPORT
            
        if report_name is not None:
            report_status = DeviceStatus.objects.filter(
                device=device,
                name=report_name
            ).order_by('-created_at').first()
            if report_status:
                report_data = report_status.status

        # Get weekly/monthly energy consumption data by appliance.
        # x, consumption_data_by_appaliance = data_report.get_data_with_apaliances(
        #     start_time=start_time,
        #     end_time=end_time
        # )

        return Response(report_data)

    def device_settings_data(self, request, device_id):

        dev_user = request.user
        device = dev_user.device_list(return_objects=True, device_id=device_id)

        dev_types = []
        for dev_type in DeviceType.objects.all():
            dev_types.append({'value': dev_type.name, 'label': dev_type.name})

        device_data = {
            'ip_address': device.ip_address,
            'alias': device.alias,
            'type': [x.name for x in device.types.all()],
            'device_types': dev_types,
            'installation_date': device.installation_date.strftime("%d-%b-%Y") if device.installation_date else None,
            'operator': {},
            'device_contact': device.device_contact_number,
            'avatar': device.avatar.url if device.avatar else None,
            'position': {
                'latitude': device.position.latitude if device.position else None,
                'longitude': device.position.longitude if device.position else None
            },
            'api_key': device.access_token,
        }

        return Response(device_data)

    def set_settings_data(self, request, device_id):

        dev_user = request.user
        device = dev_user.device_list(return_objects=True, device_id=device_id)
        data = request.data
        device.alias = data.get('alias', device.alias)
        device.device_contact_number = data.get('device_contact')
        latitude = data.get('latitude')
        longitude = data.get('longitude')

        if latitude is not None and longitude is not None:
            device.position = "{}, {}".format(latitude, longitude)

        avatar = data.get('avatar')
        if avatar:
            fs = FileSystemStorage()
            avatar = fs.save(device.ip_address, avatar)
            device.avatar = avatar

        dev_type = data.get('type')
        if isinstance(dev_type, list):
            dev_type = DeviceType.objects.filter(name__in=dev_type)
            device.types = dev_type

        device.save()
        device.refresh_from_db()

        dev_types = []
        for dev_type in DeviceType.objects.all():
            dev_types.append({'value': dev_type.name, 'label': dev_type.name})

        device_data = {
            'ip_address': device.ip_address,
            'alias': device.alias,
            'type': [x.name for x in device.types.all()],
            'device_types': dev_types,
            'installation_date': device.installation_date.strftime("%d-%b-%Y") if device.installation_date else None,
            'operator': {},
            'device_contact': device.device_contact_number,
            'avatar': device.avatar.url if device.avatar else None,
            'position': {
                'latitude': device.position.latitude if device.position else None,
                'longitude': device.position.longitude if device.position else None
            },
            'api_key': device.access_token,
        }

        return Response(device_data)
