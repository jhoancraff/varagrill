"""PDF del inventario actual: Ingrediente, Unidad, Costo unitario, Valor total y Stock actual."""
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from .base import Columna, formatear_numero, generar_pdf_tabla

UNIDADES = {'g': 'Gramos', 'ml': 'Mililitros', 'unidad': 'Unidad'}

COLUMNAS = [
    Columna('Ingrediente', 0.36),
    Columna('Unidad', 0.14, 'centro'),
    Columna('Costo unitario ($)', 0.19, 'derecha'),
    Columna('Valor total ($)', 0.16, 'derecha'),
    Columna('Stock actual', 0.15, 'derecha'),
]


def armar_filas_inventario(ingredientes):
    """
    ingredientes: iterable de dicts con nombre, unidad_medida, stock_actual y
    costo_unitario (el costo ya "efectivo", el mismo que muestra el sistema).

    Devuelve (filas, total). El valor de cada fila se redondea a 2 decimales y el
    total es la suma de esas filas ya redondeadas, para que lo impreso cuadre.
    """
    filas = []
    total = Decimal('0')
    for item in sorted(ingredientes, key=lambda i: (i['nombre'] or '').lower()):
        stock = Decimal(item['stock_actual'] or 0)
        costo = Decimal(item['costo_unitario'] or 0)
        valor = (stock * costo).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        total += valor
        filas.append({
            'nombre': item['nombre'] or '',
            'unidad': UNIDADES.get(item['unidad_medida'], item['unidad_medida'] or ''),
            'costo_unitario': costo,
            'valor_total': valor,
            'stock_actual': stock,
        })
    return filas, total


def generar_pdf_inventario(ingredientes, generado_en=None):
    filas, total = armar_filas_inventario(ingredientes)
    texto_total = f'$ {formatear_numero(total)}'
    return generar_pdf_tabla(
        titulo='Inventario actual',
        columnas=COLUMNAS,
        filas=[
            [
                fila['nombre'],
                fila['unidad'],
                formatear_numero(fila['costo_unitario'], 2, 6),
                formatear_numero(fila['valor_total']),
                formatear_numero(fila['stock_actual'], 0, 2),
            ]
            for fila in filas
        ],
        resumen=(f'<b>{len(filas)}</b> ingredientes', f'Valor total del inventario: <b>{texto_total}</b>'),
        fila_total=['Total del inventario', '', '', texto_total, ''],
        generado_en=generado_en or datetime.now(),
        mensaje_vacio='No hay ingredientes registrados.',
    )
