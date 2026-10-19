"""
PDF de la conciliacion bancaria por movimiento (ver conciliacion_bancaria.py).

Recibe filas ya armadas por la vista (reportes_pdf_views.reporte_conciliacion_bancaria_pdf_view) y solo
las convierte en secciones: resumen por estado, lo que NO coincide, lo que falta por revisar, lo que
esta en el sistema pero no en el banco, las comisiones por dia, el POS por dia y, si se pide, el
detalle de lo conciliado.
"""
from datetime import datetime

from .base import Columna, Seccion, formatear_numero, generar_pdf_reporte

ESTADOS_TEXTO = {
    'conciliado': 'Conciliados',
    'por_revisar': 'Por revisar',
    'sin_coincidencia': 'Sin coincidencia en el sistema',
    'ignorado': 'Ignorados',
    'pendiente': 'Pendientes (POS u otros sin cruzar)',
}

COLUMNAS_RESUMEN = [
    Columna('Estado', 0.46), Columna('Movimientos', 0.14, 'derecha'),
    Columna('Créditos (Bs)', 0.2, 'derecha'), Columna('Débitos (Bs)', 0.2, 'derecha'),
]
COLUMNAS_MOVIMIENTO = [
    Columna('Fecha', 0.1), Columna('Referencia', 0.1), Columna('Descripción', 0.28), Columna('Tipo', 0.07),
    Columna('Monto (Bs)', 0.12, 'derecha'), Columna('Observación del banco', 0.33),
]
COLUMNAS_SUGERIDO = [
    Columna('Fecha', 0.09), Columna('Referencia', 0.09), Columna('Descripción', 0.22), Columna('Monto (Bs)', 0.11, 'derecha'),
    Columna('Sugerido por el sistema', 0.29), Columna('Diferencia (Bs)', 0.1, 'derecha'), Columna('Nota', 0.1),
]
COLUMNAS_CONCILIADO = [
    Columna('Fecha', 0.1), Columna('Referencia', 0.1), Columna('Descripción', 0.27), Columna('Tipo', 0.07),
    Columna('Monto (Bs)', 0.12, 'derecha'), Columna('Conciliado con', 0.34),
]
COLUMNAS_SISTEMA = [
    Columna('Fecha', 0.1), Columna('Sentido', 0.09), Columna('Registro del sistema', 0.5),
    Columna('Referencia', 0.13), Columna('Monto (Bs)', 0.18, 'derecha'),
]
COLUMNAS_COMISION = [
    Columna('Día', 0.14), Columna('Comisiones del banco (Bs)', 0.26, 'derecha'),
    Columna('Gasto en el sistema (Bs)', 0.26, 'derecha'), Columna('Diferencia (Bs)', 0.2, 'derecha'), Columna('Estado', 0.14),
]
COLUMNAS_POS = [
    Columna('Día de acreditación', 0.22), Columna('Banco (Bs)', 0.2, 'derecha'), Columna('Sistema (Bs)', 0.2, 'derecha'),
    Columna('Diferencia (Bs)', 0.2, 'derecha'), Columna('%', 0.18, 'derecha'),
]


COLUMNAS_CIERRE = [
    Columna('Día', 0.09), Columna('Estado', 0.11), Columna('Movimientos', 0.09, 'derecha'), Columna('Conciliados', 0.09, 'derecha'),
    Columna('Créditos (Bs)', 0.13, 'derecha'), Columna('Débitos (Bs)', 0.13, 'derecha'), Columna('Saldo final banco (Bs)', 0.14, 'derecha'),
    Columna('Saldo vs. día anterior', 0.1), Columna('Cerrado por', 0.12),
]


def _fecha_hora(dt):
    return dt.strftime('%d/%m/%Y %H:%M')


def _tipo(tipo):
    return 'Crédito' if tipo == 'credito' else 'Débito'


def _num(valor):
    return formatear_numero(valor) if valor is not None else '—'


def generar_pdf_conciliacion_bancaria(
    cuenta, desde, hasta, resumen, sin_coincidencia, por_revisar, conciliados, no_banco, comisiones, pos,
    generado_en=None, incluir_conciliados=True, cierres=None,
):
    """
    resumen          salida de conciliacion_bancaria.resumen_movimientos
    sin_coincidencia [{fecha, referencia, descripcion, tipo, monto, observacion}]
    por_revisar      [{fecha, referencia, descripcion, monto, sugerido, diferencia, nota}]
    conciliados      [{fecha, referencia, descripcion, tipo, monto, con}]
    no_banco         [{fecha(date), sentido, etiqueta, referencia, monto}]
    comisiones       [{dia(date), banco, sistema, diferencia, estado}]
    pos              [{fecha(date), banco, sistema, diferencia, porcentaje}]
    cierres          [{fecha(date), estado, total, conciliados, creditos, debitos, saldo_final, continuidad, cerrado_por}]
    """
    total = resumen['total']
    estados = resumen['estados']
    conciliados_n = estados['conciliado']['cantidad']
    pct = (conciliados_n / total * 100) if total else 0

    secciones = [Seccion(
        titulo='Resumen por estado', columnas=COLUMNAS_RESUMEN,
        filas=[
            [ESTADOS_TEXTO[e], str(estados[e]['cantidad']), _num(estados[e]['creditos']), _num(estados[e]['debitos'])]
            for e in ('conciliado', 'por_revisar', 'sin_coincidencia', 'ignorado', 'pendiente') if estados[e]['cantidad']
        ],
        fila_total=['Total', str(total), _num(resumen['creditos']), _num(resumen['debitos'])],
        mensaje_vacio='No hay movimientos del banco cargados en este rango.',
    )]
    if cierres:
        secciones.append(Seccion(
            titulo='Cierre de la conciliación por día', columnas=COLUMNAS_CIERRE,
            filas=[[
                c['fecha'].strftime('%d/%m/%Y'), c['estado'], str(c['total']), str(c['conciliados']),
                _num(c['creditos']), _num(c['debitos']), _num(c['saldo_final']), c['continuidad'], c['cerrado_por'],
            ] for c in cierres],
        ))
    if sin_coincidencia:
        secciones.append(Seccion(
            titulo='Sin coincidencia en el sistema', detalle=f'{len(sin_coincidencia)} movimientos',
            columnas=COLUMNAS_MOVIMIENTO,
            filas=[[_fecha_hora(m['fecha']), m['referencia'], m['descripcion'], _tipo(m['tipo']), _num(m['monto']), m['observacion']]
                   for m in sin_coincidencia],
        ))
    if por_revisar:
        secciones.append(Seccion(
            titulo='Por revisar (sugeridos, falta confirmar)', detalle=f'{len(por_revisar)} movimientos',
            columnas=COLUMNAS_SUGERIDO,
            filas=[[m['fecha'].strftime('%d/%m/%Y'), m['referencia'], m['descripcion'], _num(m['monto']),
                    m['sugerido'], _num(m['diferencia']), m['nota']] for m in por_revisar],
        ))
    if no_banco:
        secciones.append(Seccion(
            titulo='En el sistema pero NO en el banco', detalle=f'{len(no_banco)} registros', columnas=COLUMNAS_SISTEMA,
            filas=[[r['fecha'].strftime('%d/%m/%Y'), 'Cobro' if r['sentido'] == 'credito' else 'Pago', r['etiqueta'],
                    r['referencia'], _num(r['monto'])] for r in no_banco],
        ))
    if comisiones:
        secciones.append(Seccion(
            titulo='Comisiones por día', columnas=COLUMNAS_COMISION,
            filas=[[c['dia'].strftime('%d/%m/%Y'), _num(c['banco']), _num(c['sistema']), _num(c['diferencia']), c['estado']]
                   for c in comisiones],
        ))
    if pos:
        secciones.append(Seccion(
            titulo='Punto de venta: acreditado por el banco vs. lotes del sistema', columnas=COLUMNAS_POS,
            filas=[[p['fecha'].strftime('%d/%m/%Y'), _num(p['banco']), _num(p['sistema']), _num(p['diferencia']),
                    f'{formatear_numero(p["porcentaje"])} %' if p['porcentaje'] is not None else '—'] for p in pos],
        ))
    if incluir_conciliados and conciliados:
        secciones.append(Seccion(
            titulo='Movimientos conciliados', detalle=f'{len(conciliados)} movimientos', columnas=COLUMNAS_CONCILIADO,
            filas=[[_fecha_hora(m['fecha']), m['referencia'], m['descripcion'], _tipo(m['tipo']), _num(m['monto']), m['con']]
                   for m in conciliados],
        ))

    return generar_pdf_reporte(
        titulo=f'Conciliación bancaria · {cuenta}',
        subtitulo=f'Del {desde.strftime("%d/%m/%Y")} al {hasta.strftime("%d/%m/%Y")}',
        resumen=(
            f'<b>{total}</b> movimientos · <b>{conciliados_n}</b> conciliados ({formatear_numero(pct, 1, 1)} %)'
            f' · {estados["por_revisar"]["cantidad"]} por revisar · {estados["sin_coincidencia"]["cantidad"]} sin coincidencia',
            f'Créditos: <b>Bs. {_num(resumen["creditos"])}</b> · Débitos: <b>Bs. {_num(resumen["debitos"])}</b>',
        ),
        secciones=secciones, orientacion='horizontal', generado_en=generado_en or datetime.now(),
    )
