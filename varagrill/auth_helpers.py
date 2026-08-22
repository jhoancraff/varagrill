"""
Helpers de autenticacion/roles compartidos entre las vistas del restaurante
(api_views.py) y las de contabilidad (contabilidad_views.py), para que
ninguno de los dos dependa del otro solo por estas funciones chicas.
"""
from django.http import JsonResponse


def _auth_response(payload, status=200):
    response = JsonResponse(payload, status=status)
    response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0, private'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    response['Vary'] = 'Cookie'
    return response


def _get_role_name(user):
    return str(getattr(getattr(user, 'id_role', None), 'nombre_role', '') or '').strip()


def _is_mesero_user(user):
    return _get_role_name(user).lower() == 'mesero'


def _is_cajera_user(user):
    if not getattr(user, 'is_authenticated', False):
        return False
    return _get_role_name(user).lower() == 'cajera'


def _is_admin_user(user):
    if not getattr(user, 'is_authenticated', False):
        return False
    role_name = _get_role_name(user).lower()
    return role_name == 'administrador' or bool(getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False))
