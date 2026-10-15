"""
Movimiento de inventario: que ingredientes se movieron en un rango de fechas, cuanto, y de donde vino
cada movimiento (de que pedido, de que nota de entrega).

Tres consultas, todas de solo lectura y para administradores:

  reporte_movimiento_inventario_view          una fila por ingrediente con movimiento: entradas, salidas,
                                              ajustes y movimientos. Se agrega en la base, asi que un rango
                                              largo no manda miles de filas.
  reporte_movimiento_inventario_detalle_view  los movimientos de UN ingrediente en el rango, mas recientes
                                              primero, cada uno con su origen.
  movimiento_inventario_pedido_view /         lo que abre el enlace de un movimiento: los productos del
  movimiento_inventario_nota_view             pedido y la(s) nota(s) de entrega en que se vendio.

No se cuentan los movimientos de rollback (rollback_inventario.py): son correcciones masivas del inventario
con motivo "ROLLBACK inventario ...", no movimientos del negocio.
"""
import unicodedata
from datetime import date
from decimal import Decimal

from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from .auth_helpers import _auth_response, _is_admin_user
from .models import VGMovimientoInventario, VGNotaEntrega, VGPedido

# Tope de movimientos que devuelve el detalle de un ingrediente: un insumo muy vendido puede tener miles
# en un rango largo; si se pasa, la pantalla avisa y pide acotar las fechas.
LIMITE_DETALLE = 2000

TIPOS_VALIDOS = {'entrada', 'salida', 'ajuste'}


def _sin_acentos(texto):
    return ''.join(c for c in unicodedata.normalize('NFKD', texto or '') if not unicodedata.combining(c)).lower()


def _solo_admin(request):
    if request.method != 'GET':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)
    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)
    return None


def _rango(request):
    """(desde, hasta) de la consulta (hoy por defecto) o None si las fechas no valen."""
    try:
        desde_raw = request.GET.get('desde')
        hasta_raw = request.GET.get('hasta')
        desde = date.fromisoformat(desde_raw) if desde_raw else timezone.localdate()
        hasta = date.fromisoformat(hasta_raw) if hasta_raw else timezone.localdate()
    except ValueError:
        return None
    if desde > hasta:
        return None
    return desde, hasta


def _movimientos_del_rango(desde, hasta, tipo=None):
    consulta = (
        VGMovimientoInventario.objects
        .filter(fecha_movimiento__date__gte=desde, fecha_movimiento__date__lte=hasta)
        .exclude(motivo__istartswith='ROLLBACK')
    )
    if tipo in TIPOS_VALIDOS:
        consulta = consulta.filter(tipo_movimiento=tipo)
    return consulta


def _origen(movimiento):
    """
    De donde vino un movimiento. Solo `pedido` y `nota_entrega` abren la ventana de detalle; los demas
    (compra, ajuste de inventario) se muestran como texto.
    """
    motivo = _sin_acentos(movimiento.motivo)
    referencia = movimiento.id_referencia
    if referencia and motivo.startswith('venta'):
        return {'tipo': 'pedido', 'id': referencia, 'etiqueta': f'Pedido #{referencia}'}
    if referencia and motivo.startswith('reversion por anulacion de nota'):
        return {'tipo': 'nota_entrega', 'id': referencia, 'etiqueta': f'Nota de entrega {referencia:08d}'}
    if movimiento.compra_id:
        return {'tipo': 'compra', 'id': movimiento.compra_id, 'etiqueta': f'Compra #{movimiento.compra_id}'}
    if referencia and movimiento.tipo_movimiento == 'ajuste':
        return {'tipo': 'ajuste', 'id': referencia, 'etiqueta': f'Ajuste #{referencia}'}
    return None


def reporte_movimiento_inventario_view(request):
    """
    Ingredientes con movimiento en el rango (`desde`/`hasta`, hoy por defecto), con lo que entro, lo que
    salio y los ajustes. `q` filtra por nombre y `tipo` (entrada|salida|ajuste) deja solo ese tipo de movimiento.
    """
    error = _solo_admin(request)
    if error:
        return error
    rango = _rango(request)
    if rango is None:
        return _auth_response({'ok': False, 'message': 'Las fechas no son validas.'}, status=400)
    desde, hasta = rango

    consulta = _movimientos_del_rango(desde, hasta, request.GET.get('tipo'))
    texto = (request.GET.get('q') or '').strip()
    if texto:
        consulta = consulta.filter(ingrediente__nombre__icontains=texto)

    cero = Value(Decimal('0'), output_field=DecimalField())

    def suma(tipo):
        return Coalesce(Sum('cantidad', filter=Q(tipo_movimiento=tipo)), cero, output_field=DecimalField())

    filas = (
        consulta
        .values('ingrediente_id', 'ingrediente__nombre', 'ingrediente__unidad_medida', 'ingrediente__stock_actual')
        .annotate(entradas=suma('entrada'), salidas=suma('salida'), ajustes=suma('ajuste'), movimientos=Count('id'))
        .order_by('ingrediente__nombre')
    )

    ingredientes = []
    total_movimientos = 0
    for fila in filas:
        entradas, salidas, ajustes = fila['entradas'], fila['salidas'], fila['ajustes']
        total_movimientos += fila['movimientos']
        ingredientes.append({
            'ingrediente_id': fila['ingrediente_id'],
            'nombre': fila['ingrediente__nombre'],
            'unidad': fila['ingrediente__unidad_medida'],
            'stock_actual': str(fila['ingrediente__stock_actual']),
            'entradas': str(entradas),
            'salidas': str(salidas),
            # Los ajustes ya traen su signo (suman o restan al stock).
            'ajustes': str(ajustes),
            'neto': str(entradas - salidas + ajustes),
            'movimientos': fila['movimientos'],
        })

    return _auth_response({
        'ok': True,
        'desde': desde.isoformat(),
        'hasta': hasta.isoformat(),
        'ingredientes': ingredientes,
        'total_ingredientes': len(ingredientes),
        'total_movimientos': total_movimientos,
    })


def reporte_movimiento_inventario_detalle_view(request, ingrediente_id):
    """Los movimientos de un ingrediente en el rango, mas recientes primero, cada uno con su origen."""
    error = _solo_admin(request)
    if error:
        return error
    rango = _rango(request)
    if rango is None:
        return _auth_response({'ok': False, 'message': 'Las fechas no son validas.'}, status=400)
    desde, hasta = rango

    consulta = (
        _movimientos_del_rango(desde, hasta, request.GET.get('tipo'))
        .filter(ingrediente_id=ingrediente_id)
        .select_related('creado_por')
        .order_by('-fecha_movimiento', '-id')
    )
    total = consulta.count()
    movimientos = []
    for movimiento in consulta[:LIMITE_DETALLE]:
        usuario = movimiento.creado_por
        movimientos.append({
            'id': movimiento.id,
            'fecha_hora': timezone.localtime(movimiento.fecha_movimiento).isoformat(),
            'tipo': movimiento.tipo_movimiento,
            'cantidad': str(movimiento.cantidad),
            'motivo': movimiento.motivo,
            'usuario': (usuario.get_full_name() or usuario.username) if usuario else '',
            'origen': _origen(movimiento),
        })

    return _auth_response({
        'ok': True,
        'ingrediente_id': ingrediente_id,
        'movimientos': movimientos,
        'total': total,
        'truncado': total > LIMITE_DETALLE,
        'limite': LIMITE_DETALLE,
    })


def _serializar_nota(nota):
    return {
        'id': nota.id,
        'codigo': nota.codigo,
        'estado': nota.estado,
        'fecha_emision': timezone.localtime(nota.fecha_emision).isoformat(),
        'total': str(nota.total),
        # Una nota puede cubrir varios pedidos: su total es el de todos, no el de este.
        'pedidos': [pedido.id for pedido in nota.pedidos.all()],
        'metodo_pago': nota.metodo_pago.nombre if nota.metodo_pago_id else '',
        'motivo_anulacion': nota.motivo_anulacion,
    }


def _serializar_pedido(pedido):
    cliente = pedido.cliente
    usuario = pedido.usuario
    return {
        'id': pedido.id,
        'fecha_hora': timezone.localtime(pedido.fecha_creacion).isoformat(),
        'estado': pedido.estado,
        'tipo_pedido': pedido.tipo_pedido,
        'mesa': pedido.mesa.numero if pedido.mesa_id else None,
        'cliente': (' '.join(filter(None, [cliente.nombre, cliente.apellido])) if cliente else ''),
        'mesero': (usuario.get_full_name() or usuario.username) if usuario else '',
        'subtotal': str(pedido.subtotal),
        'total': str(pedido.total),
        'cargo_delivery': str(pedido.cargo_delivery),
        'notas': pedido.notas,
        'productos': [
            {
                'producto': detalle.producto.nombre,
                'cantidad': detalle.cantidad,
                'peso_gramos': str(detalle.peso_gramos) if detalle.peso_gramos is not None else None,
                'precio_unitario': str(detalle.precio_unitario),
                'subtotal': str(detalle.subtotal),
                'notas': detalle.notas,
            }
            for detalle in pedido.detalles.all()
        ],
        'notas_entrega': [_serializar_nota(nota) for nota in pedido.notas_entrega.all()],
        'facturas': [
            {'id': factura.id, 'codigo': f'{factura.numero_factura:08d}'}
            for factura in pedido.facturas.all()
        ],
    }


def _pedidos_con_detalle():
    return (
        VGPedido.objects
        .select_related('mesa', 'usuario', 'cliente')
        .prefetch_related('detalles__producto', 'notas_entrega__metodo_pago', 'notas_entrega__pedidos', 'facturas')
    )


def movimiento_inventario_pedido_view(request, pedido_id):
    """Un pedido: los productos que llevaba y la nota de entrega (o factura) en la que se vendio."""
    error = _solo_admin(request)
    if error:
        return error
    pedido = _pedidos_con_detalle().filter(pk=pedido_id).first()
    if pedido is None:
        return _auth_response({'ok': False, 'message': 'No se encontro ese pedido.'}, status=404)
    return _auth_response({'ok': True, 'pedido': _serializar_pedido(pedido)})


def movimiento_inventario_nota_view(request, nota_id):
    """Una nota de entrega y los pedidos (con sus productos) que se vendieron en ella."""
    error = _solo_admin(request)
    if error:
        return error
    nota = VGNotaEntrega.objects.select_related('metodo_pago').filter(pk=nota_id).first()
    if nota is None:
        return _auth_response({'ok': False, 'message': 'No se encontro esa nota de entrega.'}, status=404)
    pedidos = _pedidos_con_detalle().filter(notas_entrega=nota).order_by('id')
    return _auth_response({
        'ok': True,
        'nota': _serializar_nota(nota),
        'pedidos': [_serializar_pedido(pedido) for pedido in pedidos],
    })
