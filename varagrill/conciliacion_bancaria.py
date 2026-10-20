"""
Conciliacion bancaria por MOVIMIENTO: compara cada linea del extracto del banco contra los
registros del sistema para saber si esa transaccion esta registrada o no.

  - Credito (entra plata): se busca en los pagos de notas de entrega/facturas, los ingresos
    extra y las transferencias entre cuentas propias de esa cuenta.
  - Debito (sale plata): se busca en los abonos de gastos y de compras y en las transferencias
    propias. El gasto guarda la referencia bancaria en `numero_comprobante`.
  - Comisiones (COM TRF, TDY COM.P2P, DOM POS): el negocio registra UN gasto "comision" por dia,
    asi que se comparan por dia: la suma de las comisiones del banco contra ese gasto.
  - Punto de venta (POS): el banco acredita el lote, no cada venta. En esta fase solo se muestra
    la comparacion por dia contra los lotes acreditados (ver resumen_pos); no se vinculan.

Niveles de confianza de cada cruce (ver evaluar):
  seguro        referencia (exacta o sufijo de 4+ digitos) + monto dentro de la tolerancia -> se
                confirma solo.
  por revisar   mismo monto y fecha cercana sin referencia, o referencia con monto distinto -> el
                sistema sugiere y una persona confirma o rechaza.
  sin coincidencia

Un registro del sistema solo se concilia contra UN movimiento (salvo los gastos de comision del
dia). Al reves si: UN movimiento puede pagar VARIOS registros (ej. una sola transferencia al
proveedor que salda una compra y un gasto): se vinculan todos juntos y su suma se compara con el
monto del banco (ver vincular_varios; si comparten la referencia del banco y suman el monto, el
cruce automatico los une solo). Nada de esto modifica pagos, gastos ni compras: solo crea vinculos
(VGConciliacionMovimiento).

Cierre diario (VGCierreConciliacion): cada dia se "cierra" cuando no queda nada por revisar; el cierre
guarda la foto de los numeros del dia y bloquea el dia (no se tocan sus movimientos ni se importan
lineas nuevas). Ver cerrar_dia / reabrir_cierre / listar_cierres.
"""
import re
from bisect import bisect_left, bisect_right
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from itertools import combinations

from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.utils import timezone

from .models import (
    VGAbonoCompra, VGAbonoGasto, VGCierreConciliacion, VGConciliacionMovimiento, VGExtractoBancario, VGGasto, VGIngresoExtra, VGLotePOS,
    VGMetodoPago, VGMovimientoBancario, VGPago, VGTransferenciaCuenta,
)

CENT = Decimal('0.01')

# Tolerancias (acordadas con el negocio).
TOL_MONTO_EXACTO = Decimal('0.02')          # sin referencia: el monto debe ser practicamente identico
TOL_REF_ABS = Decimal('2.00')               # con referencia: hasta 2 Bs de diferencia (redondeo de la tasa)...
TOL_REF_PCT = Decimal('0.01')               # ...o 1% del monto, lo que sea mayor
TOL_MONTO_APROX_PCT = Decimal('0.01')       # sin referencia, "posible": hasta 1%
TOL_COMISION_DIA = Decimal('0.05')          # suma de comisiones del dia vs el gasto
VENTANA_CREDITO_DIAS = 1                    # monto igual, sin referencia
VENTANA_DEBITO_DIAS = 7                     # el gasto se suele registrar despues del pago
VENTANA_APROX_DIAS = 2
VENTANA_REF_EXACTA_DIAS = 31
VENTANA_REF_SUFIJO_DIAS = 3
MIN_DIGITOS_SUFIJO = 4
HOLGURA_POOL_DIAS = 31                      # cuanto se amplian las fechas al buscar candidatos
PUNTAJE_SEGURO = 95
PUNTAJE_PROBABLE_MIN = 66                   # "confirmar probables" en bloque
MIN_DIGITOS_GRUPO = 4                       # pago dividido automatico: referencia de al menos 4 digitos...
MAX_GRUPO = 10                              # ...y hasta 10 registros con esa misma referencia
VENTANA_TODOS_DIAS = 7                      # "ver todos" al elegir a mano: registros hasta 7 dias alrededor
LIMITE_TODOS = 80

ESTADOS_RECONCILIABLES = ('pendiente', 'por_revisar', 'sin_coincidencia')


class CuentaNoSoportada(Exception):
    pass


# ---------------------------------------------------------------------------
# Cuentas
# ---------------------------------------------------------------------------
def normalizar_cuenta(nombre):
    """'Banco plaza natural   ' -> 'Banco plaza natural' (como VGMetodoPago.cuenta_bancaria sin espacios sobrantes)."""
    return ' '.join(str(nombre or '').split())


def _clave_cuenta(nombre):
    return normalizar_cuenta(nombre).lower()


def metodos_de_cuenta(cuenta):
    clave = _clave_cuenta(cuenta)
    if not clave:
        return []
    return [m for m in VGMetodoPago.objects.all() if _clave_cuenta(m.cuenta_bancaria) == clave]


def cuentas_disponibles():
    """Cuentas bancarias reales (agrupadas por VGMetodoPago.cuenta_bancaria) y si ya se pueden conciliar."""
    grupos = {}
    for metodo in VGMetodoPago.objects.exclude(cuenta_bancaria='').order_by('nombre'):
        clave = _clave_cuenta(metodo.cuenta_bancaria)
        if not clave:
            continue
        g = grupos.setdefault(clave, {'nombre': normalizar_cuenta(metodo.cuenta_bancaria), 'metodos': []})
        g['metodos'].append(metodo)
    cargados = {}
    for fila in VGMovimientoBancario.objects.values('cuenta_bancaria').annotate(n=Count('id')):
        clave = _clave_cuenta(fila['cuenta_bancaria'])
        cargados[clave] = cargados.get(clave, 0) + fila['n']
    cuentas = []
    for g in sorted(grupos.values(), key=lambda x: x['nombre'].lower()):
        monedas = {m.moneda for m in g['metodos']}
        cuentas.append({
            'movimientos_cargados': cargados.get(_clave_cuenta(g['nombre']), 0),
            'nombre': g['nombre'],
            'moneda': next(iter(monedas)) if len(monedas) == 1 else 'MIXTA',
            'soportada': monedas == {'VES'},
            'metodos': [{'nombre': m.nombre, 'activo': m.activo} for m in g['metodos']],
        })
    return cuentas


def _exigir_cuenta_ves(cuenta):
    metodos = metodos_de_cuenta(cuenta)
    if not metodos:
        raise CuentaNoSoportada('Esa cuenta no existe.')
    if any(m.moneda != 'VES' for m in metodos):
        raise CuentaNoSoportada('Por ahora solo se pueden conciliar cuentas en bolívares.')
    return metodos


# ---------------------------------------------------------------------------
# Importacion
# ---------------------------------------------------------------------------
def _hacer_aware(naive):
    return timezone.make_aware(naive, timezone.get_current_timezone())


def _fecha_local(dt):
    return timezone.localtime(dt).date()


def _a_fecha(valor):
    if isinstance(valor, datetime):
        return timezone.localtime(valor).date() if timezone.is_aware(valor) else valor.date()
    return valor


def fechas_cerradas(cuenta, desde, hasta):
    """Dias de esa cuenta con un cierre vigente entre desde y hasta."""
    return set(
        VGCierreConciliacion.objects.filter(
            cuenta_bancaria=normalizar_cuenta(cuenta), estado='vigente', fecha__range=(desde, hasta),
        ).values_list('fecha', flat=True)
    )


def movimientos_en_dias_cerrados(cuenta, parseado):
    """Lineas NUEVAS del archivo que caen en un dia ya cerrado (no se importan): {'cantidad', 'dias'}."""
    cuenta = normalizar_cuenta(cuenta)
    movimientos = parseado['movimientos']
    if not movimientos:
        return {'cantidad': 0, 'dias': []}
    existentes = set(
        VGMovimientoBancario.objects.filter(
            cuenta_bancaria=cuenta, huella__in=[m['huella'] for m in movimientos],
        ).values_list('huella', flat=True)
    )
    fechas = [m['fecha'].date() for m in movimientos]
    cerrados = fechas_cerradas(cuenta, min(fechas), max(fechas))
    en_cerrados = [m for m in movimientos if m['huella'] not in existentes and m['fecha'].date() in cerrados]
    return {'cantidad': len(en_cerrados), 'dias': sorted({m['fecha'].date() for m in en_cerrados})}


def importar_extracto(cuenta, parseado, nombre_archivo, usuario):
    """
    Guarda las lineas nuevas del archivo ya leido (banco_excel.parsear_extracto) y omite las que ya
    existen (misma huella en la misma cuenta). Devuelve el VGExtractoBancario creado.
    """
    cuenta = normalizar_cuenta(cuenta)
    _exigir_cuenta_ves(cuenta)
    movimientos = parseado['movimientos']
    existentes = set(
        VGMovimientoBancario.objects.filter(
            cuenta_bancaria=cuenta, huella__in=[m['huella'] for m in movimientos],
        ).values_list('huella', flat=True)
    )
    nuevos = [m for m in movimientos if m['huella'] not in existentes]
    fechas = [m['fecha'].date() for m in movimientos]
    # Un dia cerrado no admite lineas nuevas: para agregarlas hay que reabrir su cierre.
    cerrados = fechas_cerradas(cuenta, min(fechas), max(fechas)) if fechas else set()
    omitidos_cerrados = [m for m in nuevos if m['fecha'].date() in cerrados]
    nuevos = [m for m in nuevos if m['fecha'].date() not in cerrados]
    with transaction.atomic():
        extracto = VGExtractoBancario.objects.create(
            cuenta_bancaria=cuenta, nombre_archivo=(nombre_archivo or '')[:255],
            huella_archivo=parseado['huella_archivo'],
            fecha_desde=min(fechas) if fechas else None, fecha_hasta=max(fechas) if fechas else None,
            movimientos_leidos=len(movimientos), movimientos_nuevos=len(nuevos),
            duplicados_omitidos=len(existentes), omitidos_dia_cerrado=len(omitidos_cerrados),
            saltos_saldo=parseado['saltos_saldo'],
            creado_por=usuario, actualizado_por=usuario,
        )
        VGMovimientoBancario.objects.bulk_create([
            VGMovimientoBancario(
                extracto=extracto, cuenta_bancaria=cuenta, fecha=_hacer_aware(m['fecha']), referencia=m['referencia'],
                descripcion=m['descripcion'], tipo=m['tipo'], monto=m['monto'], saldo=m['saldo'],
                observacion=m['observacion'], clase=m['clase'], huella=m['huella'], estado='pendiente',
                creado_por=usuario, actualizado_por=usuario,
            )
            for m in nuevos
        ])
    return extracto


# ---------------------------------------------------------------------------
# Candidatos del sistema
# ---------------------------------------------------------------------------
@dataclass
class Candidato:
    tipo: str            # VGConciliacionMovimiento.ORIGENES
    id: int
    fecha: date
    monto: Decimal       # en Bs
    referencia: str      # solo digitos, sin ceros a la izquierda; '' si el registro no tiene referencia bancaria
    etiqueta: str
    texto: str = ''
    fechas_alt: tuple = ()
    extra: dict = field(default_factory=dict)

    def __post_init__(self):
        # algunas fechas del sistema son DateTimeField (compras): aqui todo se compara por dia local
        self.fecha = _a_fecha(self.fecha)
        self.fechas_alt = tuple(_a_fecha(f) for f in self.fechas_alt if f)

    @property
    def clave(self):
        return (self.tipo, self.id)


def _solo_digitos(texto):
    return re.sub(r'\D', '', str(texto or '')).lstrip('0')


def _referencia_bancaria(texto):
    """La referencia del sistema solo sirve si es puramente numerica (un 'ABONO-2026...' o '18oct26' no lo es)."""
    texto = str(texto or '').strip()
    return _solo_digitos(texto) if re.fullmatch(r'\d{3,}', texto) else ''


def _bs(monto, tasa):
    return (Decimal(monto) * Decimal(tasa)).quantize(CENT) if monto is not None and tasa else None


def _es_gasto_comision(gasto):
    return 'comisi' in (gasto.descripcion or '').lower() or 'comisi' in (gasto.categoria.nombre or '').lower()


def _cargar_pool(cuenta, desde, hasta, es_credito):
    """Registros del sistema de esa cuenta con fecha entre desde y hasta (ya ampliadas por quien llama)."""
    metodos = metodos_de_cuenta(cuenta)
    ids_metodos = [m.id for m in metodos]
    ids_sin_efectivo = [m.id for m in metodos if not m.es_efectivo]
    ids_sin_pos = [m.id for m in metodos if not m.es_efectivo and not m.es_punto_venta]
    candidatos = []

    if es_credito:
        for p in (
            VGPago.objects.filter(metodo_pago_id__in=ids_sin_pos, estado='completado', fecha_pago__date__range=(desde, hasta))
            .select_related('nota_entrega', 'factura', 'pedido', 'metodo_pago')
        ):
            monto = _bs(p.monto, p.tasa_cambio_referencia)
            if monto is None:
                continue
            if p.nota_entrega_id:
                etiqueta = f'Nota de entrega {p.nota_entrega.codigo}'
                extra = {'nota_entrega_id': p.nota_entrega_id, 'documento': etiqueta}
            elif p.factura_id:
                etiqueta = f'Factura {p.factura.numero_factura}'
                extra = {'factura_id': p.factura_id, 'documento': etiqueta}
            else:
                etiqueta = f'Pedido #{p.pedido_id}'
                extra = {'pedido_id': p.pedido_id, 'documento': etiqueta}
            candidatos.append(Candidato(
                'pago', p.id, _fecha_local(p.fecha_pago), monto, _referencia_bancaria(p.referencia),
                f'{etiqueta} · {p.metodo_pago.nombre}', extra=extra | {'referencia_original': p.referencia},
            ))
        for t in VGTransferenciaCuenta.objects.filter(
            cuenta_destino_id__in=ids_metodos, moneda_destino='VES', fecha__range=(desde, hasta),
        ):
            candidatos.append(Candidato(
                'transferencia', t.id, t.fecha, t.monto_destino, _referencia_bancaria(t.referencia),
                f'Transferencia entre cuentas: {t.concepto}', texto=t.concepto,
                extra={'referencia_original': t.referencia},
            ))
        for i in VGIngresoExtra.objects.filter(
            metodo_pago_id__in=ids_sin_efectivo, fecha_creacion__date__range=(desde, hasta),
        ).select_related('metodo_pago'):
            monto = _bs(i.monto, i.tasa_cambio_referencia)
            if monto is None:
                continue
            candidatos.append(Candidato(
                'ingreso_extra', i.id, _fecha_local(i.fecha_creacion), monto, '',
                f'{i.get_tipo_display()}: {i.descripcion or i.metodo_pago.nombre}', texto=i.descripcion,
            ))
        return candidatos

    # Debitos: se incluyen TODOS los metodos no efectivo de la cuenta (una compra con tarjeta de debito
    # se registra con el metodo de punto de venta).
    for a in (
        VGAbonoGasto.objects.filter(metodo_pago_id__in=ids_sin_efectivo, fecha_pago__date__range=(desde, hasta))
        .select_related('gasto__categoria', 'metodo_pago')
    ):
        if _es_gasto_comision(a.gasto):
            continue  # las comisiones se concilian por dia, no una a una
        monto = _bs(a.monto, a.tasa_cambio_referencia or a.gasto.tasa_cambio_referencia)
        if monto is None:
            continue
        g = a.gasto
        etiqueta = f'Gasto: {g.descripcion}' + (f' ({g.proveedor_nombre})' if g.proveedor_nombre else '')
        candidatos.append(Candidato(
            'abono_gasto', a.id, _fecha_local(a.fecha_pago), monto,
            _referencia_bancaria(a.referencia) or _referencia_bancaria(g.numero_comprobante),
            etiqueta, texto=f'{g.descripcion} {g.proveedor_nombre}', fechas_alt=(g.fecha_gasto,),
            extra={'gasto_id': g.id, 'referencia_original': g.numero_comprobante, 'metodo': a.metodo_pago.nombre},
        ))
    for a in (
        VGAbonoCompra.objects.filter(metodo_pago_id__in=ids_sin_efectivo, fecha_pago__date__range=(desde, hasta))
        .select_related('compra', 'metodo_pago')
    ):
        monto = _bs(a.monto, a.tasa_cambio_referencia)
        if monto is None:
            continue
        c = a.compra
        alt = tuple(f for f in (c.fecha_compra, c.fecha_factura) if f)
        candidatos.append(Candidato(
            'abono_compra', a.id, _fecha_local(a.fecha_pago), monto, _referencia_bancaria(a.referencia),
            f'Compra: {c.proveedor_nombre}' + (f' · factura {c.numero_factura_proveedor}' if c.numero_factura_proveedor else ''),
            texto=f'{c.proveedor_nombre} {c.numero_factura_proveedor}', fechas_alt=alt,
            extra={'compra_id': c.id, 'referencia_original': a.referencia, 'metodo': a.metodo_pago.nombre},
        ))
    for t in VGTransferenciaCuenta.objects.filter(
        cuenta_origen_id__in=ids_metodos, moneda_origen='VES', fecha__range=(desde, hasta),
    ):
        candidatos.append(Candidato(
            'transferencia', t.id, t.fecha, t.monto_origen, _referencia_bancaria(t.referencia),
            f'Transferencia entre cuentas: {t.concepto}', texto=t.concepto, extra={'referencia_original': t.referencia},
        ))
    return candidatos


def _claves_ocupadas():
    """Registros del sistema que ya estan confirmados contra otro movimiento."""
    return set(
        VGConciliacionMovimiento.objects.filter(estado='confirmado').exclude(metodo='comision_dia')
        .values_list('origen_tipo', 'origen_id')
    )


# ---------------------------------------------------------------------------
# Evaluacion de un par movimiento <-> candidato
# ---------------------------------------------------------------------------
@dataclass
class Evaluacion:
    puntaje: int
    metodo: str            # referencia | monto_fecha
    diferencia: Decimal    # candidato - banco (Bs)
    dias: int
    nota: str = ''

    @property
    def seguro(self):
        return self.puntaje >= PUNTAJE_SEGURO


def _tokens(texto):
    return {t for t in re.findall(r'[a-z0-9]{5,}', str(texto or '').lower())}


def _dias_entre(fecha_mov, candidato):
    return min(abs((fecha_mov - f).days) for f in (candidato.fecha, *candidato.fechas_alt))


def evaluar(mov, candidato, es_credito):
    """Puntua el par (None si no se parecen lo suficiente). Ver el docstring del modulo."""
    fecha_mov = _fecha_local(mov.fecha)
    dias = _dias_entre(fecha_mov, candidato)
    diferencia = (candidato.monto - mov.monto).quantize(CENT)
    absoluta = abs(diferencia)
    ref_banco = _solo_digitos(mov.referencia)
    tol_ref = max(TOL_REF_ABS, (mov.monto * TOL_REF_PCT).quantize(CENT))

    exacta = bool(candidato.referencia) and ref_banco == candidato.referencia
    sufijo = (
        bool(candidato.referencia) and not exacta and len(candidato.referencia) >= MIN_DIGITOS_SUFIJO
        and ref_banco.endswith(candidato.referencia)
    )
    if exacta and dias <= VENTANA_REF_EXACTA_DIAS:
        if absoluta <= tol_ref:
            return Evaluacion(100, 'referencia', diferencia, dias)
        return Evaluacion(
            60, 'referencia', diferencia, dias,
            f'La referencia coincide pero el monto difiere en Bs {absoluta:,.2f}: revisa si se registró mal.',
        )
    if sufijo and dias <= VENTANA_REF_SUFIJO_DIAS and absoluta <= tol_ref:
        return Evaluacion(PUNTAJE_SEGURO, 'referencia', diferencia, dias)

    ventana = VENTANA_CREDITO_DIAS if es_credito else VENTANA_DEBITO_DIAS
    bonus = 0
    if not es_credito and _tokens(mov.observacion) & _tokens(candidato.texto):
        bonus = 10
    if absoluta <= TOL_MONTO_EXACTO and dias <= ventana:
        return Evaluacion(min(90, 80 - 2 * dias + bonus), 'monto_fecha', diferencia, dias)
    if absoluta <= mov.monto * TOL_MONTO_APROX_PCT and dias <= VENTANA_APROX_DIAS:
        return Evaluacion(40 - dias + bonus, 'monto_fecha', diferencia, dias, 'El monto no es idéntico.')
    return None


# ---------------------------------------------------------------------------
# Conciliacion
# ---------------------------------------------------------------------------
def _movimientos_en_rango(cuenta, desde, hasta):
    return VGMovimientoBancario.objects.filter(
        cuenta_bancaria=cuenta, fecha__date__gte=desde, fecha__date__lte=hasta,
    )


def _guardar_vinculo(mov, candidato, ev, estado, usuario, metodo=None, nota=None):
    return VGConciliacionMovimiento.objects.update_or_create(
        movimiento=mov, origen_tipo=candidato.tipo, origen_id=candidato.id,
        defaults={
            'monto_sistema': candidato.monto, 'diferencia': ev.diferencia, 'metodo': metodo or ev.metodo,
            'puntaje': ev.puntaje, 'estado': estado, 'nota': (nota if nota is not None else ev.nota)[:255],
            'creado_por': usuario, 'actualizado_por': usuario,
        },
    )[0]


def _tolerancia_referencia(mov):
    return max(TOL_REF_ABS, (mov.monto * TOL_REF_PCT).quantize(CENT))


def _guardar_grupo(mov, candidatos, usuario, metodo, puntaje):
    """
    Confirma varios registros del sistema contra UN movimiento (pago dividido). Cada registro queda con su
    propio monto; la diferencia entre la suma y el banco se anota una sola vez (en el primero) y en la nota.
    """
    total = sum((c.monto for c in candidatos), Decimal('0'))
    diferencia = (total - mov.monto).quantize(CENT)
    nota = f'Pago dividido en {len(candidatos)} registros: suma Bs {total:,.2f}.'
    if abs(diferencia) > _tolerancia_referencia(mov):
        nota += f' Difiere del banco en Bs {abs(diferencia):,.2f}.'
    fecha_mov = _fecha_local(mov.fecha)
    for i, cand in enumerate(candidatos):
        ev = Evaluacion(puntaje, metodo, diferencia if i == 0 else Decimal('0.00'), _dias_entre(fecha_mov, cand), nota)
        _guardar_vinculo(mov, cand, ev, 'confirmado', usuario, metodo=metodo)


def _grupo_por_referencia(mov, pool, ocupadas, rechazados, usados):
    """
    Varios registros con la MISMA referencia del banco cuya suma es el monto del movimiento (una transferencia que
    paga, por ejemplo, una compra y un gasto a la vez). None si no hay, si un solo registro ya alcanza (eso lo
    resuelve el cruce normal) o si la referencia es corta y podria coincidir por casualidad.
    """
    ref = _solo_digitos(mov.referencia)
    if len(ref) < MIN_DIGITOS_GRUPO:
        return None
    fecha_mov = _fecha_local(mov.fecha)
    mismos = [
        c for c in pool
        if c.referencia == ref and c.clave not in ocupadas and c.clave not in usados
        and (mov.id, *c.clave) not in rechazados and _dias_entre(fecha_mov, c) <= VENTANA_REF_EXACTA_DIAS
    ]
    if len(mismos) < 2 or len(mismos) > MAX_GRUPO:
        return None
    tolerancia = _tolerancia_referencia(mov)
    if any(abs(c.monto - mov.monto) <= tolerancia for c in mismos):
        return None
    for tamano in range(2, len(mismos) + 1):
        for combo in combinations(mismos, tamano):
            if abs(sum((c.monto for c in combo), Decimal('0')) - mov.monto) <= tolerancia:
                return list(combo)
    return None


def _indexar(pool):
    """Indices para no comparar cada movimiento contra todo el pool: por monto (ordenado) y por ultimos 3 digitos de la referencia."""
    por_monto = sorted(range(len(pool)), key=lambda i: pool[i].monto)
    montos = [pool[i].monto for i in por_monto]
    por_ref = defaultdict(list)
    for i, c in enumerate(pool):
        if len(c.referencia) >= 3:
            por_ref[c.referencia[-3:]].append(i)
    return montos, por_monto, por_ref


def _candidatos_de(mov, pool, indice):
    """Solo los candidatos que pueden puntuar: monto cercano o referencia que termina igual."""
    montos, por_monto, por_ref = indice
    margen = max(TOL_REF_ABS, mov.monto * max(TOL_REF_PCT, TOL_MONTO_APROX_PCT))
    elegidos = set(por_monto[bisect_left(montos, mov.monto - margen):bisect_right(montos, mov.monto + margen)])
    ref = _solo_digitos(mov.referencia)
    if len(ref) >= 3:
        elegidos.update(por_ref.get(ref[-3:], ()))
    return [pool[i] for i in sorted(elegidos)]


def _conciliar_lado(movs, pool, ocupadas, rechazados, es_credito, usuario):
    """Asigna a cada movimiento su mejor candidato (cada candidato se usa una sola vez)."""
    pares = []
    por_mov = defaultdict(list)
    indice = _indexar(pool)
    # Primero los pagos divididos (varios registros con la referencia del banco que suman su monto): esos
    # registros ya no compiten por ningun otro movimiento.
    grupos, usados_grupo = {}, set()
    for mov in movs:
        grupo = _grupo_por_referencia(mov, pool, ocupadas, rechazados, usados_grupo)
        if grupo:
            grupos[mov.id] = grupo
            usados_grupo.update(c.clave for c in grupo)
    for mov in movs:
        if mov.id in grupos:
            continue
        for cand in _candidatos_de(mov, pool, indice):
            if cand.clave in ocupadas or cand.clave in usados_grupo or (mov.id, *cand.clave) in rechazados:
                continue
            ev = evaluar(mov, cand, es_credito)
            if ev is not None:
                pares.append((mov, cand, ev))
                por_mov[mov.id].append((cand, ev))
    pares.sort(key=lambda p: (-p[2].puntaje, abs(p[2].diferencia), p[2].dias, p[0].id))

    asignados, usados = {}, set()
    for mov, cand, ev in pares:
        if mov.id in asignados or cand.clave in usados:
            continue
        asignados[mov.id] = (cand, ev)
        usados.add(cand.clave)

    resultado = defaultdict(int)
    for mov in movs:
        if mov.id in grupos:
            _guardar_grupo(mov, grupos[mov.id], usuario, 'referencia', 100)
            mov.estado = 'conciliado'
            mov.save(update_fields=['estado', 'fecha_actualizacion'])
            resultado['conciliado'] += 1
            continue
        asignado = asignados.get(mov.id)
        if asignado is None:
            mov.estado = 'sin_coincidencia'
            mov.save(update_fields=['estado', 'fecha_actualizacion'])
            resultado['sin_coincidencia'] += 1
            continue
        cand, ev = asignado
        if ev.metodo == 'monto_fecha' and ev.puntaje >= 60:
            alternativas = [
                c for c, e in por_mov[mov.id]
                if c.clave != cand.clave and e.metodo == 'monto_fecha' and abs(e.diferencia) <= TOL_MONTO_EXACTO
            ]
            if alternativas:
                ev.nota = f'Hay {len(alternativas)} registro(s) más con el mismo monto: confirma que es este.'
        if ev.seguro:
            _guardar_vinculo(mov, cand, ev, 'confirmado', usuario)
            mov.estado = 'conciliado'
            resultado['conciliado'] += 1
        else:
            _guardar_vinculo(mov, cand, ev, 'sugerido', usuario)
            mov.estado = 'por_revisar'
            resultado['por_revisar'] += 1
        mov.save(update_fields=['estado', 'fecha_actualizacion'])
    return resultado


def _comisiones_por_dia(movs, usuario, cuenta):
    """Las comisiones de cada dia (suma) contra el gasto de comision de ese dia."""
    por_dia = defaultdict(list)
    for m in movs:
        por_dia[_fecha_local(m.fecha)].append(m)
    rechazados = set(
        VGConciliacionMovimiento.objects.filter(movimiento__in=movs, estado='rechazado', metodo='comision_dia')
        .values_list('movimiento_id', 'origen_id')
    )
    resultado = defaultdict(int)
    for dia, lista in sorted(por_dia.items()):
        # el total del dia incluye TODAS las comisiones de ese dia, aunque algunas ya estuvieran resueltas
        total = sum(
            (c.monto for c in VGMovimientoBancario.objects.filter(
                cuenta_bancaria=cuenta, clase='comision', fecha__date=dia,
            ).exclude(estado='ignorado')),
            Decimal('0'),
        )
        gastos = [
            g for g in VGGasto.objects.filter(fecha_gasto=dia).select_related('categoria')
            if _es_gasto_comision(g) and g.tasa_cambio_referencia
        ]
        elegido = None
        if gastos:
            elegido = min(gastos, key=lambda g: abs(_bs(g.monto, g.tasa_cambio_referencia) - total))
        for m in lista:
            gasto = elegido if elegido is not None and (m.id, elegido.id) not in rechazados else None
            if gasto is None:
                m.estado = 'sin_coincidencia'
                resultado['sin_coincidencia'] += 1
            else:
                monto_gasto = _bs(gasto.monto, gasto.tasa_cambio_referencia)
                diferencia = (monto_gasto - total).quantize(CENT)
                coincide = abs(diferencia) <= TOL_COMISION_DIA
                nota = (
                    f'Suma de las comisiones del día: Bs {total:,.2f}.'
                    if coincide else
                    f'La suma de comisiones del día (Bs {total:,.2f}) difiere del gasto (Bs {monto_gasto:,.2f}).'
                )
                VGConciliacionMovimiento.objects.update_or_create(
                    movimiento=m, origen_tipo='gasto', origen_id=gasto.id,
                    defaults={
                        'monto_sistema': monto_gasto, 'diferencia': diferencia, 'metodo': 'comision_dia',
                        'puntaje': 100 if coincide else 50, 'estado': 'confirmado' if coincide else 'sugerido',
                        'nota': nota, 'creado_por': usuario, 'actualizado_por': usuario,
                    },
                )
                m.estado = 'conciliado' if coincide else 'por_revisar'
                resultado['conciliado' if coincide else 'por_revisar'] += 1
            m.save(update_fields=['estado', 'fecha_actualizacion'])
    return resultado


def conciliar(cuenta, desde, hasta, usuario, solo_movimientos=None):
    """
    Corre el cruce para los movimientos de `cuenta` entre `desde` y `hasta` que aun no estan resueltos
    (pendientes, por revisar o sin coincidencia). Lo ya confirmado o ignorado no se toca. Devuelve un
    conteo por resultado.
    """
    cuenta = normalizar_cuenta(cuenta)
    _exigir_cuenta_ves(cuenta)
    movs_qs = _movimientos_en_rango(cuenta, desde, hasta).filter(estado__in=ESTADOS_RECONCILIABLES)
    if solo_movimientos is not None:
        movs_qs = movs_qs.filter(id__in=[m.id for m in solo_movimientos])
    cerrados = fechas_cerradas(cuenta, desde, hasta)
    movs = [m for m in movs_qs if _fecha_local(m.fecha) not in cerrados]
    total = defaultdict(int)
    if not movs:
        return dict(total)

    with transaction.atomic():
        # Se descartan las sugerencias anteriores de estos movimientos para recalcularlas con lo ultimo.
        VGConciliacionMovimiento.objects.filter(movimiento__in=movs, estado='sugerido').delete()
        ocupadas = _claves_ocupadas()
        rechazados = set(
            VGConciliacionMovimiento.objects.filter(movimiento__in=movs, estado='rechazado')
            .values_list('movimiento_id', 'origen_tipo', 'origen_id')
        )
        for m in movs:
            if m.clase == 'pos':
                if m.estado != 'pendiente':
                    m.estado = 'pendiente'
                    m.save(update_fields=['estado', 'fecha_actualizacion'])
                total['pos'] += 1

        creditos = [m for m in movs if m.tipo == 'credito' and m.clase not in ('pos', 'comision')]
        debitos = [m for m in movs if m.tipo == 'debito' and m.clase not in ('pos', 'comision')]
        comisiones = [m for m in movs if m.clase == 'comision']
        holgura = timedelta(days=HOLGURA_POOL_DIAS)
        rango = (desde - holgura, hasta + holgura)
        for lista, es_credito in ((creditos, True), (debitos, False)):
            if lista:
                pool = _cargar_pool(cuenta, rango[0], rango[1], es_credito)
                for clave, n in _conciliar_lado(lista, pool, ocupadas, rechazados, es_credito, usuario).items():
                    total[clave] += n
                # lo que acaba de quedar confirmado no puede volver a usarse en el otro lado
                ocupadas = _claves_ocupadas()
        for clave, n in _comisiones_por_dia(comisiones, usuario, cuenta).items():
            total[clave] += n
    return dict(total)


# ---------------------------------------------------------------------------
# Acciones sobre un movimiento
# ---------------------------------------------------------------------------
class AccionInvalida(Exception):
    pass


def _exigir_dia_abierto(mov):
    if VGCierreConciliacion.objects.filter(
        cuenta_bancaria=mov.cuenta_bancaria, estado='vigente', fecha=_fecha_local(mov.fecha),
    ).exists():
        raise AccionInvalida('Ese día ya está cerrado: reabre el cierre del día para cambiar algo.')


def _refrescar_estado(mov):
    """Recalcula mov.estado a partir de sus vinculos (sin tocar ignorado)."""
    if mov.estado == 'ignorado':
        return
    vinculos = list(mov.vinculos.all())
    if any(v.estado == 'confirmado' for v in vinculos):
        mov.estado = 'conciliado'
    elif any(v.estado == 'sugerido' for v in vinculos):
        mov.estado = 'por_revisar'
    else:
        mov.estado = 'pendiente'
    mov.save(update_fields=['estado', 'fecha_actualizacion'])


def confirmar_vinculo(vinculo, usuario):
    if vinculo.estado == 'rechazado':
        raise AccionInvalida('Ese vínculo fue rechazado.')
    mov = vinculo.movimiento
    _exigir_dia_abierto(mov)
    try:
        with transaction.atomic():
            vinculo.estado = 'confirmado'
            vinculo.actualizado_por = usuario
            vinculo.save()
            mov.vinculos.filter(estado='sugerido').exclude(pk=vinculo.pk).delete()
            _refrescar_estado(mov)
    except IntegrityError:
        raise AccionInvalida('Ese registro del sistema ya está conciliado con otro movimiento del banco.')
    return mov


def rechazar_vinculo(vinculo, usuario):
    mov = vinculo.movimiento
    _exigir_dia_abierto(mov)
    if vinculo.estado == 'confirmado':
        raise AccionInvalida('Para rechazar un vínculo confirmado, primero deshaz la conciliación.')
    vinculo.estado = 'rechazado'
    vinculo.actualizado_por = usuario
    vinculo.save()
    mov.estado = 'pendiente'
    mov.save(update_fields=['estado', 'fecha_actualizacion'])
    # se busca la siguiente mejor opcion para ese movimiento
    dia = _fecha_local(mov.fecha)
    conciliar(mov.cuenta_bancaria, dia, dia, usuario, solo_movimientos=[mov])
    mov.refresh_from_db()
    return mov


def vincular_manual(mov, tipo, origen_id, usuario):
    """Una persona elige un registro concreto del sistema para este movimiento."""
    return vincular_varios(mov, [(tipo, origen_id)], usuario)


def vincular_varios(mov, origenes, usuario):
    """
    Una persona elige uno o VARIOS registros del sistema que este movimiento pago a la vez (ej. una transferencia
    que salda una compra y un gasto del mismo proveedor). `origenes` es una lista de (tipo, origen_id). Todos
    quedan confirmados juntos; si su suma no es el monto del banco, queda anotada la diferencia.
    """
    _exigir_dia_abierto(mov)
    if mov.estado == 'ignorado':
        raise AccionInvalida('Este movimiento está ignorado: reábrelo primero.')
    if mov.clase == 'comision':
        raise AccionInvalida('Las comisiones se concilian por día contra el gasto de comisión.')
    claves = list(dict.fromkeys((str(tipo), int(origen_id)) for tipo, origen_id in origenes))
    if not claves:
        raise AccionInvalida('Elige al menos un registro del sistema.')
    if mov.vinculos.filter(estado='confirmado').exists():
        raise AccionInvalida('Este movimiento ya está conciliado: deshaz la conciliación primero.')
    es_credito = mov.tipo == 'credito'
    dia = _fecha_local(mov.fecha)
    pool = _cargar_pool(mov.cuenta_bancaria, dia - timedelta(days=HOLGURA_POOL_DIAS), dia + timedelta(days=HOLGURA_POOL_DIAS), es_credito)
    por_clave = {c.clave: c for c in pool}
    elegidos = []
    for clave in claves:
        cand = por_clave.get(clave)
        if cand is None:
            raise AccionInvalida('Ese registro no es un candidato válido para este movimiento.')
        elegidos.append(cand)
    ocupadas = _claves_ocupadas()
    if any(c.clave in ocupadas for c in elegidos):
        raise AccionInvalida('Ese registro del sistema ya está conciliado con otro movimiento del banco.')
    try:
        with transaction.atomic():
            mov.vinculos.filter(estado='sugerido').delete()
            if len(elegidos) == 1:
                cand = elegidos[0]
                ev = Evaluacion(
                    100, 'manual', (cand.monto - mov.monto).quantize(CENT), _dias_entre(dia, cand),
                    'Elegido manualmente.' if abs(cand.monto - mov.monto) <= TOL_MONTO_EXACTO else 'Elegido manualmente; el monto difiere.',
                )
                _guardar_vinculo(mov, cand, ev, 'confirmado', usuario, metodo='manual')
            else:
                _guardar_grupo(mov, elegidos, usuario, 'manual', 100)
            _refrescar_estado(mov)
    except IntegrityError:
        raise AccionInvalida('Ese registro del sistema ya está conciliado con otro movimiento del banco.')
    return mov


def candidatos_para(mov, limite=8, todos=False):
    """
    Registros del sistema que podrian ser este movimiento, del mejor al peor (para elegir a mano).
    Con `todos`, cualquier registro libre de esa cuenta en los dias cercanos aunque su monto no se parezca: sirve para
    armar un pago dividido (los de la misma referencia del banco van primero).
    """
    es_credito = mov.tipo == 'credito'
    dia = _fecha_local(mov.fecha)
    pool = _cargar_pool(mov.cuenta_bancaria, dia - timedelta(days=HOLGURA_POOL_DIAS), dia + timedelta(days=HOLGURA_POOL_DIAS), es_credito)
    ocupadas = _claves_ocupadas()
    ref_banco = _solo_digitos(mov.referencia)
    filas = []
    for c in pool:
        if c.clave in ocupadas:
            continue
        ev = evaluar(mov, c, es_credito)
        dias = _dias_entre(dia, c)
        if todos:
            if dias > VENTANA_TODOS_DIAS:
                continue
            if ev is None:
                misma_ref = bool(ref_banco) and c.referencia == ref_banco
                ev = Evaluacion(
                    60 if misma_ref else max(1, 10 - dias), 'manual', (c.monto - mov.monto).quantize(CENT), dias,
                    'Misma referencia que el banco.' if misma_ref else '',
                )
            filas.append((c, ev))
            continue
        if ev is None:
            # mas laxo que el cruce automatico: monto parecido (10%) y fecha cercana; si la observacion del
            # banco comparte palabras con el registro (ej. "insumos para llevar"), sube en la lista.
            if dias <= VENTANA_DEBITO_DIAS and abs(c.monto - mov.monto) <= mov.monto * Decimal('0.10'):
                parecido = bool(_tokens(f'{mov.observacion} {mov.descripcion}') & _tokens(c.texto))
                ev = Evaluacion(
                    max(1, 10 + (25 if parecido else 0) - dias), 'manual', (c.monto - mov.monto).quantize(CENT), dias,
                    'Monto y descripción parecidos.' if parecido else 'Monto parecido.',
                )
            else:
                continue
        filas.append((c, ev))
    if todos:
        filas.sort(key=lambda x: (-x[1].puntaje, x[1].dias, x[0].monto))
        return filas[:LIMITE_TODOS]
    filas.sort(key=lambda x: (-x[1].puntaje, abs(x[1].diferencia), x[1].dias))
    return filas[:limite]


def ignorar_movimiento(mov, motivo, usuario):
    _exigir_dia_abierto(mov)
    motivo = (motivo or '').strip()
    if not motivo:
        raise AccionInvalida('Escribe el motivo para ignorar este movimiento.')
    if mov.vinculos.filter(estado='confirmado').exists():
        raise AccionInvalida('Este movimiento está conciliado: deshaz la conciliación primero.')
    mov.vinculos.filter(estado='sugerido').delete()
    mov.estado = 'ignorado'
    mov.motivo_ignorado = motivo[:255]
    mov.actualizado_por = usuario
    mov.save(update_fields=['estado', 'motivo_ignorado', 'actualizado_por', 'fecha_actualizacion'])
    return mov


def reabrir_movimiento(mov, usuario):
    """Deshace una conciliacion o un 'ignorado' y lo deja pendiente para volver a cruzarlo."""
    _exigir_dia_abierto(mov)
    with transaction.atomic():
        mov.vinculos.exclude(estado='rechazado').delete()
        mov.estado = 'pendiente'
        mov.motivo_ignorado = ''
        mov.actualizado_por = usuario
        mov.save(update_fields=['estado', 'motivo_ignorado', 'actualizado_por', 'fecha_actualizacion'])
    dia = _fecha_local(mov.fecha)
    conciliar(mov.cuenta_bancaria, dia, dia, usuario, solo_movimientos=[mov])
    mov.refresh_from_db()
    return mov


def confirmar_probables(cuenta, desde, hasta, usuario):
    """Confirma en bloque las sugerencias fuertes (sin otros candidatos con el mismo monto)."""
    confirmados = 0
    sugeridos = VGConciliacionMovimiento.objects.filter(
        movimiento__cuenta_bancaria=normalizar_cuenta(cuenta), movimiento__estado='por_revisar',
        movimiento__fecha__date__gte=desde, movimiento__fecha__date__lte=hasta,
        estado='sugerido', puntaje__gte=PUNTAJE_PROBABLE_MIN, nota='',
    ).exclude(metodo='comision_dia').select_related('movimiento')
    for v in sugeridos:
        try:  # confirmar_vinculo rechaza los movimientos de un dia cerrado
            confirmar_vinculo(v, usuario)
            confirmados += 1
        except AccionInvalida:
            continue
    return confirmados


# ---------------------------------------------------------------------------
# Reportes
# ---------------------------------------------------------------------------
def registros_sin_movimiento(cuenta, desde, hasta):
    """Lo que el sistema registro en esa cuenta y NO aparece en el banco (ni como sugerencia)."""
    cuenta = normalizar_cuenta(cuenta)
    _exigir_cuenta_ves(cuenta)
    vinculados = set(
        VGConciliacionMovimiento.objects.exclude(estado='rechazado').values_list('origen_tipo', 'origen_id')
    )
    gastos_comision = set(
        VGConciliacionMovimiento.objects.filter(metodo='comision_dia').exclude(estado='rechazado')
        .values_list('origen_id', flat=True)
    )
    filas = []
    for es_credito in (True, False):
        for c in _cargar_pool(cuenta, desde, hasta, es_credito):
            if c.clave in vinculados:
                continue
            if c.tipo == 'abono_gasto' and c.extra.get('gasto_id') in gastos_comision:
                continue
            if not (desde <= c.fecha <= hasta):
                continue
            filas.append({'sentido': 'credito' if es_credito else 'debito', 'candidato': c})
    filas.sort(key=lambda f: (f['candidato'].fecha, f['candidato'].monto))
    return filas


def resumen_pos(cuenta, desde, hasta):
    """Por dia de acreditacion: lo que el banco acredito por POS vs. lo que el sistema acredito en lotes."""
    cuenta = normalizar_cuenta(cuenta)
    metodos_pos = [m.id for m in metodos_de_cuenta(cuenta) if m.es_punto_venta]
    banco = defaultdict(Decimal)
    for m in _movimientos_en_rango(cuenta, desde, hasta).filter(clase='pos', tipo='credito'):
        banco[_fecha_local(m.fecha)] += m.monto
    sistema = defaultdict(Decimal)
    for lote in VGLotePOS.objects.filter(
        metodo_pago_id__in=metodos_pos, estado='acreditado', fecha_abono_real__range=(desde, hasta),
    ):
        sistema[lote.fecha_abono_real] += lote.monto_bruto_sistema_bs
    filas = []
    for dia in sorted(set(banco) | set(sistema)):
        b, s = banco.get(dia, Decimal('0')), sistema.get(dia, Decimal('0'))
        dif = (b - s).quantize(CENT)
        filas.append({
            'fecha': dia, 'banco': b.quantize(CENT), 'sistema': s.quantize(CENT), 'diferencia': dif,
            'porcentaje': (dif / s * 100).quantize(CENT) if s else None,
        })
    return filas


def resumen_movimientos(cuenta, desde, hasta):
    """Conteos y montos por estado y por sentido (credito/debito), para las tarjetas y el PDF."""
    movs = _movimientos_en_rango(normalizar_cuenta(cuenta), desde, hasta)
    resumen = {
        'total': 0, 'creditos': Decimal('0'), 'debitos': Decimal('0'),
        'estados': {e: {'cantidad': 0, 'creditos': Decimal('0'), 'debitos': Decimal('0')} for e, _ in VGMovimientoBancario.ESTADOS},
    }
    for m in movs.only('estado', 'tipo', 'monto'):
        resumen['total'] += 1
        clave = 'creditos' if m.tipo == 'credito' else 'debitos'
        resumen[clave] += m.monto
        bloque = resumen['estados'][m.estado]
        bloque['cantidad'] += 1
        bloque[clave] += m.monto
    return resumen


# ---------------------------------------------------------------------------
# Cierre diario de la conciliacion
# ---------------------------------------------------------------------------
def _saldo_final_y_saltos(movs):
    """
    (saldo de la ultima linea del dia, saltos de saldo dentro del dia) usando la cadena de saldos:
    cada linea debe tener otra cuyo saldo sea (su saldo - su movimiento con signo); la ultima del dia
    es la que no es "anterior" de ninguna. Las lineas del archivo no vienen ordenadas por hora, por eso
    no basta con mirar la ultima fila. Si la cadena es ambigua se usa la fecha mas reciente.
    """
    con_saldo = [m for m in movs if m.saldo is not None]
    if not con_saldo:
        return None, 0

    def firmado(m):
        return m.monto if m.tipo == 'credito' else -m.monto

    por_saldo = defaultdict(list)
    for i, m in enumerate(con_saldo):
        por_saldo[m.saldo].append(i)
    son_anteriores, sin_anterior = set(), 0
    for i, m in enumerate(con_saldo):
        anteriores = [j for j in por_saldo.get(m.saldo - firmado(m), []) if j != i]
        if anteriores:
            son_anteriores.update(anteriores)
        else:
            sin_anterior += 1
    finales = [m for i, m in enumerate(con_saldo) if i not in son_anteriores]
    final = finales[0].saldo if len(finales) == 1 else max(con_saldo, key=lambda m: (m.fecha, m.id)).saldo
    return final, max(0, sin_anterior - 1)


def estadisticas_dias(cuenta, desde, hasta):
    """
    {fecha: numeros del dia} para cada dia del rango, aunque no tenga movimientos. Una sola pasada
    por la base para todo el rango (los registros del sistema sin banco y el POS se piden una vez).
    """
    cuenta = normalizar_cuenta(cuenta)
    por_dia = defaultdict(list)
    for m in _movimientos_en_rango(cuenta, desde, hasta):
        por_dia[_fecha_local(m.fecha)].append(m)
    sin_banco = defaultdict(int)
    for f in registros_sin_movimiento(cuenta, desde, hasta):
        sin_banco[f['candidato'].fecha] += 1
    pos = {f['fecha']: f for f in resumen_pos(cuenta, desde, hasta)}

    resultado = {}
    dia = desde
    while dia <= hasta:
        lista = por_dia.get(dia, [])
        por_estado = defaultdict(int)
        for m in lista:
            por_estado[m.estado] += 1
        pendientes_pos = sum(1 for m in lista if m.estado == 'pendiente' and m.clase == 'pos')
        creditos = sum((m.monto for m in lista if m.tipo == 'credito'), Decimal('0'))
        debitos = sum((m.monto for m in lista if m.tipo == 'debito'), Decimal('0'))
        saldo_final, saltos = _saldo_final_y_saltos(lista)
        saldo_inicial = (saldo_final - (creditos - debitos)) if saldo_final is not None else None
        pendientes_otros = por_estado['pendiente'] - pendientes_pos
        resultado[dia] = {
            'fecha': dia, 'total': len(lista), 'conciliados': por_estado['conciliado'], 'ignorados': por_estado['ignorado'],
            'por_revisar': por_estado['por_revisar'], 'sin_coincidencia': por_estado['sin_coincidencia'],
            'pendientes_pos': pendientes_pos, 'pendientes_otros': pendientes_otros,
            'bloqueos': por_estado['por_revisar'] + por_estado['sin_coincidencia'] + pendientes_otros,
            'creditos': creditos.quantize(CENT), 'debitos': debitos.quantize(CENT),
            'saldo_inicial': saldo_inicial, 'saldo_final': saldo_final, 'saltos_saldo': saltos,
            'registros_sin_banco': sin_banco.get(dia, 0),
            'pos_banco': pos[dia]['banco'] if dia in pos else Decimal('0'),
            'pos_sistema': pos[dia]['sistema'] if dia in pos else Decimal('0'),
        }
        dia += timedelta(days=1)
    return resultado


def listar_cierres(cuenta, desde, hasta):
    """
    Estado de cada dia del rango: cerrado (con su foto), pendiente (hay movimientos sin resolver), listo
    (todo resuelto, falta cerrarlo) o sin_movimientos (no hay lineas cargadas). En los cerrados se
    revisa la continuidad del saldo contra el cierre anterior.
    """
    cuenta = normalizar_cuenta(cuenta)
    estadisticas = estadisticas_dias(cuenta, desde, hasta)
    cierres = {
        c.fecha: c for c in VGCierreConciliacion.objects.filter(
            cuenta_bancaria=cuenta, estado='vigente', fecha__range=(desde, hasta),
        ).select_related('creado_por')
    }
    reaperturas = defaultdict(int)
    for fecha in VGCierreConciliacion.objects.filter(
        cuenta_bancaria=cuenta, estado='reabierto', fecha__range=(desde, hasta),
    ).values_list('fecha', flat=True):
        reaperturas[fecha] += 1

    anterior = VGCierreConciliacion.objects.filter(
        cuenta_bancaria=cuenta, estado='vigente', fecha__lt=desde, saldo_final_banco__isnull=False,
    ).order_by('-fecha').first()
    ultimo_final = anterior.saldo_final_banco if anterior else None
    hueco_con_movimientos = False  # hubo un dia sin cerrar y con movimientos desde el ultimo cierre

    dias = []
    for dia in sorted(estadisticas):
        s = estadisticas[dia]
        cierre = cierres.get(dia)
        if cierre is not None:
            estado = 'cerrado'
            continuidad = None
            if cierre.saldo_inicial_banco is not None and ultimo_final is not None and not hueco_con_movimientos:
                continuidad = abs(cierre.saldo_inicial_banco - ultimo_final) <= TOL_COMISION_DIA
            if cierre.saldo_final_banco is not None:
                ultimo_final = cierre.saldo_final_banco
            hueco_con_movimientos = False
        else:
            estado = 'sin_movimientos' if s['total'] == 0 else ('pendiente' if s['bloqueos'] else 'listo')
            continuidad = None
            if s['total'] > 0:
                hueco_con_movimientos = True
        dias.append({
            **s, 'estado': estado, 'cierre': cierre, 'continuidad': continuidad, 'reaperturas': reaperturas.get(dia, 0),
        })

    cerrados = [d for d in dias if d['estado'] == 'cerrado']
    resumen = {
        'dias': len(dias), 'cerrados': len(cerrados),
        'pendientes': sum(1 for d in dias if d['estado'] == 'pendiente'),
        'listos': sum(1 for d in dias if d['estado'] == 'listo'),
        'sin_movimientos': sum(1 for d in dias if d['estado'] == 'sin_movimientos'),
        'discontinuidades': sum(1 for d in cerrados if d['continuidad'] is False),
        'creditos_cerrados': sum((d['cierre'].creditos for d in cerrados), Decimal('0')),
        'debitos_cerrados': sum((d['cierre'].debitos for d in cerrados), Decimal('0')),
    }
    resumen['completo'] = resumen['cerrados'] == resumen['dias'] and resumen['discontinuidades'] == 0
    return dias, resumen


def continuidad_con_cierre_anterior(cuenta, fecha, saldo_inicial):
    """
    (True|False|None, saldo_final_del_cierre_anterior): si el saldo con que abre este dia es el mismo con que
    cerro el ultimo dia cerrado. None si no hay con que comparar (primer cierre, sin saldos, o hay movimientos
    de dias intermedios todavia sin cerrar).
    """
    anterior = VGCierreConciliacion.objects.filter(
        cuenta_bancaria=cuenta, estado='vigente', fecha__lt=fecha, saldo_final_banco__isnull=False,
    ).order_by('-fecha').first()
    if anterior is None or saldo_inicial is None:
        return None, None
    hay_hueco = VGMovimientoBancario.objects.filter(
        cuenta_bancaria=cuenta, fecha__date__gt=anterior.fecha, fecha__date__lt=fecha,
    ).exists()
    if hay_hueco:
        return None, anterior.saldo_final_banco
    return abs(anterior.saldo_final_banco - saldo_inicial) <= TOL_COMISION_DIA, anterior.saldo_final_banco


def cerrar_dia(cuenta, fecha, nota, usuario):
    """
    Confirma la conciliacion de un dia y guarda su foto. Falla si quedan movimientos por revisar o sin
    coincidencia, o si el dia aun no ocurre. Un dia sin movimientos solo se cierra con una nota que
    explique por que (para que no se cierre "en blanco" por olvidar subir el archivo).
    """
    cuenta = normalizar_cuenta(cuenta)
    _exigir_cuenta_ves(cuenta)
    nota = (nota or '').strip()
    if fecha > timezone.localdate():
        raise AccionInvalida('No se puede cerrar un día que todavía no ha ocurrido.')
    with transaction.atomic():
        if VGCierreConciliacion.objects.select_for_update().filter(
            cuenta_bancaria=cuenta, fecha=fecha, estado='vigente',
        ).exists():
            raise AccionInvalida('Ese día ya está cerrado.')
        s = estadisticas_dias(cuenta, fecha, fecha)[fecha]
        if s['bloqueos']:
            partes = []
            if s['por_revisar']:
                partes.append(f"{s['por_revisar']} por revisar")
            if s['sin_coincidencia']:
                partes.append(f"{s['sin_coincidencia']} sin coincidencia")
            if s['pendientes_otros']:
                partes.append(f"{s['pendientes_otros']} pendientes")
            raise AccionInvalida(
                'No se puede cerrar el día: faltan por resolver ' + ', '.join(partes)
                + '. Confírmalos, vincúlalos o ignóralos con un motivo.'
            )
        continuidad, saldo_anterior = continuidad_con_cierre_anterior(cuenta, fecha, s['saldo_inicial'])
        if (s['saltos_saldo'] > 0 or continuidad is False) and not nota:
            motivo = (
                f"el saldo del día anterior cerró en Bs {saldo_anterior:,.2f} pero este día abre en Bs {s['saldo_inicial']:,.2f}"
                if continuidad is False else f"la columna Saldo tiene {s['saltos_saldo']} salto(s) dentro del día"
            )
            raise AccionInvalida(
                f'El saldo del banco no encadena ({motivo}): puede faltar alguna línea en el archivo. '
                'Revisa el archivo, o escribe una nota que explique la diferencia para cerrar el día igual.'
            )
        if s['total'] == 0 and not nota:
            raise AccionInvalida(
                'Ese día no tiene movimientos del banco cargados. Sube el archivo, o escribe una nota que explique '
                'por qué no hubo movimientos para poder cerrarlo.'
            )
        return VGCierreConciliacion.objects.create(
            cuenta_bancaria=cuenta, fecha=fecha, estado='vigente', movimientos_total=s['total'],
            conciliados=s['conciliados'], ignorados=s['ignorados'], pendientes_pos=s['pendientes_pos'],
            creditos=s['creditos'], debitos=s['debitos'], saldo_inicial_banco=s['saldo_inicial'],
            saldo_final_banco=s['saldo_final'], saltos_saldo=s['saltos_saldo'],
            registros_sin_banco=s['registros_sin_banco'], pos_banco=s['pos_banco'], pos_sistema=s['pos_sistema'],
            nota=nota[:255], creado_por=usuario, actualizado_por=usuario,
        )


def reabrir_cierre(cierre, motivo, usuario):
    """Reabre un dia cerrado (queda registrado quien y por que); el dia vuelve a admitir cambios y se puede cerrar de nuevo."""
    motivo = (motivo or '').strip()
    if not motivo:
        raise AccionInvalida('Escribe el motivo para reabrir el día.')
    if cierre.estado != 'vigente':
        raise AccionInvalida('Ese cierre ya fue reabierto.')
    cierre.estado = 'reabierto'
    cierre.reabierto_por = usuario
    cierre.fecha_reapertura = timezone.now()
    cierre.motivo_reapertura = motivo[:255]
    cierre.actualizado_por = usuario
    cierre.save()
    return cierre
