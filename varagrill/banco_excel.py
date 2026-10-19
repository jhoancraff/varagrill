"""
Lectura del extracto del banco (el .xlsx o .csv que se exporta de la banca en linea) para la
conciliacion bancaria por movimiento (ver conciliacion_bancaria.py y conciliacion_bancaria_views.py).

Igual que ingredientes_excel.py, el .xlsx se lee solo con la libreria estandar (zipfile +
ElementTree): openpyxl/pandas no estan entre las dependencias del proyecto.

El archivo del Banco Plaza que motivo esto trae una hoja por dia, las columnas Fecha, Referencia,
Descripcion, Tipo, Monto, Saldo y Observacion (con mayusculas/espacios distintos entre hojas, y a
veces columnas sueltas a la derecha con sumas manuales), los montos como TEXTO en formato
espanol ('-36.828,00') y las fechas como texto ('01/10/2026 23:20:08'). Por eso el lector:
  - busca la fila de encabezados en cada hoja por el NOMBRE de las columnas (sin mayusculas ni
    tildes) y descarta las columnas que no reconoce;
  - acepta montos como texto en formato espanol o como numeros de Excel;
  - acepta fechas como texto o como numero de serie de Excel;
  - da a cada linea una huella para no duplicar al volver a subir un rango que ya se cargo.
"""
import csv
import hashlib
import io
import re
import zipfile
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree as ET

from .ingredientes_excel import NS, R_NS, REL_NS, _col_letters_to_index, _load_shared_strings, _normalize_text


class ExtractoInvalido(Exception):
    """El archivo no se puede leer como extracto bancario."""


# Nombre normalizado del encabezado -> campo del movimiento.
ALIAS_COLUMNAS = {
    'fecha': 'fecha', 'fecha y hora': 'fecha', 'fecha operacion': 'fecha',
    'referencia': 'referencia', 'ref': 'referencia', 'nro referencia': 'referencia',
    'numero de referencia': 'referencia', 'nro. referencia': 'referencia',
    'descripcion': 'descripcion', 'concepto': 'descripcion', 'detalle': 'descripcion',
    'tipo': 'tipo', 'tipo de movimiento': 'tipo', 'tipo movimiento': 'tipo',
    'monto': 'monto', 'importe': 'monto',
    'saldo': 'saldo', 'saldo disponible': 'saldo',
    'observacion': 'observacion', 'observaciones': 'observacion', 'nota': 'observacion', 'notas': 'observacion',
}

FORMATOS_FECHA = ('%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M', '%d/%m/%Y', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d')
EXCEL_EPOCH = datetime(1899, 12, 30)
MAX_FILAS_BUSQUEDA_ENCABEZADO = 30


# ---------------------------------------------------------------------------
# Lectura cruda de celdas
# ---------------------------------------------------------------------------
def _celda(cell_el, shared_strings):
    """(texto, es_numero): un numero de Excel viene con punto decimal; un texto, tal cual esta escrito."""
    tipo = cell_el.get('t')
    if tipo == 's':
        valor = cell_el.find(f'{NS}v')
        if valor is None or valor.text is None:
            return '', False
        indice = int(valor.text)
        return (shared_strings[indice] if indice < len(shared_strings) else ''), False
    if tipo == 'inlineStr':
        is_el = cell_el.find(f'{NS}is')
        return (''.join(t.text or '' for t in is_el.iter(f'{NS}t')) if is_el is not None else ''), False
    valor = cell_el.find(f'{NS}v')
    texto = valor.text if valor is not None and valor.text is not None else ''
    return texto, tipo in (None, 'n') and texto != ''


def _hojas_xlsx(archive):
    """[(nombre_hoja, ruta_dentro_del_zip)] en el orden del libro."""
    try:
        with archive.open('xl/workbook.xml') as fh:
            libro = ET.parse(fh).getroot()
        with archive.open('xl/_rels/workbook.xml.rels') as fh:
            rels = ET.parse(fh).getroot()
    except KeyError:
        raise ExtractoInvalido('El archivo no tiene la estructura de un .xlsx válido.')
    destinos = {}
    for rel in rels.findall(f'{REL_NS}Relationship'):
        destino = rel.get('Target', '')
        destinos[rel.get('Id')] = destino.lstrip('/') if destino.startswith('/') else (
            destino if destino.startswith('xl/') else f'xl/{destino}'
        )
    hojas = []
    for hoja in libro.findall(f'{NS}sheets/{NS}sheet'):
        ruta = destinos.get(hoja.get(f'{R_NS}id'))
        if ruta:
            hojas.append((hoja.get('name') or ruta, ruta))
    if not hojas:
        raise ExtractoInvalido('El archivo no tiene ninguna hoja.')
    return hojas


def leer_hojas_xlsx(contenido):
    """[(nombre_hoja, [ {columna: (texto, es_numero)} por fila ])] de TODAS las hojas del libro."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(contenido))
    except zipfile.BadZipFile:
        raise ExtractoInvalido('El archivo no es un .xlsx válido.')
    resultado = []
    with archive:
        compartidos = _load_shared_strings(archive)
        for nombre, ruta in _hojas_xlsx(archive):
            try:
                with archive.open(ruta) as fh:
                    raiz = ET.parse(fh).getroot()
            except (KeyError, ET.ParseError):
                continue
            filas = []
            for fila_el in raiz.findall(f'{NS}sheetData/{NS}row'):
                celdas = {}
                for celda_el in fila_el.findall(f'{NS}c'):
                    ref = celda_el.get('r')
                    if ref:
                        celdas[_col_letters_to_index(ref)] = _celda(celda_el, compartidos)
                filas.append(celdas)
            resultado.append((nombre, filas))
    return resultado


def leer_hojas_csv(contenido):
    for codificacion in ('utf-8-sig', 'cp1252'):
        try:
            texto = contenido.decode(codificacion)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ExtractoInvalido('No se pudo leer el texto del archivo.')
    primera = texto.splitlines()[0] if texto.splitlines() else ''
    separador = max((';', ',', '\t'), key=primera.count)
    filas = [
        {indice: (valor, False) for indice, valor in enumerate(registro)}
        for registro in csv.reader(io.StringIO(texto), delimiter=separador)
    ]
    return [('csv', filas)]


# ---------------------------------------------------------------------------
# Conversion de valores
# ---------------------------------------------------------------------------
def parsear_monto(texto, es_numero=False):
    """'-36.828,00' -> Decimal('-36828.00'); '1234.5' (celda numerica) -> Decimal('1234.5'). None si no es un monto."""
    texto = str(texto or '').strip()
    if not texto:
        return None
    negativo = texto.startswith('-') or (texto.startswith('(') and texto.endswith(')'))
    limpio = re.sub(r'[^\d.,]', '', texto)
    if not limpio:
        return None
    if es_numero:
        pass  # un numero de Excel ya trae punto decimal
    elif ',' in limpio:
        limpio = limpio.replace('.', '').replace(',', '.')
    elif re.fullmatch(r'\d{1,3}(\.\d{3})+', limpio):
        limpio = limpio.replace('.', '')  # '36.828' sin decimales = miles
    try:
        valor = Decimal(limpio)
    except InvalidOperation:
        return None
    return -valor if negativo else valor


def parsear_fecha(texto, es_numero=False):
    texto = str(texto or '').strip()
    if not texto:
        return None
    if es_numero or re.fullmatch(r'\d{5}(\.\d+)?', texto):
        try:
            serie = float(texto)
        except ValueError:
            return None
        if 20000 <= serie <= 80000:
            return (EXCEL_EPOCH + timedelta(days=serie)).replace(microsecond=0)
        return None
    for formato in FORMATOS_FECHA:
        try:
            return datetime.strptime(texto, formato)
        except ValueError:
            continue
    return None


def _normalizar_encabezado(texto):
    return re.sub(r'\s+', ' ', _normalize_text(texto)).strip(' .:')


def _normalizar_descripcion(texto):
    return ' '.join(str(texto or '').upper().split())


def huella_movimiento(fecha, referencia, descripcion, tipo, monto, saldo):
    """Identifica una linea del banco: la referencia SOLA no sirve (una transferencia y su comision la comparten)."""
    base = '|'.join([
        fecha.isoformat(), str(referencia).strip(), _normalizar_descripcion(descripcion), tipo,
        str(monto), '' if saldo is None else str(saldo),
    ])
    return hashlib.sha1(base.encode('utf-8')).hexdigest()


def clasificar(descripcion, tipo):
    """Que es la linea segun la descripcion del banco (Banco Plaza) -> VGMovimientoBancario.CLASES."""
    d = _normalizar_descripcion(descripcion)
    if d.startswith(('COM ', 'TDY COM', 'DOM POS', 'COMISION')) or ' COMISION' in d:
        return 'comision'
    if d.startswith('POS '):
        return 'pos'
    if d.startswith('COMPRA '):
        return 'compra_tarjeta'
    if d.startswith(('TDY RECIB', 'PAGO MOVIL RECIB')):
        return 'pago_movil_recibido'
    if d.startswith(('TDY ENVIO', 'TDY PAGO', 'PAGO MOVIL ENV')):
        return 'pago_movil_enviado'
    if d.startswith('TRF'):
        return 'transferencia_recibida' if tipo == 'credito' else 'transferencia_enviada'
    return 'otro_credito' if tipo == 'credito' else 'otro_debito'


# ---------------------------------------------------------------------------
# Lectura del extracto
# ---------------------------------------------------------------------------
def _encabezado(filas):
    """(indice_de_fila, {campo: columna}) de la primera fila que tenga Fecha y Monto, o (None, {})."""
    for indice, celdas in enumerate(filas[:MAX_FILAS_BUSQUEDA_ENCABEZADO]):
        columnas = {}
        for columna, (texto, _) in celdas.items():
            campo = ALIAS_COLUMNAS.get(_normalizar_encabezado(texto))
            if campo and campo not in columnas:
                columnas[campo] = columna
        if 'fecha' in columnas and 'monto' in columnas:
            return indice, columnas
    return None, {}


def _texto(celdas, columnas, campo):
    columna = columnas.get(campo)
    if columna is None:
        return ''
    return str(celdas.get(columna, ('', False))[0] or '').strip()


def verificar_saldos(movimientos):
    """
    Cuantas veces la columna Saldo no encadena: cada fila debe tener otra cuyo saldo sea
    (su saldo - su movimiento con signo). La fila mas antigua no tiene anterior, asi que se
    descuenta una. Un salto suele significar que falta alguna linea en el archivo.
    """
    por_saldo = {}
    for indice, m in enumerate(movimientos):
        if m['saldo'] is not None:
            por_saldo.setdefault(m['saldo'], []).append(indice)
    sin_anterior = 0
    for indice, m in enumerate(movimientos):
        if m['saldo'] is None:
            continue
        firmado = m['monto'] if m['tipo'] == 'credito' else -m['monto']
        anteriores = [i for i in por_saldo.get(m['saldo'] - firmado, []) if i != indice]
        if not anteriores:
            sin_anterior += 1
    return max(0, sin_anterior - 1)


def parsear_extracto(contenido, nombre_archivo=''):
    """
    Lee todas las hojas del archivo. Devuelve:
      movimientos        lista de dicts (hoja, fila, fecha, referencia, descripcion, tipo, monto, saldo,
                         observacion, clase, huella), sin repetidas dentro del mismo archivo
      errores            [{hoja, fila, motivo}] de las filas que no se pudieron leer
      hojas              [{nombre, movimientos}] de las hojas que si tenian encabezados
      hojas_omitidas     nombres de hojas sin encabezados Fecha/Monto
      repetidas_en_archivo  lineas identicas dentro del mismo archivo que se descartaron
      saltos_saldo       ver verificar_saldos
      huella_archivo     sha256 del archivo
    Lanza ExtractoInvalido si no se puede leer nada.
    """
    if not contenido:
        raise ExtractoInvalido('El archivo está vacío.')
    es_xlsx = contenido[:2] == b'PK' or nombre_archivo.lower().endswith('.xlsx')
    hojas_crudas = leer_hojas_xlsx(contenido) if es_xlsx else leer_hojas_csv(contenido)

    movimientos, errores, hojas, omitidas = [], [], [], []
    vistas = set()
    repetidas = 0
    for nombre_hoja, filas in hojas_crudas:
        inicio, columnas = _encabezado(filas)
        if inicio is None:
            if any(str(v[0]).strip() for celdas in filas for v in celdas.values()):
                omitidas.append(nombre_hoja)  # tiene datos pero no es un extracto
            continue
        cantidad = 0
        for desplazamiento, celdas in enumerate(filas[inicio + 1:], start=inicio + 2):
            if not any(str(v[0]).strip() for v in celdas.values()):
                continue
            fecha_texto, fecha_num = celdas.get(columnas['fecha'], ('', False))
            monto_texto, monto_num = celdas.get(columnas['monto'], ('', False))
            if not str(fecha_texto).strip() and not str(monto_texto).strip():
                continue
            fecha = parsear_fecha(fecha_texto, fecha_num)
            monto = parsear_monto(monto_texto, monto_num)
            if fecha is None or monto is None:
                errores.append({
                    'hoja': nombre_hoja, 'fila': desplazamiento,
                    'motivo': 'La fecha no se pudo leer.' if fecha is None else 'El monto no se pudo leer.',
                })
                continue
            tipo_texto = _normalizar_encabezado(_texto(celdas, columnas, 'tipo'))
            if tipo_texto.startswith('d'):
                tipo = 'debito'
            elif tipo_texto.startswith('c'):
                tipo = 'credito'
            else:
                tipo = 'debito' if monto < 0 else 'credito'
            monto = abs(monto)
            saldo_texto, saldo_num = celdas.get(columnas.get('saldo', -1), ('', False))
            saldo = parsear_monto(saldo_texto, saldo_num)
            referencia = _texto(celdas, columnas, 'referencia')
            descripcion = _texto(celdas, columnas, 'descripcion')
            huella = huella_movimiento(fecha, referencia, descripcion, tipo, monto, saldo)
            if huella in vistas:
                repetidas += 1
                continue
            vistas.add(huella)
            movimientos.append({
                'hoja': nombre_hoja, 'fila': desplazamiento, 'fecha': fecha, 'referencia': referencia[:40],
                'descripcion': descripcion[:255], 'tipo': tipo, 'monto': monto, 'saldo': saldo,
                'observacion': _texto(celdas, columnas, 'observacion')[:255],
                'clase': clasificar(descripcion, tipo), 'huella': huella,
            })
            cantidad += 1
        hojas.append({'nombre': nombre_hoja, 'movimientos': cantidad})

    if not hojas:
        raise ExtractoInvalido(
            'No se encontraron las columnas "Fecha" y "Monto" en ninguna hoja. ¿Es el archivo de movimientos del banco?'
        )
    return {
        'movimientos': movimientos, 'errores': errores, 'hojas': hojas, 'hojas_omitidas': omitidas,
        'repetidas_en_archivo': repetidas, 'saltos_saldo': verificar_saldos(movimientos),
        'huella_archivo': hashlib.sha256(contenido).hexdigest(),
    }
