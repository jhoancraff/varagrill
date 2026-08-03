import os

import requests


def _is_enabled() -> bool:
    return os.getenv('WHATSAPP_ALERTS_ENABLED', '').strip().lower() in {'1', 'true', 'yes', 'on'}


def _build_order_message(pedido, actor_user) -> str:
    mesa_label = f"Mesa {pedido.mesa.numero}" if pedido.mesa else 'Sin mesa'
    actor_name = getattr(actor_user, 'username', 'mesero')
    return (
        f"Nuevo pedido #{pedido.id}\n"
        f"{mesa_label} · {pedido.tipo_pedido}\n"
        f"Total: ${pedido.total}\n"
        f"Mesero: {actor_name}\n"
        "Revisa la cocina en Varagrill."
    )


def send_whatsapp_new_order_alert(pedido, actor_user) -> None:
    if not _is_enabled():
        return

    phone_number_id = os.getenv('WHATSAPP_PHONE_NUMBER_ID', '').strip()
    access_token = os.getenv('WHATSAPP_ACCESS_TOKEN', '').strip()
    to_phone = os.getenv('WHATSAPP_TO_PHONE', '').strip()

    if not phone_number_id or not access_token or not to_phone:
        return

    url = f"https://graph.facebook.com/v20.0/{phone_number_id}/messages"
    message_text = _build_order_message(pedido, actor_user)

    payload = {
        'messaging_product': 'whatsapp',
        'to': to_phone,
        'type': 'text',
        'text': {
            'preview_url': False,
            'body': message_text,
        },
    }

    response = requests.post(
        url,
        headers={
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
        },
        json=payload,
        timeout=8,
    )
    response.raise_for_status()
