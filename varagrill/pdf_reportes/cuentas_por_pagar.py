"""
PDF de cuentas por pagar: lotes (compras a proveedores) y gastos, segun los filtros de quien lo pide
(tipo, estado y rango de fechas; ver reportes_pdf_views.reporte_cuentas_por_pagar_pdf_view).

Cada tipo es un bloque con su tabla y su total (Total y Saldo en $ y en Bs); si salen los dos tipos,
al final va un resumen. Los numeros son los de la pantalla de Cuentas por pagar (los calcula
_serialize_compra / _serialize_gasto), asi que el PDF no contradice lo que se ve.

Recibe las cuentas ya normalizadas por la vista (ver CUENTA_EJEMPLO) y no toca la base de datos.
"""
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from .base import Columna, Seccion, formatear_numero, generar_pdf_reporte

# Una cuenta, tal como la entrega la vista. Los montos pueden venir como Decimal o texto.
CUENTA_EJEMPLO = {
    'tipo': 'compra',            # 'compra' (lote) o 'gasto'
    'id': 12,
    'titulo': 'Proveedor o categoria',
    'detalle': 'Factura 0045 / descripcion del gasto',
    'fecha': None,               # date: fecha de la factura (lote) o del gasto
    'estado': 'pendiente',       # 'pendiente' | 'abonada_parcial' | 'pagada'
    'total': '100.00', 'total_bs': '90000.00',
    'saldo': '40.00', 'saldo_bs': '36000.00',   # los *_bs pueden ser None (sin tasa)
    'fecha_pago': None,          # date en que se termino de pagar (solo si esta pagada)
}

ETIQUETA_ESTADO = {'pendiente': 'Pendiente', 'abonada_parcial': 'Abonada', 'pagada': 'Pagada'}
TIPOS = {
    'compra': {'plural': 'Lotes', 'singular': 'lote', 'plural_min': 'lotes', 'titulo': 'Proveedor', 'detalle': 'Factura'},
    'gasto': {'plural': 'Gastos', 'singular': 'gasto', 'plural_min': 'gastos', 'titulo': 'Categoría', 'detalle': 'Descripción'},
}
TEXTO_ESTADO = {'pendientes': 'Pendientes', 'pagadas': 'Pagadas', 'todos': 'Pendientes y pagadas'}
TEXTO_TIPO = {'todos': 'Lotes y gastos', 'compra': 'Solo lotes', 'gasto': 'Solo gastos'}

COLUMNAS_RESUMEN = [
    Columna('Tipo', 0.34),
    Columna('Cuentas', 0.14, 'centro'),
    Columna('Total ($)', 0.14, 'derecha'),
    Columna('Saldo ($)', 0.14, 'derecha'),
    Columna('Saldo (Bs)', 0.24, 'derecha'),
]


def _columnas(tipo):
    textos = TIPOS[tipo]
    return [
        Columna('Nº', 0.05),
        Columna(textos['titulo'], 0.125),
        Columna(textos['detalle'], 0.195),
        Columna('Fecha', 0.085, 'centro'),
        Columna('Estado', 0.08, 'centro'),
        Columna('Total ($)', 0.085, 'derecha'),
        Columna('Total (Bs)', 0.105, 'derecha'),
        Columna('Saldo ($)', 0.085, 'derecha'),
        Columna('Saldo (Bs)', 0.105, 'derecha'),
        Columna('Pagada el', 0.085, 'centro'),
    ]


def _dos_decimales(valor):
    if valor in (None, ''):
        return None
    return Decimal(str(valor)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _dia(fecha):
    return fecha.strftime('%d/%m/%Y') if fecha else '—'


def _texto_cantidad(cantidad, singular, plural):
    return f'{cantidad} {singular if cantidad == 1 else plural}'


def _numero_o_guion(valor):
    return formatear_numero(valor) if valor is not None else '—'


def armar_bloques_cuentas(cuentas):
    """
    Agrupa por tipo (lotes primero, luego gastos) y calcula filas y totales de cada uno. Los
    totales suman los montos ya redondeados a 2 decimales para que lo impreso cuadre.
    Devuelve una lista de dicts: tipo, filas, cantidad, total, total_bs, saldo, saldo_bs, sin_tasa.
    """
    bloques = []
    for tipo in ('compra', 'gasto'):
        del_tipo = sorted(
            (c for c in cuentas if c['tipo'] == tipo),
            key=lambda c: (c['fecha'] is None, c['fecha'], c['id']),
        )
        if not del_tipo:
            continue
        bloque = {
            'tipo': tipo, 'filas': [], 'cantidad': len(del_tipo),
            'total': Decimal('0'), 'total_bs': Decimal('0'), 'saldo': Decimal('0'), 'saldo_bs': Decimal('0'),
            'sin_tasa': 0,
        }
        for cuenta in del_tipo:
            total = _dos_decimales(cuenta['total']) or Decimal('0')
            saldo = _dos_decimales(cuenta['saldo']) or Decimal('0')
            total_bs = _dos_decimales(cuenta.get('total_bs'))
            saldo_bs = _dos_decimales(cuenta.get('saldo_bs'))
            bloque['total'] += total
            bloque['saldo'] += saldo
            if total_bs is None or saldo_bs is None:
                bloque['sin_tasa'] += 1
            if total_bs is not None:
                bloque['total_bs'] += total_bs
            if saldo_bs is not None:
                bloque['saldo_bs'] += saldo_bs
            bloque['filas'].append([
                f'#{cuenta["id"]}',
                cuenta['titulo'] or '—',
                cuenta['detalle'] or '—',
                _dia(cuenta['fecha']),
                ETIQUETA_ESTADO.get(cuenta['estado'], cuenta['estado']),
                formatear_numero(total),
                _numero_o_guion(total_bs),
                formatear_numero(saldo),
                _numero_o_guion(saldo_bs),
                _dia(cuenta.get('fecha_pago')),
            ])
        bloques.append(bloque)
    return bloques


def _texto_rango(desde, hasta, estado):
    if desde is None and hasta is None:
        return None
    if desde and hasta:
        rango = f'del {_dia(desde)} al {_dia(hasta)}'
    elif desde:
        rango = f'desde el {_dia(desde)}'
    else:
        rango = f'hasta el {_dia(hasta)}'
    criterio = {
        'pendientes': 'por fecha de la cuenta',
        'pagadas': 'por fecha de pago',
        'todos': 'pendientes por fecha de la cuenta, pagadas por fecha de pago',
    }[estado]
    return f'{rango} ({criterio})'


def generar_pdf_cuentas_por_pagar(cuentas, tipo='todos', estado='pendientes', desde=None, hasta=None, generado_en=None):
    bloques = armar_bloques_cuentas(cuentas)
    cantidad = sum(b['cantidad'] for b in bloques)
    total = sum((b['total'] for b in bloques), Decimal('0'))
    saldo = sum((b['saldo'] for b in bloques), Decimal('0'))
    saldo_bs = sum((b['saldo_bs'] for b in bloques), Decimal('0'))
    sin_tasa = sum(b['sin_tasa'] for b in bloques)

    subtitulo = ' · '.join(
        parte for parte in (TEXTO_TIPO[tipo], TEXTO_ESTADO[estado], _texto_rango(desde, hasta, estado)) if parte
    )

    secciones = []
    for bloque in bloques:
        textos = TIPOS[bloque['tipo']]
        secciones.append(Seccion(
            titulo=textos['plural'],
            detalle=_texto_cantidad(bloque['cantidad'], textos['singular'], textos['plural_min']),
            columnas=_columnas(bloque['tipo']),
            filas=bloque['filas'],
            fila_total=[
                f'Total {textos["plural_min"]}', '', '', '', '',
                formatear_numero(bloque['total']), formatear_numero(bloque['total_bs']),
                formatear_numero(bloque['saldo']), formatear_numero(bloque['saldo_bs']), '',
            ],
        ))

    if not bloques:
        secciones.append(Seccion(
            columnas=_columnas('compra'), filas=[], mensaje_vacio='No hay cuentas por pagar con estos filtros.',
        ))
    elif len(bloques) > 1:
        secciones.append(Seccion(
            titulo='Resumen',
            columnas=COLUMNAS_RESUMEN,
            filas=[
                [
                    TIPOS[b['tipo']]['plural'], str(b['cantidad']), formatear_numero(b['total']),
                    formatear_numero(b['saldo']), formatear_numero(b['saldo_bs']),
                ]
                for b in bloques
            ],
            fila_total=['Total general', str(cantidad), formatear_numero(total), formatear_numero(saldo), formatear_numero(saldo_bs)],
        ))

    izquierda = f'<b>{_texto_cantidad(cantidad, "cuenta", "cuentas")}</b>'
    if len(bloques) > 1:
        partes = ', '.join(_texto_cantidad(b['cantidad'], TIPOS[b['tipo']]['singular'], TIPOS[b['tipo']]['plural_min']) for b in bloques)
        izquierda += f' ({partes})'
    if sin_tasa:
        izquierda += f' · {_texto_cantidad(sin_tasa, "cuenta", "cuentas")} sin tasa (no suma en Bs)'
    derecha = f'Total: <b>$ {formatear_numero(total)}</b> · Saldo pendiente: <b>$ {formatear_numero(saldo)}</b>'

    return generar_pdf_reporte(
        titulo='Cuentas por pagar',
        subtitulo=subtitulo,
        resumen=(izquierda, derecha),
        secciones=secciones,
        orientacion='horizontal',
        generado_en=generado_en or datetime.now(),
    )
