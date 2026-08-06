import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer


class PedidosConsumer(AsyncWebsocketConsumer):
    """
    Socket único para todo el equipo autenticado. Cada usuario se une a su propio grupo
    personal (avisos como "tu pedido está listo") y, si es cocinero, también al grupo de
    rol que recibe las comandas nuevas/actualizadas.
    """

    async def connect(self):
        user = self.scope.get('user')
        if not user or not user.is_authenticated:
            await self.close(code=4403)
            return

        role_name = await _get_user_role_name(user)
        self.group_names = [f'usuario_{user.id}_notifications']
        if role_name == 'cocinero':
            self.group_names.append('role_cocinero_notifications')

        for group_name in self.group_names:
            await self.channel_layer.group_add(group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        for group_name in getattr(self, 'group_names', []):
            await self.channel_layer.group_discard(group_name, self.channel_name)

    async def cocina_order_notification(self, event):
        await self._forward(event)

    async def usuario_order_notification(self, event):
        await self._forward(event)

    async def _forward(self, event):
        payload = event.get('payload', {})
        await self.send(text_data=json.dumps({
            'event': payload.get('event', 'NOTIFICACION'),
            'type': event.get('type', 'notification'),
            'payload': payload,
        }))


@database_sync_to_async
def _get_user_role_name(user):
    return ((getattr(getattr(user, 'id_role', None), 'nombre_role', '') or '').strip().lower())


# Compatibilidad hacia atras con rutas/imports existentes.
CocinaConsumer = PedidosConsumer
MeseroNotificationsConsumer = PedidosConsumer