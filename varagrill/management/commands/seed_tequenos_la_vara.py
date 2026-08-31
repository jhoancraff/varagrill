# -*- coding: utf-8 -*-
"""
Replica en esta base de datos los ingredientes, subrecetas y la receta de "Tequeños la
vara" tal como están en el Excel de referencia (Costo_-_-este_Si_2.xlsx), para que el
costo calculado por el sistema coincida con el del Excel ($3.25).

Generado a partir de la carga que se hizo a mano en el ambiente de desarrollo para
verificar por qué producción daba $3.35 en vez de $3.25 -- el resultado de esa prueba
fue que la fórmula del sistema es correcta (da 3.2547 sin redondear, igual que el
Excel); la diferencia venía de los datos, no del cálculo.

IMPORTANTE antes de correrlo contra producción:
- Actualiza ingredientes que YA EXISTEN por nombre exacto (ver INGREDIENTES, más abajo)
  con el contenido de envase / peso real / precio de compra del Excel. Si ese ingrediente
  ya lo usa OTRA receta en este sistema, el costo mostrado de esa otra receta también va
  a cambiar -- no es un efecto secundario raro, es intencional (mismo ingrediente, mismo
  costo real), pero conviene saberlo antes de correrlo en un ambiente con datos reales.
- Es seguro correrlo más de una vez: usa get_or_create para ingredientes/subrecetas/
  producto, y siempre deja los componentes de cada subreceta y la receta del producto en
  el mismo estado final (los recrea desde cero cada vez), así que repetir la carga no
  duplica nada.
- Usa --dry-run para ver exactamente qué se crearía/actualizaría sin guardar nada.

Uso:
    python manage.py seed_tequenos_la_vara --dry-run   # solo mostrar, no guardar
    python manage.py seed_tequenos_la_vara             # aplicar de verdad
"""
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from varagrill.models import (
    VGCategoriaProducto,
    VGIngrediente,
    VGPreparacion,
    VGProducto,
    VGRecetaPreparacion,
    VGRecetaProducto,
)

D = Decimal

# (nombre, unidad, contenido_envase, peso_real, precio_compra)
# Los primeros 9 ya suelen existir con otro nombre/precio en un sistema en uso real
# (Sal, Ajo, Agua...) -- este comando los busca por nombre exacto y, si existen, PISA
# su contenido de envase / peso real / precio de compra con el valor del Excel. Si no
# existen, los crea. El resto son ingredientes nuevos específicos de esta receta.
INGREDIENTES = [
    ('Sal', 'g', D('1000'), D('1000'), D('0.73')),
    ('Ajo', 'g', D('1000'), D('850'), D('5')),
    ('Agua', 'ml', D('18000'), D('18000'), D('1')),
    ('Mayonesa', 'g', D('910'), D('910'), D('8.59')),
    ('Vinagre', 'ml', D('500'), D('500'), D('1.5')),
    ('Pimienta negra molida', 'g', D('1000'), D('1000'), D('28.4')),
    ('Mostaza', 'g', D('4000'), D('4000'), D('9.89')),
    ('Azucar', 'g', D('1000'), D('1000'), D('1.4')),
    ('Limon', 'g', D('1000'), D('1000'), D('3.9')),
    ('cebolla blanca', 'g', D('1000'), D('800'), D('1.29')),
    ('perejil', 'g', D('1000'), D('600'), D('1.55331762756621')),
    ('pimenton', 'g', D('1000'), D('750'), D('1.55331762756621')),
    ('alcaparras', 'g', D('200'), D('200'), D('2.2')),
    ('pepino', 'g', D('1000'), D('650'), D('1.03554508504414')),
    ('paprika dulce', 'g', D('1000'), D('1000'), D('28')),
    ('oregano molido', 'g', D('1000'), D('1000'), D('9.52')),
    ('Aceite', 'ml', D('18000'), D('18000'), D('57')),
    ('papelon', 'g', D('500'), D('100'), D('1.65')),
    ('Guayabita', 'g', D('100'), D('100'), D('12')),
    ('Clavo molido', 'g', D('1000'), D('1000'), D('35.99')),
    ('Canela molida', 'g', D('1000'), D('1000'), D('24.49')),
    ('Pimienta entera', 'g', D('1000'), D('1000'), D('42')),
    ('semillas de mostaza', 'g', D('1000'), D('1000'), D('22.23')),
    ('Tequeños con queso y tocineta', 'unidad', D('24'), D('24'), D('11')),
]

# (nombre_ingrediente, cantidad_requerida)
PEPINO_AGRIDULCE = [
    ('Agua', '655'), ('Sal', '50'), ('Azucar', '300'), ('pepino', '655'),
    ('Vinagre', '150'), ('Pimienta entera', '5'), ('semillas de mostaza', '5'),
]
PAPELON_ESPECIADO = [
    ('papelon', '480'), ('Agua', '500'), ('Guayabita', '5'), ('Clavo molido', '3.5'), ('Canela molida', '6'),
]
# Tártara de la Casa también lleva 125 g de Pepino Agridulce (subreceta), agregado aparte.
TARTARA_DE_LA_CASA = [
    ('Mayonesa', '2730'), ('alcaparras', '215'), ('cebolla blanca', '300'), ('perejil', '160'),
    ('Limon', '60'), ('Pimienta negra molida', '5'), ('Sal', '15'), ('pimenton', '155'),
    ('paprika dulce', '10'), ('oregano molido', '10'), ('Ajo', '100'), ('Aceite', '100'),
    ('Mostaza', '50'), ('Vinagre', '100'),
]


class Command(BaseCommand):
    help = "Crea/actualiza ingredientes, subrecetas y la receta de 'Tequeños la vara' para que coincida con el Excel de referencia."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Muestra qué se crearía/actualizaría sin guardar nada en la base de datos.',
        )
        parser.add_argument(
            '--categoria', default='Pasapalos',
            help="Categoría del producto final (se crea si no existe). Por defecto: 'Pasapalos'.",
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        if dry_run:
            self.stdout.write(self.style.WARNING('--dry-run: no se va a guardar nada, solo se muestra qué pasaría.\n'))

        try:
            with transaction.atomic():
                self._crear_ingredientes()
                pepino_agridulce = self._crear_subreceta('Pepino Agridulce', D('1415'), 'g', PEPINO_AGRIDULCE)
                papelon_especiado = self._crear_subreceta('Papelón Especiado', D('1000'), 'g', PAPELON_ESPECIADO)
                tartara = self._crear_subreceta(
                    'Tártara de la Casa', D('3955'), 'g', TARTARA_DE_LA_CASA,
                    sub_preparaciones=[(pepino_agridulce, '125')],
                )
                self._crear_producto(options['categoria'], papelon_especiado, tartara)

                if dry_run:
                    raise _DryRunAbort()
        except _DryRunAbort:
            pass

        if dry_run:
            self.stdout.write(self.style.WARNING('\n--dry-run: nada se guardó.'))
        else:
            self.stdout.write(self.style.SUCCESS(
                "\nListo: ingredientes, subrecetas ('Papelón Especiado', 'Pepino Agridulce', "
                "'Tártara de la Casa') y el producto 'Tequeños la vara' quedaron creados/actualizados."
            ))

    def _buscar_unico(self, queryset, nombre, tipo_label, detalle_extra=None):
        """
        Reemplaza a get_or_create(nombre=...) con un chequeo explícito de duplicados: si
        ya existe MÁS DE UNO con ese nombre exacto (posible en una base de datos real que
        no tuvo la disciplina de este script desde el principio -- fue justo lo que pasó
        en producción con 'Tequeños la vara'), corta la ejecución con un mensaje claro en
        vez de dejar que Django reviente con MultipleObjectsReturned a mitad de la carga.
        Devuelve (instancia_o_None, cantidad_encontrada).
        """
        encontrados = list(queryset.filter(nombre=nombre))
        if len(encontrados) > 1:
            self.stdout.write(self.style.ERROR(f"\nHay {len(encontrados)} {tipo_label} llamados exactamente '{nombre}':"))
            for obj in encontrados:
                extra = f' {detalle_extra(obj)}' if detalle_extra else ''
                self.stdout.write(f'  id={obj.id}{extra}')
            raise CommandError(
                f"No se puede seguir: hay {len(encontrados)} {tipo_label} duplicados llamados '{nombre}'. "
                "Borrá o renombrá el que sobra a mano (revisando primero si alguno ya lo usa otra receta/pedido) "
                "y volvé a correr el comando."
            )
        return (encontrados[0], 1) if encontrados else (None, 0)

    def _crear_ingredientes(self):
        self.stdout.write('Ingredientes:')
        for nombre, unidad, contenido_envase, peso_real, precio_compra in INGREDIENTES:
            costo_unitario = (precio_compra / peso_real).quantize(D('0.000001'))
            ingrediente, encontrado = self._buscar_unico(
                VGIngrediente.objects, nombre, 'ingredientes',
                detalle_extra=lambda i: f"costo_unitario={i.costo_unitario} contenido_envase={i.contenido_envase} peso_real={i.peso_real}",
            )
            if not encontrado:
                ingrediente = VGIngrediente.objects.create(
                    nombre=nombre, unidad_medida=unidad, stock_actual=0, stock_minimo=0,
                    contenido_envase=contenido_envase, peso_real=peso_real,
                    precio_compra=precio_compra, costo_unitario=costo_unitario,
                )
                self.stdout.write(f'  creado:      {nombre:35s} costo_unitario = {costo_unitario}')
            else:
                costo_anterior = ingrediente.costo_unitario
                ingrediente.contenido_envase = contenido_envase
                ingrediente.peso_real = peso_real
                ingrediente.precio_compra = precio_compra
                ingrediente.costo_unitario = costo_unitario
                ingrediente.save(update_fields=['contenido_envase', 'peso_real', 'precio_compra', 'costo_unitario'])
                self.stdout.write(f'  actualizado: {nombre:35s} costo_unitario {costo_anterior} -> {costo_unitario}')

    def _crear_subreceta(self, nombre, rendimiento_cantidad, rendimiento_unidad, componentes, sub_preparaciones=None):
        preparacion, encontrada = self._buscar_unico(
            VGPreparacion.objects, nombre, 'subrecetas (VGPreparacion)',
            detalle_extra=lambda p: f"rinde={p.rendimiento_cantidad} {p.rendimiento_unidad} es_adicional={p.es_adicional}",
        )
        if not encontrada:
            preparacion = VGPreparacion.objects.create(
                nombre=nombre, rendimiento_cantidad=rendimiento_cantidad,
                rendimiento_unidad=rendimiento_unidad, es_adicional=False,
            )
        else:
            preparacion.rendimiento_cantidad = rendimiento_cantidad
            preparacion.rendimiento_unidad = rendimiento_unidad
            preparacion.save(update_fields=['rendimiento_cantidad', 'rendimiento_unidad'])

        VGRecetaPreparacion.objects.filter(preparacion=preparacion).delete()
        for nombre_ingrediente, cantidad in componentes:
            ingrediente, encontrado = self._buscar_unico(VGIngrediente.objects, nombre_ingrediente, 'ingredientes')
            if not encontrado:
                raise CommandError(
                    f"'{nombre}' necesita el ingrediente '{nombre_ingrediente}', pero no se encontró -- "
                    "revisá que la sección de ingredientes se haya corrido antes (no debería pasar si corrés "
                    "el comando completo, sin recortar)."
                )
            VGRecetaPreparacion.objects.create(preparacion=preparacion, ingrediente=ingrediente, cantidad_requerida=D(cantidad))
        for sub_preparacion, cantidad in (sub_preparaciones or []):
            VGRecetaPreparacion.objects.create(
                preparacion=preparacion, sub_preparacion=sub_preparacion, cantidad_requerida=D(cantidad),
            )

        total_componentes = len(componentes) + len(sub_preparaciones or [])
        self.stdout.write(f"{'creada' if not encontrada else 'actualizada'}: {nombre} ({total_componentes} componentes, rinde {rendimiento_cantidad} {rendimiento_unidad})")
        return preparacion

    def _crear_producto(self, nombre_categoria, papelon_especiado, tartara):
        categoria, _ = self._buscar_unico(VGCategoriaProducto.objects, nombre_categoria, 'categorías')
        if categoria is None:
            categoria = VGCategoriaProducto.objects.create(nombre=nombre_categoria)

        tequeno_ingrediente, encontrado = self._buscar_unico(VGIngrediente.objects, 'Tequeños con queso y tocineta', 'ingredientes')
        if not encontrado:
            raise CommandError("No se encontró el ingrediente 'Tequeños con queso y tocineta' -- no debería pasar si corrés el comando completo.")

        producto, encontrado = self._buscar_unico(
            VGProducto.objects, 'Tequeños la vara', 'productos',
            detalle_extra=lambda p: f"categoria={p.categoria} precio_venta={p.precio_venta} disponible={p.disponible} creado={p.fecha_creacion}",
        )
        if not encontrado:
            producto = VGProducto.objects.create(
                nombre='Tequeños la vara', categoria=categoria, precio_venta=D('0.00'), disponible=False,
            )

        VGRecetaProducto.objects.filter(producto=producto).delete()
        VGRecetaProducto.objects.create(producto=producto, ingrediente=tequeno_ingrediente, cantidad_requerida=D('6'))
        VGRecetaProducto.objects.create(producto=producto, preparacion=papelon_especiado, cantidad_requerida=D('30'))
        VGRecetaProducto.objects.create(producto=producto, preparacion=tartara, cantidad_requerida=D('30'))

        self.stdout.write(
            f"{'creado' if not encontrado else 'actualizado'}: producto 'Tequeños la vara' (id={producto.id}, "
            f"categoría='{categoria.nombre}', disponible={producto.disponible}, precio_venta={producto.precio_venta})"
        )
        if not encontrado:
            self.stdout.write(self.style.WARNING(
                "  -> Se creó con disponible=False y precio_venta=0.00 a propósito (no había precio de venta "
                "en el Excel). Ponle el precio real y márcalo disponible desde el panel cuando quieras venderlo."
            ))


class _DryRunAbort(Exception):
    """Señal interna para deshacer la transacción en modo --dry-run sin marcarlo como error real."""
