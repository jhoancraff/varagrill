from django.core.validators import MinValueValidator
from django.db import models

from .base import VGAuditoria


# ---------------------------------------------------------------------------
# Metodos de pago (configurables por el analista)
# ---------------------------------------------------------------------------
class VGMetodoPago(VGAuditoria):
    """
    Tipo de metodo de pago disponible al cobrar (Efectivo, Tarjeta, Binance,
    Zelle, ...). El analista puede agregar nuevos desde el Panel analista;
    desactivarlos (activo=False) los quita del selector de cobro sin borrar
    el historico de VGPago que ya los uso (metodo_pago usa on_delete=PROTECT).
    es_efectivo marca cuales cuentan como dinero fisico en caja para el
    cuadre diario (ver varagrill/reportes.py); los demas solo se muestran
    como referencia informativa en ese reporte.

    moneda indica en que moneda se recibe el dinero fisicamente (VES para
    metodos como transferencia/pago movil, USD para zelle/binance/efectivo).
    Los montos siempre se guardan en USD en VGPago (asi funciona el precio de
    los productos); para un metodo en VES, el reporte de cuadre de caja
    convierte ese monto a bolivares con la tasa BCV del dia, para mostrarlo
    en la moneda real que recibio el cajero.
    """
    MONEDAS = [
        ("USD", "Dólares"),
        ("VES", "Bolívares"),
    ]
    nombre = models.CharField(max_length=50, unique=True)
    moneda = models.CharField(max_length=3, choices=MONEDAS, default="USD")
    es_efectivo = models.BooleanField(
        default=False,
        help_text="Si esta activo, este metodo cuenta como efectivo fisico en el cuadre de caja.",
    )
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "vg_metodos_pago"
        verbose_name = "Metodo de pago"
        verbose_name_plural = "Metodos de pago"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


# ---------------------------------------------------------------------------
# Cuadre de caja diario
# ---------------------------------------------------------------------------
class VGConsignacionCaja(VGAuditoria):
    """
    Entrega parcial de efectivo durante el turno (ej. cuando la caja acumula
    mucho dinero y se deposita/entrega antes del cierre). Puede haber varias
    en un mismo día; creado_por (de VGAuditoria) registra quién la hizo.
    """
    fecha = models.DateField()
    monto = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    notas = models.TextField(blank=True)

    class Meta:
        db_table = "vg_consignaciones_caja"
        verbose_name = "Consignación de caja"
        verbose_name_plural = "Consignaciones de caja"
        ordering = ["fecha", "fecha_creacion"]

    def __str__(self):
        return f"Consignación {self.monto} — {self.fecha}"


class VGCierreCaja(VGAuditoria):
    """
    Cierre único al final del día, lo hace la última persona del turno.
    efectivo_esperado es el snapshot de lo cobrado en efectivo ese día (vía
    VGPago; los demás métodos —tarjeta, transferencia, binance, zelle...— no
    pasan por la caja física y solo se muestran como referencia en el
    reporte, no entran en este cuadre); total_consignado es la suma de las
    VGConsignacionCaja del día; efectivo_contado_final es lo que la persona
    contó físicamente en caja al momento de cerrar.
    """
    fecha = models.DateField(unique=True)
    efectivo_esperado = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_consignado = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    efectivo_contado_final = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    diferencia = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    notas = models.TextField(blank=True)

    class Meta:
        db_table = "vg_cierres_caja"
        verbose_name = "Cierre de caja"
        verbose_name_plural = "Cierres de caja"
        ordering = ["-fecha"]

    def __str__(self):
        return f"Cierre de caja — {self.fecha}"
