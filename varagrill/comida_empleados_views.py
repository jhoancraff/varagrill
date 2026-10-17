"""
Comida de empleados: una seccion aparte (administradores y contadores) para registrar la comida que se
prepara para el personal. No se vende ni se factura: solo descuenta del inventario los ingredientes de una
receta, de una subreceta o de un ingrediente suelto.

Descuenta con las mismas funciones que el cobro de un pedido (recetas, subrecetas anidadas y rendimientos),
asi un ingrediente sale del inventario igual que si se vendiera. Cada registro guarda, por ingrediente, lo
que descontó y su costo de ese momento (VGDetalleComidaEmpleados): con eso se anula reponiendo exactamente lo
descontado, y el Estado de resultados la cuenta como "Alimentacion del personal".

  comida_empleados_opciones_view          que se puede elegir (recetas marcadas, subrecetas, ingredientes)
  comida_empleados_previsualizar_view     que ingredientes descontaria, con su stock, sin tocar nada
  comida_empleados_view                   GET: historial por rango. POST: registrar
  comida_empleados_detalle_view           una comida con sus ingredientes
  comida_empleados_anular_view            anularla y reponer el stock (solo administradores)
"""
import json
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .api_views import (
    HIDDEN_INGREDIENT_IDS,
    _add_preparation_needs,
    _costo_unitario_efectivo,
    _load_preparation_structure,
    _product_recipe_components,
)
from .auth_helpers import _auth_response, _get_role_name, _is_admin_user
from .models import (
    VGComidaEmpleados,
    VGDetalleComidaEmpleados,
    VGIngrediente,
    VGMovimientoInventario,
    VGPreparacion,
    VGProducto,
)
from .tasa_cambio import tasa_cambio_para_registro

CENTAVO = Decimal('0.01')
CANTIDAD_MAXIMA = Decimal('1000000')
TURNOS = {valor for valor, _etiqueta in VGComidaEmpleados.TURNOS}
TIPOS = {valor for valor, _etiqueta in VGComidaEmpleados.TIPOS_ORIGEN}


def _es_administrador(user):
    """
    Administrador de verdad (rol Administrador o acceso de dueño). El Contador entra a la seccion y registra
    la comida de hoy, pero no puede registrar fechas pasadas ni anular.
    """
    if not _is_admin_user(user):
        return False
    return (
        _get_role_name(user).lower() == 'administrador'
        or bool(getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False))
    )


def _solo_admin(request, metodos=('GET',)):
    if request.method not in metodos:
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)
    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)
    return None


def _json_body(request):
    try:
        return json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return None


def _decimal(valor):
    try:
        return Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _fmt(valor):
    """Una cantidad para un texto (12.50 -> '12.5', 3.00 -> '3')."""
    texto = f'{Decimal(valor):f}'
    return texto.rstrip('0').rstrip('.') if '.' in texto else texto


# ── seleccion y consumo ─────────────────────────────────────────────────────
def _resolver_origen(tipo, origen_id):
    """(objeto, unidad, error) de lo que se eligio. Una receta tiene que estar marcada para empleados."""
    if tipo not in TIPOS:
        return None, None, 'Elige una receta, una subreceta o un ingrediente.'
    try:
        origen_id = int(origen_id)
    except (TypeError, ValueError):
        return None, None, 'Elige una receta, una subreceta o un ingrediente.'

    if tipo == 'receta':
        receta = VGProducto.objects.filter(categoria__nombre__iexact='Recetas', pk=origen_id).first()
        if receta is None:
            return None, None, 'Esa receta no existe.'
        if not receta.apta_comida_empleados:
            return None, None, f'La receta "{receta.nombre}" no está marcada para comida de empleados.'
        return receta, 'porciones', None
    if tipo == 'subreceta':
        subreceta = VGPreparacion.objects.filter(pk=origen_id).first()
        if subreceta is None:
            return None, None, 'Esa subreceta no existe.'
        return subreceta, subreceta.rendimiento_unidad or 'unidad', None
    ingrediente = VGIngrediente.objects.filter(pk=origen_id).exclude(id__in=HIDDEN_INGREDIENT_IDS).first()
    if ingrediente is None:
        return None, None, 'Ese ingrediente no existe.'
    return ingrediente, ingrediente.unidad_medida, None


def _necesidades(tipo, objeto, cantidad):
    """{ingrediente_id: Decimal} que hay que descontar, con la misma expansion que usa el cobro de un pedido."""
    if tipo == 'ingrediente':
        return {objeto.id: cantidad}
    components_by_preparation, yields_by_preparation = _load_preparation_structure()
    needs = {}
    if tipo == 'subreceta':
        _add_preparation_needs(objeto.id, cantidad, components_by_preparation, yields_by_preparation, needs, set())
        return needs
    for component in _product_recipe_components(objeto):
        monto = component['cantidad'] * cantidad
        if component['tipo'] == 'ingrediente':
            needs[component['referencia_id']] = needs.get(component['referencia_id'], Decimal('0')) + monto
        else:
            _add_preparation_needs(
                component['referencia_id'], monto, components_by_preparation, yields_by_preparation, needs, set(),
            )
    return needs


def _lineas(necesidades, ingredientes_por_id):
    """Las cantidades redondeadas al centavo (como se guarda el stock), con stock, costo y si alcanza."""
    lineas = []
    for ingrediente_id in sorted(necesidades, key=lambda i: ingredientes_por_id[i].nombre.lower()):
        ingrediente = ingredientes_por_id[ingrediente_id]
        cantidad = necesidades[ingrediente_id].quantize(CENTAVO, rounding=ROUND_HALF_UP)
        if cantidad <= 0:
            continue
        costo_unitario = _costo_unitario_efectivo(ingrediente.costo_unitario, ingrediente.precio_compra, ingrediente.peso_real)
        stock = Decimal(str(ingrediente.stock_actual))
        lineas.append({
            'ingrediente': ingrediente,
            'cantidad': cantidad,
            'costo_unitario': costo_unitario,
            'costo': cantidad * costo_unitario,
            'stock_actual': stock,
            'stock_despues': stock - cantidad,
        })
    return lineas


def _lineas_json(lineas):
    return [
        {
            'ingrediente_id': l['ingrediente'].id,
            'nombre': l['ingrediente'].nombre,
            'unidad': l['ingrediente'].unidad_medida,
            'cantidad': str(l['cantidad']),
            'stock_actual': str(l['stock_actual']),
            'stock_despues': str(l['stock_despues']),
            'alcanza': l['stock_despues'] >= 0,
            'costo': str(l['costo'].quantize(Decimal('0.0001'))),
        }
        for l in lineas
    ]


def _leer_seleccion(data):
    """(tipo, objeto, unidad, cantidad, error) de lo que mando la pantalla."""
    tipo = str(data.get('tipo') or '').strip().lower()
    objeto, unidad, error = _resolver_origen(tipo, data.get('origen_id'))
    if error:
        return None, None, None, None, error
    cantidad = _decimal(data.get('cantidad'))
    if cantidad is None or cantidad <= 0:
        return None, None, None, None, 'Indica una cantidad mayor a cero.'
    if cantidad > CANTIDAD_MAXIMA:
        return None, None, None, None, 'La cantidad es demasiado grande.'
    return tipo, objeto, unidad, cantidad, None


def _leer_fecha(data, user):
    """(fecha, error): hoy por defecto; una fecha pasada solo la puede registrar un administrador."""
    hoy = timezone.localdate()
    texto = data.get('fecha')
    if not texto:
        return hoy, None
    try:
        fecha = date.fromisoformat(str(texto))
    except ValueError:
        return None, 'La fecha no es válida.'
    if fecha > hoy:
        return None, 'La fecha no puede ser futura.'
    if fecha < hoy and not _es_administrador(user):
        return None, 'Solo un administrador puede registrar una comida de una fecha pasada.'
    return fecha, None


def _turno(data):
    turno = str(data.get('turno') or '').strip().lower()
    return turno if turno in TURNOS else ''


def _ya_registradas(fecha, turno):
    """Comidas registradas ese dia (y ese turno, si se indica): para avisar antes de duplicar."""
    consulta = VGComidaEmpleados.objects.filter(fecha=fecha, estado='registrada')
    if turno:
        consulta = consulta.filter(turno=turno)
    return [
        {'id': c.id, 'nombre': c.nombre_origen, 'cantidad': str(c.cantidad), 'unidad': c.unidad, 'turno': c.turno}
        for c in consulta[:10]
    ]


# ── serializacion ───────────────────────────────────────────────────────────
def _usuario(user):
    return (user.get_full_name() or user.username) if user else ''


def _serializar(comida, con_lineas=False):
    data = {
        'id': comida.id,
        'fecha': comida.fecha.isoformat(),
        'turno': comida.turno,
        'turno_label': comida.get_turno_display() if comida.turno else '',
        'tipo_origen': comida.tipo_origen,
        'tipo_origen_label': comida.get_tipo_origen_display(),
        'nombre': comida.nombre_origen,
        'cantidad': str(comida.cantidad),
        'unidad': comida.unidad,
        'nota': comida.nota,
        'estado': comida.estado,
        'costo_total': str(comida.costo_total.quantize(CENTAVO)),
        'tasa_cambio_referencia': str(comida.tasa_cambio_referencia) if comida.tasa_cambio_referencia is not None else None,
        'registrada_por': _usuario(comida.creado_por),
        'fecha_creacion': timezone.localtime(comida.fecha_creacion).isoformat(),
        'anulada_por': _usuario(comida.anulada_por),
        'fecha_anulacion': timezone.localtime(comida.fecha_anulacion).isoformat() if comida.fecha_anulacion else None,
        'motivo_anulacion': comida.motivo_anulacion,
    }
    if con_lineas:
        data['lineas'] = [
            {
                'ingrediente_id': d.ingrediente_id,
                'nombre': d.ingrediente.nombre,
                'unidad': d.ingrediente.unidad_medida,
                'cantidad': str(d.cantidad),
                'costo': str((d.cantidad * d.costo_unitario).quantize(Decimal('0.0001'))),
            }
            for d in comida.detalles.select_related('ingrediente').order_by('ingrediente__nombre')
        ]
    return data


# ── vistas ──────────────────────────────────────────────────────────────────
@csrf_exempt
def comida_empleados_opciones_view(request):
    """Lo que se puede elegir: recetas marcadas para empleados, subrecetas e ingredientes."""
    error = _solo_admin(request)
    if error:
        return error
    return _auth_response({
        'ok': True,
        'recetas': list(
            VGProducto.objects.filter(categoria__nombre__iexact='Recetas', apta_comida_empleados=True)
            .order_by('nombre').values('id', 'nombre')
        ),
        'subrecetas': list(
            VGPreparacion.objects.order_by('nombre').values('id', 'nombre', 'rendimiento_unidad')
        ),
        'ingredientes': list(
            VGIngrediente.objects.exclude(id__in=HIDDEN_INGREDIENT_IDS).order_by('nombre')
            .values('id', 'nombre', 'unidad_medida', 'stock_actual')
        ),
        'turnos': [{'value': v, 'label': e} for v, e in VGComidaEmpleados.TURNOS],
        'puede_fecha_pasada': _es_administrador(request.user),
        'puede_anular': _es_administrador(request.user),
    })


@csrf_exempt
def comida_empleados_previsualizar_view(request):
    """Que ingredientes se descontarian y como quedaria el stock. No guarda nada."""
    error = _solo_admin(request, ('POST',))
    if error:
        return error
    data = _json_body(request)
    if data is None:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)
    tipo, objeto, unidad, cantidad, error_texto = _leer_seleccion(data)
    if error_texto:
        return _auth_response({'ok': False, 'message': error_texto}, status=400)
    fecha, error_texto = _leer_fecha(data, request.user)
    if error_texto:
        return _auth_response({'ok': False, 'message': error_texto}, status=400)

    necesidades = _necesidades(tipo, objeto, cantidad)
    ingredientes = VGIngrediente.objects.in_bulk(list(necesidades))
    lineas = _lineas(necesidades, ingredientes)
    if not lineas:
        return _auth_response({
            'ok': False,
            'message': 'Esa selección no descuenta ningún ingrediente (¿la receta está vacía o la cantidad es muy pequeña?).',
        }, status=400)
    return _auth_response({
        'ok': True,
        'nombre': objeto.nombre,
        'unidad': unidad,
        'lineas': _lineas_json(lineas),
        'costo_total': str(sum((l['costo'] for l in lineas), Decimal('0')).quantize(CENTAVO)),
        'sin_stock': [l['ingrediente'].nombre for l in lineas if l['stock_despues'] < 0],
        'ya_registradas': _ya_registradas(fecha, _turno(data)),
    })


@csrf_exempt
def comida_empleados_view(request):
    """GET: el historial de un rango (el mes en curso por defecto). POST: registrar una comida."""
    error = _solo_admin(request, ('GET', 'POST'))
    if error:
        return error
    if request.method == 'GET':
        return _listar(request)
    return _registrar(request)


def _listar(request):
    hoy = timezone.localdate()
    try:
        desde = date.fromisoformat(request.GET['desde']) if request.GET.get('desde') else hoy.replace(day=1)
        hasta = date.fromisoformat(request.GET['hasta']) if request.GET.get('hasta') else hoy
    except ValueError:
        return _auth_response({'ok': False, 'message': 'Las fechas no son validas.'}, status=400)
    if desde > hasta:
        return _auth_response({'ok': False, 'message': '"Desde" no puede ser posterior a "Hasta".'}, status=400)

    comidas = list(
        VGComidaEmpleados.objects.filter(fecha__gte=desde, fecha__lte=hasta)
        .select_related('creado_por', 'anulada_por').order_by('-fecha', '-id')
    )
    registradas = [c for c in comidas if c.estado == 'registrada']
    return _auth_response({
        'ok': True,
        'desde': desde.isoformat(),
        'hasta': hasta.isoformat(),
        'comidas': [_serializar(c) for c in comidas],
        'total_registradas': len(registradas),
        'costo_total': str(sum((c.costo_total for c in registradas), Decimal('0')).quantize(CENTAVO)),
    })


def _registrar(request):
    data = _json_body(request)
    if data is None:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)
    tipo, objeto, unidad, cantidad, error_texto = _leer_seleccion(data)
    if error_texto:
        return _auth_response({'ok': False, 'message': error_texto}, status=400)
    fecha, error_texto = _leer_fecha(data, request.user)
    if error_texto:
        return _auth_response({'ok': False, 'message': error_texto}, status=400)
    turno = _turno(data)
    nota = str(data.get('nota') or '').strip()[:255]

    necesidades = _necesidades(tipo, objeto, cantidad)
    if not necesidades:
        return _auth_response({'ok': False, 'message': 'Esa selección no descuenta ningún ingrediente.'}, status=400)

    with transaction.atomic():
        # Se bloquean los ingredientes para que dos registros a la vez no descuenten sobre el mismo stock.
        ingredientes = {
            i.id: i for i in VGIngrediente.objects.select_for_update().filter(id__in=list(necesidades)).order_by('id')
        }
        lineas = _lineas(necesidades, ingredientes)
        if not lineas:
            return _auth_response({'ok': False, 'message': 'Esa selección no descuenta ningún ingrediente.'}, status=400)

        faltantes = [l for l in lineas if l['stock_despues'] < 0]
        if faltantes and not data.get('confirmar_stock_insuficiente'):
            return _auth_response({
                'ok': False,
                'code': 'stock_insuficiente',
                'message': 'Algunos ingredientes no alcanzan: el stock quedaría en negativo.',
                'sin_stock': [l['ingrediente'].nombre for l in faltantes],
                'lineas': _lineas_json(lineas),
            }, status=409)

        comida = VGComidaEmpleados.objects.create(
            fecha=fecha,
            turno=turno,
            tipo_origen=tipo,
            receta=objeto if tipo == 'receta' else None,
            subreceta=objeto if tipo == 'subreceta' else None,
            ingrediente=objeto if tipo == 'ingrediente' else None,
            nombre_origen=objeto.nombre,
            cantidad=cantidad,
            unidad=unidad,
            nota=nota,
            costo_total=sum((l['costo'] for l in lineas), Decimal('0')),
            tasa_cambio_referencia=tasa_cambio_para_registro(),
            creado_por=request.user,
            actualizado_por=request.user,
        )
        motivo = f'Comida de empleados — {objeto.nombre} ({_fmt(cantidad)} {unidad}) #{comida.id}'[:255]
        movimientos = []
        for linea in lineas:
            ingrediente = linea['ingrediente']
            ingrediente.stock_actual = linea['stock_despues']
            ingrediente.save(update_fields=['stock_actual'])
            VGDetalleComidaEmpleados.objects.create(
                comida=comida, ingrediente=ingrediente, cantidad=linea['cantidad'], costo_unitario=linea['costo_unitario'],
            )
            movimientos.append(VGMovimientoInventario.objects.create(
                ingrediente=ingrediente,
                tipo_movimiento='salida',
                cantidad=linea['cantidad'],
                motivo=motivo,
                id_referencia=comida.id,
                creado_por=request.user,
            ))
        if fecha != timezone.localdate():
            # Una comida de un dia pasado cuenta en los reportes de ese dia.
            VGMovimientoInventario.objects.filter(pk__in=[m.pk for m in movimientos]).update(
                fecha_movimiento=timezone.make_aware(datetime(fecha.year, fecha.month, fecha.day, 12, 0)),
            )

    comida = VGComidaEmpleados.objects.select_related('creado_por', 'anulada_por').get(pk=comida.pk)
    return _auth_response({
        'ok': True,
        'message': f'Comida registrada: se descontaron {len(lineas)} ingredientes del inventario.',
        'comida': _serializar(comida, con_lineas=True),
    }, status=201)


@csrf_exempt
def comida_empleados_detalle_view(request, comida_id):
    """Una comida con los ingredientes que descontó."""
    error = _solo_admin(request)
    if error:
        return error
    comida = VGComidaEmpleados.objects.select_related('creado_por', 'anulada_por').filter(pk=comida_id).first()
    if comida is None:
        return _auth_response({'ok': False, 'message': 'No se encontró esa comida.'}, status=404)
    return _auth_response({'ok': True, 'comida': _serializar(comida, con_lineas=True)})


@csrf_exempt
def comida_empleados_anular_view(request, comida_id):
    """Anula una comida y repone al inventario exactamente lo que descontó. Solo administradores."""
    error = _solo_admin(request, ('POST',))
    if error:
        return error
    if not _es_administrador(request.user):
        return _auth_response({'ok': False, 'message': 'Solo un administrador puede anular una comida.'}, status=403)
    data = _json_body(request)
    if data is None:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)
    motivo = str(data.get('motivo') or '').strip()[:255]
    if not motivo:
        return _auth_response({'ok': False, 'message': 'Indica el motivo de la anulación.'}, status=400)

    with transaction.atomic():
        comida = VGComidaEmpleados.objects.select_for_update().filter(pk=comida_id).first()
        if comida is None:
            return _auth_response({'ok': False, 'message': 'No se encontró esa comida.'}, status=404)
        if comida.estado == 'anulada':
            return _auth_response({'ok': False, 'message': 'Esa comida ya estaba anulada.'}, status=400)

        detalles = list(comida.detalles.all())
        ingredientes = {
            i.id: i for i in VGIngrediente.objects.select_for_update().filter(id__in=[d.ingrediente_id for d in detalles]).order_by('id')
        }
        for detalle in detalles:
            ingrediente = ingredientes[detalle.ingrediente_id]
            ingrediente.stock_actual = Decimal(str(ingrediente.stock_actual)) + detalle.cantidad
            ingrediente.save(update_fields=['stock_actual'])
            VGMovimientoInventario.objects.create(
                ingrediente=ingrediente,
                tipo_movimiento='entrada',
                cantidad=detalle.cantidad,
                motivo=f'Reversión de comida de empleados #{comida.id}',
                id_referencia=comida.id,
                creado_por=request.user,
            )
        comida.estado = 'anulada'
        comida.anulada_por = request.user
        comida.fecha_anulacion = timezone.now()
        comida.motivo_anulacion = motivo
        comida.actualizado_por = request.user
        comida.save()

    comida = VGComidaEmpleados.objects.select_related('creado_por', 'anulada_por').get(pk=comida_id)
    return _auth_response({
        'ok': True,
        'message': 'Comida anulada: se repuso el inventario.',
        'comida': _serializar(comida, con_lineas=True),
    })
