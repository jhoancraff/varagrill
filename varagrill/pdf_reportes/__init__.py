"""
Reportes en PDF.

  base.py        lo comun a todos (estilos, formato de numeros, cabecera, tabla, pie).
  inventario.py  un reporte: solo sus columnas y como convertir sus datos en filas.

Para un reporte nuevo: crear <reporte>.py con sus Columna y una funcion que llame a
generar_pdf_tabla(), exportarla aqui, y agregar su vista en reportes_pdf_views.py.
"""
from .base import Columna, Seccion, escapar, formatear_numero, generar_pdf_reporte, generar_pdf_tabla
from .gastos import armar_bloques_gastos, generar_pdf_gastos
from .inventario import armar_filas_inventario, generar_pdf_inventario

__all__ = [
    'Columna', 'Seccion', 'escapar', 'formatear_numero', 'generar_pdf_reporte', 'generar_pdf_tabla',
    'armar_filas_inventario', 'generar_pdf_inventario', 'armar_bloques_gastos', 'generar_pdf_gastos',
]
