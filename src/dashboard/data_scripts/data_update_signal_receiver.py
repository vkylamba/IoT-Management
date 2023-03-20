
import json
import logging
from datetime import datetime, timedelta

import pytz
from django.conf import settings
from django.core.cache import cache

from device.models import DeviceStatus

from .property_updaters import update_device_properties
from .widgets_updater import update_user_widgets

logger = logging.getLogger("django")


def update_device_info_on_meter_data_update(device, meters_and_data, weather_and_load_data, data_arrival_time=None):
    other_data = device.other_data if device.other_data is not None else {}
    last_update_time = other_data.get('properties_update_time')
    this_data_time = data_arrival_time if data_arrival_time is not None else datetime.utcnow()
    data_updated = False

    if last_update_time is None:
        data = update_device_properties(device, meters_and_data)
        other_data['properties_update_time'] = this_data_time.strftime(settings.TIME_FORMAT_STRING)
        data_updated = True
    else:
        this_data_time = this_data_time.astimezone(pytz.utc)
        last_update_time = datetime.strptime(last_update_time, settings.TIME_FORMAT_STRING).astimezone(pytz.utc)
        if (this_data_time - last_update_time) > timedelta(minutes=settings.DEVICE_PROPERTY_UPDATE_DELAY_MINUTES):
            data = update_device_properties(device, meters_and_data)
            update_user_widgets(device)
            other_data['properties_update_time'] = this_data_time.strftime(settings.TIME_FORMAT_STRING)
            data_updated = True

    if data_updated:
        if weather_and_load_data is not None:
            data.update(weather_and_load_data)
        if data is not None:
            dev_status = DeviceStatus(
                device=device,
                name=DeviceStatus.DAILY_STATUS,
                status=data
            )
            dev_status.save()
            dev_status.created_at = this_data_time
            dev_status.save()
        device.other_data = other_data
        device.save()

        # Update cache too
        cache_name = f"device_status_{device.ip_address}"
        logger.info(f"Updating device status cache, {cache_name}")
        cache.set(cache_name, json.dumps(data), 15 * 60)
