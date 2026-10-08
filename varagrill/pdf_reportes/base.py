"""
Base comun de los reportes en PDF (ReportLab).

Aqui vive todo lo que NO depende del reporte: colores, estilos, formato de numeros,
cabecera con logo, franja de resumen, tabla con encabezado repetido y pie
"Pagina X de Y". Un reporte nuevo (gastos, notas de entrega...) no dibuja nada:
solo describe sus columnas, convierte sus datos en filas de texto y llama a
generar_pdf_tabla(). Ver inventario.py como ejemplo.

Este modulo no conoce Django ni la base de datos: recibe datos ya calculados y
devuelve los bytes del PDF, asi se prueba sin servidor.
"""
import os
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

NOMBRE_NEGOCIO = 'Varagrill'

# Mismos colores del sistema (rojo de la marca) para que todos los PDF se reconozcan.
ROJO_MARCA = colors.HexColor('#bf1f1f')
GRIS_TEXTO = colors.HexColor('#2b2323')
GRIS_SUAVE = colors.HexColor('#6f6464')
GRIS_FILA = colors.HexColor('#f6f1f1')
GRIS_LINEA = colors.HexColor('#ddd3d3')

MARGEN_LATERAL = 15 * mm

# base.py -> pdf_reportes/ -> varagrill/ -> raiz del proyecto
_RAIZ_PROYECTO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RUTA_LOGO = os.path.join(_RAIZ_PROYECTO, 'frontend', 'public', 'assets', 'varagrill-logo.jpg')

_ALINEACIONES = {'izquierda': TA_LEFT, 'centro': TA_CENTER, 'derecha': TA_RIGHT}


@dataclass(frozen=True)
class Columna:
    """Una columna de la tabla. `ancho` es la fraccion del ancho util (todas deben sumar 1)."""
    etiqueta: str
    ancho: float
    alinear: str = 'izquierda'


def formatear_numero(valor, decimales_min=2, decimales_max=2):
    """1234.5 -> '1.234,50' (separadores como en el resto del sistema, es-VE).

    Con decimales_max > decimales_min se quitan los ceros sobrantes hasta el minimo:
    un costo de 0.58 sale '0,58' y uno de 0.001429 sale '0,001429'.
    """
    numero = Decimal(valor or 0).quantize(Decimal(1).scaleb(-decimales_max), rounding=ROUND_HALF_UP)
    texto = f'{abs(numero):,.{decimales_max}f}'
    if decimales_max > decimales_min:
        entero, _, decimales = texto.partition('.')
        decimales = decimales.rstrip('0').ljust(decimales_min, '0')
        texto = f'{entero}.{decimales}' if decimales else entero
    texto = texto.replace(',', '\0').replace('.', ',').replace('\0', '.')
    return f'-{texto}' if numero < 0 else texto


class _LienzoNumerado(pdf_canvas.Canvas):
    """Pie de pagina 'Pagina X de Y' (hay que conocer el total antes de dibujarlo)."""

    def __init__(self, *args, texto_pie='', **kwargs):
        super().__init__(*args, **kwargs)
        self._paginas = []
        self.texto_pie = texto_pie

    def showPage(self):
        self._paginas.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._paginas)
        for estado in self._paginas:
            self.__dict__.update(estado)
            ancho_pagina = self._pagesize[0]
            self.setFont('Helvetica', 8)
            self.setFillColor(GRIS_SUAVE)
            self.drawRightString(ancho_pagina - MARGEN_LATERAL, 9 * mm, f'Página {self._pageNumber} de {total}')
            self.drawString(MARGEN_LATERAL, 9 * mm, self.texto_pie)
            super().showPage()
        super().save()


def _fabrica_lienzo(texto_pie):
    def fabrica(*args, **kwargs):
        return _LienzoNumerado(*args, texto_pie=texto_pie, **kwargs)
    return fabrica


def _estilos():
    celda = ParagraphStyle('celda', fontName='Helvetica', fontSize=9, leading=11, textColor=GRIS_TEXTO)
    estilos = {
        'titulo': ParagraphStyle('titulo', fontName='Helvetica-Bold', fontSize=20, leading=24, textColor=GRIS_TEXTO),
        'subtitulo': ParagraphStyle('subtitulo', fontName='Helvetica', fontSize=9.5, leading=13, textColor=GRIS_SUAVE),
        'resumen_derecha': ParagraphStyle('resumen_derecha', parent=celda, alignment=TA_RIGHT),
        'celda': celda,
    }
    for nombre, alineacion in _ALINEACIONES.items():
        estilos[f'celda_{nombre}'] = ParagraphStyle(f'celda_{nombre}', parent=celda, alignment=alineacion)
        estilos[f'encabezado_{nombre}'] = ParagraphStyle(
            f'encabezado_{nombre}', parent=celda, fontName='Helvetica-Bold', textColor=colors.white, alignment=alineacion,
        )
        estilos[f'total_{nombre}'] = ParagraphStyle(
            f'total_{nombre}', parent=celda, fontName='Helvetica-Bold', fontSize=10, alignment=alineacion,
        )
    return estilos


def generar_pdf_tabla(
    *, titulo, columnas, filas, subtitulo=None, resumen=None, fila_total=None,
    orientacion='vertical', generado_en=None, mensaje_vacio='No hay datos para mostrar.',
):
    """
    Arma un PDF con cabecera, franja de resumen opcional y una tabla. Devuelve los bytes.

    titulo, subtitulo  texto plano (ej. 'Reporte de gastos', 'Del 01/10/2026 al 08/10/2026').
    columnas           lista de Columna (etiqueta, ancho, alinear).
    filas              lista de filas; cada fila es una lista de TEXTOS ya formateados, uno por
                       columna (usar formatear_numero para los numeros). Se escapan solos.
    resumen            (texto_izquierda, texto_derecha) para la franja bajo el titulo. Aceptan
                       <b>negrita</b>; si llevan datos del usuario, pasarlos por escapar().
    fila_total         lista con un texto por columna para la ultima fila. La primera celda se
                       extiende hasta la primera celda con texto (las vacias del medio se unen).
    orientacion        'vertical' (A4) u 'horizontal' (A4 apaisado, para tablas anchas).
    """
    if orientacion not in ('vertical', 'horizontal'):
        raise ValueError("orientacion debe ser 'vertical' u 'horizontal'.")
    if abs(sum(c.ancho for c in columnas) - 1) > 0.01:
        raise ValueError('Los anchos de las columnas deben sumar 1.')
    if any(c.alinear not in _ALINEACIONES for c in columnas):
        raise ValueError(f'alinear debe ser uno de: {", ".join(_ALINEACIONES)}.')
    for fila in list(filas) + ([fila_total] if fila_total else []):
        if len(fila) != len(columnas):
            raise ValueError('Cada fila debe tener un texto por columna.')

    generado_en = generado_en or datetime.now()
    tamano = landscape(A4) if orientacion == 'horizontal' else A4
    ancho_util = tamano[0] - 2 * MARGEN_LATERAL
    estilos = _estilos()

    buffer = BytesIO()
    documento = SimpleDocTemplate(
        buffer, pagesize=tamano, leftMargin=MARGEN_LATERAL, rightMargin=MARGEN_LATERAL, topMargin=14 * mm, bottomMargin=16 * mm,
        title=titulo, author=NOMBRE_NEGOCIO,
    )
    elementos = []

    # Cabecera: logo + titulo del reporte
    partes_subtitulo = [NOMBRE_NEGOCIO]
    if subtitulo:
        partes_subtitulo.append(escape(subtitulo))
    partes_subtitulo.append(f'Generado el {generado_en.strftime("%d/%m/%Y %H:%M")}')
    texto_cabecera = [
        Paragraph(escape(titulo), estilos['titulo']),
        Paragraph(' · '.join(partes_subtitulo), estilos['subtitulo']),
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

    if resumen:
        franja = Table(
            [[Paragraph(resumen[0], estilos['celda']), Paragraph(resumen[1], estilos['resumen_derecha'])]],
            colWidths=[None, None],
        )
        franja.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), GRIS_FILA),
            ('LINEBEFORE', (0, 0), (0, 0), 3, ROJO_MARCA),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 9),
            ('RIGHTPADDING', (0, 0), (-1, -1), 9),
        ]))
        elementos.append(franja)
        elementos.append(Spacer(1, 5 * mm))

    # Tabla: cada celda es un Paragraph para que el texto largo baje de linea en vez de salirse.
    datos = [[Paragraph(escape(c.etiqueta), estilos[f'encabezado_{c.alinear}']) for c in columnas]]
    for fila in filas:
        datos.append([Paragraph(escape(str(texto)), estilos[f'celda_{c.alinear}']) for texto, c in zip(fila, columnas)])
    if not filas:
        datos.append([Paragraph(escape(mensaje_vacio), estilos['celda'])] + [''] * (len(columnas) - 1))
    ultima_fila_datos = len(datos) - 1

    estilo = [
        ('BACKGROUND', (0, 0), (-1, 0), ROJO_MARCA),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 7),
        ('RIGHTPADDING', (0, 0), (-1, -1), 7),
        ('LINEBELOW', (0, 1), (-1, ultima_fila_datos), 0.4, GRIS_LINEA),
    ]
    for indice in range(2, ultima_fila_datos + 1, 2):
        estilo.append(('BACKGROUND', (0, indice), (-1, indice), GRIS_FILA))
    if not filas:
        estilo.append(('SPAN', (0, 1), (-1, 1)))

    if fila_total:
        datos.append([Paragraph(escape(str(texto)), estilos[f'total_{c.alinear}']) for texto, c in zip(fila_total, columnas)])
        primera_con_texto = next((i for i, texto in enumerate(fila_total) if i > 0 and str(texto).strip()), 1)
        estilo += [
            ('LINEABOVE', (0, -1), (-1, -1), 1.2, ROJO_MARCA),
            ('BACKGROUND', (0, -1), (-1, -1), GRIS_FILA),
        ]
        if primera_con_texto > 1:
            estilo.append(('SPAN', (0, -1), (primera_con_texto - 1, -1)))

    tabla = Table(datos, colWidths=[ancho_util * c.ancho for c in columnas], repeatRows=1)
    tabla.setStyle(TableStyle(estilo))
    elementos.append(tabla)

    documento.build(elementos, canvasmaker=_fabrica_lienzo(f'{NOMBRE_NEGOCIO} · {titulo}'))
    return buffer.getvalue()


def escapar(texto):
    """Para meter datos del usuario dentro de los textos del resumen (que aceptan marcas <b>)."""
    return escape(str(texto))
