from django.urls import re_path

from . import socket_consumers

websocket_urlpatterns = [
    re_path(r'^', socket_consumers.InputDataConsumer.as_asgi()),
]
