# -*- coding: utf-8 -*-
"""
Alerta diaria de stock minimo por Telegram (ver varagrill/alertas_stock.py).

Se ejecuta cada hora desde un timer de systemd (deploy/varagrill-alerta-stock.*.example). Cada corrida decide sola
si hay algo que enviar: manda el resumen una sola vez al dia y reintenta cada hora si fallo.

Uso:
    python manage.py alertas_stock_minimo             # la corrida normal (la del timer)
    python manage.py alertas_stock_minimo --simular   # muestra el mensaje de hoy sin enviarlo ni registrarlo
    python manage.py alertas_stock_minimo --probar    # manda un mensaje de prueba a los chats configurados
    python manage.py alertas_stock_minimo --estado    # resultado de los ultimos 7 dias

Si el envio falla, el comando termina con error (el timer lo muestra como fallido en journalctl) y se reintenta
en la hora siguiente.
"""
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from varagrill import alertas_stock
from varagrill.models import VGEjecucionAlertaStock
from varagrill.telegram_alertas import configuracion, enviar_texto, limpiar_error

MENSAJES = {
    'fuera_de_horario': 'Todavía no es la hora de inicio ({hora}:00); no se hace nada.',
    'ya_enviado': 'El aviso de hoy ya quedó registrado; no se repite.',
    'sin_alertas': 'Ningún ingrediente con stock mínimo definido está en su mínimo; no hay nada que enviar.',
    'enviado': 'Aviso enviado por Telegram ({ingredientes} ingrediente(s)).',
}


class Command(BaseCommand):
    help = 'Envía por Telegram los ingredientes con stock mínimo definido que están en su mínimo o por debajo (una vez al día).'

    def add_arguments(self, parser):
        parser.add_argument('--simular', action='store_true', help='Muestra el mensaje sin enviarlo ni registrar el día.')
        parser.add_argument('--probar', action='store_true', help='Manda un mensaje de prueba a los chats configurados.')
        parser.add_argument('--estado', action='store_true', help='Muestra el resultado de los últimos 7 días.')

    def handle(self, *args, **options):
        if options['estado']:
            return self._estado()
        if options['probar']:
            return self._probar()
        if options['simular']:
            return self._simular()

        resultado = alertas_stock.ejecutar()
        if resultado['resultado'] == 'fallido':
            raise CommandError(f"No se pudo enviar el aviso: {resultado['error']}")
        self.stdout.write(MENSAJES[resultado['resultado']].format(hora=alertas_stock.hora_inicio(), **resultado))

    def _simular(self):
        ingredientes = alertas_stock.ingredientes_en_minimo()
        if not ingredientes:
            self.stdout.write('Ningún ingrediente con stock mínimo definido está en su mínimo: hoy no se enviaría nada.')
            return
        self.stdout.write(alertas_stock.armar_mensaje(ingredientes, timezone.localdate()))

    def _probar(self):
        token, chats = configuracion()
        if not token or not chats:
            raise CommandError('Faltan TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_IDS en el .env.')
        fallos = 0
        for chat in chats:
            try:
                enviar_texto(token, chat, '✅ Prueba de Varagrill: las alertas de stock mínimo llegan a este chat.')
                self.stdout.write(f'{chat}: enviado')
            except Exception as error:  # noqa: BLE001
                fallos += 1
                self.stdout.write(f'{chat}: ERROR — {limpiar_error(error, token)}')
        if fallos:
            raise CommandError(f'{fallos} chat(s) no recibieron el mensaje de prueba.')

    def _estado(self):
        registros = list(VGEjecucionAlertaStock.objects.all()[:7])
        if not registros:
            self.stdout.write('Todavía no hay corridas registradas.')
            return
        for registro in registros:
            hora = timezone.localtime(registro.completado_en).strftime('%H:%M') if registro.completado_en else '—'
            detalle = f' — {registro.ultimo_error}' if registro.ultimo_error else ''
            self.stdout.write(
                f'{registro.fecha:%d/%m/%Y}  {registro.get_estado_display():<32} '
                f'{registro.cantidad_ingredientes} ingrediente(s), {registro.intentos} intento(s), hora {hora}{detalle}'
            )
