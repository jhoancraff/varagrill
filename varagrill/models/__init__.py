"""
Modelos separados en dos archivos segun a que parte del negocio pertenecen:
- restaurant.py: todo lo propio del restaurante (menu, inventario, mesas,
  usuarios, pedidos, promociones...).
- contabilidad.py: metodos de pago y cuadre de caja.
- base.py: VGAuditoria, la base abstracta que usan ambos.

Este __init__ re-exporta todo para que el resto del proyecto siga
haciendo `from .models import X` / `from varagrill.models import X`
exactamente igual que cuando todo vivia en un solo models.py.
"""
from .base import VGAuditoria
from .contabilidad import (
    VGCierreCaja,
    VGConsignacionCaja,
    VGCorrelativoFiscal,
    VGDatosFiscalesEmisor,
    VGFactura,
    VGFacturaLinea,
    VGMetodoPago,
    VGOrdenCobro,
    VGPreFactura,
    VGPreFacturaLinea,
)
from .restaurant import (
    VGCategoriaProducto,
    VGCliente,
    VGCompra,
    VGDetalleCompra,
    VGDetallePedido,
    VGDetallePedidoAdicional,
    VGImpresoraCaja,
    VGIngrediente,
    VGMesa,
    VGMovimientoInventario,
    VGPago,
    VGPedido,
    VGPreparacion,
    VGProducto,
    VGPromocion,
    VGRecetaPreparacion,
    VGRecetaProducto,
    VGRecomendacionChef,
    VGRol,
    VGTasaCambio,
    VGUsuario,
)

__all__ = [
    "VGAuditoria",
    "VGCategoriaProducto",
    "VGCierreCaja",
    "VGCliente",
    "VGCompra",
    "VGConsignacionCaja",
    "VGCorrelativoFiscal",
    "VGDatosFiscalesEmisor",
    "VGDetalleCompra",
    "VGDetallePedido",
    "VGDetallePedidoAdicional",
    "VGFactura",
    "VGFacturaLinea",
    "VGImpresoraCaja",
    "VGIngrediente",
    "VGMesa",
    "VGMetodoPago",
    "VGMovimientoInventario",
    "VGOrdenCobro",
    "VGPago",
    "VGPedido",
    "VGPreFactura",
    "VGPreFacturaLinea",
    "VGPreparacion",
    "VGProducto",
    "VGPromocion",
    "VGRecetaPreparacion",
    "VGRecetaProducto",
    "VGRecomendacionChef",
    "VGRol",
    "VGTasaCambio",
    "VGUsuario",
]
