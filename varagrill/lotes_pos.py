"""
Lotes de punto de venta (POS): el dinero cobrado por punto de venta (debito/
credito) no suma al saldo de la cuenta el dia del cobro. Los cobros se agrupan en
lotes —como el cierre de lote de la maquina fisica— y el saldo sube cuando el
personal revisa el punto/banco y, si el lote cayo, toca "Acreditar".

Sin parametros: no hay hora de corte, dias de abono, comisiones, retenciones ni
calendario de feriados. Acreditar suma el monto que el sistema registro (USD y Bs
con la tasa congelada de cada cobro), tal cual, con fecha de abono = hoy.

  abierto  -> recibe cada cobro POS del metodo (hay UNO por metodo)
  cerrado  -> la cajera cerro el lote (o se autoclausuro al cerrar la caja)
  acreditado -> un clic: suma al saldo de la cuenta
  anulado  -> descartado con motivo

Contabilidad LIGERA: la cuenta transitoria "POS por cobrar" es un saldo CALCULADO
(reportes.pos_por_cobrar_transitorio) — lotes abierto/cerrado. TODO FASE 7: el
motor de partida doble (asiento de acreditacion Banco / POS por cobrar).

Todo cambio de estado corre en transaction.atomic con select_for_update y es
idempotente: repetir una accion sobre un lote que ya la tiene aplicada se rechaza,
nunca duplica montos.
"""
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import VGCorreccionMetodoPago, VGCorrelativoFiscal, VGLotePOS, VGPago

SEIS_DECIMALES = Decimal('0.000001')
CENTIMOS = Decimal('0.01')

ESTADOS_NO_ACREDITADOS = ('abierto', 'cerrado')
SERIE_LOTE_POS = 'LOTE_POS'


class LoteError(Exception):
    """Regla de negocio incumplida al operar un lote; el mensaje es apto para mostrar al usuario."""


# ---------------------------------------------------------------------------
# Montos de un lote
# ---------------------------------------------------------------------------
def _tasa_para_fecha(fecha):
    from .reportes import tasa_para_fecha  # import tardio: reportes importa este modulo
    return tasa_para_fecha(fecha)


def _tasa_de_pago(pago):
    """Tasa con la que se cobro ese pago (la propia, la de su documento, o la del dia)."""
    return (
        pago.tasa_cambio_referencia
        or (pago.nota_entrega.tasa_cambio_referencia if pago.nota_entrega_id else None)
        or (pago.factura.tasa_cambio_referencia if pago.factura_id else None)
        or _tasa_para_fecha(timezone.localtime(pago.fecha_pago).date())
    )


def _pagos_vigentes(lote):
    return lote.pagos.filter(estado='completado').select_related('nota_entrega', 'factura')


def recalcular_lote(lote, forzar=False):
    """
    Vuelve a sumar los cobros vigentes de un lote ABIERTO (los anulados no
    cuentan). Un lote ya cerrado queda congelado: es lo que la maquina cerro.
    `forzar` lo recalcula igual: solo lo usa mover_pago_de_lote, cuando un
    administrador saca a proposito un cobro de un lote cerrado.
    """
    if lote.estado != 'abierto' and not forzar:
        return lote
    bruto_usd = Decimal('0')
    bruto_bs = Decimal('0')
    for pago in _pagos_vigentes(lote):
        bruto_usd += pago.monto
        tasa = _tasa_de_pago(pago)
        if tasa:
            bruto_bs += (pago.monto * tasa).quantize(CENTIMOS)
    lote.monto_bruto_usd = bruto_usd.quantize(SEIS_DECIMALES)
    lote.monto_bruto_sistema_bs = bruto_bs
    lote.save(update_fields=['monto_bruto_usd', 'monto_bruto_sistema_bs', 'fecha_actualizacion'])
    return lote


# ---------------------------------------------------------------------------
# Lote abierto y asignacion de cobros
# ---------------------------------------------------------------------------
def obtener_o_crear_lote_abierto(metodo, usuario=None):
    """
    El lote 'abierto' del metodo (hay UNO por metodo — constraint
    un_lote_abierto_por_metodo), creandolo si no existe. Dos cajeros cobrando
    a la vez pueden intentar crearlo juntos: el segundo choca con la constraint
    y simplemente recoge el que gano.
    """
    for _ in range(3):
        with transaction.atomic():
            lote = (
                VGLotePOS.objects.select_for_update().select_related('metodo_pago')
                .filter(metodo_pago=metodo, estado='abierto').first()
            )
            if lote is not None:
                return lote
            try:
                with transaction.atomic():
                    return VGLotePOS.objects.create(
                        numero=VGCorrelativoFiscal.siguiente(SERIE_LOTE_POS),
                        metodo_pago=metodo,
                        cuenta_bancaria=metodo.cuenta_bancaria,
                        fecha_operacion=timezone.localdate(),
                        moneda=metodo.moneda,
                        creado_por=usuario,
                        actualizado_por=usuario,
                    )
            except IntegrityError:
                continue
    raise LoteError('No se pudo abrir el lote POS; intenta de nuevo.')


def asignar_pago_a_lote(pago, usuario=None):
    """
    Si el metodo del pago es punto de venta, lo mete al lote abierto del metodo
    (creandolo si hace falta) y deja el lote al dia. No hace nada con metodos
    que no son POS. Se llama justo despues de crear el VGPago.
    """
    metodo = pago.metodo_pago
    if not metodo.es_punto_venta:
        return None
    with transaction.atomic():
        lote = obtener_o_crear_lote_abierto(metodo, usuario)
        pago.lote_pos = lote
        pago.save(update_fields=['lote_pos'])
        recalcular_lote(lote)
    return lote


def pago_anulado(pago):
    """Un cobro POS se anulo (devolucion/reembolso): si su lote sigue abierto, se recalcula la sumatoria."""
    if pago.lote_pos_id:
        recalcular_lote(VGLotePOS.objects.select_related('metodo_pago').get(pk=pago.lote_pos_id))


def validar_cambio_metodo_pago(pago):
    """
    Mensaje de error si el cobro NO puede cambiar de cuenta porque ya forma parte
    de un lote POS cerrado/acreditado; None si se puede. Un lote ABIERTO si admite el cambio.
    """
    if pago.lote_pos_id:
        lote = VGLotePOS.objects.get(pk=pago.lote_pos_id)
        if lote.estado != 'abierto':
            return (
                f'Este cobro ya esta en el lote POS #{lote.numero} ({lote.get_estado_display().lower()}); '
                'un administrador debe sacarlo con "Mover cobro" en Lotes de punto de venta (detalle del lote).'
            )
    return None


def aplicar_cambio_metodo_pago(pago, usuario=None):
    """Despues de cambiar pago.metodo_pago: lo saca del lote abierto anterior y lo asigna al del metodo nuevo si es POS."""
    with transaction.atomic():
        if pago.lote_pos_id:
            lote_anterior = VGLotePOS.objects.select_related('metodo_pago').get(pk=pago.lote_pos_id)
            pago.lote_pos = None
            pago.save(update_fields=['lote_pos'])
            recalcular_lote(lote_anterior)
        asignar_pago_a_lote(pago, usuario)


# ---------------------------------------------------------------------------
# Cerrar / acreditar / reabrir / anular
# ---------------------------------------------------------------------------
def _anotar(lote, texto):
    lote.notas = (lote.notas + '\n' if lote.notas else '') + texto


def _etiqueta_usuario(usuario):
    if usuario is None:
        return 'sistema'
    return usuario.get_full_name() or usuario.username


def _sello():
    return timezone.localtime().strftime('%Y-%m-%d %H:%M')


def cerrar_lote(lote, usuario, ahora=None):
    """
    Cierre (parcial) del lote abierto: recalcula el monto desde sus cobros, lo
    congela y pasa a 'cerrado'. El siguiente cobro POS de ese metodo abre un lote
    nuevo automaticamente.
    """
    with transaction.atomic():
        lote = VGLotePOS.objects.select_for_update().select_related('metodo_pago').get(pk=lote.pk)
        if lote.estado != 'abierto':
            raise LoteError(f'El lote #{lote.numero} ya no esta abierto.')
        if not lote.pagos.filter(estado='completado').exists():
            raise LoteError(f'El lote #{lote.numero} no tiene cobros para cerrar.')
        recalcular_lote(lote)
        lote.fecha_cierre = ahora or timezone.now()
        lote.estado = 'cerrado'
        lote.cerrado_por = usuario
        lote.actualizado_por = usuario
        lote.save(update_fields=['fecha_cierre', 'estado', 'cerrado_por', 'actualizado_por', 'fecha_actualizacion'])
        return lote


def autoclausurar_lotes_abiertos(usuario, ahora=None):
    """
    Al cerrar la caja se cierran TODOS los lotes POS que sigan abiertos. Un lote
    abierto sin cobros vigentes (todos anulados) no tiene nada que cerrar: se marca
    'anulado' con una nota. Devuelve los lotes que quedaron 'cerrado'.
    """
    cerrados = []
    with transaction.atomic():
        for lote in VGLotePOS.objects.select_for_update().select_related('metodo_pago').filter(estado='abierto'):
            if not lote.pagos.filter(estado='completado').exists():
                lote.estado = 'anulado'
                _anotar(lote, 'Autoanulado al cerrar la caja: no tenia cobros vigentes.')
                lote.actualizado_por = usuario
                lote.save(update_fields=['estado', 'notas', 'actualizado_por', 'fecha_actualizacion'])
                continue
            cerrados.append(cerrar_lote(lote, usuario, ahora))
    return cerrados


def acreditar_lote(lote, usuario, ahora=None):
    """
    El lote cayo en el banco: suma su monto al saldo de la cuenta (con fecha de
    abono = hoy). Solo desde 'cerrado'. Repetirlo se rechaza, asi un doble clic
    nunca suma dos veces.
    """
    with transaction.atomic():
        lote = VGLotePOS.objects.select_for_update().select_related('metodo_pago').get(pk=lote.pk)
        if lote.estado == 'acreditado':
            raise LoteError(f'El lote #{lote.numero} ya esta acreditado.')
        if lote.estado != 'cerrado':
            raise LoteError('Solo se puede acreditar un lote cerrado: cierra el lote primero.')
        ahora = ahora or timezone.now()
        lote.estado = 'acreditado'
        lote.fecha_abono_real = timezone.localtime(ahora).date()
        lote.fecha_acreditacion = ahora
        lote.acreditado_por = usuario
        lote.actualizado_por = usuario
        lote.save(update_fields=[
            'estado', 'fecha_abono_real', 'fecha_acreditacion', 'acreditado_por',
            'actualizado_por', 'fecha_actualizacion',
        ])
        return lote


def revertir_acreditacion(lote, usuario, motivo):
    """Deshace una acreditacion hecha por error: el lote vuelve a 'cerrado' (motivo obligatorio, anotado)."""
    motivo = (motivo or '').strip()
    if not motivo:
        raise LoteError('El motivo es obligatorio.')
    with transaction.atomic():
        lote = VGLotePOS.objects.select_for_update().get(pk=lote.pk)
        if lote.estado != 'acreditado':
            raise LoteError('Solo se puede revertir un lote acreditado.')
        _anotar(lote, f'[{_sello()}] Acreditacion revertida por {_etiqueta_usuario(usuario)}: {motivo}')
        lote.estado = 'cerrado'
        lote.fecha_abono_real = None
        lote.fecha_acreditacion = None
        lote.acreditado_por = None
        lote.actualizado_por = usuario
        lote.save(update_fields=[
            'estado', 'fecha_abono_real', 'fecha_acreditacion', 'acreditado_por', 'notas',
            'actualizado_por', 'fecha_actualizacion',
        ])
        return lote


def mover_pago_de_lote(pago, usuario, motivo, metodo_destino=None):
    """
    Saca un cobro de un lote CERRADO al que no pertenece (por ejemplo, se dieron
    cuenta al final del dia): sin reabrir el lote, aunque el metodo ya tenga otro
    lote abierto. Dos destinos:

      - mismo metodo (metodo_destino vacio): pasa al lote ABIERTO actual del metodo;
      - otro metodo: cambia la cuenta del cobro (queda auditado en
        VGCorreccionMetodoPago); si el nuevo metodo es punto de venta entra a su lote
        abierto, y si no, suma al saldo de esa cuenta de una vez.

    El lote cerrado se recalcula sin ese cobro (para que vuelva a cuadrar con el
    cierre del punto) y, si se queda sin cobros, se anula. Motivo obligatorio,
    anotado en los lotes. Un lote abierto usa "cambiar cuenta" del cuadre y uno
    acreditado se revierte primero.
    """
    motivo = (motivo or '').strip()
    if not motivo:
        raise LoteError('El motivo es obligatorio.')
    with transaction.atomic():
        pago = VGPago.objects.select_for_update().select_related('metodo_pago').get(pk=pago.pk)
        if not pago.lote_pos_id:
            raise LoteError('Este cobro no esta en ningun lote.')
        if pago.estado != 'completado':
            raise LoteError('Este cobro esta anulado.')
        origen = VGLotePOS.objects.select_for_update().select_related('metodo_pago').get(pk=pago.lote_pos_id)
        if origen.estado == 'acreditado':
            raise LoteError('El lote ya esta acreditado: reviertelo primero (se vuelve a cerrar) y luego mueve el cobro.')
        if origen.estado != 'cerrado':
            raise LoteError('Solo se mueven cobros de un lote cerrado. Si el lote esta abierto, usa "cambiar cuenta" en el cuadre de caja.')

        metodo_anterior = pago.metodo_pago
        cambia_metodo = metodo_destino is not None and metodo_destino.pk != metodo_anterior.pk
        if cambia_metodo:
            if not metodo_destino.activo:
                raise LoteError('La cuenta elegida esta desactivada.')
            VGCorreccionMetodoPago.objects.create(
                tipo='pago', registro_id=pago.id, metodo_anterior=metodo_anterior, metodo_nuevo=metodo_destino,
                motivo=motivo, creado_por=usuario, actualizado_por=usuario,
            )
            pago.metodo_pago = metodo_destino

        destino = None
        if pago.metodo_pago.es_punto_venta:
            destino = obtener_o_crear_lote_abierto(pago.metodo_pago, usuario)
        pago.lote_pos = destino
        pago.save(update_fields=['metodo_pago', 'lote_pos'])

        # El lote cerrado vuelve a sumar solo lo que le queda; si no queda nada, se anula.
        origen = VGLotePOS.objects.select_related('metodo_pago').get(pk=origen.pk)
        recalcular_lote(origen, forzar=True)
        hacia = (
            f'al lote #{destino.numero}' if destino
            else f'a la cuenta {pago.metodo_pago.nombre} (fuera de lotes)'
        )
        _anotar(origen, f'[{_sello()}] {_etiqueta_usuario(usuario)} saco el cobro #{pago.id} y lo paso {hacia}: {motivo}')
        if not origen.pagos.filter(estado='completado').exists():
            origen.estado = 'anulado'
            _anotar(origen, 'Anulado automaticamente: se quedo sin cobros.')
        origen.actualizado_por = usuario
        origen.save(update_fields=['estado', 'notas', 'actualizado_por', 'fecha_actualizacion'])
        if destino:
            _anotar(destino, f'[{_sello()}] Recibio el cobro #{pago.id} del lote #{origen.numero}: {motivo}')
            destino.save(update_fields=['notas', 'fecha_actualizacion'])
            recalcular_lote(destino)
        return origen


def reabrir_lote(lote, usuario, motivo):
    """
    Devuelve un lote 'cerrado' a 'abierto' (por ejemplo, se cerro por error). Solo
    si NO esta acreditado, con motivo obligatorio anotado, y solo si el metodo no
    tiene ya otro lote abierto (habria dos).
    """
    motivo = (motivo or '').strip()
    if not motivo:
        raise LoteError('El motivo es obligatorio.')
    with transaction.atomic():
        lote = VGLotePOS.objects.select_for_update().select_related('metodo_pago').get(pk=lote.pk)
        if lote.estado != 'cerrado':
            raise LoteError('Solo se puede reabrir un lote cerrado que aun no se ha acreditado.')
        if VGLotePOS.objects.filter(metodo_pago=lote.metodo_pago, estado='abierto').exists():
            raise LoteError('Este metodo ya tiene un lote abierto: ciérralo antes de reabrir otro.')
        _anotar(lote, f'[{_sello()}] Reabierto por {_etiqueta_usuario(usuario)}: {motivo}')
        lote.estado = 'abierto'
        lote.fecha_cierre = None
        lote.cerrado_por = None
        lote.actualizado_por = usuario
        lote.save(update_fields=['estado', 'fecha_cierre', 'cerrado_por', 'notas', 'actualizado_por', 'fecha_actualizacion'])
        recalcular_lote(lote)
        return lote


def anular_lote(lote, usuario, motivo):
    """
    Descarta un lote que aun no se acredito (motivo obligatorio anotado). Sus
    cobros no se pierden: pasan al lote abierto actual del metodo (se crea si no
    hay), asi nunca quedan cobros POS sin lote. Un lote ABIERTO solo se puede
    anular si esta vacio.
    """
    motivo = (motivo or '').strip()
    if not motivo:
        raise LoteError('El motivo es obligatorio.')
    with transaction.atomic():
        lote = VGLotePOS.objects.select_for_update().select_related('metodo_pago').get(pk=lote.pk)
        if lote.estado not in ESTADOS_NO_ACREDITADOS:
            raise LoteError('Un lote acreditado ya no se puede anular: revierte la acreditacion primero.')
        pagos = list(lote.pagos.all())
        if lote.estado == 'abierto' and any(p.estado == 'completado' for p in pagos):
            raise LoteError('Un lote abierto con cobros no se anula: ciérralo o muévele la cuenta a los cobros.')
        destino = None
        if pagos and lote.estado == 'cerrado':
            lote.estado = 'anulado'  # libera la constraint antes de resolver el lote destino
            lote.save(update_fields=['estado'])
            destino = obtener_o_crear_lote_abierto(lote.metodo_pago, usuario)
            lote.pagos.update(lote_pos=destino)
            recalcular_lote(destino)
        _anotar(lote, f'[{_sello()}] Anulado por {_etiqueta_usuario(usuario)}: {motivo}'
                + (f' (cobros movidos al lote #{destino.numero})' if destino else ''))
        lote.estado = 'anulado'
        lote.actualizado_por = usuario
        lote.save(update_fields=['estado', 'notas', 'actualizado_por', 'fecha_actualizacion'])
        return lote


# ---------------------------------------------------------------------------
# Backfill historico
# ---------------------------------------------------------------------------
def backfill_historico_metodo(metodo, usuario=None):
    """
    Cuando un metodo se marca como POS, sus cobros anteriores (sin lote) se agrupan
    en un VGLotePOS por dia para NO alterar los saldos que el usuario ya conoce:
    los dias que ya pasaron quedan 'acreditado' (abono = ese mismo dia, el saldo no
    cambia ni un centimo) y los de hoy entran al lote abierto actual. Idempotente:
    solo toca cobros sin lote. Devuelve cuantos lotes historicos creo.
    """
    hoy = timezone.localdate()
    pagos_por_dia = {}
    for pago in (
        VGPago.objects.filter(metodo_pago=metodo, estado='completado', lote_pos__isnull=True)
        .select_related('nota_entrega', 'factura').order_by('fecha_pago')
    ):
        pagos_por_dia.setdefault(timezone.localtime(pago.fecha_pago).date(), []).append(pago)

    creados = 0
    with transaction.atomic():
        for dia, pagos in sorted(pagos_por_dia.items()):
            if dia >= hoy:
                for pago in pagos:
                    asignar_pago_a_lote(pago, usuario)
                continue
            bruto_usd = sum((p.monto for p in pagos), Decimal('0')).quantize(SEIS_DECIMALES)
            bruto_bs = Decimal('0')
            for pago in pagos:
                tasa = _tasa_de_pago(pago)
                if tasa:
                    bruto_bs += (pago.monto * tasa).quantize(CENTIMOS)
            lote = VGLotePOS.objects.create(
                numero=VGCorrelativoFiscal.siguiente(SERIE_LOTE_POS),
                metodo_pago=metodo, cuenta_bancaria=metodo.cuenta_bancaria, fecha_operacion=dia,
                fecha_cierre=pagos[-1].fecha_pago, estado='acreditado', moneda=metodo.moneda,
                monto_bruto_usd=bruto_usd, monto_bruto_sistema_bs=bruto_bs,
                fecha_abono_real=dia, fecha_acreditacion=pagos[-1].fecha_pago,
                notas='Lote generado automaticamente a partir del historico al activar el metodo como punto de venta.',
                creado_por=usuario, actualizado_por=usuario,
            )
            VGPago.objects.filter(pk__in=[p.pk for p in pagos]).update(lote_pos=lote)
            creados += 1
    return creados
