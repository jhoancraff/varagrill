from django.urls import re_path

from .consumers import CocinaConsumer


websocket_urlpatterns = [
    re_path(r'^ws/pedidos/$', CocinaConsumer.as_asgi()),
    re_path(r'^ws/notificaciones/cocina/$', CocinaConsumer.as_asgi()),
]
