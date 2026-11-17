"""
Envio de mensajes por Telegram (bot) para las alertas del sistema.

Configuracion (en el .env):
    TELEGRAM_BOT_TOKEN   token que entrega @BotFather al crear el bot.
    TELEGRAM_CHAT_IDS    ids de los chats que reciben el aviso, separados por coma (una persona o un grupo).
"""
import os

import requests

# Telegram rechaza mensajes de mas de 4096 caracteres: se parte en varios con margen de sobra.
LIMITE_MENSAJE = 4000


def configuracion():
    """Devuelve (token, [chat_ids]) leidos del entorno; vacios si no esta configurado."""
    token = os.getenv('TELEGRAM_BOT_TOKEN', '').strip()
    chats = [chat.strip() for chat in os.getenv('TELEGRAM_CHAT_IDS', '').split(',') if chat.strip()]
    return token, chats


def partir_mensaje(texto, limite=LIMITE_MENSAJE):
    """Parte un texto largo en trozos de hasta `limite` caracteres, cortando por lineas."""
    partes = []
    actual = ''
    for linea in texto.split('\n'):
        while len(linea) > limite:
            if actual:
                partes.append(actual)
                actual = ''
            partes.append(linea[:limite])
            linea = linea[limite:]
        candidato = f'{actual}\n{linea}' if actual else linea
        if len(candidato) > limite:
            partes.append(actual)
            actual = linea
        else:
            actual = candidato
    if actual:
        partes.append(actual)
    return partes or ['']


def limpiar_error(error, token):
    """Texto del error sin el token: requests mete la URL (con el token) en sus mensajes de error."""
    texto = str(error)
    return texto.replace(token, '***') if token else texto


def enviar_texto(token, chat_id, texto):
    """
    Manda `texto` al chat indicado. Si no se pudo (sin internet, token malo, chat inexistente, bot bloqueado...)
    lanza una excepcion con la razon, para que quien llama decida si reintenta.
    """
    for parte in partir_mensaje(texto):
        respuesta = requests.post(
            f'https://api.telegram.org/bot{token}/sendMessage',
            json={'chat_id': chat_id, 'text': parte},
            timeout=10,
        )
        if not respuesta.ok:
            try:
                detalle = respuesta.json().get('description') or respuesta.text
            except ValueError:
                detalle = respuesta.text
            raise RuntimeError(f'Telegram respondió {respuesta.status_code}: {detalle}')
