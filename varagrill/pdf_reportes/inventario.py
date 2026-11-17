"""
PDF del inventario actual: Ingrediente, Unidad, Costo unitario, Valor total y Stock actual.

Con una categoria elegida imprime solo esa categoria (una tabla). Sin categoria elegida y con
ingredientes clasificados, imprime un bloque por categoria con su subtotal y el total general
al final; si nada esta clasificado todavia, la tabla unica de siempre.
"""
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from .base import Columna, Seccion, formatear_numero, generar_pdf_reporte, generar_pdf_tabla

SIN_CATEGORIA = 'Sin categoría'

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
            'categoria': (item.get('categoria_nombre') or '').strip(),
        })
    return filas, total


def _texto_fila(fila):
    return [
        fila['nombre'],
        fila['unidad'],
        formatear_numero(fila['costo_unitario'], 2, 6),
        formatear_numero(fila['valor_total']),
        formatear_numero(fila['stock_actual'], 0, 2),
    ]


def generar_pdf_inventario(ingredientes, generado_en=None, categoria_nombre=None):
    """
    ingredientes: ver armar_filas_inventario (cada uno puede traer 'categoria_nombre').
    categoria_nombre: si se indica, el PDF es de esa categoria (el filtrado ya lo hizo la vista).
    """
    filas, total = armar_filas_inventario(ingredientes)
    texto_total = f'$ {formatear_numero(total)}'
    generado_en = generado_en or datetime.now()
    hay_categorias = any(fila['categoria'] for fila in filas)

    if categoria_nombre is not None or not hay_categorias:
        return generar_pdf_tabla(
            titulo='Inventario actual',
            subtitulo=f'Categoría: {categoria_nombre}' if categoria_nombre is not None else None,
            columnas=COLUMNAS,
            filas=[_texto_fila(fila) for fila in filas],
            resumen=(f'<b>{len(filas)}</b> ingredientes', f'Valor total del inventario: <b>{texto_total}</b>'),
            fila_total=['Total del inventario', '', '', texto_total, ''],
            generado_en=generado_en,
            mensaje_vacio=(
                'No hay ingredientes registrados.' if categoria_nombre is None
                else 'No hay ingredientes en esta categoría.'
            ),
        )

    por_categoria = {}
    for fila in filas:
        por_categoria.setdefault(fila['categoria'] or SIN_CATEGORIA, []).append(fila)
    orden = sorted(por_categoria, key=lambda nombre: (nombre == SIN_CATEGORIA, nombre.lower()))
    secciones = []
    for nombre in orden:
        grupo = por_categoria[nombre]
        subtotal = sum((fila['valor_total'] for fila in grupo), Decimal('0'))
        secciones.append(Seccion(
            titulo=nombre,
            detalle=f'{len(grupo)} ingrediente{"s" if len(grupo) != 1 else ""}',
            columnas=COLUMNAS,
            filas=[_texto_fila(fila) for fila in grupo],
            fila_total=[f'Subtotal {nombre}', '', '', f'$ {formatear_numero(subtotal)}', ''],
        ))
    return generar_pdf_reporte(
        titulo='Inventario actual',
        subtitulo='Por categoría',
        secciones=secciones,
        resumen=(
            f'<b>{len(filas)}</b> ingredientes en <b>{len(secciones)}</b> categorías',
            f'Valor total del inventario: <b>{texto_total}</b>',
        ),
        generado_en=generado_en,
    )
