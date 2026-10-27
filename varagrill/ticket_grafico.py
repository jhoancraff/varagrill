"""
Tickets de la impresora de CAJA con logo y tipografía propia.

Las impresoras térmicas solo traen fuentes de matriz de puntos de fábrica; para
que el recibo salga con el logo de Varagrill y una letra como la de un recibo de
caja "de verdad" (sans-serif, etiquetas en negrita, montos alineados a la
derecha) el ticket se dibuja como imagen con Pillow y se manda como raster
ESC/POS (GS v 0). Solo la impresora de caja usa esto: las comandas de cocina
(impresion_termica.py) siguen en texto.

Un ticket se describe UNA sola vez como lista de operaciones (`Ticket`) y se
puede materializar de dos formas:
  - to_text_bytes(): ESC/POS de texto, de 32 columnas — el de siempre; es el
    respaldo si Pillow o las fuentes no están disponibles, y lo que leen las
    pruebas,
  - to_raster_bytes(): el ticket gráfico.
`to_bytes()` intenta el gráfico y cae al de texto si algo falla: un problema de
fuentes nunca debe dejar a caja sin recibo.

El ancho en puntos es configurable (settings.TICKET_CAJA_ANCHO_PUNTOS): 384 para
papel de 58 mm (por defecto) o 576 para 80 mm.
"""
import logging
import os
import textwrap
from functools import lru_cache

from django.conf import settings

from .impresion_termica import (
    ALIGN_CENTER,
    ALIGN_LEFT,
    BOLD_OFF,
    BOLD_ON,
    CUT,
    ESC_POS_WCP1252,
    FEED,
    GS,
    INIT,
    KANJI_OFF,
    LINE_WIDTH,
    _text,
)

logger = logging.getLogger(__name__)

ANCHO_POR_DEFECTO = 576  # papel de 80 mm
ANCHO_DE_DISENO = 384  # ancho para el que se afinaron los tamaños de letra
MARGEN = 6
UMBRAL_NEGRO = 150
FILAS_POR_FRANJA = 192  # GS v 0 en franjas: algunas impresoras tienen buffer corto

TAMANO_TEXTO = 22
TAMANO_PEQUENO = 19
TAMANO_TITULO = 28
TAMANO_TOTAL = 28

LOGO_PATH = os.path.join(os.path.dirname(__file__), 'assets', 'varagrill-logo-ticket.png')

_FUENTES_REGULAR = (
    r'C:\Windows\Fonts\arial.ttf',
    '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
    '/usr/share/fonts/liberation/LiberationSans-Regular.ttf',
    '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
)
_FUENTES_NEGRITA = (
    r'C:\Windows\Fonts\arialbd.ttf',
    '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
    '/usr/share/fonts/liberation/LiberationSans-Bold.ttf',
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
)


def escala_ticket(ancho):
    """
    Los tamaños de letra se afinaron para 384 puntos (58 mm). En papel más ancho
    crecen un poco —no proporcionalmente— para que el ticket no quede con letra
    diminuta ni con renglones de 60 caracteres.
    """
    return 1 + (ancho / ANCHO_DE_DISENO - 1) * 0.4


def ancho_ticket():
    ancho = int(getattr(settings, 'TICKET_CAJA_ANCHO_PUNTOS', ANCHO_POR_DEFECTO) or ANCHO_POR_DEFECTO)
    return max(8, ancho - ancho % 8)


def _ruta_fuente(negrita):
    for ruta in (_FUENTES_NEGRITA if negrita else _FUENTES_REGULAR):
        if os.path.exists(ruta):
            return ruta
    # reportlab ya es dependencia del proyecto y trae Bitstream Vera.
    import reportlab
    return os.path.join(os.path.dirname(reportlab.__file__), 'fonts', 'VeraBd.ttf' if negrita else 'Vera.ttf')


@lru_cache(maxsize=16)
def _fuente(tamano, negrita):
    from PIL import ImageFont
    return ImageFont.truetype(_ruta_fuente(negrita), tamano)


def logo_alto_base():
    """Alto (en puntos) del logo en un ticket de 384 de ancho."""
    return 84


@lru_cache(maxsize=1)
def _logo():
    from PIL import Image
    return Image.open(LOGO_PATH).convert('L')


class Ticket:
    """Lista de operaciones de un ticket; ver el docstring del módulo."""

    def __init__(self):
        self.ops = []

    # --- construcción ---------------------------------------------------
    def logo(self):
        """El logo de Varagrill (solo en el ticket gráfico; en texto no imprime nada)."""
        self.ops.append(('logo',))

    def centro(self, texto, negrita=False, grande=False):
        self.ops.append(('centro', str(texto), negrita, grande))

    def izq(self, texto, negrita=False):
        self.ops.append(('izq', str(texto), negrita))

    def campo(self, etiqueta, valor):
        """'Etiqueta: valor' — la etiqueta va en negrita en el ticket gráfico."""
        self.ops.append(('campo', str(etiqueta), str(valor)))

    def fila(self, izquierda, derecha, negrita=False, grande=False):
        """Texto a la izquierda y monto a la derecha."""
        self.ops.append(('fila', str(izquierda), str(derecha), negrita, grande))

    def item(self, texto, monto=None, bs=None):
        """
        Renglón de un producto: nombre a la izquierda y su monto a la derecha. Con `bs`, el monto en
        bolívares va debajo del monto en dólares, alineado a la derecha y más pequeño.
        """
        self.ops.append(('item', str(texto), None if monto is None else str(monto), None if bs is None else str(bs)))

    def detalle(self, texto):
        """Línea secundaria de un renglón (nota, opción, adicional), más pequeña."""
        self.ops.append(('detalle', str(texto)))

    def total_dual(self, usd, bs=None):
        self.ops.append(('total_dual', str(usd), None if bs is None else str(bs)))

    def separador(self, caracter='-'):
        self.ops.append(('sep', caracter))

    # --- ESC/POS de texto (32 columnas) --------------------------------
    def texto_plano(self):
        """El ticket como texto, una línea por renglón (para pruebas y respaldo)."""
        return [linea for linea, _negrita, _centro in self._lineas_texto()]

    def _lineas_texto(self):
        lineas = []

        def agregar(texto, negrita=False, centro=False, envolver=False):
            partes = (textwrap.wrap(texto, LINE_WIDTH) or ['']) if envolver else [texto]
            for parte in partes:
                lineas.append((parte, negrita, centro))

        for op in self.ops:
            tipo = op[0]
            if tipo == 'logo':
                continue
            if tipo == 'centro':
                agregar(op[1], negrita=op[2], centro=True, envolver=True)
            elif tipo == 'izq':
                agregar(op[1], negrita=op[2], envolver=True)
            elif tipo == 'campo':
                agregar(f'{op[1]} {op[2]}', envolver=True)
            elif tipo == 'fila':
                agregar(f'{op[1]} {op[2]}'.strip(), negrita=op[3], envolver=True)
            elif tipo == 'item':
                agregar(op[1], envolver=True)
                if op[2] is not None:
                    agregar(f'  {op[2]}')
                if op[3] is not None:
                    agregar(f'  {op[3]}')
            elif tipo == 'detalle':
                agregar(op[1], envolver=True)
            elif tipo == 'total_dual':
                agregar(f'TOTAL: {op[1]}', negrita=True)
                if op[2] is not None:
                    agregar(f'       {op[2]}', negrita=True)
            elif tipo == 'sep':
                agregar(op[1] * LINE_WIDTH)
        return lineas

    def to_text_bytes(self):
        out = bytearray()
        out += INIT + KANJI_OFF + ESC_POS_WCP1252
        for texto, negrita, centro in self._lineas_texto():
            out += ALIGN_CENTER if centro else ALIGN_LEFT
            if negrita:
                out += BOLD_ON
            out += _text(texto) + FEED
            if negrita:
                out += BOLD_OFF
        out += ALIGN_LEFT
        out += FEED + FEED + FEED + FEED
        out += CUT
        return bytes(out)

    # --- ticket gráfico -------------------------------------------------
    def to_image(self):
        """Dibuja el ticket completo: imagen 'L' (255 = blanco) de ancho ancho_ticket()."""
        from PIL import Image

        ancho = ancho_ticket()
        franjas = [self._franja(op, ancho) for op in self.ops]
        franjas = [franja for franja in franjas if franja is not None]
        alto = sum(franja.height for franja in franjas) + 2 * MARGEN
        lienzo = Image.new('L', (ancho, alto), 255)
        y = MARGEN
        for franja in franjas:
            lienzo.paste(franja, (0, y))
            y += franja.height
        return lienzo

    def to_raster_bytes(self):
        from PIL import Image

        imagen = self.to_image()
        ancho, alto = imagen.size
        # Umbral duro (texto limpio): lo oscuro pasa a 255 y en el modo '1' de
        # Pillow un pixel 255 es el bit 1, que en ESC/POS es un punto negro.
        bits = imagen.point(lambda valor: 255 if valor < UMBRAL_NEGRO else 0).convert('1', dither=Image.Dither.NONE)
        ancho_bytes = ancho // 8
        out = bytearray()
        out += INIT + ALIGN_CENTER
        for inicio in range(0, alto, FILAS_POR_FRANJA):
            fin = min(inicio + FILAS_POR_FRANJA, alto)
            franja = bits.crop((0, inicio, ancho, fin)).tobytes()
            filas = fin - inicio
            out += GS + b'v0' + b'\x00'
            out += ancho_bytes.to_bytes(2, 'little') + filas.to_bytes(2, 'little')
            out += franja
        out += ALIGN_LEFT
        out += FEED + FEED + FEED + FEED
        out += CUT
        return bytes(out)

    def to_bytes(self):
        """Gráfico si se puede; si algo falla (Pillow, fuentes) cae al texto de siempre."""
        if getattr(settings, 'TICKET_CAJA_GRAFICO', True):
            try:
                return self.to_raster_bytes()
            except Exception:
                logger.exception('No se pudo dibujar el ticket gráfico; se imprime en texto.')
        return self.to_text_bytes()

    # --- dibujo de cada operación ---------------------------------------
    def _franja(self, op, ancho):
        from PIL import Image, ImageDraw

        tipo = op[0]
        util = ancho - 2 * MARGEN

        def envolver(texto, fuente, maximo):
            """Parte `texto` en líneas que quepan en `maximo` puntos."""
            lineas = []
            for parrafo in str(texto).split('\n'):
                actual = ''
                for palabra in parrafo.split(' '):
                    prueba = palabra if not actual else f'{actual} {palabra}'
                    if fuente.getlength(prueba) <= maximo or not actual:
                        actual = prueba
                    else:
                        lineas.append(actual)
                        actual = palabra
                    # una palabra sola más ancha que la línea se corta por caracteres
                    while fuente.getlength(actual) > maximo and len(actual) > 1:
                        corte = len(actual) - 1
                        while corte > 1 and fuente.getlength(actual[:corte]) > maximo:
                            corte -= 1
                        lineas.append(actual[:corte])
                        actual = actual[corte:]
                lineas.append(actual)
            return lineas or ['']

        def franja_texto(lineas, fuente, alineacion='izq', interlineado=4):
            alto_linea = fuente.size + interlineado
            franja = Image.new('L', (ancho, alto_linea * len(lineas) + 2), 255)
            dibujo = ImageDraw.Draw(franja)
            y = 1
            for linea in lineas:
                largo = fuente.getlength(linea)
                if alineacion == 'centro':
                    x = (ancho - largo) / 2
                elif alineacion == 'der':
                    x = ancho - MARGEN - largo
                else:
                    x = MARGEN
                dibujo.text((x, y), linea, font=fuente, fill=0)
                y += alto_linea
            return franja

        def franja_fila(izquierda, derecha, fuente, interlineado=4):
            """Izquierda ajustada al espacio que deja el monto; el monto siempre en la primera línea."""
            ancho_der = fuente.getlength(derecha) if derecha else 0
            reservado = ancho_der + 10 if derecha else 0
            lineas = envolver(izquierda, fuente, max(util - reservado, util // 3))
            alto_linea = fuente.size + interlineado
            franja = Image.new('L', (ancho, alto_linea * len(lineas) + 2), 255)
            dibujo = ImageDraw.Draw(franja)
            for numero, linea in enumerate(lineas):
                dibujo.text((MARGEN, 1 + numero * alto_linea), linea, font=fuente, fill=0)
            if derecha:
                dibujo.text((ancho - MARGEN - ancho_der, 1), derecha, font=fuente, fill=0)
            return franja

        esc = escala_ticket(ancho)
        t_texto = round(TAMANO_TEXTO * esc)
        t_pequeno = round(TAMANO_PEQUENO * esc)
        t_titulo = round(TAMANO_TITULO * esc)
        normal = _fuente(t_texto, False)
        negrita = _fuente(t_texto, True)
        pequena = _fuente(t_pequeno, False)

        if tipo == 'logo':
            logo = _logo()
            alto_logo = round(logo_alto_base() * esc)
            logo = logo.resize((round(logo.width * alto_logo / logo.height), alto_logo), Image.LANCZOS)
            logo = logo.point(lambda valor: 0 if valor < 160 else 255)
            franja = Image.new('L', (ancho, logo.height + 8), 255)
            franja.paste(logo, ((ancho - logo.width) // 2, 4))
            return franja
        if tipo == 'centro':
            _, texto, es_negrita, grande = op
            fuente = _fuente(t_titulo if grande else t_texto, es_negrita or grande)
            return franja_texto(envolver(texto, fuente, util), fuente, 'centro', interlineado=6 if grande else 4)
        if tipo == 'izq':
            return franja_texto(envolver(op[1], negrita if op[2] else normal, util), negrita if op[2] else normal)
        if tipo == 'campo':
            _, etiqueta, valor = op
            ancho_etiqueta = negrita.getlength(etiqueta + ' ')
            alto_linea = t_texto + 4
            lineas = envolver(valor, normal, max(util - ancho_etiqueta, util // 3))
            franja = Image.new('L', (ancho, alto_linea * len(lineas) + 2), 255)
            dibujo = ImageDraw.Draw(franja)
            dibujo.text((MARGEN, 1), etiqueta, font=negrita, fill=0)
            for numero, linea in enumerate(lineas):
                dibujo.text((MARGEN + ancho_etiqueta, 1 + numero * alto_linea), linea, font=normal, fill=0)
            return franja
        if tipo == 'fila':
            _, izquierda, derecha, es_negrita, grande = op
            fuente = _fuente(t_titulo if grande else t_texto, es_negrita or grande)
            return franja_fila(izquierda, derecha, fuente)
        if tipo == 'item':
            franja = franja_fila(op[1], op[2] or '', normal)
            if op[3] is None:
                return franja
            segunda = franja_texto([op[3]], pequena, 'der', interlineado=2)
            conjunto = Image.new('L', (ancho, franja.height + segunda.height), 255)
            conjunto.paste(franja, (0, 0))
            conjunto.paste(segunda, (0, franja.height))
            return conjunto
        if tipo == 'detalle':
            return self._detalle(op[1], pequena, ancho, util)
        if tipo == 'total_dual':
            _, usd, bs = op
            fuente = _fuente(t_titulo, True)
            primera = franja_fila('TOTAL:', usd, fuente, interlineado=6)
            if bs is None:
                return primera
            segunda = franja_texto([bs], fuente, 'der', interlineado=6)
            conjunto = Image.new('L', (ancho, primera.height + segunda.height), 255)
            conjunto.paste(primera, (0, 0))
            conjunto.paste(segunda, (0, primera.height))
            return conjunto
        if tipo == 'sep':
            franja = Image.new('L', (ancho, 12), 255)
            dibujo = ImageDraw.Draw(franja)
            if op[1] == '=':
                dibujo.rectangle((MARGEN, 3, ancho - MARGEN, 4), fill=0)
                dibujo.rectangle((MARGEN, 7, ancho - MARGEN, 8), fill=0)
            else:
                dibujo.rectangle((MARGEN, 5, ancho - MARGEN, 6), fill=0)
            return franja
        return None

    @staticmethod
    def _detalle(texto, fuente, ancho, util):
        from PIL import Image, ImageDraw

        sangria = 14
        lineas = []
        actual = ''
        for palabra in str(texto).strip().split(' '):
            prueba = palabra if not actual else f'{actual} {palabra}'
            if fuente.getlength(prueba) <= util - sangria or not actual:
                actual = prueba
            else:
                lineas.append(actual)
                actual = palabra
        lineas.append(actual)
        alto_linea = fuente.size + 3
        franja = Image.new('L', (ancho, alto_linea * len(lineas) + 2), 255)
        dibujo = ImageDraw.Draw(franja)
        for numero, linea in enumerate(lineas):
            dibujo.text((MARGEN + sangria, 1 + numero * alto_linea), linea, font=fuente, fill=0)
        return franja
