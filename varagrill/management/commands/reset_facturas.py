# -*- coding: utf-8 -*-
"""
Borra TODAS las facturas (y sus pre-facturas, si no se excluyen) y reinicia los
correlativos fiscales para que la próxima factura vuelva a salir con el número 1.

Borra, en este orden (el orden importa: VGPago.factura usa on_delete=PROTECT, así
que hay que quitar los pagos antes de poder borrar la factura que referencian):
  1. VGPago ligados a una factura (abonos/cobros de facturas — no toca pagos
     directos de pedido, esos no dependen de ninguna factura).
  2. VGFactura — arrastra en cascada VGFacturaLinea y VGOrdenCobro.
  3. VGPreFactura — arrastra en cascada VGPreFacturaLinea (solo si no se pasa
     --mantener-prefacturas).
  4. Resetea VGCorrelativoFiscal: 'FACTURA' y 'CONTROL' a 0 siempre; 'PREFACTURA'
     también a 0 salvo que se use --mantener-prefacturas.

Los VGPedido que estaban ligados a esas facturas NO se tocan ni se borran — solo
pierden la marca de "ya facturado" (la relación M2M se limpia sola al borrar la
factura), igual que sus VGPago directos (pedido=..., factura=None), que tampoco
se tocan.

Es IRREVERSIBLE — no hay soft-delete ni backup automático. Si esto es una base de
datos con facturas fiscales reales ya reportadas al SENIAT/lo que corresponda,
reiniciar el correlativo después de borrarlas puede pisar esos números si algún
registro externo (papel, otro sistema) todavía los referencia — pensado para
limpiar datos de prueba, no para "renumerar" una operación fiscal real en curso.

Uso:
    python manage.py reset_facturas --dry-run                       # solo mostrar cuántos se borrarían
    python manage.py reset_facturas --confirmar                     # borrar todo, incluidas las pre-facturas
    python manage.py reset_facturas --confirmar --mantener-prefacturas  # dejar las pre-facturas y su correlativo intactos
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from varagrill.models import (
    VGCorrelativoFiscal,
    VGFactura,
    VGFacturaLinea,
    VGOrdenCobro,
    VGPago,
    VGPreFactura,
    VGPreFacturaLinea,
)


class Command(BaseCommand):
    help = "Borra todas las facturas (y opcionalmente las pre-facturas) y reinicia los correlativos fiscales a 0."

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirmar", action="store_true",
            help="Ejecuta el borrado de verdad. Sin este flag, el comando no toca nada (salvo --dry-run).",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Solo muestra cuántos registros se borrarían de cada tabla, sin borrar ni resetear nada.",
        )
        parser.add_argument(
            "--mantener-prefacturas", action="store_true",
            help="No borra VGPreFactura ni resetea el correlativo PREFACTURA — solo toca FACTURA/CONTROL.",
        )

    def handle(self, *args, **options):
        incluir_prefacturas = not options["mantener_prefacturas"]

        pagos_qs = VGPago.objects.filter(factura__isnull=False)
        facturas_qs = VGFactura.objects.all()
        lineas_qs = VGFacturaLinea.objects.all()
        ordenes_qs = VGOrdenCobro.objects.all()
        prefacturas_qs = VGPreFactura.objects.all()
        prefactura_lineas_qs = VGPreFacturaLinea.objects.all()

        self.stdout.write("Se borrarían:")
        self.stdout.write(f"  VGPago (ligados a factura): {pagos_qs.count()}")
        self.stdout.write(f"  VGFactura: {facturas_qs.count()}")
        self.stdout.write(f"  VGFacturaLinea: {lineas_qs.count()}")
        self.stdout.write(f"  VGOrdenCobro: {ordenes_qs.count()}")
        if incluir_prefacturas:
            self.stdout.write(f"  VGPreFactura: {prefacturas_qs.count()}")
            self.stdout.write(f"  VGPreFacturaLinea: {prefactura_lineas_qs.count()}")
        else:
            self.stdout.write("  VGPreFactura: NO se toca (--mantener-prefacturas)")

        series_a_resetear = ["FACTURA", "CONTROL"] + (["PREFACTURA"] if incluir_prefacturas else [])
        self.stdout.write(f"Correlativos a reiniciar a 0: {', '.join(series_a_resetear)}")

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("--dry-run: no se borró ni se reinició nada."))
            return

        if not options["confirmar"]:
            raise CommandError(
                "Esto borra datos de verdad. Corre con --dry-run primero para ver el alcance, "
                "y con --confirmar cuando estés seguro."
            )

        with transaction.atomic():
            pagos_borrados = pagos_qs.delete()[0]
            facturas_borradas = facturas_qs.delete()[0]
            prefacturas_borradas = 0
            if incluir_prefacturas:
                prefacturas_borradas = prefacturas_qs.delete()[0]

            VGCorrelativoFiscal.objects.filter(serie__in=series_a_resetear).update(ultimo_numero=0)

        self.stdout.write(self.style.SUCCESS(
            f"Listo. VGPago borrados: {pagos_borrados}. VGFactura (+líneas/orden de cobro) borrados: "
            f"{facturas_borradas}. "
            + (f"VGPreFactura (+líneas) borrados: {prefacturas_borradas}. " if incluir_prefacturas else "")
            + f"Correlativos reiniciados: {', '.join(series_a_resetear)}."
        ))
