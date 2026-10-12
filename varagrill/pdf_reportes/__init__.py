"""
Reportes en PDF.

  base.py        lo comun a todos (estilos, formato de numeros, cabecera, tabla, pie).
  inventario.py  un reporte: solo sus columnas y como convertir sus datos en filas.

Para un reporte nuevo: crear <reporte>.py con sus Columna y una funcion que llame a
generar_pdf_tabla(), exportarla aqui, y agregar su vista en reportes_pdf_views.py.
"""
from .base import Columna, Seccion, escapar, formatear_numero, generar_pdf_reporte, generar_pdf_tabla
from .cuentas_por_cobrar import armar_bloques_clientes, generar_pdf_cuentas_por_cobrar
from .cuentas_por_pagar import armar_bloques_cuentas, generar_pdf_cuentas_por_pagar
from .facturado import armar_dias_facturado, generar_pdf_facturado
from .gastos import armar_bloques_gastos, generar_pdf_gastos
from .inventario import armar_filas_inventario, generar_pdf_inventario
from .margen_por_plato import armar_secciones_margen_por_plato, generar_pdf_margen_por_plato

__all__ = [
    'Columna', 'Seccion', 'escapar', 'formatear_numero', 'generar_pdf_reporte', 'generar_pdf_tabla',
    'armar_filas_inventario', 'generar_pdf_inventario', 'armar_bloques_gastos', 'generar_pdf_gastos',
    'armar_dias_facturado', 'generar_pdf_facturado', 'armar_bloques_cuentas', 'generar_pdf_cuentas_por_pagar',
    'armar_bloques_clientes', 'generar_pdf_cuentas_por_cobrar',
    'armar_secciones_margen_por_plato', 'generar_pdf_margen_por_plato',
]
