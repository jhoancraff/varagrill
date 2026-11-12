# -*- coding: utf-8 -*-
"""
Corrige compras que se costearon descontando la merma del "Peso real" del ingrediente, cuando la cantidad que se
carga es el peso sin merma (la merma, si existe, vive en la subreceta: ej. "Pork belly cocina" rinde 1000 g con
1400 g de Pork Belly).

Antes de que la pantalla de compras dejara de ajustar por merma, cada compra dividía el precio entre la cantidad
"utilizable" (cantidad x peso_real / contenido_envase). El total a pagar de la compra era el de la factura, pero el
costo de la línea y el costo del producto salían inflados (en Pork Belly, 10.50 por kilo de la factura salía a 17.50).

Qué hace, para UN ingrediente y las compras que se indiquen (sin tocar su peso real ni su stock):
  - en cada línea de esas compras, vuelve el costo unitario al de la factura (costo x peso_real / contenido_envase),
    de modo que la línea sume lo mismo que el total a pagar; el total, el saldo y los abonos NO se tocan;
  - deja el costo del ingrediente en el de la compra más reciente de las indicadas, con el precio del envase que hace
    que los reportes (precio_compra / peso_real) den ese mismo costo, y registra el cambio en el historial de costos
    como corregido y revisado.

Por defecto solo MUESTRA lo que cambiaría (simulacro): hay que pasar --aplicar para escribir. Si el ingrediente ya
no tiene merma configurada (peso_real igual al contenido del envase) no hay nada que corregir y se niega.

Uso:
    python manage.py corregir_merma_duplicada --ingrediente 230 --compras 192 207
    python manage.py corregir_merma_duplicada --ingrediente 230 --compras 192 207 --aplicar
"""
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from varagrill.compras_views import _precio_envase_de_compra
from varagrill.costos_historial import origen_costo
from varagrill.models import VGCompra, VGDetalleCompra, VGHistorialCostoIngrediente, VGIngrediente

SEIS = Decimal('0.000001')
TOLERANCIA = Decimal('0.50')
ORIGEN = 'Corrección: la merma ya está en la subreceta'


class Command(BaseCommand):
    help = 'Quita la merma del peso real que se descontó de más en las compras de un ingrediente.'

    def add_arguments(self, parser):
        parser.add_argument('--ingrediente', type=int, required=True, help='ID del ingrediente (ej. Pork Belly).')
        parser.add_argument('--compras', type=int, nargs='+', required=True, help='IDs de las compras a corregir.')
        parser.add_argument('--aplicar', action='store_true', help='Escribe los cambios. Sin esto solo muestra.')

    def handle(self, *args, **opts):
        try:
            ingrediente = VGIngrediente.objects.get(pk=opts['ingrediente'])
        except VGIngrediente.DoesNotExist:
            raise CommandError(f"No existe el ingrediente {opts['ingrediente']}.")
        if not ingrediente.contenido_envase or not ingrediente.peso_real:
            raise CommandError('El ingrediente no tiene contenido del envase y peso real: no hay merma que quitar.')
        if ingrediente.peso_real >= ingrediente.contenido_envase:
            raise CommandError('El peso real es igual al contenido del envase: no hay merma que quitar.')

        factor = ingrediente.peso_real / ingrediente.contenido_envase
        self.stdout.write(
            f'Ingrediente #{ingrediente.id} {ingrediente.nombre}: peso real {ingrediente.peso_real} de '
            f'{ingrediente.contenido_envase} (factor {factor}); costo actual {ingrediente.costo_unitario}; '
            f'precio de envase {ingrediente.precio_compra}.'
        )

        cambios = []
        for compra_id in opts['compras']:
            try:
                compra = VGCompra.objects.get(pk=compra_id)
            except VGCompra.DoesNotExist:
                raise CommandError(f'No existe la compra {compra_id}.')
            todas = list(compra.detalles.all())
            lineas = [d for d in todas if d.ingrediente_id == ingrediente.id]
            if not lineas:
                raise CommandError(f'La compra {compra_id} no tiene líneas de {ingrediente.nombre}.')
            if len(lineas) != len(todas):
                raise CommandError(f'La compra {compra_id} tiene líneas de otros ingredientes: se corrige a mano.')
            suma = sum((d.subtotal for d in todas), Decimal('0'))
            if abs(suma - compra.total) <= TOLERANCIA:
                self.stdout.write(f'  Compra #{compra.id}: sus líneas ya suman su total ({compra.total:.2f}); se omite.')
                continue
            if abs(suma * factor - compra.total) > TOLERANCIA:
                raise CommandError(
                    f'La compra {compra_id} no encaja con la merma de {factor}: las líneas suman {suma:.2f} y el total es '
                    f'{compra.total:.2f}. No se toca.'
                )
            for linea in lineas:
                nuevo = (linea.costo_unitario * factor).quantize(SEIS)
                cambios.append((compra, linea, nuevo))
                self.stdout.write(
                    f'  Compra #{compra.id} ({compra.proveedor_nombre}, factura {compra.numero_factura_proveedor}): '
                    f'{linea.cantidad} x {linea.costo_unitario} = {linea.subtotal:.2f}  ->  '
                    f'{linea.cantidad} x {nuevo} = {linea.cantidad * nuevo:.2f}   (total a pagar: {compra.total:.2f}, no cambia)'
                )

        if not cambios:
            raise CommandError('Ninguna de las compras indicadas necesita corrección.')

        compra_final, _, costo_final = max(cambios, key=lambda c: (c[0].fecha_compra, c[0].id))
        precio_envase = _precio_envase_de_compra(costo_final, ingrediente)
        self.stdout.write(
            f'Costo del ingrediente: {ingrediente.costo_unitario} -> {costo_final} (el de la compra #{compra_final.id}); '
            f'precio de envase {ingrediente.precio_compra} -> {precio_envase}; el peso real NO cambia.'
        )

        if not opts['aplicar']:
            self.stdout.write(self.style.WARNING('SIMULACRO: no se escribió nada. Repite con --aplicar para guardar.'))
            return

        with transaction.atomic():
            for _compra, linea, nuevo in cambios:
                linea.costo_unitario = nuevo
                linea.save(update_fields=['costo_unitario'])
            ingrediente = VGIngrediente.objects.select_for_update().get(pk=ingrediente.pk)
            ingrediente.costo_unitario = costo_final
            ingrediente.precio_compra = precio_envase
            with origen_costo(ORIGEN, compra=compra_final):
                ingrediente.save(update_fields=['costo_unitario', 'precio_compra', 'fecha_actualizacion'])
            VGHistorialCostoIngrediente.objects.filter(
                ingrediente=ingrediente, compra=compra_final, origen=ORIGEN,
            ).update(revisada=True, nota_revision='Corrección de merma descontada de más (la merma ya está en la subreceta)')
        self.stdout.write(self.style.SUCCESS('Listo: cambios guardados.'))
