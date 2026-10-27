"""
Anular una factura de compra, con auditoría obligatoria y advertencias.

Anular NO borra la compra: la marca `estado='cancelado'` y desde ese momento deja de contar en todos lados.
Es lo contrario de cargarla:

  * El stock vuelve a como estaba: a cada ingrediente se le resta lo que esa compra le sumó (si tenías 2 kg
    y la factura trajo 10 kg, quedas en 12 kg; al anularla quedas otra vez en 2 kg). Se resta de lo que hay
    HOY, no se "congela" el stock de aquel día: si ya se consumió parte, queda lo que de verdad falta y puede
    salir en negativo (el sistema lo advierte). Cada ajuste queda como un movimiento de inventario.
  * El costo del ingrediente NO se toca: la compra anterior puede tener un costo que no sirva de referencia
    (una carga de prueba, una cortesía), así que si el precio de esa factura estaba mal se corrige a mano en
    el ingrediente.
  * La deuda con el proveedor desaparece de cuentas por pagar.
  * Si ya tenía pagos (VGAbonoCompra), el dinero "vuelve": sube el saldo de cada cuenta (banco o caja) y se
    deshace el vínculo con la conciliación bancaria, igual que al inhabilitar un gasto.

Como es un cambio con efecto en inventario y dinero, tiene tres seguros (mismos que gastos_inhabilitacion):
  1. Motivo obligatorio (mínimo MOTIVO_MINIMO caracteres), guardado en VGAnulacionCompra.
  2. Advertencias: el sistema calcula qué va a cambiar y cada una hay que aceptarla expresamente.
  3. Bloqueos: lo que impide anular hasta resolver otra cosa (ej. un movimiento del banco conciliado con un
     pago está en un día cerrado de la conciliación).

La anulación no se puede deshacer: para recuperar la factura hay que cargarla de nuevo.

Los lugares que suman pagos de compras (reportes.py, conciliacion_bancaria.py, compras_views.py,
reportes_pdf_views.py) excluyen las compras canceladas.
"""
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from . import conciliacion_bancaria as motor
from .gastos_inhabilitacion import MOTIVO_MINIMO, _bs_texto, _efecto_cuentas, _fecha_texto, _serializar_efecto
from .models import (
    VGAnulacionCompra,
    VGCompra,
    VGConciliacionMovimiento,
    VGIngrediente,
    VGMovimientoInventario,
)

CENT = Decimal('0.01')


class AnulacionInvalida(Exception):
    """Datos inválidos (motivo muy corto...). Se responde 400."""


class AnulacionBloqueada(Exception):
    """Algo lo impide hasta que se resuelva (`bloqueos`). Se responde 409."""

    def __init__(self, bloqueos):
        super().__init__('; '.join(b['mensaje'] for b in bloqueos))
        self.bloqueos = bloqueos


class RequiereConfirmacion(Exception):
    """Faltan advertencias por aceptar (`advertencias`). Se responde 409."""

    def __init__(self, advertencias):
        super().__init__('Faltan advertencias por aceptar.')
        self.advertencias = advertencias


def _cantidad_texto(valor):
    texto = f'{Decimal(valor).quantize(CENT):f}'
    return texto[:-3] if texto.endswith('.00') else texto


def _abonos(compra):
    return list(compra.abonos.select_related('metodo_pago').order_by('fecha_pago', 'id'))


def _vinculos_de(abonos):
    """Vínculos de conciliación que apuntan a los pagos de esta compra (sin contar los rechazados)."""
    ids_abonos = [a.id for a in abonos]
    if not ids_abonos:
        return []
    return list(
        VGConciliacionMovimiento.objects.filter(Q(origen_tipo='abono_compra', origen_id__in=ids_abonos))
        .exclude(estado='rechazado').select_related('movimiento')
    )


def _lineas_stock(compra, ingredientes=None):
    """
    Una fila por ingrediente de la compra: cuánto sumó, cómo está su stock hoy y cómo quedaría. `ingredientes`
    ({id: VGIngrediente}) permite usar las filas ya bloqueadas al aplicar.
    """
    por_ingrediente = {}
    for detalle in compra.detalles.select_related('ingrediente').order_by('id'):
        ingrediente = (ingredientes or {}).get(detalle.ingrediente_id) or detalle.ingrediente
        fila = por_ingrediente.setdefault(ingrediente.id, {'ingrediente': ingrediente, 'cantidad': Decimal('0')})
        fila['cantidad'] += detalle.cantidad

    lineas = []
    for fila in por_ingrediente.values():
        ingrediente = fila['ingrediente']
        stock_antes = Decimal(str(ingrediente.stock_actual))
        lineas.append({
            'ingrediente': ingrediente, 'cantidad': fila['cantidad'],
            'stock_antes': stock_antes, 'stock_despues': stock_antes - fila['cantidad'],
        })
    return lineas


def _serializar_lineas_stock(lineas):
    return [
        {
            'ingrediente_id': l['ingrediente'].id, 'nombre': l['ingrediente'].nombre, 'unidad': l['ingrediente'].unidad_medida,
            'cantidad': str(l['cantidad']), 'stock_antes': str(l['stock_antes']), 'stock_despues': str(l['stock_despues']),
        }
        for l in lineas
    ]


def evaluar(compra):
    """
    Qué pasaría al anularla: cómo queda el stock de cada ingrediente, el efecto en cada cuenta por lo ya
    pagado, vínculos de conciliación afectados, advertencias (hay que aceptarlas) y bloqueos. No toca nada.
    """
    abonos = _abonos(compra)
    efecto = _efecto_cuentas(abonos)
    total_usd = sum((e['usd'] for e in efecto), Decimal('0'))
    vinculos = _vinculos_de(abonos)
    lineas = _lineas_stock(compra)
    advertencias, bloqueos = [], []

    if compra.estado == 'cancelado':
        bloqueos.append({'codigo': 'ya_anulada', 'mensaje': 'Esta factura de compra ya está anulada.'})

    if lineas:
        advertencias.append({
            'codigo': 'revierte_stock',
            'mensaje': 'El stock vuelve a como estaba antes de esta factura (se le resta lo que ella sumó). No se puede deshacer.',
            'detalle': [
                f"{l['ingrediente'].nombre}: {_cantidad_texto(l['stock_antes'])} → {_cantidad_texto(l['stock_despues'])} "
                f"{l['ingrediente'].unidad_medida} (resta {_cantidad_texto(l['cantidad'])})"
                for l in lineas
            ],
        })
    negativos = [l for l in lineas if l['stock_despues'] < 0]
    if negativos:
        advertencias.append({
            'codigo': 'stock_negativo',
            'mensaje': 'Parte de esa mercancía ya se consumió: estos ingredientes quedarían con stock negativo.',
            'detalle': [
                f"{l['ingrediente'].nombre}: quedaría en {_cantidad_texto(l['stock_despues'])} {l['ingrediente'].unidad_medida}"
                for l in negativos
            ],
        })

    if compra.saldo_pendiente > 0:
        advertencias.append({
            'codigo': 'deuda_cancelada',
            'mensaje': f'Se cancela la deuda con {compra.proveedor_nombre}: ${compra.saldo_pendiente.quantize(CENT)} dejan de ser por pagar.',
            'detalle': [],
        })

    if efecto:
        lineas_cuentas = []
        for e in efecto:
            monto = _bs_texto(e['bs']) if e['bs'] is not None else f"${e['usd'].quantize(CENT)}"
            if e['es_efectivo']:
                lineas_cuentas.append(f"Caja en efectivo ({e['metodo']}): {monto}")
            else:
                lineas_cuentas.append(f"{e['cuenta']}: {monto}")
        advertencias.append({
            'codigo': 'devuelve_al_banco',
            'mensaje': 'El dinero de sus pagos vuelve: el saldo de estas cuentas sube.',
            'detalle': lineas_cuentas,
        })

    if vinculos:
        lineas_vinculos = []
        for v in vinculos:
            mov = v.movimiento
            dia = motor._fecha_local(mov.fecha)
            lineas_vinculos.append(f'{mov.cuenta_bancaria} · {_fecha_texto(dia)} · {_bs_texto(mov.monto)} · ref. {mov.referencia or "—"}')
            if dia in motor.fechas_cerradas(mov.cuenta_bancaria, dia, dia):
                bloqueos.append({
                    'codigo': 'dia_conciliacion_cerrado',
                    'mensaje': (
                        f'El movimiento del banco del {_fecha_texto(dia)} ({mov.cuenta_bancaria}) conciliado con un pago de esta '
                        'factura está en un día cerrado: reabre el cierre de ese día en la conciliación primero.'
                    ),
                })
        advertencias.append({
            'codigo': 'conciliado',
            'mensaje': 'Está conciliada con el banco: se deshace el vínculo y el movimiento vuelve a quedar por revisar.',
            'detalle': lineas_vinculos,
        })

    hoy = timezone.localdate()
    fecha_documento = compra.fecha_factura or timezone.localtime(compra.fecha_creacion).date()
    if fecha_documento < date(hoy.year, hoy.month, 1):
        advertencias.append({
            'codigo': 'periodo_pasado',
            'mensaje': (
                f'La factura es del {_fecha_texto(fecha_documento)}: cambian los totales de ese período '
                '(flujo del banco de las fechas de sus pagos).'
            ),
            'detalle': [],
        })

    if any(e['es_efectivo'] for e in efecto) and any(
        timezone.localtime(a.fecha_pago).date() < hoy for a in abonos if a.metodo_pago.es_efectivo
    ):
        advertencias.append({
            'codigo': 'caja_de_otro_dia',
            'mensaje': 'Se pagó en efectivo en un día anterior: cambia el efectivo esperado de caja de ese día.',
            'detalle': [],
        })

    notas_vigentes = compra.notas_credito.filter(estado='vigente').count()
    if notas_vigentes:
        advertencias.append({
            'codigo': 'notas_credito',
            'mensaje': f'Tiene {notas_vigentes} nota(s) de crédito del proveedor vigente(s): dejan de contar junto con la factura.',
            'detalle': [],
        })

    return {
        'compra': {
            'id': compra.id, 'proveedor_nombre': compra.proveedor_nombre,
            'numero_factura_proveedor': compra.numero_factura_proveedor, 'total': str(compra.total),
            'saldo_pendiente': str(compra.saldo_pendiente), 'estado_pago': compra.estado_pago, 'estado': compra.estado,
            'fecha': fecha_documento.isoformat(),
        },
        'stock': _serializar_lineas_stock(lineas),
        'abonos': len(abonos),
        'monto_usd': str(total_usd.quantize(CENT)),
        'efecto_cuentas': _serializar_efecto(efecto),
        'advertencias': advertencias,
        'bloqueos': bloqueos,
        '_lineas': lineas, '_efecto': efecto, '_vinculos': vinculos,
    }


def _publico(evaluacion):
    return {k: v for k, v in evaluacion.items() if not k.startswith('_')}


def vista_previa(compra):
    return _publico(evaluar(compra))


def serializar_auditoria(registro):
    return {
        'id': registro.id, 'motivo': registro.motivo, 'total_compra': str(registro.total_compra),
        'stock_revertido': registro.stock_revertido,
        'monto_usd_afectado': str(registro.monto_usd_afectado), 'abonos_afectados': registro.abonos_afectados,
        'efecto_cuentas': registro.efecto_cuentas, 'advertencias_aceptadas': registro.advertencias_aceptadas,
        'vinculos_deshechos': registro.vinculos_deshechos,
        'por': (registro.creado_por.get_full_name() or registro.creado_por.username) if registro.creado_por else '',
        'fecha': registro.fecha_creacion.isoformat(),
    }


def ultima_anulacion(compra):
    """La auditoría de la anulación de una compra cancelada, o None."""
    if compra.estado != 'cancelado':
        return None
    registro = compra.anulaciones.select_related('creado_por').order_by('-fecha_creacion').first()
    return serializar_auditoria(registro) if registro else None


def aplicar(compra_id, motivo, aceptadas, usuario):
    """
    Anula la compra. Lanza AnulacionInvalida (400), AnulacionBloqueada (409) o RequiereConfirmacion (409) si falta
    algo; si todo está en orden devuelve el VGAnulacionCompra creado.
    """
    motivo = str(motivo or '').strip()
    if len(motivo) < MOTIVO_MINIMO:
        raise AnulacionInvalida(f'Escribe el motivo para la auditoría (mínimo {MOTIVO_MINIMO} caracteres).')
    aceptadas = {str(c) for c in (aceptadas or [])}

    with transaction.atomic():
        compra = VGCompra.objects.select_for_update().get(pk=compra_id)
        # Se bloquean los ingredientes de la factura: el stock que se evalúa es el que se guarda.
        ids = list(compra.detalles.values_list('ingrediente_id', flat=True).distinct())
        ingredientes = {i.id: i for i in VGIngrediente.objects.select_for_update().filter(pk__in=ids).order_by('id')}

        evaluacion = evaluar(compra)
        if evaluacion['bloqueos']:
            raise AnulacionBloqueada(evaluacion['bloqueos'])
        faltan = [a for a in evaluacion['advertencias'] if a['codigo'] not in aceptadas]
        if faltan:
            raise RequiereConfirmacion(faltan)

        # Con las filas bloqueadas, el stock de cada línea es el actual de verdad.
        lineas = _lineas_stock(compra, ingredientes)
        for linea in lineas:
            ingrediente = linea['ingrediente']
            ingrediente.stock_actual = linea['stock_despues']
            ingrediente.actualizado_por = usuario
            ingrediente.save(update_fields=['stock_actual', 'actualizado_por', 'fecha_actualizacion'])
            VGMovimientoInventario.objects.create(
                ingrediente=ingrediente, tipo_movimiento='salida', cantidad=linea['cantidad'],
                motivo=f'Anulación de compra #{compra.id}', compra=compra, creado_por=usuario,
            )

        deshechos = []
        if evaluacion['_vinculos']:
            movimientos = {}
            for vinculo in evaluacion['_vinculos']:
                mov = vinculo.movimiento
                movimientos[mov.id] = mov
                deshechos.append({
                    'movimiento_id': mov.id, 'cuenta': mov.cuenta_bancaria,
                    'fecha': motor._fecha_local(mov.fecha).isoformat(), 'monto': str(mov.monto), 'referencia': mov.referencia,
                })
            VGConciliacionMovimiento.objects.filter(pk__in=[v.pk for v in evaluacion['_vinculos']]).delete()
            for mov in movimientos.values():
                # Vuelve al cruce: se recalcula su estado (y su mejor candidato) ya sin esta compra.
                if mov.estado != 'ignorado':
                    mov.estado = 'pendiente'
                    mov.save(update_fields=['estado', 'fecha_actualizacion'])
                    dia = motor._fecha_local(mov.fecha)
                    try:
                        motor.conciliar(mov.cuenta_bancaria, dia, dia, usuario, solo_movimientos=[mov])
                    except motor.CuentaNoSoportada:
                        pass

        total, saldo, estado_pago = compra.total, compra.saldo_pendiente, compra.estado_pago
        compra.estado = 'cancelado'
        compra.actualizado_por = usuario
        compra.save(update_fields=['estado', 'actualizado_por', 'fecha_actualizacion'])

        registro = VGAnulacionCompra.objects.create(
            compra=compra, motivo=motivo, total_compra=total, saldo_pendiente=saldo, estado_pago=estado_pago,
            stock_revertido=_serializar_lineas_stock(lineas), abonos_afectados=evaluacion['abonos'],
            monto_usd_afectado=Decimal(evaluacion['monto_usd']), efecto_cuentas=evaluacion['efecto_cuentas'],
            advertencias_aceptadas=[{'codigo': a['codigo'], 'mensaje': a['mensaje']} for a in evaluacion['advertencias']],
            vinculos_deshechos=deshechos, creado_por=usuario, actualizado_por=usuario,
        )
    return registro
