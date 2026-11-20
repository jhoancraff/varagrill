"""
Configuracion de merma de los ingredientes (Costeo -> Configuracion de merma).

Un ingrediente con "peso real" menor que el "contenido del envase" pierde una parte al prepararlo (pelar el aguacate,
limpiar el cebollin...). El costo ya lo considera (precio del envase / peso real = costo por gramo aprovechable),
pero el inventario descontaba lo que dice la receta tal cual, asi que el sistema creia que quedaba mas de lo que hay.

Cada ingrediente tiene un interruptor (VGIngrediente.descuenta_merma, apagado por defecto). Encendido, al vender se
descuenta lo que de verdad se consumio: cantidad de la receta x contenido del envase / peso real (ej. 500 g de
aguacate con envase de 1000 g y peso real de 500 g descuentan 1000 g). Ver api_views._aplicar_merma_a_necesidades.

Solo debe encenderse cuando las recetas de ese ingrediente estan escritas en gramos ya limpios/aprovechables. Si la
receta ya cuenta la perdida (ej. "Pork belly cocina": 1400 g crudos rinden 1000 g), descontar la merma otra vez
duplicaria el consumo. Por eso no se activa solo: lo decide quien conoce las recetas.
"""
import json
from decimal import Decimal

from django.db.models import F, Q
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .api_views import HIDDEN_INGREDIENT_IDS, _factor_merma_de
from .auth_helpers import _auth_response, _is_admin_user
from .models import VGIngrediente, VGRecetaPreparacion, VGRecetaProducto

MAX_IDS_POR_ENVIO = 500
USOS_POR_INGREDIENTE = 8


def _con_merma():
    """Ingredientes (g/ml) con envase y peso real cargados y peso real menor al envase: los que tienen merma."""
    return (
        VGIngrediente.objects.exclude(id__in=HIDDEN_INGREDIENT_IDS)
        .exclude(unidad_medida='unidad')
        .filter(contenido_envase__gt=0, peso_real__gt=0, peso_real__lt=F('contenido_envase'))
    )


def _listado_queryset():
    # Tambien los que quedaron encendidos y ya no tienen merma (se cambio el peso real): hay que poder apagarlos.
    return (
        VGIngrediente.objects.exclude(id__in=HIDDEN_INGREDIENT_IDS)
        .filter(Q(pk__in=_con_merma().values('pk')) | Q(descuenta_merma=True))
        .select_related('categoria')
        .order_by('nombre')
    )


def _usos(ingrediente_ids):
    """{ingrediente_id: [{'tipo', 'nombre', 'cantidad'}]}: en que recetas y subrecetas se usa cada ingrediente."""
    usos = {}
    for fila in VGRecetaProducto.objects.filter(ingrediente_id__in=ingrediente_ids).select_related('producto'):
        usos.setdefault(fila.ingrediente_id, []).append(
            {'tipo': 'receta', 'nombre': fila.producto.nombre, 'cantidad': f'{fila.cantidad_requerida.normalize():f}'}
        )
    for fila in VGRecetaPreparacion.objects.filter(ingrediente_id__in=ingrediente_ids).select_related('preparacion'):
        usos.setdefault(fila.ingrediente_id, []).append(
            {'tipo': 'subreceta', 'nombre': fila.preparacion.nombre, 'cantidad': f'{fila.cantidad_requerida.normalize():f}'}
        )
    return usos


def _serialize(ingrediente, usos):
    factor = _factor_merma_de(ingrediente, ignorar_interruptor=True)
    merma_pct = (Decimal('1') - Decimal(ingrediente.peso_real) / Decimal(ingrediente.contenido_envase)) * Decimal('100') \
        if ingrediente.contenido_envase and ingrediente.peso_real else None
    lista = usos.get(ingrediente.id, [])
    return {
        'id': ingrediente.id,
        'nombre': ingrediente.nombre,
        'unidad': ingrediente.unidad_medida,
        'categoria': ingrediente.categoria.nombre if ingrediente.categoria_id else '',
        'contenido_envase': str(ingrediente.contenido_envase) if ingrediente.contenido_envase is not None else None,
        'peso_real': str(ingrediente.peso_real) if ingrediente.peso_real is not None else None,
        'merma_pct': str(merma_pct.quantize(Decimal('0.1'))) if merma_pct is not None else None,
        'factor': str(factor.quantize(Decimal('0.01'))),
        'stock_actual': str(ingrediente.stock_actual),
        'descuenta_merma': ingrediente.descuenta_merma,
        # Encendido pero sin merma real (peso real igual al envase, o es "unidad"): no descuenta nada extra.
        'aplica': ingrediente.descuenta_merma and factor > 1,
        'usos': lista[:USOS_POR_INGREDIENTE],
        'usos_total': len(lista),
    }


def _respuesta_listado(extra=None):
    ingredientes = list(_listado_queryset())
    usos = _usos([i.id for i in ingredientes])
    datos = [_serialize(i, usos) for i in ingredientes]
    resumen = {'con_merma': len(datos), 'activos': sum(1 for d in datos if d['descuenta_merma'])}
    return {'ok': True, 'ingredientes': datos, 'resumen': resumen, **(extra or {})}


@csrf_exempt
def admin_merma_ingredientes_view(request):
    if request.method not in ('GET', 'POST'):
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)
    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)

    if request.method == 'GET':
        return _auth_response(_respuesta_listado())

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)

    if str(data.get('action', '')).strip().lower() != 'actualizar':
        return _auth_response({'ok': False, 'message': 'Accion invalida.'}, status=400)

    activar = data.get('descuenta_merma')
    if not isinstance(activar, bool):
        return _auth_response({'ok': False, 'message': 'Indica si se activa o se desactiva el descuento de merma.'}, status=400)

    ids = data.get('ids')
    if not isinstance(ids, list) or not ids:
        return _auth_response({'ok': False, 'message': 'Selecciona al menos un ingrediente.'}, status=400)
    if len(ids) > MAX_IDS_POR_ENVIO:
        return _auth_response({'ok': False, 'message': f'Maximo {MAX_IDS_POR_ENVIO} ingredientes por vez.'}, status=400)
    try:
        ids = sorted({int(valor) for valor in ids})
    except (TypeError, ValueError):
        return _auth_response({'ok': False, 'message': 'Hay un ingrediente invalido en la seleccion.'}, status=400)

    existentes = VGIngrediente.objects.filter(pk__in=ids).exclude(id__in=HIDDEN_INGREDIENT_IDS)
    if existentes.count() != len(ids):
        return _auth_response({'ok': False, 'message': 'Hay ingredientes que ya no existen.'}, status=400)

    if activar:
        sin_merma = list(existentes.exclude(pk__in=_con_merma().values('pk')).values_list('nombre', flat=True))
        if sin_merma:
            return _auth_response({
                'ok': False,
                'message': (
                    'Estos ingredientes no tienen merma (su peso real no es menor que el contenido del envase, '
                    'o se miden por unidad): ' + ', '.join(sorted(sin_merma)[:5]) + '.'
                ),
            }, status=400)

    cambiados = existentes.exclude(descuenta_merma=activar).update(
        descuenta_merma=activar, actualizado_por=request.user, fecha_actualizacion=timezone.now(),
    )
    accion = 'se descontará la merma' if activar else 'dejará de descontarse la merma'
    return _auth_response(_respuesta_listado({
        'message': (
            f'{cambiados} ingrediente(s) actualizado(s): al vender {accion} del inventario.'
            if cambiados else 'No había nada que cambiar.'
        ),
        'cambiados': cambiados,
    }))
