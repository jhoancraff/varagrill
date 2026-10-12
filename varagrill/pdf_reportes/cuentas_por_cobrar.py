"""
PDF de cuentas por cobrar: las notas de entrega que los clientes todavia deben (o ya pagaron),
agrupadas por cliente, segun los filtros de quien lo pide (estado, rango de fechas y cliente;
ver reportes_pdf_views.reporte_cuentas_por_cobrar_pdf_view).

Cada cliente es un bloque con sus notas y su total; "Sin cliente" va al final. Si hay mas de un
bloque, al final va el resumen por cliente con el total general. Los numeros son los de la
pantalla de Notas de entrega (los calcula _serialize_nota_entrega): el saldo en Bs usa la tasa
con la que se cobraria hoy esa nota, no la del dia en que se emitio.

Recibe las notas ya normalizadas por la vista (ver NOTA_EJEMPLO) y no toca la base de datos.
"""
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from .base import Columna, Seccion, formatear_numero, generar_pdf_reporte

# Una nota, tal como la entrega la vista. Los montos pueden venir como Decimal o texto.
NOTA_EJEMPLO = {
    'id': 12,
    'codigo': '00000012',
    'cliente_id': 3,             # opcional: si llega, dos clientes con el mismo nombre no se mezclan
    'cliente': 'Nombre del cliente o vacio',
    'fecha': None,               # date de emision
    'estado': 'pendiente_pago',  # 'pendiente_pago' | 'abonada_parcial' | 'pagada'
    'total': '40.00',
    'saldo': '25.00',
    'tasa': '960.0000',          # tasa con la que se cobraria hoy (None si ya esta pagada o no hay)
    'saldo_bs': '24000.00',      # None si no hay tasa
    'fecha_pago': None,          # date del ultimo pago (solo si esta pagada)
    'dias': 15,                  # dias desde la emision (solo si tiene saldo)
}

ETIQUETA_ESTADO = {'pendiente_pago': 'Pendiente', 'abonada_parcial': 'Abonada', 'pagada': 'Pagada'}
TEXTO_ESTADO = {'pendientes': 'Pendientes (incluye abonadas)', 'pagadas': 'Pagadas', 'todas': 'Pendientes y pagadas'}
SIN_CLIENTE = 'Sin cliente'

COLUMNAS_NOTAS = [
    Columna('Nota', 0.095),
    Columna('Emitida', 0.095, 'centro'),
    Columna('Días', 0.075, 'centro'),
    Columna('Estado', 0.10, 'centro'),
    Columna('Total ($)', 0.10, 'derecha'),
    Columna('Abonado ($)', 0.10, 'derecha'),
    Columna('Saldo ($)', 0.10, 'derecha'),
    Columna('Tasa (Bs/$)', 0.09, 'derecha'),
    Columna('Saldo (Bs)', 0.15, 'derecha'),
    Columna('Pagada el', 0.095, 'centro'),
]

COLUMNAS_RESUMEN = [
    Columna('Cliente', 0.36),
    Columna('Notas', 0.10, 'centro'),
    Columna('Total ($)', 0.16, 'derecha'),
    Columna('Saldo ($)', 0.16, 'derecha'),
    Columna('Saldo (Bs)', 0.22, 'derecha'),
]


def _dos_decimales(valor):
    if valor in (None, ''):
        return None
    return Decimal(str(valor)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _dia(fecha):
    return fecha.strftime('%d/%m/%Y') if fecha else '—'


def _texto_cantidad(cantidad, singular, plural):
    return f'{cantidad} {singular if cantidad == 1 else plural}'


def _numero_o_guion(valor, decimales_max=2):
    return formatear_numero(valor, 2, decimales_max) if valor is not None else '—'


def armar_bloques_clientes(notas):
    """
    Agrupa por cliente (alfabetico, "Sin cliente" al final) y calcula las filas y totales de cada
    uno. Los totales suman los montos ya redondeados a 2 decimales para que lo impreso cuadre.
    Devuelve una lista de dicts: cliente, filas, cantidad, total, abonado, saldo, saldo_bs, sin_tasa.
    """
    # Por cliente (su id, si llega) y no solo por nombre: dos clientes con el mismo nombre no se mezclan.
    por_cliente = {}
    for nota in notas:
        clave = (nota.get('cliente_id'), (nota.get('cliente') or '').strip())
        por_cliente.setdefault(clave, []).append(nota)

    def orden(clave):
        return (clave[1] == '', clave[1].lower(), clave[0] or 0)

    bloques = []
    for clave in sorted(por_cliente, key=orden):
        nombre = clave[1]
        bloque = {
            'cliente': nombre or SIN_CLIENTE, 'filas': [], 'cantidad': 0,
            'total': Decimal('0'), 'abonado': Decimal('0'), 'saldo': Decimal('0'), 'saldo_bs': Decimal('0'),
            'sin_tasa': 0,
        }
        for nota in sorted(por_cliente[clave], key=lambda n: (n['fecha'], n['id'])):
            total = _dos_decimales(nota['total']) or Decimal('0')
            saldo = _dos_decimales(nota['saldo']) or Decimal('0')
            abonado = total - saldo
            saldo_bs = _dos_decimales(nota.get('saldo_bs'))
            tasa = Decimal(str(nota['tasa'])) if nota.get('tasa') not in (None, '') else None
            bloque['cantidad'] += 1
            bloque['total'] += total
            bloque['abonado'] += abonado
            bloque['saldo'] += saldo
            if saldo_bs is not None:
                bloque['saldo_bs'] += saldo_bs
            elif saldo > 0:
                bloque['sin_tasa'] += 1
            bloque['filas'].append([
                nota['codigo'],
                _dia(nota['fecha']),
                str(nota['dias']) if nota.get('dias') is not None else '—',
                ETIQUETA_ESTADO.get(nota['estado'], nota['estado']),
                formatear_numero(total),
                formatear_numero(abonado),
                formatear_numero(saldo),
                _numero_o_guion(tasa, 4),
                _numero_o_guion(saldo_bs),
                _dia(nota.get('fecha_pago')),
            ])
        bloques.append(bloque)
    return bloques


def _texto_rango(desde, hasta):
    if desde is None and hasta is None:
        return None
    if desde and hasta:
        rango = f'del {_dia(desde)} al {_dia(hasta)}'
    elif desde:
        rango = f'desde el {_dia(desde)}'
    else:
        rango = f'hasta el {_dia(hasta)}'
    return f'{rango} (por fecha de emisión)'


def generar_pdf_cuentas_por_cobrar(notas, estado='pendientes', desde=None, hasta=None, cliente='', generado_en=None):
    bloques = armar_bloques_clientes(notas)
    cantidad = sum(b['cantidad'] for b in bloques)
    total = sum((b['total'] for b in bloques), Decimal('0'))
    abonado = sum((b['abonado'] for b in bloques), Decimal('0'))
    saldo = sum((b['saldo'] for b in bloques), Decimal('0'))
    saldo_bs = sum((b['saldo_bs'] for b in bloques), Decimal('0'))
    sin_tasa = sum(b['sin_tasa'] for b in bloques)

    subtitulo = ' · '.join(parte for parte in (
        TEXTO_ESTADO[estado],
        _texto_rango(desde, hasta),
        f'Cliente: {cliente}' if cliente else None,
    ) if parte)

    secciones = []
    for bloque in bloques:
        secciones.append(Seccion(
            titulo=bloque['cliente'],
            detalle=_texto_cantidad(bloque['cantidad'], 'nota', 'notas'),
            columnas=COLUMNAS_NOTAS,
            filas=bloque['filas'],
            fila_total=[
                f'Total {bloque["cliente"]}', '', '', '',
                formatear_numero(bloque['total']), formatear_numero(bloque['abonado']),
                formatear_numero(bloque['saldo']), '', formatear_numero(bloque['saldo_bs']), '',
            ],
        ))

    if not bloques:
        secciones.append(Seccion(
            columnas=COLUMNAS_NOTAS, filas=[], mensaje_vacio='No hay notas de entrega por cobrar con estos filtros.',
        ))
    elif len(bloques) > 1:
        secciones.append(Seccion(
            titulo='Resumen por cliente',
            columnas=COLUMNAS_RESUMEN,
            filas=[
                [b['cliente'], str(b['cantidad']), formatear_numero(b['total']), formatear_numero(b['saldo']), formatear_numero(b['saldo_bs'])]
                for b in bloques
            ],
            fila_total=['Total general', str(cantidad), formatear_numero(total), formatear_numero(saldo), formatear_numero(saldo_bs)],
        ))

    izquierda = f'<b>{_texto_cantidad(cantidad, "nota de entrega", "notas de entrega")}</b>'
    if len(bloques) > 1:
        izquierda += f' de {_texto_cantidad(len(bloques), "cliente", "clientes")}'
    if sin_tasa:
        izquierda += f' · {_texto_cantidad(sin_tasa, "nota", "notas")} sin tasa (no suma en Bs)'
    derecha = f'Por cobrar: <b>$ {formatear_numero(saldo)}</b> · <b>Bs. {formatear_numero(saldo_bs)}</b>'

    return generar_pdf_reporte(
        titulo='Cuentas por cobrar',
        subtitulo=subtitulo,
        resumen=(izquierda, derecha),
        secciones=secciones,
        orientacion='horizontal',
        generado_en=generado_en or datetime.now(),
    )
