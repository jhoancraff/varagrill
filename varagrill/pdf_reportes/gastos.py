"""
PDF de gastos por rango de fechas, agrupado por categoria.

Cada categoria es un bloque (Nomina, Servicios...) con las columnas Descripcion, Monto (Bs),
Tasa y Fecha, y al final del bloque el total en bolivares y en dolares. Al final del reporte
va el resumen con el total de cada categoria y el total general.

Recibe los gastos ya serializados por gastos_views._serialize_gasto (los mismos numeros que
muestra el reporte en pantalla), asi este modulo no toca la base de datos.
"""
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from .base import Columna, Seccion, formatear_numero, generar_pdf_reporte

COLUMNAS_BLOQUE = [
    Columna('Descripción del gasto', 0.44),
    Columna('Monto (Bs)', 0.22, 'derecha'),
    Columna('Tasa (Bs/$)', 0.16, 'derecha'),
    Columna('Fecha', 0.18, 'centro'),
]

COLUMNAS_RESUMEN = [
    Columna('Categoría', 0.44),
    Columna('Total (Bs)', 0.22, 'derecha'),
    Columna('Total ($)', 0.16, 'derecha'),
    Columna('Gastos', 0.18, 'centro'),
]

# Un gasto que todavia no se pago completo no tiene "tasa de pago" definitiva (su saldo se
# valora con la tasa de hoy), asi que se marca en la descripcion para no confundirlo.
ETIQUETA_ESTADO = {'pendiente': ' (pendiente)', 'abonada_parcial': ' (abonado parcial)'}


def _decimal(valor):
    return Decimal(str(valor)) if valor not in (None, '') else None


def tasa_del_gasto(gasto):
    """
    Tasa a la que quedo el gasto. Uno cargado en bolivares conserva la tasa del dia en que se
    registro; uno en dolares ya pagado conserva la de su(s) abono(s), que se obtiene de dividir
    sus bolivares entre sus dolares (si hubo varios abonos con tasas distintas, es el promedio
    ponderado, asi Monto Bs / Tasa siempre da el monto en dolares).
    """
    referencia = _decimal(gasto.get('tasa_cambio_referencia'))
    total_bs = _decimal(gasto.get('total_bs'))
    monto = _decimal(gasto.get('monto'))
    if gasto.get('moneda_origen') == 'VES' and referencia:
        return referencia
    if total_bs is not None and monto:
        return total_bs / monto
    return referencia


def _fecha(valor):
    if isinstance(valor, (date, datetime)):
        return valor
    return date.fromisoformat(str(valor)[:10])


def armar_bloques_gastos(gastos):
    """
    Agrupa por categoria (orden alfabetico) y calcula las filas y totales de cada una.
    Devuelve una lista de dicts: categoria, filas, total_bs, total_usd, cantidad, sin_tasa.

    El total en Bs suma los montos de cada fila ya redondeados a 2 decimales, para que lo
    impreso cuadre; el total en dolares es la suma de los montos en dolares de los gastos.
    """
    por_categoria = {}
    for gasto in gastos:
        por_categoria.setdefault(gasto['categoria_nombre'], []).append(gasto)

    bloques = []
    for categoria in sorted(por_categoria, key=lambda nombre: nombre.lower()):
        filas = []
        total_bs = Decimal('0')
        total_usd = Decimal('0')
        sin_tasa = 0
        for gasto in sorted(por_categoria[categoria], key=lambda g: (_fecha(g['fecha_gasto']), g['id'])):
            monto_bs = _decimal(gasto.get('total_bs'))
            tasa = tasa_del_gasto(gasto)
            if monto_bs is None:
                sin_tasa += 1
            else:
                total_bs += monto_bs
            total_usd += _decimal(gasto.get('monto')) or Decimal('0')
            filas.append({
                'descripcion': gasto['descripcion'] + ETIQUETA_ESTADO.get(gasto.get('estado_pago'), ''),
                'monto_bs': monto_bs,
                'tasa': tasa,
                'fecha': _fecha(gasto['fecha_gasto']),
            })
        bloques.append({
            'categoria': categoria,
            'filas': filas,
            'total_bs': total_bs.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            'total_usd': total_usd.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            'cantidad': len(filas),
            'sin_tasa': sin_tasa,
        })
    return bloques


def _texto_cantidad(cantidad, singular, plural):
    return f'{cantidad} {singular if cantidad == 1 else plural}'


def generar_pdf_gastos(gastos, desde, hasta, generado_en=None):
    bloques = armar_bloques_gastos(gastos)
    total_bs = sum((b['total_bs'] for b in bloques), Decimal('0'))
    total_usd = sum((b['total_usd'] for b in bloques), Decimal('0'))
    cantidad = sum(b['cantidad'] for b in bloques)
    sin_tasa = sum(b['sin_tasa'] for b in bloques)
    subtitulo = f'Del {_fecha(desde).strftime("%d/%m/%Y")} al {_fecha(hasta).strftime("%d/%m/%Y")}'

    secciones = []
    for bloque in bloques:
        secciones.append(Seccion(
            titulo=bloque['categoria'],
            detalle=_texto_cantidad(bloque['cantidad'], 'gasto', 'gastos'),
            columnas=COLUMNAS_BLOQUE,
            filas=[
                [
                    fila['descripcion'],
                    formatear_numero(fila['monto_bs']) if fila['monto_bs'] is not None else 'Sin tasa',
                    formatear_numero(fila['tasa'], 4, 4) if fila['tasa'] else '—',
                    fila['fecha'].strftime('%d/%m/%Y'),
                ]
                for fila in bloque['filas']
            ],
            fila_total=[
                f'Total {bloque["categoria"]}',
                f'Bs. {formatear_numero(bloque["total_bs"])}',
                f'$ {formatear_numero(bloque["total_usd"])}',
                '',
            ],
        ))

    if not bloques:
        secciones.append(Seccion(
            columnas=COLUMNAS_BLOQUE, filas=[], mensaje_vacio='No hay gastos registrados en este rango de fechas.',
        ))
    else:
        secciones.append(Seccion(
            titulo='Total por categoría',
            columnas=COLUMNAS_RESUMEN,
            filas=[
                [b['categoria'], formatear_numero(b['total_bs']), formatear_numero(b['total_usd']), str(b['cantidad'])]
                for b in bloques
            ],
            fila_total=['Total general', formatear_numero(total_bs), formatear_numero(total_usd), str(cantidad)],
        ))

    izquierda = f'<b>{_texto_cantidad(cantidad, "gasto", "gastos")}</b> en <b>{_texto_cantidad(len(bloques), "categoría", "categorías")}</b>'
    if sin_tasa:
        izquierda += f' · {_texto_cantidad(sin_tasa, "gasto", "gastos")} sin tasa (no suma en Bs)'
    return generar_pdf_reporte(
        titulo='Reporte de gastos',
        subtitulo=subtitulo,
        resumen=(izquierda, f'Total: <b>Bs. {formatear_numero(total_bs)}</b> · <b>$ {formatear_numero(total_usd)}</b>'),
        secciones=secciones,
        generado_en=generado_en or datetime.now(),
    )
