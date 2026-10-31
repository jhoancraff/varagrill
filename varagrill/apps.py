from django.apps import AppConfig


class VaragrillConfig(AppConfig):
    name = 'varagrill'

    def ready(self):
        from .costos_historial import conectar_senales
        conectar_senales()
