"""
Inhabilitar (y rehabilitar) un gasto, con auditoría obligatoria y advertencias.

Inhabilitar un gasto NO lo borra: lo marca `inhabilitado` y desde ese momento deja de contar en todos
lados. Lo que más importa: sus pagos (VGAbonoGasto) dejan de salir del banco y de la caja, es decir el
dinero "vuelve" — la disponibilidad de cada cuenta sube por lo que ese gasto había sacado. También
deja de sumar al estado de resultados, a las cuentas por pagar, a los reportes de gastos y al cruce
de la conciliación bancaria (donde, si estaba conciliado con un movimiento del banco, ese vínculo se
deshace y el movimiento vuelve a quedar por revisar).

Como es un cambio con efecto en el dinero, tiene tres seguros:
  1. Motivo obligatorio (mínimo MOTIVO_MINIMO caracteres), guardado en VGInhabilitacionGasto.
  2. Advertencias: el sistema calcula qué va a cambiar y cada advertencia tiene que aceptarse
     expresamente (`aceptadas` = códigos). Sin eso responde que falta confirmar y no hace nada.
  3. Bloqueos: lo que no se puede hacer hasta resolver otra cosa (ej. el movimiento del banco
     conciliado con ese pago está en un día cerrado de la conciliación: hay que reabrir el cierre).

Rehabilitar hace lo contrario (los pagos vuelven a salir del banco) con las mismas reglas. No recrea
vínculos de conciliación: después de rehabilitar basta "Volver a cruzar" en la conciliación.

Los lugares que suman gastos (reportes.py, conciliacion_bancaria.py, contabilidad_views.py,
compras_views.py, reportes_pdf_views.py, gastos_views.py) filtran `inhabilitado=False`.
"""
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from . import conciliacion_bancaria as motor
from .models import VGConciliacionMovimiento, VGGasto, VGInhabilitacionGasto

MOTIVO_MINIMO = 10
CENT = Decimal('0.01')


class InhabilitacionInvalida(Exception):
    """Datos inválidos (motivo muy corto, acción desconocida...). Se responde 400."""


class InhabilitacionBloqueada(Exception):
    """Algo lo impide hasta que se resuelva (`bloqueos`). Se responde 409."""

    def __init__(self, bloqueos):
        super().__init__('; '.join(b['mensaje'] for b in bloqueos))
        self.bloqueos = bloqueos


class RequiereConfirmacion(Exception):
    """Faltan advertencias por aceptar (`advertencias`). Se responde 409."""

    def __init__(self, advertencias):
        super().__init__('Faltan advertencias por aceptar.')
        self.advertencias = advertencias


def _bs_texto(monto):
    entero, _, decimales = f'{monto:,.2f}'.partition('.')
    return f"Bs {entero.replace(',', '.')},{decimales}"


def _fecha_texto(valor):
    return valor.strftime('%d/%m/%Y')


def _abonos(gasto):
    return list(gasto.abonos.select_related('metodo_pago').order_by('fecha_pago', 'id'))


def _efecto_cuentas(abonos):
    """Lo que cada cuenta (banco o caja) recupera: agrupado por cuenta bancaria, o por método si no tiene cuenta."""
    grupos = {}
    for abono in abonos:
        metodo = abono.metodo_pago
        nombre = motor.normalizar_cuenta(metodo.cuenta_bancaria) or metodo.nombre
        g = grupos.setdefault(nombre, {
            'cuenta': nombre, 'metodo': metodo.nombre, 'es_efectivo': metodo.es_efectivo,
            'moneda': metodo.moneda, 'abonos': 0, 'usd': Decimal('0'), 'bs': None,
        })
        g['abonos'] += 1
        g['usd'] += abono.monto
        if metodo.moneda == 'VES' and abono.tasa_cambio_referencia:
            g['bs'] = (g['bs'] or Decimal('0')) + (abono.monto * abono.tasa_cambio_referencia).quantize(CENT)
    return list(grupos.values())


def _vinculos_de(gasto, abonos):
    """Vínculos de conciliación que apuntan a este gasto o a sus pagos (sin contar los rechazados)."""
    ids_abonos = [a.id for a in abonos]
    filtro = Q(origen_tipo='gasto', origen_id=gasto.id)
    if ids_abonos:
        filtro |= Q(origen_tipo='abono_gasto', origen_id__in=ids_abonos)
    return list(
        VGConciliacionMovimiento.objects.filter(filtro).exclude(estado='rechazado').select_related('movimiento')
    )


def _serializar_efecto(efecto):
    return [
        {
            'cuenta': e['cuenta'], 'metodo': e['metodo'], 'es_efectivo': e['es_efectivo'], 'moneda': e['moneda'],
            'abonos': e['abonos'], 'usd': str(e['usd'].quantize(Decimal('0.01'))),
            'bs': str(e['bs']) if e['bs'] is not None else None,
        }
        for e in efecto
    ]


def evaluar(gasto, accion='inhabilitar'):
    """
    Qué pasaría: impacto por cuenta, vínculos de conciliación afectados, advertencias (hay que aceptarlas) y
    bloqueos (no se puede seguir). No toca nada.
    """
    if accion not in ('inhabilitar', 'rehabilitar'):
        raise InhabilitacionInvalida('Acción inválida.')
    inhabilita = accion == 'inhabilitar'
    abonos = _abonos(gasto)
    efecto = _efecto_cuentas(abonos)
    total_usd = sum((e['usd'] for e in efecto), Decimal('0'))
    vinculos = _vinculos_de(gasto, abonos) if inhabilita else []
    advertencias, bloqueos = [], []

    if inhabilita and gasto.inhabilitado:
        bloqueos.append({'codigo': 'ya_inhabilitado', 'mensaje': 'Este gasto ya está inhabilitado.'})
    if not inhabilita and not gasto.inhabilitado:
        bloqueos.append({'codigo': 'no_inhabilitado', 'mensaje': 'Este gasto no está inhabilitado.'})

    if efecto:
        lineas = []
        for e in efecto:
            monto = _bs_texto(e['bs']) if e['bs'] is not None else f"${e['usd'].quantize(Decimal('0.01'))}"
            if e['es_efectivo']:
                lineas.append(f"Caja en efectivo ({e['metodo']}): {monto}")
            else:
                lineas.append(f"{e['cuenta']}: {monto}")
        advertencias.append({
            'codigo': 'devuelve_al_banco' if inhabilita else 'vuelve_a_salir',
            'mensaje': (
                'El dinero de sus pagos vuelve: el saldo de estas cuentas sube.' if inhabilita
                else 'Sus pagos vuelven a salir: el saldo de estas cuentas baja.'
            ),
            'detalle': lineas,
        })
    elif inhabilita:
        advertencias.append({
            'codigo': 'sin_pagos',
            'mensaje': 'Todavía no tiene pagos: solo dejará de contar como gasto y como deuda por pagar.',
            'detalle': [],
        })

    if vinculos:
        lineas = []
        for v in vinculos:
            mov = v.movimiento
            dia = motor._fecha_local(mov.fecha)
            lineas.append(f'{mov.cuenta_bancaria} · {_fecha_texto(dia)} · {_bs_texto(mov.monto)} · ref. {mov.referencia or "—"}')
            if dia in motor.fechas_cerradas(mov.cuenta_bancaria, dia, dia):
                bloqueos.append({
                    'codigo': 'dia_conciliacion_cerrado',
                    'mensaje': (
                        f'El movimiento del banco del {_fecha_texto(dia)} ({mov.cuenta_bancaria}) conciliado con este gasto '
                        'está en un día cerrado: reabre el cierre de ese día en la conciliación primero.'
                    ),
                })
        advertencias.append({
            'codigo': 'conciliado',
            'mensaje': 'Está conciliado con el banco: se deshace el vínculo y el movimiento vuelve a quedar por revisar.',
            'detalle': lineas,
        })

    hoy = timezone.localdate()
    if gasto.fecha_gasto < date(hoy.year, hoy.month, 1):
        advertencias.append({
            'codigo': 'periodo_pasado',
            'mensaje': (
                f'El gasto es del {_fecha_texto(gasto.fecha_gasto)}: cambian los totales de ese período '
                '(estado de resultados y flujo del banco de esa fecha).'
            ),
            'detalle': [],
        })

    if any(e['es_efectivo'] for e in efecto) and any(timezone.localtime(a.fecha_pago).date() < hoy for a in abonos if a.metodo_pago.es_efectivo):
        advertencias.append({
            'codigo': 'caja_de_otro_dia',
            'mensaje': 'Se pagó en efectivo en un día anterior: cambia el efectivo esperado de caja de ese día.',
            'detalle': [],
        })

    if inhabilita and motor._es_gasto_comision(gasto):
        advertencias.append({
            'codigo': 'comision',
            'mensaje': 'Es un gasto de comisión bancaria: las comisiones del banco de ese día quedan sin su gasto.',
            'detalle': [],
        })

    return {
        'accion': accion,
        'gasto': {
            'id': gasto.id, 'descripcion': gasto.descripcion, 'monto': str(gasto.monto),
            'fecha_gasto': gasto.fecha_gasto.isoformat(), 'estado_pago': gasto.estado_pago,
            'inhabilitado': gasto.inhabilitado,
        },
        'abonos': len(abonos),
        'monto_usd': str(total_usd.quantize(Decimal('0.01'))),
        'efecto_cuentas': _serializar_efecto(efecto),
        'advertencias': advertencias,
        'bloqueos': bloqueos,
        '_efecto': efecto, '_vinculos': vinculos,
    }


def _publico(evaluacion):
    return {k: v for k, v in evaluacion.items() if not k.startswith('_')}


def vista_previa(gasto, accion='inhabilitar'):
    return _publico(evaluar(gasto, accion))


def serializar_auditoria(registro):
    return {
        'id': registro.id, 'accion': registro.accion, 'motivo': registro.motivo,
        'monto_usd_afectado': str(registro.monto_usd_afectado), 'abonos_afectados': registro.abonos_afectados,
        'efecto_cuentas': registro.efecto_cuentas, 'advertencias_aceptadas': registro.advertencias_aceptadas,
        'vinculos_deshechos': registro.vinculos_deshechos,
        'por': (registro.creado_por.get_full_name() or registro.creado_por.username) if registro.creado_por else '',
        'fecha': registro.fecha_creacion.isoformat(),
    }


def aplicar(gasto_id, accion, motivo, aceptadas, usuario):
    """
    Inhabilita o rehabilita el gasto. Lanza InhabilitacionInvalida (400), InhabilitacionBloqueada (409) o
    RequiereConfirmacion (409) si falta algo; si todo está en orden devuelve el VGInhabilitacionGasto creado.
    """
    motivo = str(motivo or '').strip()
    if len(motivo) < MOTIVO_MINIMO:
        raise InhabilitacionInvalida(f'Escribe el motivo para la auditoría (mínimo {MOTIVO_MINIMO} caracteres).')
    aceptadas = {str(c) for c in (aceptadas or [])}

    with transaction.atomic():
        gasto = VGGasto.objects.select_for_update().select_related('categoria').get(pk=gasto_id)
        evaluacion = evaluar(gasto, accion)
        if evaluacion['bloqueos']:
            raise InhabilitacionBloqueada(evaluacion['bloqueos'])
        faltan = [a for a in evaluacion['advertencias'] if a['codigo'] not in aceptadas]
        if faltan:
            raise RequiereConfirmacion(faltan)

        inhabilita = accion == 'inhabilitar'
        gasto.inhabilitado = inhabilita
        gasto.actualizado_por = usuario
        gasto.save(update_fields=['inhabilitado', 'actualizado_por', 'fecha_actualizacion'])

        deshechos = []
        if inhabilita and evaluacion['_vinculos']:
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
                # Vuelve al cruce: se recalcula su estado (y su mejor candidato) ya sin este gasto.
                if mov.estado != 'ignorado':
                    mov.estado = 'pendiente'
                    mov.save(update_fields=['estado', 'fecha_actualizacion'])
                    dia = motor._fecha_local(mov.fecha)
                    try:
                        motor.conciliar(mov.cuenta_bancaria, dia, dia, usuario, solo_movimientos=[mov])
                    except motor.CuentaNoSoportada:
                        pass

        registro = VGInhabilitacionGasto.objects.create(
            gasto=gasto, accion='inhabilitado' if inhabilita else 'rehabilitado', motivo=motivo,
            monto_gasto=gasto.monto, estado_pago=gasto.estado_pago, abonos_afectados=evaluacion['abonos'],
            monto_usd_afectado=Decimal(evaluacion['monto_usd']), efecto_cuentas=evaluacion['efecto_cuentas'],
            advertencias_aceptadas=[{'codigo': a['codigo'], 'mensaje': a['mensaje']} for a in evaluacion['advertencias']],
            vinculos_deshechos=deshechos, creado_por=usuario, actualizado_por=usuario,
        )
    return registro
