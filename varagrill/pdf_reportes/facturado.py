"""
PDF de lo facturado (notas de entrega emitidas) de un dia o de un rango de fechas.

Es el detalle de la tarjeta "Facturado" del cuadre de caja: las mismas notas y los mismos
montos que "Ventas del dia — detalle" (reportes.detalle_ventas_rango), asi que el total del
PDF coincide con el del cuadre. Eso incluye las notas anuladas, igual que el cuadre; se
marcan con el estado "Anulada" y el resumen dice cuantas son y por cuanto.

Un dia es una sola tabla. Un rango trae un bloque por dia (con su total) y, al final, el
total por dia y el total general. Cada nota ocupa una fila por pago (abono), como en pantalla.
La tasa es la que quedo congelada en el pago (la del dia en que se cobro) y solo aplica a los
pagos en bolivares.

Recibe las notas ya armadas (con `fecha_emision` en hora local) y no toca la base de datos.
"""
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from .base import Columna, Seccion, formatear_numero, generar_pdf_reporte

DIAS_SEMANA = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']

ETIQUETA_ESTADO = {
    'pendiente_pago': 'Pendiente',
    'abonada_parcial': 'Abonada parcial',
    'pagada': 'Pagada',
    'anulada': 'Anulada',
}

COLUMNAS_DIA = [
    Columna('Nota', 0.085),
    Columna('Hora', 0.055, 'centro'),
    Columna('Cliente', 0.09),
    Columna('Monto ($)', 0.08, 'derecha'),
    Columna('Estado', 0.09, 'centro'),
    Columna('Método de pago', 0.13),
    Columna('Banco', 0.10),
    Columna('Referencia', 0.12),
    Columna('Pagado ($)', 0.08, 'derecha'),
    Columna('Tasa (Bs/$)', 0.08, 'derecha'),
    Columna('Pagado (Bs)', 0.09, 'derecha'),
]

COLUMNAS_RESUMEN = [
    Columna('Día', 0.5),
    Columna('Notas', 0.2, 'centro'),
    Columna('Total facturado ($)', 0.3, 'derecha'),
]


def _dos_decimales(valor):
    return Decimal(valor).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _texto_cantidad(cantidad, singular, plural):
    return f'{cantidad} {singular if cantidad == 1 else plural}'


def _fecha_larga(fecha):
    return f'{DIAS_SEMANA[fecha.weekday()]} {fecha.strftime("%d/%m/%Y")}'


def _etiqueta_metodo(pago):
    return f'{pago["metodo_pago_nombre"]} ({"Bs" if pago["metodo_pago_moneda"] == "VES" else "$"})'


def armar_dias_facturado(notas):
    """
    Agrupa las notas por dia de emision (en orden) y arma las filas de cada dia.
    Devuelve una lista de dicts: fecha, filas, total, cantidad, anuladas, total_anuladas.

    Los totales suman los montos reales de las notas y se redondean una sola vez al final,
    igual que el cuadre de caja, para que el total del PDF sea el mismo de la pantalla.
    """
    por_dia = {}
    for nota in sorted(notas, key=lambda n: (n['fecha_emision'], n['id'])):
        por_dia.setdefault(nota['fecha_emision'].date(), []).append(nota)

    dias = []
    for fecha in sorted(por_dia):
        filas = []
        total = Decimal('0')
        total_anuladas = Decimal('0')
        anuladas = 0
        for nota in por_dia[fecha]:
            monto = Decimal(nota['total'])
            total += monto
            if nota['estado'] == 'anulada':
                anuladas += 1
                total_anuladas += monto

            pagos = nota['pagos']
            for indice, pago in enumerate(pagos or [None]):
                if indice == 0:
                    codigo = nota['codigo']
                    if len(pagos) > 1:
                        codigo += f' (abono 1 de {len(pagos)})'
                else:
                    codigo = f'Abono {indice + 1} de {len(pagos)}'
                primera = indice == 0
                filas.append([
                    codigo,
                    nota['fecha_emision'].strftime('%H:%M') if primera else '',
                    (nota['cliente'] or '—') if primera else '',
                    formatear_numero(monto) if primera else '',
                    ETIQUETA_ESTADO.get(nota['estado'], nota['estado']) if primera else '',
                    _etiqueta_metodo(pago) if pago else '—',
                    (pago['cuenta_bancaria'] or '—') if pago else '—',
                    (pago['referencia'] or '—') if pago else '—',
                    formatear_numero(pago['monto']) if pago else '—',
                    formatear_numero(pago['tasa'], 2, 4) if pago and pago.get('tasa') else '—',
                    formatear_numero(pago['monto_bs']) if pago and pago['monto_bs'] is not None else '—',
                ])
        dias.append({
            'fecha': fecha,
            'filas': filas,
            'total': _dos_decimales(total),
            'cantidad': len(por_dia[fecha]),
            'anuladas': anuladas,
            'total_anuladas': _dos_decimales(total_anuladas),
        })
    return dias


def generar_pdf_facturado(notas, desde, hasta, generado_en=None):
    dias = armar_dias_facturado(notas)
    total = _dos_decimales(sum((Decimal(n['total']) for n in notas), Decimal('0')))
    cantidad = len(notas)
    anuladas = sum(dia['anuladas'] for dia in dias)
    total_anuladas = _dos_decimales(sum((Decimal(n['total']) for n in notas if n['estado'] == 'anulada'), Decimal('0')))

    un_solo_dia = desde == hasta
    subtitulo = (
        f'Notas de entrega del {_fecha_larga(desde)}' if un_solo_dia
        else f'Notas de entrega del {desde.strftime("%d/%m/%Y")} al {hasta.strftime("%d/%m/%Y")}'
    )

    secciones = []
    for dia in dias:
        secciones.append(Seccion(
            titulo=None if un_solo_dia else _fecha_larga(dia['fecha']),
            detalle=None if un_solo_dia else _texto_cantidad(dia['cantidad'], 'nota', 'notas'),
            columnas=COLUMNAS_DIA,
            filas=dia['filas'],
            fila_total=[
                'Total facturado' if un_solo_dia else 'Total del día', '', '', f'$ {formatear_numero(dia["total"])}',
                '', '', '', '', '', '', '',
            ],
        ))

    if not dias:
        secciones.append(Seccion(
            columnas=COLUMNAS_DIA, filas=[], mensaje_vacio='No se emitió ninguna nota de entrega en este período.',
        ))
    elif not un_solo_dia:
        secciones.append(Seccion(
            titulo='Total por día',
            columnas=COLUMNAS_RESUMEN,
            filas=[
                [_fecha_larga(dia['fecha']), str(dia['cantidad']), formatear_numero(dia['total'])]
                for dia in dias
            ],
            fila_total=['Total facturado', str(cantidad), formatear_numero(total)],
        ))

    izquierda = f'<b>{_texto_cantidad(cantidad, "nota de entrega", "notas de entrega")}</b>'
    if anuladas:
        izquierda += (
            f' · {_texto_cantidad(anuladas, "anulada", "anuladas")} por $ {formatear_numero(total_anuladas)}'
            ' (incluidas en el total)'
        )
    return generar_pdf_reporte(
        titulo='Reporte de facturado',
        subtitulo=subtitulo,
        resumen=(izquierda, f'Total facturado: <b>$ {formatear_numero(total)}</b>'),
        secciones=secciones,
        orientacion='horizontal',
        generado_en=generado_en or datetime.now(),
    )
