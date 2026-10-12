"""
PDF del margen de ganancia por plato, en detalle, de un dia o de un rango de fechas.

Es el reporte "Detalles de margen de ganancia por plato" (api_views.armar_margen_ganancia_detallado):
las mismas ventas, con el mismo costo historico (el congelado al cobrar), asi que el PDF coincide
con la pantalla. Abre con un resumen de una fila por plato y el total del periodo (ventas, costo y
ganancia) y sigue con un bloque por plato: cada venta, con su costo, y el total de ese plato.

Recibe los datos ya armados (secciones y totales con los numeros como texto, igual que el JSON de
la vista) y no toca la base de datos.
"""
from datetime import datetime
from decimal import Decimal

from .base import Columna, Seccion, formatear_numero, generar_pdf_reporte

COLUMNAS_PLATO = [
    Columna('Fecha / hora', 0.12),
    Columna('Cantidad', 0.10, 'derecha'),
    Columna('Pedido', 0.07, 'centro'),
    Columna('Nota de entrega', 0.10),
    Columna('Ingreso ($)', 0.11, 'derecha'),
    Columna('Costo ($)', 0.11, 'derecha'),
    Columna('Costo + margen de producción ($)', 0.14, 'derecha'),
    Columna('Ganancia ($)', 0.12, 'derecha'),
    Columna('Ganancia (%)', 0.13, 'derecha'),
]

COLUMNAS_RESUMEN = [
    Columna('Plato', 0.21),
    Columna('Categoría', 0.19),
    Columna('Cantidad', 0.09, 'derecha'),
    Columna('Ventas ($)', 0.10, 'derecha'),
    Columna('Costo ($)', 0.10, 'derecha'),
    Columna('Costo + margen de producción ($)', 0.12, 'derecha'),
    Columna('Ganancia ($)', 0.10, 'derecha'),
    Columna('Ganancia (%)', 0.09, 'derecha'),
]

MARCA_ESTIMADO = ' *'

# Las ventas de un plato se parten en bloques de hasta este tamano, cada uno con el nombre del plato
# (un plato con cientos de ventas ocupa varias paginas y, sin esto, las siguientes no dirian de que
# plato son). Es un poco menos de lo que cabe en una pagina para que el bloque entre entero.
FILAS_POR_BLOQUE = 20


def _texto_cantidad_total(seccion):
    """'12 u.', '2,35 kg' o '12 u. + 2,35 kg' (un plato vendido por peso y por unidad)."""
    partes = []
    if Decimal(seccion['total_unidades']) > 0:
        partes.append(f'{formatear_numero(seccion["total_unidades"], 0, 2)} u.')
    if Decimal(seccion['total_kg']) > 0:
        partes.append(f'{formatear_numero(seccion["total_kg"])} kg')
    return ' + '.join(partes) or '—'


def _texto_cantidad_fila(fila):
    """Un plato por unidad: '2 u.'. Por peso: los gramos de cada porcion, y 'x n' si fueron varias."""
    if fila['unidad'] == 'kg' and fila['peso_gramos'] is not None:
        texto = f'{formatear_numero(fila["peso_gramos"], 0, 2)} g'
        if Decimal(fila['cantidad']) != 1:
            texto += f' × {formatear_numero(fila["cantidad"], 0, 2)}'
        return texto
    return f'{formatear_numero(fila["cantidad"], 0, 2)} u.'


def _fecha_hora(texto_iso):
    return datetime.fromisoformat(texto_iso).strftime('%d/%m/%Y %H:%M')


def _texto_ventas(cantidad):
    return f'{cantidad} venta' if cantidad == 1 else f'{cantidad} ventas'


def armar_secciones_margen_por_plato(secciones, totales):
    """Las secciones del PDF: el resumen por plato primero y, despues, el detalle de cada plato."""
    if not secciones:
        return [Seccion(
            columnas=COLUMNAS_PLATO, filas=[], mensaje_vacio='No hay ventas de platos en este período.',
        )]

    resultado = [Seccion(
        titulo='Resumen por plato',
        detalle=f'{len(secciones)} platos' if len(secciones) != 1 else '1 plato',
        columnas=COLUMNAS_RESUMEN,
        filas=[
            [
                s['nombre'] + (MARCA_ESTIMADO if s['tiene_costo_estimado'] else ''),
                s['categoria'],
                _texto_cantidad_total(s),
                formatear_numero(s['total_ingreso']),
                formatear_numero(s['total_costo']),
                formatear_numero(s['total_costo_con_margen']),
                formatear_numero(s['total_ganancia_monto']),
                formatear_numero(s['total_ganancia_pct']),
            ]
            for s in secciones
        ],
        fila_total=[
            'Total del período', '', '',
            formatear_numero(totales['ingreso_total']),
            formatear_numero(totales['costo_total']),
            formatear_numero(totales['costo_con_margen_total']),
            formatear_numero(totales['ganancia_monto']),
            formatear_numero(totales['ganancia_pct']),
        ],
    )]

    for s in secciones:
        filas = []
        for fila in s['filas']:
            filas.append([
                _fecha_hora(fila['fecha_hora']),
                _texto_cantidad_fila(fila),
                f'#{fila["pedido_id"]}',
                fila['nota_entrega_codigo'] or '—',
                formatear_numero(fila['ingreso']),
                formatear_numero(fila['costo']) + (MARCA_ESTIMADO if fila['costo_estimado'] else ''),
                formatear_numero(fila['costo_con_margen']) + (
                    MARCA_ESTIMADO if fila['margen_estimado'] or fila['costo_estimado'] else ''
                ),
                formatear_numero(fila['ganancia_monto']),
                formatear_numero(fila['ganancia_pct']),
            ])
        fila_total = [
            'Total', _texto_cantidad_total(s), '', '',
            formatear_numero(s['total_ingreso']),
            formatear_numero(s['total_costo']),
            formatear_numero(s['total_costo_con_margen']),
            formatear_numero(s['total_ganancia_monto']),
            formatear_numero(s['total_ganancia_pct']),
        ]
        bloques = [filas[i:i + FILAS_POR_BLOQUE] for i in range(0, len(filas), FILAS_POR_BLOQUE)] or [[]]
        for numero, bloque in enumerate(bloques):
            es_ultimo = numero == len(bloques) - 1
            resultado.append(Seccion(
                titulo=s['nombre'] if numero == 0 else f'{s["nombre"]} (continúa)',
                detalle=(
                    f'{s["categoria"]} · {_texto_ventas(s["total_lineas"])}' if numero == 0
                    else f'{s["categoria"]} · {numero * FILAS_POR_BLOQUE + 1} a {numero * FILAS_POR_BLOQUE + len(bloque)}'
                    f' de {s["total_lineas"]}'
                ),
                columnas=COLUMNAS_PLATO,
                filas=bloque,
                fila_total=fila_total if es_ultimo else None,
            ))
    return resultado


def generar_pdf_margen_por_plato(secciones, totales, total_lineas, desde, hasta, generado_en=None):
    """
    `secciones` y `totales` tienen la forma de armar_margen_ganancia_detallado(); `total_lineas` es
    la cantidad de ventas (lineas) que suman esos totales.
    """
    rango = (
        f'Ventas del {desde.strftime("%d/%m/%Y")}' if desde == hasta
        else f'Ventas del {desde.strftime("%d/%m/%Y")} al {hasta.strftime("%d/%m/%Y")}'
    )
    estimado = any(s['tiene_costo_estimado'] or s['tiene_margen_estimado'] for s in secciones)
    subtitulo = rango + ' · Costo histórico, congelado al cobrar, más el margen de producción'
    if estimado:
        subtitulo += ' · * estimado con el costo de la receta o el margen de producción de hoy (venta anterior al costo histórico)'

    izquierda = (
        f'<b>{len(secciones)} {"plato" if len(secciones) == 1 else "platos"}</b> · {_texto_ventas(total_lineas)}'
        f' · Ganancia: <b>$ {formatear_numero(totales["ganancia_monto"])}</b>'
        f' ({formatear_numero(totales["ganancia_pct"])}%)'
    )
    derecha = (
        f'Total de ventas: <b>$ {formatear_numero(totales["ingreso_total"])}</b>'
        f' · Total del costo: <b>$ {formatear_numero(totales["costo_con_margen_total"])}</b>'
    )
    return generar_pdf_reporte(
        titulo='Margen de ganancia por plato',
        subtitulo=subtitulo,
        resumen=(izquierda, derecha),
        secciones=armar_secciones_margen_por_plato(secciones, totales),
        orientacion='horizontal',
        generado_en=generado_en or datetime.now(),
    )
