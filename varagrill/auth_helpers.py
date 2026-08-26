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


def _is_contador_user(user):
    if not getattr(user, 'is_authenticated', False):
        return False
    return _get_role_name(user).lower() == 'contador'


def _is_owner_user(user):
    """
    Nivel superior de acceso real (el dueño del negocio), separado a propósito del rol
    'Administrador': un usuario con rol Administrador gestiona el día a día (menú,
    usuarios, mesas, recetas, contabilidad...) pero NO ve las pantallas más sensibles
    (impresoras, datos fiscales, historial de compras) — esas quedan reservadas a
    cuentas marcadas is_staff/is_superuser en Django, sin importar el rol de catálogo
    que tengan asignado. Ver _is_owner_or_contador_user para las vistas donde el
    Contador también debe entrar a esas mismas pantallas.
    """
    if not getattr(user, 'is_authenticated', False):
        return False
    return bool(getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False))


def _is_owner_or_contador_user(user):
    return _is_owner_user(user) or _is_contador_user(user)


def _is_admin_user(user):
    if not getattr(user, 'is_authenticated', False):
        return False
    role_name = _get_role_name(user).lower()
    if role_name in ('administrador', 'contador'):
        return True
    return bool(getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False))
