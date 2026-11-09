"""
Comandas de cocina / parrilla / barra dibujadas como imagen (Pillow), con la misma tipografía
que la nota de entrega (ver ticket_grafico.py) pero SIN logo, pensadas para leerse de lejos:

  - rótulo negro con la estación (COCINA, PARRILLA, BARRA),
  - MESA N grande (o el tipo de pedido y el cliente cuando no hay mesa),
  - pedido, hora, cliente y mesero en letra mediana,
  - cada plato armado en una barra negra, con cantidad y nombre en negrita grande,
  - opciones (») y adicionales (+) más pequeños, y las notas con asterisco (*), sin caja.

Este módulo solo DIBUJA a partir de un diccionario simple (ver `dibujar_comanda`); quién arma ese
diccionario y cae al texto de siempre si algo falla es impresion_termica.py.

Los tamaños se afinaron para papel de 80 mm (576 puntos) y escalan en proporción para otros anchos.
"""
from .ticket_grafico import _fuente

ANCHO_DE_DISENO = 576
MARGEN = 10


def _escala(ancho):
    return ancho / ANCHO_DE_DISENO


def dibujar_comanda(datos, ancho=ANCHO_DE_DISENO):
    """
    `datos`:
      estacion          texto del rótulo negro de arriba
      titulo            línea grande ("MESA 7", "DELIVERY", "SIN MESA")
      cliente_grande    (opcional) nombre del cliente en grande, bajo el título (pedidos sin mesa)
      tipo              (opcional) texto de la barra de tipo de pedido ("DELIVERY"); vacío = no se dibuja
      pedido, hora, cliente, mesero    la fila de datos del pedido (cliente puede ir vacío)
      bloques           [{'plato': 'PLATO 2 - CARNES' | None,
                          'lineas': [{'cantidad', 'nombre', 'nota', 'opciones': [...], 'adicionales': [...]}]}]
      nota_pedido       (opcional) nota general del pedido
    Devuelve una imagen 'L' (255 = blanco) de `ancho` puntos.
    """
    from PIL import Image, ImageDraw

    esc = _escala(ancho)
    margen = max(round(MARGEN * esc), 4)

    def f(tamano, negrita=True):
        return _fuente(max(round(tamano * esc), 8), negrita)

    franjas = []

    def envolver(texto, fuente, maximo):
        lineas, actual = [], ''
        for palabra in str(texto).split(' '):
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
        return lineas

    def espacio(alto):
        franjas.append(Image.new('L', (ancho, max(round(alto * esc), 1)), 255))

    def texto(contenido, fuente, alineacion='izq', sangria=0, interlineado=6):
        lineas = envolver(contenido, fuente, ancho - 2 * margen - sangria)
        alto_linea = fuente.size + round(interlineado * esc)
        franja = Image.new('L', (ancho, alto_linea * len(lineas) + 4), 255)
        dibujo = ImageDraw.Draw(franja)
        for numero, linea in enumerate(lineas):
            largo = fuente.getlength(linea)
            if alineacion == 'centro':
                x = (ancho - largo) / 2
            else:
                x = margen + sangria
            dibujo.text((x, 2 + numero * alto_linea), linea, font=fuente, fill=0)
        franjas.append(franja)

    def barra_negra(contenido, fuente, alineacion='centro', relleno=10):
        relleno = round(relleno * esc)
        lineas = envolver(contenido, fuente, ancho - 2 * margen - 2 * relleno)
        alto_linea = fuente.size + round(4 * esc)
        alto = alto_linea * len(lineas) + 2 * relleno
        franja = Image.new('L', (ancho, alto + 8), 255)
        dibujo = ImageDraw.Draw(franja)
        dibujo.rectangle((margen, 4, ancho - margen, 4 + alto), fill=0)
        for numero, linea in enumerate(lineas):
            largo = fuente.getlength(linea)
            x = (ancho - largo) / 2 if alineacion == 'centro' else margen + 14 * esc
            dibujo.text((x, 4 + relleno - 2 + numero * alto_linea), linea, font=fuente, fill=255)
        franjas.append(franja)

    def separador(grueso=False):
        franja = Image.new('L', (ancho, 16), 255)
        dibujo = ImageDraw.Draw(franja)
        if grueso:
            dibujo.rectangle((margen, 4, ancho - margen, 9), fill=0)
        else:
            paso = max(round(14 * esc), 6)
            for x in range(margen, ancho - margen, paso):
                dibujo.rectangle((x, 7, x + paso // 2, 8), fill=0)
        franjas.append(franja)

    def linea_principal(cantidad, nombre):
        f_cantidad, f_nombre = f(40), f(34)
        ancho_cantidad = max(f_cantidad.getlength(str(cantidad)) + 14 * esc, 70 * esc)
        lineas = envolver(nombre, f_nombre, ancho - 2 * margen - ancho_cantidad)
        alto_linea = f_nombre.size + round(6 * esc)
        franja = Image.new('L', (ancho, max(alto_linea * len(lineas), f_cantidad.size + round(6 * esc)) + 6), 255)
        dibujo = ImageDraw.Draw(franja)
        dibujo.text((margen, 2), str(cantidad), font=f_cantidad, fill=0)
        for numero, linea in enumerate(lineas):
            dibujo.text((margen + ancho_cantidad, 4 + numero * alto_linea), linea, font=f_nombre, fill=0)
        franjas.append(franja)

    sangria = round(34 * esc)

    # --- cabecera ---
    espacio(4)
    barra_negra(datos['estacion'], f(46), relleno=12)
    espacio(6)
    texto(datos['titulo'], f(58), 'centro', interlineado=2)
    if datos.get('cliente_grande'):
        texto(datos['cliente_grande'], f(40), 'centro', interlineado=2)
    if datos.get('tipo'):
        barra_negra(datos['tipo'], f(34), relleno=6)
    espacio(4)
    pedido_y_hora = f"Pedido #{datos['pedido']}   ·   {datos['hora']}"
    texto(pedido_y_hora, f(28), 'centro')
    if datos.get('cliente'):
        texto(f"Cliente: {datos['cliente']}", f(26, False), 'centro', interlineado=2)
    texto(f"Mesero: {datos['mesero']}", f(26, False), 'centro', interlineado=2)
    espacio(2)
    separador(grueso=True)

    # --- cuerpo ---
    primero = True
    for bloque in datos['bloques']:
        if not primero:
            separador()
        primero = False
        if bloque.get('plato'):
            barra_negra(bloque['plato'], f(28), alineacion='izq', relleno=4)
        for linea in bloque['lineas']:
            linea_principal(linea['cantidad'], linea['nombre'])
            for opcion in linea.get('opciones', []):
                texto(f'» {opcion}', f(26, False), sangria=sangria, interlineado=4)
            for adicional in linea.get('adicionales', []):
                texto(f'+ {adicional}', f(26), sangria=sangria, interlineado=4)
            if linea.get('nota'):
                texto(f"* {linea['nota']}", f(28), sangria=sangria, interlineado=4)

    if datos.get('nota_pedido'):
        separador(grueso=True)
        texto('NOTA DEL PEDIDO', f(24), interlineado=2)
        texto(f"* {datos['nota_pedido']}", f(28), interlineado=4)

    espacio(26)

    alto_total = sum(franja.height for franja in franjas) + 2 * margen
    lienzo = Image.new('L', (ancho, alto_total), 255)
    y = margen
    for franja in franjas:
        lienzo.paste(franja, (0, y))
        y += franja.height
    return lienzo
