import os
import csv
import logging
from collections.abc import Iterable
from datetime import datetime

import simplejson as json
from api.permissions import IsDevice, IsDeviceUser
from api.serializers import StatusTypeSerializer
from api.utils import get_or_create_user_device, process_raw_data
from device.clickhouse_models import DerivedData
from device.models import (Command, Device, DeviceStatus, Meter, StatusType,
                           UserDeviceType, DeviceType)
from django.conf import settings
from django.core.cache import cache
from django.core.files.storage import FileSystemStorage
from django.db.models import Q
from django.http import HttpResponse, FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from device.models.ota import DeviceConfig
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from utils import DataReports
from utils.weather import get_weather_data_cached
from api.viewsets.common_utils import is_device_admin

PERMISSIONS_ADMIN = settings.PERMISSIONS_ADMIN

logger = logging.getLogger('django')

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
        device = getattr(request, 'device', None)
        user = getattr(request, 'user', None)
        data = request.data

        logger.info(f"Received data {data} from user: {user}, device: {device}")
        # if device is None, then check if it is a user
        errors = []
        if device is None and user is not None:
            device = get_or_create_user_device(user, data)
        
        if device is None:
            errors.append("Device not found!")
            return Response(status=status.HTTP_422_UNPROCESSABLE_ENTITY, data=errors)

        error = process_raw_data(device, data, channel='api', data_type='data', user=user)
        if error != "":
            return Response(status=status.HTTP_400_BAD_REQUEST, data={
                "error": error
            })

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
        device, _ = is_device_admin(dev_user, device_id)

        cached_data = cache.get("device_static_data_{}".format(device_id))

        if cached_data is not None:
            return Response(json.loads(cached_data))

        latest_status = DeviceStatus.objects.filter(
            device=device,
            name=DeviceStatus.DAILY_STATUS
        ).order_by('-created_at').first()
        
        data_report = DataReports(device)
        available_device_types = UserDeviceType.objects.filter(
            user=dev_user
        ).all()
        dev_types = []
        for dev_type in available_device_types:
            dev_types.append({'value': dev_type.code, 'text': dev_type.name})

        if device.type is not None:
            available_status_types = StatusType.objects.filter(
                Q(device=device) | Q(device_type=device.type)
            ).all()
        else:
             available_status_types = StatusType.objects.filter(
                Q(device=device)
            ).all()

        status_types = []
        for status_type in available_status_types:
            if not status_type.active: continue
            status_types.append(StatusTypeSerializer(status_type).data)

        device_data = {
            'id': str(device.id),
            'numeric_id': device.numeric_id,
            'active': device.active,
            'ip_address': device.ip_address,
            'name': device.name,
            'alias': device.alias,
            'type': device.type.name if device.type is not None else None,
            'available_status_types': status_types,
            'available_device_types': dev_types,
            'installation_date': device.installation_date.strftime("%d-%b-%Y") if device.installation_date else None,
            'operator': {},
            'device_contact': device.device_contact_number,
            'avatar': device.avatar.url if device.avatar else None,
            'position': {
                'latitude': device.position.get("latitude") if device.position else None,
                'longitude': device.position.get("longitude") if device.position else None
            },
            'commands': [c.command_name for c in device.commands.all()],
            'properties': latest_status.status if latest_status else None,
            'address': device.address,
            'other_data': device.other_data,
            'token': device.access_token
        }

        if device.operator:
            operator_data = {
                '_id': str(device.operator.id),
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
        device_data['tips'] = data_report.get_energy_saving_tips(device_data['current_load'])

        device_data['status_data_today'] = data_report.get_current_day_status_data()
        device_data['loads_today'] = data_report.get_appliances_current_day()

        device_data['alarms'] = data_report.get_alarms()

        device_data['available_meter_types'] = [x for x in Meter.__dict__ if '_METER' in x]
        device_data['meters'] = [{
            "id": str(device_meter.id),
            "name": device_meter.name,
            "meter_type": device_meter.meter_type,
        } for device_meter in device.get_meters()]
        cache.set("device_static_data_{}".format(device_id), json.dumps(device_data), 120)

        return Response(device_data)

    def update_static_data(self, request, device_id):
        data = request.data
        dev_user = request.user
        device = dev_user.device_list(return_objects=True, device_id=device_id)

        if isinstance(device, list):
            device = [
                x for x in device if x.ip_address == device_id
            ]
            if len(device) == 0:
                return Response(status=status.HTTP_404_NOT_FOUND)

        if not dev_user.has_permission(settings.PERMISSIONS_ADMIN):
            return Response(status=status.HTTP_403_FORBIDDEN)

        for key in data:
            val = data[key]
            if hasattr(device, key):
                try:
                    setattr(device, key, val)
                except Exception as ex:
                    logger.warning(ex)

        if 'type' in data:
            dev_type = UserDeviceType.objects.filter(user=dev_user, code__iexact=data['type']).first()
            if dev_type:
                device.device_type = dev_type
        
        device.alias = data.get('alias', device.alias)
        device.device_contact_number = data.get('device_contact', device.device_contact_number)

        device.save()

        device_meters = device.get_meters()

        for meter_data in data.get('meters', []):
            meter = device_meters.filter(id=meter_data['id'])
            if meter.count() > 0:
                meter.update(meter_type=meter_data.get('meter_type'))

        # Update status types for the device
        errors = []
        if request.user.has_permission(PERMISSIONS_ADMIN):
            if device.device_type is not None:
                device_status_types = StatusType.objects.filter(
                    Q(device=device) | Q(device_type=device.device_type)
                ).all()
            else:
                device_status_types = StatusType.objects.filter(
                    Q(device=device)
                ).all()
            # handle the status types update
            new_available_status_types = request.data.get("available_status_types")
            if isinstance(new_available_status_types, list):
                status_ids_to_keep = []
                for new_available_status_type in new_available_status_types:
                    status_type_id = new_available_status_type.get("id")
                    if status_type_id is not None:
                        status_type = StatusType.objects.filter(
                            id=status_type_id
                        ).first()
                        if status_type is None:
                            errors.append(f"Status type with id {status_type_id} not found!")
                            continue
                    else:
                        status_type = StatusType()
                    if len(errors) == 0:
                        status_type.name = new_available_status_type.get("name", status_type.name)
                        status_type.target_type = new_available_status_type.get("target_type", status_type.target_type)
                        status_type.update_trigger = new_available_status_type.get("update_trigger", status_type.update_trigger)
                        status_type.device = device
                        status_type.device_type = new_available_status_type.get("device_type", status_type.device_type)
                        status_type.translation_schema = new_available_status_type.get("translation_schema", status_type.translation_schema)
                        status_type.save()
                
                status_ids_to_keep.append(status_type.id)
            
                # Delete the remaining status types
                device_status_types.filter(~Q(id__in=status_ids_to_keep)).delete()

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

        available_device_types = UserDeviceType.objects.filter(
            user=dev_user
        ).all()
        dev_types = []
        for dev_type in available_device_types:
            dev_types.append({'value': dev_type.code, 'text': dev_type.name})

        if device.device_type is not None:
            available_status_types = StatusType.objects.filter(
                Q(device=device) | Q(device_type=device.device_type)
            ).all()
        else:
            available_status_types = StatusType.objects.filter(
                Q(device=device)
            ).all()

        status_types = []
        for status_type in available_status_types:
            if not status_type.active: continue
            status_types.append(StatusTypeSerializer(status_type).data)


        device_data = {
            'ip_address': device.ip_address,
            'name': device.name,
            'alias': device.alias,
            'type': device.device_type.name if device.device_type is not None else None,
            'available_status_types': status_types,
            'available_device_types': dev_types,
            'installation_date': device.installation_date.strftime("%d-%b-%Y") if device.installation_date else None,
            'device_contact': device.device_contact_number,
            'avatar': device.avatar.url if device.avatar else None,
            'position': {
                'latitude': device.position.get("latitude") if device.position else None,
                'longitude': device.position.get("longitude") if device.position else None
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

        if device_id == "all":
            devices = dev_user.device_list(return_objects=True)
        else:
            devices = dev_user.device_list(return_objects=True, device_id=device_id)

        if isinstance(devices, list) and device_id != "all":
            devices = [
                x for x in devices if x.ip_address == device_id
            ]
            if len(devices) == 0:
                return Response(status=status.HTTP_404_NOT_FOUND)

        data_type = "raw"
        export_type = "json"
        data_type = request.data.get("dataType", data_type)
        export_type = request.data.get("exportType")
        start_time = request.data.get("startTime", "").strip()
        start_date = request.data.get("startDate", "").strip()
        end_time = request.data.get("endTime", "").strip()
        end_date = request.data.get("endDate", "").strip()
        if end_date == '' and end_time == '':
            end_date = start_date
            end_time = start_time
        if start_date:
            start_time = datetime.strptime(
                start_date, settings.DATE_FORMAT_STRING
            )
        else:
            start_time = datetime.strptime(
                start_time, settings.TIME_FORMAT_STRING
            )
        if end_date:
            end_time = datetime.strptime(
                end_date, settings.DATE_FORMAT_STRING
            )
        else:
            end_time = datetime.strptime(
                end_time, settings.TIME_FORMAT_STRING
            )
        selected_x_params = request.data.get("x_params")
        selected_y_params = request.data.get("y_params")
        # aggregate_data = request.GET.get('aggregate', 'yes')

        data_report = DataReports(devices, multiple=isinstance(devices, Iterable))
        data = None
        if data_type in ["raw", "raw_data"]:
            data = data_report.get_device_data(
                data_type,
                start_time,
                end_time,
                meter_type=[
                    Meter.AC_METER, Meter.INVERTER_AC_METER,
                    Meter.HOUSEHOLD_AC_METER, Meter.LOAD_AC_METER
                ]
            )
        elif export_type != "json":
            data = data_report.get_status_data([data_type], start_time, end_time)
        if export_type == "json":
            if data_type == "status":
                data = data_report.get_current_day_status_data(start_time)
            elif data_type in ["raw", "raw_data"]:
                json_data = []
                if data is not None:
                    for dt in data:
                        if isinstance(dt, dict):
                            rl_data = dt.get("status")
                            data_arrival_time = dt.get("created_at")
                            channel = "calculated"
                            data_type = dt.get("name")
                            ip_address = data_report.device.ip_address
                        else:
                            rl_data = dt.data
                            data_arrival_time = dt.data_arrival_time.strftime(settings.TIME_FORMAT_STRING)
                            channel = dt.channel
                            data_type = dt.data_type
                            ip_address = dt.device.ip_address

                        if data_arrival_time is None:
                            data_arrival_time = dt.created_at

                        json_data.append({
                            "data_arrival_time": data_arrival_time,
                            "channel": channel,
                            "data_type": data_type,
                            "ip_address": ip_address,
                            "data": rl_data
                        })
                    data = json_data
            elif data_type is not None:
                data = data_report.get_status_data([data_type], start_time, end_time)
            else:
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
                        if(param == "time"):
                            param = "data_arrival_time"
                        data_list.append(getattr(each_data, param, None))
                    dynamic_data[param] = data_list
                data = {"error": "success", "dynamic_data": dynamic_data}
            return Response(data)
        else:
            header = ["data_arrival_time", "device", "channel", "data_type", "data"]
            csv_data = []
            if data is not None:
                for dt in data:
                    if isinstance(dt, dict):
                        rl_data = dt.get("status")
                        data_arrival_time = dt.get("created_at")
                        channel = "calculated"
                        data_type = dt.get("name")
                        ip_address = data_report.device.ip_address
                    else:
                        rl_data = dt.data
                        data_arrival_time = dt.data_arrival_time.strftime(settings.TIME_FORMAT_STRING)
                        channel = dt.channel
                        data_type = dt.data_type
                        ip_address = dt.device.ip_address

                    if data_arrival_time is None:
                        data_arrival_time = dt.created_at

                    csv_data.append([
                        data_arrival_time,
                        channel,
                        data_type,
                        ip_address,
                        json.dumps(rl_data)
                    ])
            # Create the HttpResponse object with the appropriate CSV header.
            response = HttpResponse(
                content_type="text/csv",
                headers={"Content-Disposition": f'attachment; filename="{device_id}-{data_type}.csv"'},
            )

            writer = csv.writer(response)
            writer.writerow(header)
            writer.writerows(csv_data)

            return response

    def send_command(self, request, device_id):
        device, is_admin = is_device_admin(request.user, device_id)
        if device is None:
            return Response(status=status.HTTP_404_NOT_FOUND)

        if not is_admin:
            return Response(status=status.HTTP_403_FORBIDDEN)

        data = request.data
        command = data.get('command', '').strip()
        command_param = data.get("command_param")
        if command_param and isinstance(command_param, str):
            command_param = command_param.strip()

        if command != "" and command_param != "":
            # Save the command into command model
            dev_command = device.commands.filter(command_name=command).first()
            cmd = Command(
                device=device,
                status='P',
                command_in_time=timezone.now(),
                command=dev_command.command_code if dev_command else command,
                param=command_param
            )
            cmd.save()
            cmd.send()
        return Response(status=status.HTTP_201_CREATED)

    def get_report(self, request, device_id, report_type):
        """
            This will return weekly/monthly energy consumption data by day/week.
            This will return weekly/monthly energy consumption data by appliance.
            This will return weekly/monthly energy consumption data of last 3 weeks/months.
        """

        # Findout the user
        dev_user = request.user
        device = dev_user.device_list(return_objects=True, device_id=device_id)

        if isinstance(device, list):
            device = [
                x for x in device if x.ip_address == device_id
            ]
            if len(device) == 0:
                return Response(status=status.HTTP_404_NOT_FOUND)

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

    def remove_device(self, request, device_id):
        dev_user = request.user
        dev = get_object_or_404(Device, id=device_id)
        device = dev_user.device_list(return_objects=True, device_id=dev.ip_address)
        if isinstance(device, list):
            device = [
                x for x in device if x.ip_address == device_id
            ]
            if len(device) == 0:
                return Response(status=status.HTTP_404_NOT_FOUND)

        if not dev_user.has_permission(settings.PERMISSIONS_ADMIN):
            return Response(status=status.HTTP_403_FORBIDDEN)

        device.active = False
        device.save()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def get_logs(self, request, device_id):
        dev_user = request.user
        dev_user = request.user
        device = dev_user.device_list(return_objects=True, device_id=device_id)
        if isinstance(device, list):
            device = [
                x for x in device if x.ip_address == device_id
            ]
            if len(device) == 0:
                return Response(status=status.HTTP_404_NOT_FOUND)
        
        if device is None:
            return Response(status=status.HTTP_404_NOT_FOUND)

        if not dev_user.has_permission(settings.PERMISSIONS_ADMIN):
            return Response(status=status.HTTP_403_FORBIDDEN)
        
        date_str = request.query_params.get("date", None)
        format = request.query_params.get("format", None)
        if format is None:
            format = "file"
        if date_str is None:
            date_str = timezone.now().strftime("%Y-%m-%d")
        log_file = os.path.join(settings.MEDIA_ROOT, f"device-logs/device-{device.ip_address}-{date_str}.log")
        if os.path.exists(log_file):
            if format == "file":
                response = FileResponse(open(log_file, "rb"))
                return response
            else:
                logs_data = None
                with open(log_file, "r") as f:
                    logs_data = f.readlines()
                return Response(status=status.HTTP_200_OK, data={"logs": logs_data})
        return Response(status=status.HTTP_404_NOT_FOUND)

    def get_config(self, request, device_id):
        dev_user = request.user
        dev_user = request.user
        device, is_admin = is_device_admin(dev_user, device_id)
        if device is None:
            return Response(status=status.HTTP_404_NOT_FOUND)

        if not is_admin:
            return Response(status=status.HTTP_403_FORBIDDEN)
        
        # get the latest config data
        cfg = DeviceConfig.objects.filter(
            device=device,
        ).order_by('-created_at').first()
        if cfg is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        data = {
            "id": cfg.id,
            "data": cfg.data,
            "group_name": cfg.group_name,
            "version": cfg.version,
            "description": cfg.description,
            "active": cfg.active,
            "created_at": cfg.created_at.strftime(settings.TIME_FORMAT_STRING) if cfg.created_at is not None else None,
            "updated_at": cfg.updated_at.strftime(settings.TIME_FORMAT_STRING) if cfg.updated_at is not None else None,
        }
        return Response(data=data)

    def get_commands(self, request, device_id):
        dev_user = request.user
        dev_user = request.user
        device, is_admin = is_device_admin(dev_user, device_id)
        if device is None:
            return Response(status=status.HTTP_404_NOT_FOUND)

        if not is_admin:
            return Response(status=status.HTTP_403_FORBIDDEN)
        
        page_size = int(request.query_params.get("page_size", 10))
        page = int(request.query_params.get("page", 1))
        if page < 1:
            page = 1
        if page_size < 1:
            page_size = 10
        elif page_size > 100:
            page_size = 100
        commands = Command.objects.filter(
            device=device
        ).order_by('-command_in_time')
        total_commands = commands.count()
        commands = commands[(page-1)*page_size: page*page_size]
        commands_data = []
        for command in commands:
            commands_data.append({
                "id": command.id,
                "device_id": str(command.device.id),
                "command": command.command,
                "param": command.param,
                "status": command.status,
                "command_in_time": command.command_in_time.strftime(settings.TIME_FORMAT_STRING) if command.command_in_time is not None else None,
                "command_read_time": command.command_read_time.strftime(settings.TIME_FORMAT_STRING) if command.command_read_time is not None else None,
            })
        data = {
            "total": total_commands,
            "page": page,
            "page_size": page_size,
            "commands": commands_data
        }
        return Response(data=data)
