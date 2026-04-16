"""
    Script to fetch weather info from Openweathermap.
"""
import logging

import requests
from device.models import RawData
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger("django")
openwathermap_api_key = settings.OPENWEATHERMAP_API_KEY
WEATHER_RAW_DATA_TYPE = "weather"
WEATHER_RAW_DATA_CHANNEL = "weather"

url = "http://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&APPID={apikey}"


def get_weather_data(latitude, longitude):
    """
        Method to fetch weather data for the location (latitude, longitude).
    """
    weather_data_url = url.format(lat=latitude, lon=longitude, apikey=openwathermap_api_key)

    resp = requests.get(weather_data_url)
    if resp.status_code == 200:
        return resp.json()
    else:
        raise Exception(f"Error fetching weather data. {resp.status_code}")


def get_stored_weather_data(device, reference_time=None):
    weather_queryset = RawData.objects.filter(
        device=device,
        data_type=WEATHER_RAW_DATA_TYPE,
    )
    if reference_time is not None:
        if timezone.is_naive(reference_time):
            reference_time = timezone.make_aware(
                reference_time,
                timezone.get_current_timezone(),
            )
        weather_queryset = weather_queryset.filter(
            data_arrival_time__lte=reference_time,
        )
    weather_entry = weather_queryset.order_by('-data_arrival_time').first()
    return weather_entry.data if weather_entry is not None else None


def store_weather_data(device, weather_data, data_arrival_time=None):
    if not weather_data:
        return None

    if data_arrival_time is None:
        data_arrival_time = timezone.now()
    elif timezone.is_naive(data_arrival_time):
        data_arrival_time = timezone.make_aware(
            data_arrival_time,
            timezone.get_current_timezone(),
        )

    latest_weather_entry = RawData.objects.filter(
        device=device,
        data_type=WEATHER_RAW_DATA_TYPE,
    ).order_by('-data_arrival_time').first()
    if latest_weather_entry is not None:
        same_timestamp = latest_weather_entry.data_arrival_time == data_arrival_time
        same_payload = latest_weather_entry.data == weather_data
        if same_timestamp and same_payload:
            return latest_weather_entry

    return RawData.objects.create(
        device=device,
        channel=WEATHER_RAW_DATA_CHANNEL,
        data_type=WEATHER_RAW_DATA_TYPE,
        data_arrival_time=data_arrival_time,
        data=weather_data,
    )


def get_weather_data_cached(
    device,
    use_cache=True,
    reference_time=None,
    allow_fetch=True,
    store_in_raw_data=True,
):
    # logger.debug("Getting weather data for device {}".format(device.ip_address))
    if reference_time is not None:
        stored_weather_data = get_stored_weather_data(device, reference_time=reference_time)
        if stored_weather_data is not None:
            return stored_weather_data

    if use_cache:
        weather_data = cache.get("{}_weather_data".format(device.ip_address))
    else:
        weather_data = None

    if weather_data is not None:
        return weather_data

    if not allow_fetch:
        return None

    if device.position is not None:
        logger.info("Weather data not in cache for device {}".format(device.ip_address))
        try:
            weather_data = get_weather_data(device.position.get("latitude"), device.position.get("longitude"))
        except Exception as e:
            logger.exception(e)
            weather_data = {}
        else:
            cache.set("{}_weather_data".format(device.ip_address), weather_data, settings.WEATHER_DATA_CACHE_MINUTES)

        if store_in_raw_data and weather_data:
            store_weather_data(device, weather_data, data_arrival_time=reference_time)

    return weather_data
