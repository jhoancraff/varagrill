"""
Stock minimo en el sistema (Inventario -> Stock minimo): el MISMO reporte que se manda cada dia por Telegram
(ver alertas_stock.py), para que los usuarios le den seguimiento y repongan los ingredientes con una compra.

Entran los ingredientes con stock minimo definido (> 0) cuyo stock actual esta en ese minimo o por debajo, igual que
en el aviso. Aqui ademas se calcula cuanto falta para llegar al minimo y en que estado esta cada uno, y se informa
como le fue al aviso de hoy.
"""
from decimal import Decimal

from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from . import alertas_stock
from .auth_helpers import _auth_response, _is_admin_user
from .models import VGEjecucionAlertaStock

SIN_STOCK = 'sin_stock'
BAJO = 'bajo'
EN_MINIMO = 'en_minimo'


def _estado(stock, minimo):
    """'sin_stock' si ya no queda (o esta en negativo), 'bajo' si esta por debajo del minimo, 'en_minimo' si es justo."""
    if stock <= 0:
        return SIN_STOCK
    return BAJO if stock < minimo else EN_MINIMO


def _serialize(fila):
    stock = Decimal(fila['stock_actual'])
    minimo = Decimal(fila['stock_minimo'])
    return {
        'id': fila['id'],
        'nombre': fila['nombre'].strip(),
        'unidad': fila['unidad_medida'],
        'categoria': fila['categoria__nombre'] or '',
        'stock_actual': str(stock),
        'stock_minimo': str(minimo),
        # Cuanto falta para llegar al minimo (0 si ya esta justo en el): una referencia para saber cuanto comprar.
        'faltante': str(max(minimo - stock, Decimal('0'))),
        'estado': _estado(stock, minimo),
    }


def _ultimo_aviso(hoy):
    """Como le fue al aviso de Telegram de hoy (o el ultimo registrado si hoy todavia no corrio)."""
    registro = VGEjecucionAlertaStock.objects.filter(fecha__lte=hoy).first()
    if registro is None:
        return None
    return {
        'fecha': registro.fecha.isoformat(),
        'es_de_hoy': registro.fecha == hoy,
        'estado': registro.estado,
        'estado_label': registro.get_estado_display(),
        'cantidad_ingredientes': registro.cantidad_ingredientes,
        'intentos': registro.intentos,
        'ultimo_error': registro.ultimo_error,
        'completado_en': timezone.localtime(registro.completado_en).isoformat() if registro.completado_en else None,
    }


@csrf_exempt
def admin_stock_minimo_view(request):
    if request.method != 'GET':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)
    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)

    hoy = timezone.localdate()
    ingredientes = [_serialize(fila) for fila in alertas_stock.ingredientes_en_minimo()]
    return _auth_response({
        'ok': True,
        'fecha': hoy.isoformat(),
        'ingredientes': ingredientes,
        'resumen': {
            'total': len(ingredientes),
            'sin_stock': sum(1 for fila in ingredientes if fila['estado'] == SIN_STOCK),
            'bajo': sum(1 for fila in ingredientes if fila['estado'] == BAJO),
            'en_minimo': sum(1 for fila in ingredientes if fila['estado'] == EN_MINIMO),
        },
        'ultimo_aviso': _ultimo_aviso(hoy),
    })
