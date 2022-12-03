"""
    Script to fetch weather info from Openweathermap.
"""
import logging

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger("application")
openwathermap_api_key = settings.OPENWEATHERMAP_API_KEY

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


def get_weather_data_cached(device, use_cache=True):
    # logger.debug("Getting weather data for device {}".format(device.ip_address))
    if use_cache:
        weather_data = cache.get("{}_weather_data".format(device.ip_address))
    else:
        weather_data = None
    if weather_data is None and device.position is not None:
        logger.info("Weather data not in cache for device {}".format(device.ip_address))
        try:
            weather_data = get_weather_data(device.position.get("latitude"), device.position.get("longitude"))
        except Exception as e:
            logger.exception(e)
            weather_data = {}
        else:
            cache.set("{}_weather_data".format(device.ip_address), weather_data, settings.WEATHER_DATA_CACHE_MINUTES)
    return weather_data
