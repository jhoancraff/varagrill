# -*- coding: utf-8 -*-
"""
Borra TODOS los datos operativos/transaccionales (pedidos, notas de entrega,
facturas, compras, gastos, pagos, cierres de caja, movimientos de
inventario, promociones, recomendaciones del chef, historial de tasa de
cambio...) y reinicia sus contadores de ID a 1, dejando intactos el
catálogo y la configuración del negocio: usuarios, roles, ingredientes,
recetas/subrecetas, productos, clientes, categorías (de producto y de
gasto), grupos de opciones de producto, mesas, métodos de pago, datos
fiscales del emisor y la configuración de la impresora de caja.

Deliberadamente NO se llama "reset_facturas" ni reemplaza a ese comando: el
alcance acá es mucho más amplio (toda la operación, no solo facturación), y
mezclar los dos nombres/comandos sería peligroso — alguien podría correr
"reset_facturas" pensando que solo toca facturas y de paso borrar pedidos,
compras y gastos sin darse cuenta.

Qué se conserva (no se toca en absoluto):
  VGUsuario, VGRol, VGIngrediente, VGProducto, VGPreparacion,
  VGRecetaProducto, VGRecetaPreparacion, VGCliente, VGCategoriaProducto,
  VGCategoriaGasto, VGGrupoOpcionProducto, VGOpcionProducto, VGMesa,
  VGMetodoPago, VGDatosFiscalesEmisor, VGImpresoraCaja.

Los movimientos de inventario se borran por completo (entradas, salidas y
ajustes) pero el stock_actual y el resto de cada VGIngrediente NO se tocan
— el movimiento es solo el historial/auditoría de cómo se llegó a ese
stock, no la fuente de verdad del stock en sí.

Qué se borra (y su ID vuelve a arrancar en 1):
  VGPago, VGAbonoGasto, VGAbonoCompra, VGDetallePedidoOpcion,
  VGDetallePedidoAdicional, VGDetallePedido, VGPedido, VGNotaEntrega,
  VGFacturaLinea, VGOrdenCobro, VGFactura, VGPreFacturaLinea, VGPreFactura,
  VGGasto, VGDetalleCompra, VGCompra, VGDetalleCompraBorrador,
  VGCompraBorrador, VGMovimientoInventario, VGConsignacionCaja,
  VGCierreCaja, VGPromocion, VGRecomendacionChef, VGTasaCambio.

Además reinicia a 0 los tres correlativos fiscales (VGCorrelativoFiscal:
FACTURA, CONTROL, PREFACTURA) — esa tabla no se borra, solo se resetea el
contador, igual que hace reset_facturas. VGNotaEntrega no tiene correlativo
fiscal propio (su "código" es directamente su id), así que reiniciar su ID
a 1 ya deja la numeración de notas de entrega en cero — no hace falta nada
extra para eso.

Orden de borrado (importa: algunas de estas tablas se PROTEGEN entre sí —
VGAbonoGasto.gasto, VGAbonoCompra.compra y VGPago.pedido/factura/nota_entrega
usan on_delete=PROTECT — así que hay que quitar primero lo que protege antes
de poder borrar lo protegido). Todas las demás relaciones dentro del alcance
son CASCADE (se arrastran solas) o apuntan a algo que SE CONSERVA (nunca se
borra ese lado, así que no hay riesgo de tocar catálogo por accidente).

Es IRREVERSIBLE — no hay soft-delete ni backup automático.

Uso:
    python manage.py reset_datos_operativos --dry-run     # solo mostrar cuántos se borrarían
    python manage.py reset_datos_operativos --confirmar   # borrar todo y reiniciar los IDs de verdad
"""
from django.core.management.base import BaseCommand, CommandError
from django.core.management.color import no_style
from django.db import connection, transaction

from varagrill.models import (
    VGAbonoCompra,
    VGAbonoGasto,
    VGCierreCaja,
    VGCompra,
    VGCompraBorrador,
    VGConsignacionCaja,
    VGCorrelativoFiscal,
    VGFactura,
    VGGasto,
    VGMovimientoInventario,
    VGNotaEntrega,
    VGPago,
    VGPedido,
    VGPreFactura,
    VGPromocion,
    VGRecomendacionChef,
    VGTasaCambio,
)

# Orden de borrado: primero lo que PROTEGE a algo más abajo en la lista
# (VGPago protege a VGPedido, VGFactura y VGNotaEntrega; VGAbonoGasto
# protege a VGGasto; VGAbonoCompra protege a VGCompra). El resto de las
# tablas hijas (detalles, líneas, orden de cobro...) son CASCADE desde el
# modelo que aparece acá, así que no hace falta listarlas aparte — se
# arrastran solas al borrar su padre.
MODELOS_A_BORRAR_EN_ORDEN = [
    VGPago,
    VGAbonoGasto,
    VGAbonoCompra,
    VGPedido,
    VGNotaEntrega,
    VGFactura,
    VGPreFactura,
    VGGasto,
    VGCompra,
    VGCompraBorrador,
    VGMovimientoInventario,
    VGConsignacionCaja,
    VGCierreCaja,
    VGPromocion,
    VGRecomendacionChef,
    VGTasaCambio,
]

SERIES_CORRELATIVO = ["FACTURA", "CONTROL", "PREFACTURA"]


class Command(BaseCommand):
    help = "Borra todos los datos operativos/transaccionales y reinicia sus IDs a 1, conservando catálogo y configuración."

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirmar", action="store_true",
            help="Ejecuta el borrado de verdad. Sin este flag, el comando no toca nada (salvo --dry-run).",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Solo muestra cuántos registros se borrarían de cada tabla, sin borrar ni resetear nada.",
        )

    def handle(self, *args, **options):
        self.stdout.write("Se borrarían (el número incluye lo que arrastra en cascada, ej. detalles/líneas):")
        conteos = {}
        for modelo in MODELOS_A_BORRAR_EN_ORDEN:
            conteos[modelo] = modelo.objects.count()
            self.stdout.write(f"  {modelo.__name__}: {conteos[modelo]}")

        self.stdout.write(f"Correlativos a reiniciar a 0: {', '.join(SERIES_CORRELATIVO)}")
        self.stdout.write("IDs a reiniciar a 1: " + ", ".join(m.__name__ for m in MODELOS_A_BORRAR_EN_ORDEN))
        self.stdout.write(self.style.WARNING(
            "Se conservan intactos: VGUsuario, VGRol, VGIngrediente, VGProducto, VGPreparacion, "
            "VGRecetaProducto, VGRecetaPreparacion, VGCliente, VGCategoriaProducto, VGCategoriaGasto, "
            "VGGrupoOpcionProducto, VGOpcionProducto, VGMesa, VGMetodoPago, VGDatosFiscalesEmisor, VGImpresoraCaja."
        ))

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("--dry-run: no se borró ni se reinició nada."))
            return

        if not options["confirmar"]:
            raise CommandError(
                "Esto borra datos de verdad y es irreversible. Corre con --dry-run primero para ver el "
                "alcance, y con --confirmar cuando estés seguro."
            )

        with transaction.atomic():
            for modelo in MODELOS_A_BORRAR_EN_ORDEN:
                modelo.objects.all().delete()

            VGCorrelativoFiscal.objects.filter(serie__in=SERIES_CORRELATIVO).update(ultimo_numero=0)

            # Reinicia el contador de ID (secuencia) de cada tabla a 1 — usa el
            # mecanismo propio de Django (el mismo que usan `flush` y
            # `sqlsequencereset`) en vez de SQL crudo, para que funcione igual
            # sin importar el motor de base de datos configurado.
            sequence_sql = connection.ops.sequence_reset_sql(no_style(), MODELOS_A_BORRAR_EN_ORDEN)
            if sequence_sql:
                with connection.cursor() as cursor:
                    for sql in sequence_sql:
                        cursor.execute(sql)

        self.stdout.write(self.style.SUCCESS(
            "Listo. Datos operativos borrados, IDs reiniciados a 1 y correlativos fiscales en 0. "
            "Catálogo y configuración intactos."
        ))
