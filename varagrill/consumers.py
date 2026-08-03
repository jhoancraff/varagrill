import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer


class CocinaConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get('user')
        role_name = await _get_user_role_name(user)

        if not user or not user.is_authenticated or role_name != 'cocinero':
            await self.close(code=4403)
            return

        self.group_name = 'role_cocinero_notifications'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        group_name = getattr(self, 'group_name', None)
        if group_name:
            await self.channel_layer.group_discard(group_name, self.channel_name)

    async def cocina_order_notification(self, event):
        payload = event.get('payload', {})
        await self.send(text_data=json.dumps({
            'event': payload.get('event', 'NUEVA_COMANDAS'),
            'type': event.get('type', 'cocina_order_notification'),
            'payload': payload,
        }))


@database_sync_to_async
def _get_user_role_name(user):
    return ((getattr(getattr(user, 'id_role', None), 'nombre_role', '') or '').strip().lower())


# Compatibilidad hacia atras con rutas/imports existentes.
MeseroNotificationsConsumer = CocinaConsumer
