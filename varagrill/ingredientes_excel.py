"""
Parseo de archivos .xlsx subidos por el analista para cargar/actualizar ingredientes en
lote (ver AnalystIngredientsImportPage.jsx / admin_ingredientes_import_view). Solo usa la
librería estándar (zipfile + xml.etree.ElementTree) para no depender de openpyxl/pandas,
que no están entre las dependencias del proyecto (no hay requirements.txt que las declare).

Localiza la fila de encabezados buscando el texto "Ingrediente" en cualquier celda (sin
importar en qué fila/columna esté ni mayúsculas/tildes), para que sirva tanto con la
plantilla provista (frontend/public/plantilla_ingredientes.xlsx) como con variantes
razonables que un analista pueda producir.
"""
import re
import zipfile
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree as ET

NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
REL_NS = '{http://schemas.openxmlformats.org/package/2006/relationships}'
R_NS = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'

ACCENTS_TABLE = str.maketrans('áéíóúñÁÉÍÓÚÑ', 'aeiounAEIOUN')

UNIDAD_ALIASES = {
    'kg': 'kg', 'kilo': 'kg', 'kilos': 'kg', 'kilogramo': 'kg', 'kilogramos': 'kg',
    'g': 'g', 'gr': 'g', 'gramo': 'g', 'gramos': 'g',
    'l': 'l', 'lt': 'l', 'litro': 'l', 'litros': 'l',
    'ml': 'ml', 'mililitro': 'ml', 'mililitros': 'ml',
    'unidad': 'unidad', 'unidades': 'unidad', 'und': 'unidad', 'u': 'unidad',
}

HEADER_ALIASES = {
    'ingrediente': 'nombre',
    'nombre': 'nombre',
    'unidad': 'unidad',
    'cantidad': 'cantidad',
    'total': 'cantidad',
    'stock': 'cantidad',
    'stock actual': 'cantidad',
}


class InvalidExcelError(Exception):
    """El archivo no es un .xlsx válido o no tiene la estructura esperada."""


def _normalize_text(text):
    return (text or '').strip().lower().translate(ACCENTS_TABLE)


def _col_letters_to_index(cell_ref):
    """'C12' -> 2 (índice de columna base 0)."""
    match = re.match(r'[A-Z]+', cell_ref)
    if not match:
        return 0
    index = 0
    for char in match.group():
        index = index * 26 + (ord(char) - ord('A') + 1)
    return index - 1


def _load_shared_strings(archive):
    if 'xl/sharedStrings.xml' not in archive.namelist():
        return []
    with archive.open('xl/sharedStrings.xml') as fh:
        root = ET.parse(fh).getroot()
    strings = []
    for si in root.findall(f'{NS}si'):
        text = ''.join(t.text or '' for t in si.iter(f'{NS}t'))
        strings.append(text)
    return strings


def _first_sheet_path(archive):
    try:
        with archive.open('xl/workbook.xml') as fh:
            workbook_root = ET.parse(fh).getroot()
    except KeyError:
        raise InvalidExcelError('El archivo no tiene la estructura de un .xlsx válido.')

    sheet_el = workbook_root.find(f'{NS}sheets/{NS}sheet')
    if sheet_el is None:
        raise InvalidExcelError('El archivo no tiene ninguna hoja.')
    r_id = sheet_el.get(f'{R_NS}id')

    try:
        with archive.open('xl/_rels/workbook.xml.rels') as fh:
            rels_root = ET.parse(fh).getroot()
    except KeyError:
        raise InvalidExcelError('El archivo no tiene la estructura de un .xlsx válido.')

    for rel in rels_root.findall(f'{REL_NS}Relationship'):
        if rel.get('Id') == r_id:
            target = rel.get('Target', '')
            return target if target.startswith('xl/') else f'xl/{target}'

    raise InvalidExcelError('No se pudo ubicar la hoja dentro del archivo.')


def _cell_value(cell_el, shared_strings):
    cell_type = cell_el.get('t')
    if cell_type == 's':
        value_el = cell_el.find(f'{NS}v')
        if value_el is None or value_el.text is None:
            return ''
        index = int(value_el.text)
        return shared_strings[index] if index < len(shared_strings) else ''
    if cell_type == 'inlineStr':
        is_el = cell_el.find(f'{NS}is')
        if is_el is None:
            return ''
        return ''.join(t.text or '' for t in is_el.iter(f'{NS}t'))
    value_el = cell_el.find(f'{NS}v')
    if value_el is None or value_el.text is None:
        return ''
    return value_el.text


def parse_ingredientes_workbook(file_obj):
    """
    Lee la primera hoja de un .xlsx y devuelve una lista de filas de datos:
    [{'fila': int, 'nombre': str, 'unidad': str, 'cantidad': str}, ...]
    (valores tal cual vienen del archivo, sin normalizar todavía).

    Lanza InvalidExcelError si el archivo no es un zip válido, no tiene hoja legible,
    o no encuentra una columna "Ingrediente"/"Nombre" en ninguna fila.
    """
    try:
        archive = zipfile.ZipFile(file_obj)
    except zipfile.BadZipFile:
        raise InvalidExcelError('El archivo no es un .xlsx válido.')

    with archive:
        shared_strings = _load_shared_strings(archive)
        sheet_path = _first_sheet_path(archive)
        try:
            with archive.open(sheet_path) as fh:
                sheet_root = ET.parse(fh).getroot()
        except KeyError:
            raise InvalidExcelError('No se pudo leer la hoja del archivo.')

        rows = []
        for row_el in sheet_root.findall(f'{NS}sheetData/{NS}row'):
            row_cells = {}
            for cell_el in row_el.findall(f'{NS}c'):
                ref = cell_el.get('r')
                if not ref:
                    continue
                row_cells[_col_letters_to_index(ref)] = _cell_value(cell_el, shared_strings)
            rows.append(row_cells)

        header_row_index = None
        columns = {}
        for idx, row_cells in enumerate(rows):
            row_columns = {}
            for col, text in row_cells.items():
                field = HEADER_ALIASES.get(_normalize_text(text))
                if field and field not in row_columns:
                    row_columns[field] = col
            if 'nombre' in row_columns:
                header_row_index = idx
                columns = row_columns
                break

        if header_row_index is None:
            raise InvalidExcelError(
                'No se encontró la columna "Ingrediente" en el archivo. Usa la plantilla provista.'
            )

        parsed_rows = []
        for idx in range(header_row_index + 1, len(rows)):
            row_cells = rows[idx]
            nombre = str(row_cells.get(columns['nombre'], '') or '').strip()
            if not nombre:
                continue
            unidad = str(row_cells.get(columns.get('unidad', -1), '') or '').strip()
            cantidad_raw = row_cells.get(columns.get('cantidad', -1), '')
            parsed_rows.append({
                'fila': idx + 1,
                'nombre': nombre,
                'unidad': unidad,
                'cantidad': str(cantidad_raw or '').strip(),
            })

        return parsed_rows


def normalize_unidad(raw_unidad):
    """Devuelve la unidad normalizada a una choice de VGIngrediente.UNIDADES, o None si no se reconoce."""
    return UNIDAD_ALIASES.get(_normalize_text(raw_unidad))


def parse_cantidad(raw_cantidad):
    """
    Devuelve (Decimal, None) o (None, mensaje_error). Vacío se trata como 0 (fila a
    ignorar), igual que un 0 explícito — así una celda de cantidad en blanco o en "0"
    en la plantilla se comporta idéntico: ese ingrediente no se toca en esta carga.
    """
    text = str(raw_cantidad or '').strip().replace(',', '.')
    if not text:
        return Decimal('0'), None
    try:
        return Decimal(text), None
    except InvalidOperation:
        return None, f'"{raw_cantidad}" no es una cantidad numérica válida.'