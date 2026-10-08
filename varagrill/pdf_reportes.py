"""
Reportes en PDF (ReportLab).

Este modulo no conoce Django ni la base de datos: recibe datos ya calculados y
devuelve los bytes del PDF. Asi se puede probar sin servidor y las vistas
(ver reportes_pdf_views.py) solo se ocupan de consultar y de responder.
"""
import os
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

NOMBRE_NEGOCIO = 'Varagrill'

# Mismos colores del sistema (rojo de la marca) para que el PDF se reconozca.
ROJO_MARCA = colors.HexColor('#bf1f1f')
GRIS_TEXTO = colors.HexColor('#2b2323')
GRIS_SUAVE = colors.HexColor('#6f6464')
GRIS_FILA = colors.HexColor('#f6f1f1')
GRIS_LINEA = colors.HexColor('#ddd3d3')

UNIDADES = {'g': 'Gramos', 'ml': 'Mililitros', 'unidad': 'Unidad'}

_RAIZ_PROYECTO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUTA_LOGO = os.path.join(_RAIZ_PROYECTO, 'frontend', 'public', 'assets', 'varagrill-logo.jpg')


def formatear_numero(valor, decimales_min=2, decimales_max=2):
    """1234.5 -> '1.234,50' (separadores como en el resto del sistema, es-VE)."""
    numero = Decimal(valor or 0).quantize(Decimal(1).scaleb(-decimales_max), rounding=ROUND_HALF_UP)
    texto = f'{abs(numero):,.{decimales_max}f}'
    if decimales_max > decimales_min:
        entero, _, decimales = texto.partition('.')
        decimales = decimales.rstrip('0').ljust(decimales_min, '0')
        texto = f'{entero}.{decimales}' if decimales else entero
    texto = texto.replace(',', '\0').replace('.', ',').replace('\0', '.')
    return f'-{texto}' if numero < 0 else texto


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


class _LienzoNumerado(pdf_canvas.Canvas):
    """Pie de pagina 'Pagina X de Y' (hay que conocer el total antes de dibujarlo)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._paginas = []

    def showPage(self):
        self._paginas.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._paginas)
        for estado in self._paginas:
            self.__dict__.update(estado)
            self.setFont('Helvetica', 8)
            self.setFillColor(GRIS_SUAVE)
            self.drawRightString(A4[0] - 15 * mm, 9 * mm, f'Página {self._pageNumber} de {total}')
            self.drawString(15 * mm, 9 * mm, f'{NOMBRE_NEGOCIO} · Inventario actual')
            super().showPage()
        super().save()


def generar_pdf_inventario(ingredientes, generado_en=None):
    """PDF del stock actual: Ingrediente, Unidad, Costo unitario, Valor total y Stock actual."""
    generado_en = generado_en or datetime.now()
    filas, total = armar_filas_inventario(ingredientes)

    buffer = BytesIO()
    documento = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=14 * mm, bottomMargin=16 * mm,
        title='Inventario actual', author=NOMBRE_NEGOCIO,
    )

    titulo = ParagraphStyle('titulo', fontName='Helvetica-Bold', fontSize=20, leading=24, textColor=GRIS_TEXTO)
    subtitulo = ParagraphStyle('subtitulo', fontName='Helvetica', fontSize=9.5, leading=13, textColor=GRIS_SUAVE)
    celda = ParagraphStyle('celda', fontName='Helvetica', fontSize=9, leading=11, textColor=GRIS_TEXTO)
    celda_centro = ParagraphStyle('celda_centro', parent=celda, alignment=TA_CENTER)
    celda_derecha = ParagraphStyle('celda_derecha', parent=celda, alignment=TA_RIGHT)
    encabezado = ParagraphStyle('encabezado', parent=celda, fontName='Helvetica-Bold', textColor=colors.white)
    encabezado_centro = ParagraphStyle('encabezado_centro', parent=encabezado, alignment=TA_CENTER)
    encabezado_derecha = ParagraphStyle('encabezado_derecha', parent=encabezado, alignment=TA_RIGHT)
    total_etiqueta = ParagraphStyle('total_etiqueta', parent=celda, fontName='Helvetica-Bold', fontSize=10)
    total_valor = ParagraphStyle('total_valor', parent=total_etiqueta, alignment=TA_RIGHT)

    elementos = []

    # Cabecera: logo + nombre del negocio / titulo del reporte
    texto_cabecera = [
        Paragraph('Inventario actual', titulo),
        Paragraph(f'{NOMBRE_NEGOCIO} · Generado el {generado_en.strftime("%d/%m/%Y %H:%M")}', subtitulo),
    ]
    if os.path.exists(RUTA_LOGO):
        cabecera = Table([[Image(RUTA_LOGO, width=16 * mm, height=16 * mm), texto_cabecera]], colWidths=[20 * mm, None])
        cabecera.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]))
        elementos.append(cabecera)
    else:
        elementos.extend(texto_cabecera)
    elementos.append(Spacer(1, 4 * mm))

    resumen = Table(
        [[
            Paragraph(f'<b>{len(filas)}</b> ingredientes', celda),
            Paragraph(f'Valor total del inventario: <b>$ {formatear_numero(total)}</b>', celda_derecha),
        ]],
        colWidths=[None, None],
    )
    resumen.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), GRIS_FILA),
        ('LINEBEFORE', (0, 0), (0, 0), 3, ROJO_MARCA),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 9),
        ('RIGHTPADDING', (0, 0), (-1, -1), 9),
    ]))
    elementos.append(resumen)
    elementos.append(Spacer(1, 5 * mm))

    datos = [[
        Paragraph('Ingrediente', encabezado),
        Paragraph('Unidad', encabezado_centro),
        Paragraph('Costo unitario ($)', encabezado_derecha),
        Paragraph('Valor total ($)', encabezado_derecha),
        Paragraph('Stock actual', encabezado_derecha),
    ]]
    for fila in filas:
        datos.append([
            Paragraph(fila['nombre'].replace('&', '&amp;').replace('<', '&lt;'), celda),
            Paragraph(fila['unidad'], celda_centro),
            Paragraph(formatear_numero(fila['costo_unitario'], 2, 6), celda_derecha),
            Paragraph(formatear_numero(fila['valor_total']), celda_derecha),
            Paragraph(formatear_numero(fila['stock_actual'], 0, 2), celda_derecha),
        ])
    if not filas:
        datos.append([Paragraph('No hay ingredientes registrados.', celda), '', '', '', ''])
    datos.append([
        Paragraph('Total del inventario', total_etiqueta), '', '',
        Paragraph(f'$ {formatear_numero(total)}', total_valor), '',
    ])

    ancho = A4[0] - 30 * mm
    tabla = Table(
        datos,
        colWidths=[ancho * 0.36, ancho * 0.14, ancho * 0.19, ancho * 0.16, ancho * 0.15],
        repeatRows=1,
    )
    estilo = [
        ('BACKGROUND', (0, 0), (-1, 0), ROJO_MARCA),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 7),
        ('RIGHTPADDING', (0, 0), (-1, -1), 7),
        ('LINEBELOW', (0, 1), (-1, -2), 0.4, GRIS_LINEA),
        ('LINEABOVE', (0, -1), (-1, -1), 1.2, ROJO_MARCA),
        ('SPAN', (0, -1), (2, -1)),
        ('BACKGROUND', (0, -1), (-1, -1), GRIS_FILA),
    ]
    for indice in range(2, len(datos) - 1, 2):
        estilo.append(('BACKGROUND', (0, indice), (-1, indice), GRIS_FILA))
    if not filas:
        estilo.append(('SPAN', (0, 1), (-1, 1)))
    tabla.setStyle(TableStyle(estilo))
    elementos.append(tabla)

    documento.build(elementos, canvasmaker=_LienzoNumerado)
    return buffer.getvalue()
