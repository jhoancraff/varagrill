"""
Alertas de precio de ingredientes y su historial de costos (ver costos_historial.py).

GET  /api/admin/alertas-costos/?vista=alertas|historial&estado=pendientes|revisadas|todas&ingrediente_id=N
     Lista las alertas (cambios de costo que pasaron el umbral) o el historial completo, con las recetas que
     cada alerta afecta y como cambia su costo.
POST /api/admin/alertas-costos/<id>/revisar/   {nota}
     Marca la alerta como revisada (quien, cuando y una nota opcional).
"""
import json
from decimal import Decimal
from types import SimpleNamespace

from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from . import api_views as av
from .auth_helpers import _auth_response, _is_admin_user
from .costos_historial import umbral_alerta
from .models import VGHistorialCostoIngrediente, VGIngrediente, VGProducto

LIMITE_DEFECTO = 60
LIMITE_CON_IMPACTO = 30   # el calculo de recetas afectadas se hace solo para las primeras filas de la lista
MAX_RECETAS_POR_ALERTA = 8


def _usuario(usuario):
    if usuario is None:
        return ''
    return usuario.get_full_name() or usuario.username


def _recetas_afectadas(filas):
    """
    {id_de_fila: {'recetas': [...], 'mas': N}}: los productos vendibles cuyo costo cambia por el cambio de costo de
    cada fila (directo o a traves de una subreceta o receta vinculada), con su costo antes y despues. Se calcula con
    los costos de HOY de los demas ingredientes: lo unico que cambia entre "antes" y "despues" es ese ingrediente.
    """
    if not filas:
        return {}
    costos_actuales = {
        row['id']: av._costo_unitario_efectivo(row['costo_unitario'], row['precio_compra'], row['peso_real'])
        for row in VGIngrediente.objects.values('id', 'costo_unitario', 'precio_compra', 'peso_real')
    }
    components_by_preparation, yields_by_preparation = av._load_preparation_structure()
    sin_rendimiento = SimpleNamespace(rendimiento_receta_pct=Decimal('0'))
    productos = list(
        VGProducto.objects.exclude(categoria__nombre__iexact='Recetas')
        .select_related('receta_vinculada', 'subreceta_vinculada')
        .prefetch_related('receta', 'receta_vinculada__receta', 'subreceta_vinculada__componentes')
    )

    resultado = {}
    for fila in filas:
        costos = {}
        mapas = {}
        for etiqueta, valor in (('antes', fila.costo_anterior), ('despues', fila.costo_nuevo)):
            costos[etiqueta] = {**costos_actuales, fila.ingrediente_id: valor}
            mapas[etiqueta] = av._compute_preparation_cost_map(
                components_by_preparation, costos[etiqueta], yields_by_preparation,
            )
        cambian = []
        for producto in productos:
            antes = av._compute_product_unit_cost(producto, costos['antes'], mapas['antes'], sin_rendimiento)
            despues = av._compute_product_unit_cost(producto, costos['despues'], mapas['despues'], sin_rendimiento)
            if antes != despues:
                cambian.append((abs(despues - antes), producto, antes, despues))
        cambian.sort(key=lambda t: t[0], reverse=True)
        resultado[fila.id] = {
            'recetas': [
                {
                    'id': producto.id, 'nombre': producto.nombre,
                    'costo_antes': str(antes.quantize(Decimal('0.01'))), 'costo_despues': str(despues.quantize(Decimal('0.01'))),
                }
                for _dif, producto, antes, despues in cambian[:MAX_RECETAS_POR_ALERTA]
            ],
            'mas': max(len(cambian) - MAX_RECETAS_POR_ALERTA, 0),
        }
    return resultado


def serializar_cambio(fila, impacto=None):
    datos = {
        'id': fila.id,
        'fecha': fila.fecha_creacion.isoformat(),
        'ingrediente': {
            'id': fila.ingrediente_id, 'nombre': fila.ingrediente.nombre, 'unidad': fila.ingrediente.unidad_medida,
        },
        'costo_anterior': str(fila.costo_anterior),
        'costo_nuevo': str(fila.costo_nuevo),
        'variacion_pct': str(fila.variacion_pct) if fila.variacion_pct is not None else None,
        'origen': fila.origen,
        'compra_id': fila.compra_id,
        'usuario': _usuario(fila.creado_por),
        'es_alerta': fila.es_alerta,
        'revisada': fila.revisada,
        'revisada_por': _usuario(fila.revisada_por),
        'fecha_revision': fila.fecha_revision.isoformat() if fila.fecha_revision else None,
        'nota_revision': fila.nota_revision,
    }
    if impacto is not None:
        datos['recetas_afectadas'] = impacto['recetas']
        datos['recetas_afectadas_mas'] = impacto['mas']
    return datos


def alertas_costos_pendientes():
    return VGHistorialCostoIngrediente.objects.filter(es_alerta=True, revisada=False).count()


@csrf_exempt
def alertas_costos_view(request):
    if request.method != 'GET':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)
    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)

    vista = str(request.GET.get('vista', 'alertas') or 'alertas').strip().lower()
    estado = str(request.GET.get('estado', 'pendientes') or 'pendientes').strip().lower()
    consulta = VGHistorialCostoIngrediente.objects.select_related('ingrediente', 'creado_por', 'revisada_por')

    if vista == 'historial':
        ingrediente_id = request.GET.get('ingrediente_id')
        if ingrediente_id:
            try:
                consulta = consulta.filter(ingrediente_id=int(ingrediente_id))
            except ValueError:
                return _auth_response({'ok': False, 'message': 'El ingrediente no es valido.'}, status=400)
    else:
        consulta = consulta.filter(es_alerta=True)
        if estado == 'pendientes':
            consulta = consulta.filter(revisada=False)
        elif estado == 'revisadas':
            consulta = consulta.filter(revisada=True)

    try:
        limite = min(max(int(request.GET.get('limite', LIMITE_DEFECTO)), 1), 300)
    except ValueError:
        limite = LIMITE_DEFECTO
    filas = list(consulta[:limite])

    impactos = _recetas_afectadas(filas[:LIMITE_CON_IMPACTO]) if vista != 'historial' else {}
    return _auth_response({
        'ok': True,
        'vista': vista,
        'umbral_pct': str(umbral_alerta()),
        'pendientes': alertas_costos_pendientes(),
        'items': [serializar_cambio(fila, impactos.get(fila.id)) for fila in filas],
    })


@csrf_exempt
def alerta_costo_revisar_view(request, alerta_id):
    if request.method != 'POST':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)
    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)

    try:
        fila = VGHistorialCostoIngrediente.objects.select_related('ingrediente', 'creado_por', 'revisada_por').get(pk=alerta_id)
    except VGHistorialCostoIngrediente.DoesNotExist:
        return _auth_response({'ok': False, 'message': 'La alerta no existe.'}, status=404)
    if not fila.es_alerta:
        return _auth_response({'ok': False, 'message': 'Este cambio de costo no es una alerta.'}, status=400)
    if fila.revisada:
        return _auth_response({'ok': False, 'message': 'Esta alerta ya fue revisada.'}, status=409)

    fila.revisada = True
    fila.revisada_por = request.user
    fila.fecha_revision = timezone.now()
    fila.nota_revision = str(data.get('nota', '') or '').strip()[:255]
    fila.actualizado_por = request.user
    fila.save(update_fields=['revisada', 'revisada_por', 'fecha_revision', 'nota_revision', 'actualizado_por', 'fecha_actualizacion'])
    return _auth_response({
        'ok': True,
        'message': 'Alerta marcada como revisada.',
        'alerta': serializar_cambio(fila),
        'pendientes': alertas_costos_pendientes(),
    })
