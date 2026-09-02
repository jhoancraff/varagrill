from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models, transaction

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


# ---------------------------------------------------------------------------
# Datos fiscales y numeración correlativa
# ---------------------------------------------------------------------------
class VGDatosFiscalesEmisor(models.Model):
    """
    Datos del negocio que se imprimen en el encabezado de cada factura
    (RIF, razón social, domicilio...). Se espera una sola fila en la tabla;
    la vista de administración se encarga de eso, el modelo no lo fuerza.
    """
    rif = models.CharField(max_length=20)
    razon_social = models.CharField(max_length=200)
    nombre_comercial = models.CharField(max_length=200, blank=True)
    domicilio_fiscal = models.CharField(max_length=255, blank=True)
    telefono = models.CharField(max_length=20, blank=True)
    porcentaje_iva_default = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("16.00"))

    class Meta:
        db_table = "vg_datos_fiscales_emisor"
        verbose_name = "Datos fiscales del emisor"
        verbose_name_plural = "Datos fiscales del emisor"

    def __str__(self):
        return self.razon_social


class VGCorrelativoFiscal(models.Model):
    """
    Contador atómico por serie (ej: "FACTURA", "CONTROL", "PREFACTURA").
    siguiente() usa select_for_update para que dos cobros simultáneos nunca
    generen el mismo número — y los números nunca se reutilizan, ni cuando
    se anula el documento que los consumió, tal como exige un correlativo
    fiscal.
    """
    serie = models.CharField(max_length=30, unique=True)
    ultimo_numero = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "vg_correlativos_fiscales"
        verbose_name = "Correlativo fiscal"
        verbose_name_plural = "Correlativos fiscales"

    def __str__(self):
        return f"{self.serie} — {self.ultimo_numero}"

    @classmethod
    def siguiente(cls, serie):
        with transaction.atomic():
            correlativo, _ = cls.objects.select_for_update().get_or_create(serie=serie)
            correlativo.ultimo_numero += 1
            correlativo.save(update_fields=["ultimo_numero"])
            return correlativo.ultimo_numero


# ---------------------------------------------------------------------------
# Documentos de venta — base reutilizable
# ---------------------------------------------------------------------------
class VGLineaVentaBase(models.Model):
    """
    Estructura común de una línea de venta (qué se vendió, a qué precio y
    cómo se desglosa el IVA). Abstracta a propósito: la heredan las líneas
    de pre-factura y factura hoy, y cualquier futuro documento de venta
    (ej. nota de crédito) mañana, sin duplicar campos ni lógica de cálculo.
    """
    descripcion = models.CharField(max_length=255)
    producto = models.ForeignKey(
        "varagrill.VGProducto", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="%(class)s_lineas",
        help_text="Producto del menú de origen, cuando la línea viene de un pedido del restaurante.",
    )
    cantidad = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("1"))
    precio_unitario = models.DecimalField(max_digits=12, decimal_places=4)
    porcentaje_iva = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("16.00"))
    base_imponible = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    monto_iva = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        abstract = True

    def calcular_montos(self):
        """
        precio_unitario ya es el precio final de venta (el mismo que se cobra en la
        nota de entrega) — el IVA viene incluido, no se suma aparte. Por eso
        `subtotal` (lo que paga el cliente) sale directo de cantidad × precio, y
        base_imponible/monto_iva son ese mismo monto DESGLOSADO, nunca un cargo
        adicional. Así una factura y una nota de entrega del mismo pedido siempre
        dan el mismo total; monto_iva se calcula como resto (subtotal - base) para
        que la suma cuadre exacto centavo a centavo pese al redondeo.
        """
        self.subtotal = (self.cantidad * self.precio_unitario).quantize(Decimal("0.01"))
        divisor = Decimal("1") + (self.porcentaje_iva / Decimal("100"))
        self.base_imponible = (self.subtotal / divisor).quantize(Decimal("0.01")) if divisor > 0 else self.subtotal
        self.monto_iva = self.subtotal - self.base_imponible


# ---------------------------------------------------------------------------
# Pre-factura — vista previa de cuenta, sin efecto fiscal ni contable
# ---------------------------------------------------------------------------
class VGPreFactura(VGAuditoria):
    """
    Lo que se le muestra al cliente que pide ver la cuenta antes de pagar.
    No consume numeración fiscal ni genera deuda: es solo un snapshot
    imprimible. Si el cliente acepta, se convierte en una VGFactura real
    (ver VGFactura.pre_factura).
    """
    ESTADOS = [
        ("vigente", "Vigente"),
        ("convertida", "Convertida en factura"),
        ("anulada", "Anulada"),
    ]
    numero = models.PositiveIntegerField(unique=True)
    cliente = models.ForeignKey(
        "varagrill.VGCliente", on_delete=models.SET_NULL, null=True, blank=True, related_name="prefacturas",
    )
    pedidos = models.ManyToManyField("varagrill.VGPedido", blank=True, related_name="prefacturas")
    fecha_emision = models.DateTimeField(auto_now_add=True)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_iva = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    moneda = models.CharField(
        max_length=3, choices=VGMetodoPago.MONEDAS, default="USD",
        help_text="Moneda en la que se muestra esta cuenta (tomada del método de pago elegido al generarla). Los montos siempre se calculan en USD por dentro; esto solo controla en qué moneda se despliega/imprime.",
    )
    tasa_cambio_referencia = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default="vigente")
    notas = models.TextField(blank=True)

    class Meta:
        db_table = "vg_prefacturas"
        verbose_name = "Pre-factura"
        verbose_name_plural = "Pre-facturas"
        ordering = ["-fecha_emision"]

    def __str__(self):
        return f"Pre-factura PF-{self.numero:06d}"

    def recalcular_totales(self):
        lineas = list(self.lineas.all())
        self.subtotal = sum((linea.base_imponible for linea in lineas), Decimal("0"))
        self.total_iva = sum((linea.monto_iva for linea in lineas), Decimal("0"))
        self.total = self.subtotal + self.total_iva


class VGPreFacturaLinea(VGLineaVentaBase):
    prefactura = models.ForeignKey(VGPreFactura, on_delete=models.CASCADE, related_name="lineas")

    class Meta:
        db_table = "vg_prefactura_lineas"
        verbose_name = "Línea de pre-factura"
        verbose_name_plural = "Líneas de pre-factura"

    def __str__(self):
        return f"{self.prefactura} — {self.descripcion}"


# ---------------------------------------------------------------------------
# Factura — documento fiscal real
# ---------------------------------------------------------------------------
class VGFactura(VGAuditoria):
    """
    Documento de venta con numeración fiscal. No depende de VGPedido: puede
    nacer de uno o varios pedidos del restaurante (pedidos M2M) o quedar
    vacía de pedidos para futuros usos contables no ligados al restaurante
    (ver VGLineaVentaBase). numero_factura y numero_control se generan con
    VGCorrelativoFiscal.siguiente(...) al emitir, nunca se reutilizan.
    """
    ESTADOS = [
        ("pendiente_pago", "Pendiente de pago"),
        ("abonada_parcial", "Abonada parcialmente"),
        ("pagada", "Pagada"),
        ("anulada", "Anulada"),
    ]
    numero_factura = models.PositiveIntegerField(unique=True)
    numero_control = models.PositiveIntegerField(unique=True)
    cliente = models.ForeignKey("varagrill.VGCliente", on_delete=models.PROTECT, related_name="facturas")
    pre_factura = models.ForeignKey(
        VGPreFactura, on_delete=models.SET_NULL, null=True, blank=True, related_name="facturas",
    )
    pedidos = models.ManyToManyField("varagrill.VGPedido", blank=True, related_name="facturas")
    fecha_emision = models.DateTimeField(auto_now_add=True)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_iva = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    descuento = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    saldo_pendiente = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    moneda = models.CharField(
        max_length=3, choices=VGMetodoPago.MONEDAS, default="USD",
        help_text="Moneda en la que se muestra esta factura (tomada del método de pago elegido al emitirla). Los montos siempre se calculan en USD por dentro; esto solo controla en qué moneda se despliega/imprime.",
    )
    tasa_cambio_referencia = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default="pendiente_pago")
    motivo_anulacion = models.CharField(max_length=255, blank=True)
    notas = models.TextField(blank=True)

    class Meta:
        db_table = "vg_facturas"
        verbose_name = "Factura"
        verbose_name_plural = "Facturas"
        ordering = ["-fecha_emision"]

    def __str__(self):
        return f"Factura {self.numero_factura:06d}"

    def recalcular_totales(self):
        lineas = list(self.lineas.all())
        self.subtotal = sum((linea.base_imponible for linea in lineas), Decimal("0"))
        self.total_iva = sum((linea.monto_iva for linea in lineas), Decimal("0"))
        self.total = self.subtotal + self.total_iva - self.descuento


class VGFacturaLinea(VGLineaVentaBase):
    factura = models.ForeignKey(VGFactura, on_delete=models.CASCADE, related_name="lineas")

    class Meta:
        db_table = "vg_factura_lineas"
        verbose_name = "Línea de factura"
        verbose_name_plural = "Líneas de factura"

    def __str__(self):
        return f"{self.factura} — {self.descripcion}"


# ---------------------------------------------------------------------------
# Cuentas por cobrar
# ---------------------------------------------------------------------------
class VGOrdenCobro(VGAuditoria):
    """
    La deuda viva de una factura: lo que la cajera debe perseguir hasta
    saldar. Se crea junto con la factura cuando queda saldo pendiente; los
    abonos son VGPago con factura=esta_factura (ver VGPago en
    restaurant.py) y cada uno debe descontar saldo_pendiente aquí y en la
    factura dentro de la misma transacción.
    """
    ESTADOS = [
        ("pendiente", "Pendiente"),
        ("parcial", "Abonada parcialmente"),
        ("saldada", "Saldada"),
        ("anulada", "Anulada"),
    ]
    factura = models.OneToOneField(VGFactura, on_delete=models.CASCADE, related_name="orden_cobro")
    monto_total = models.DecimalField(max_digits=12, decimal_places=2)
    saldo_pendiente = models.DecimalField(max_digits=12, decimal_places=2)
    estado = models.CharField(max_length=20, choices=ESTADOS, default="pendiente")
    fecha_limite = models.DateField(null=True, blank=True)
    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="ordenes_cobro",
    )
    notas = models.TextField(blank=True)

    class Meta:
        db_table = "vg_ordenes_cobro"
        verbose_name = "Orden de cobro"
        verbose_name_plural = "Órdenes de cobro"
        ordering = ["-fecha_creacion"]

    def __str__(self):
        return f"Orden de cobro — {self.factura}"


# ---------------------------------------------------------------------------
# Nota de entrega — recibo de venta sin efecto fiscal
# ---------------------------------------------------------------------------
class VGNotaEntrega(VGAuditoria):
    """
    Recibo de venta SIN efecto fiscal: lo que hoy se emite en el mostrador en
    vez de una factura mientras el SENIAT termina de homologar el sistema.
    A diferencia de VGFactura, no tiene numero_factura/numero_control — no
    consume VGCorrelativoFiscal, su "numero" es simplemente su id interno
    (ver codigo).

    Igual que una VGFactura, nace con saldo_pendiente = total y estado
    'pendiente_pago': el pedido ya queda 'pagado' (inventario descontado,
    cocina cerrada) al emitirla, pero el DINERO se cobra aparte, en uno o
    varios abonos (ver nota_entrega_abono_view en facturacion_views.py) —
    metodo_pago acá es solo el método declarado al emitir (define en qué
    moneda se imprime/muestra la nota), no implica que ya se cobró; cada
    abono registra su propio VGPago con su propio método.

    No duplica el detalle de cada pedido (platos, acompañantes, adicionales,
    notas, mesa) en líneas propias: guarda solo la relación a los VGPedido
    de origen, y el ticket — tanto el original como cualquier reimpresión —
    se reconstruye leyendo ese detalle en vivo desde ellos (ver
    imprimir_nota_entrega_caja en impresion_lpd.py), igual que ya hacía el
    recibo de caja de siempre.
    """
    ESTADOS = [
        ("pendiente_pago", "Pendiente de pago"),
        ("abonada_parcial", "Abonada parcialmente"),
        ("pagada", "Pagada"),
    ]
    cliente = models.ForeignKey(
        "varagrill.VGCliente", on_delete=models.PROTECT, null=True, blank=True, related_name="notas_entrega",
    )
    pedidos = models.ManyToManyField("varagrill.VGPedido", related_name="notas_entrega")
    metodo_pago = models.ForeignKey(VGMetodoPago, on_delete=models.PROTECT, related_name="notas_entrega")
    fecha_emision = models.DateTimeField(auto_now_add=True)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    saldo_pendiente = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    estado = models.CharField(max_length=20, choices=ESTADOS, default="pendiente_pago")
    moneda = models.CharField(max_length=3, choices=VGMetodoPago.MONEDAS, default="USD")
    tasa_cambio_referencia = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    referencia = models.CharField(max_length=100, blank=True)

    class Meta:
        db_table = "vg_notas_entrega"
        verbose_name = "Nota de entrega"
        verbose_name_plural = "Notas de entrega"
        ordering = ["-fecha_emision"]

    @property
    def codigo(self):
        return f"{self.id:08d}"

    def __str__(self):
        return f"Nota de entrega {self.codigo}"


# ---------------------------------------------------------------------------
# Gastos operativos (alquiler, servicios, nomina, mantenimiento...)
# ---------------------------------------------------------------------------
class VGCategoriaGasto(VGAuditoria):
    """
    Clasificacion de gastos operativos (Alquiler, Servicios, Nomina...),
    configurable por el analista igual que VGMetodoPago. Desactivarla
    (activo=False) la quita del selector al registrar un gasto nuevo sin
    borrar el historico de VGGasto que ya la uso (categoria usa PROTECT).
    """
    nombre = models.CharField(max_length=80, unique=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "vg_categorias_gasto"
        verbose_name = "Categoría de gasto"
        verbose_name_plural = "Categorías de gasto"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class VGGasto(VGAuditoria):
    """
    Un gasto operativo del negocio (alquiler, luz, nomina...) — no pasa por
    inventario, a diferencia de VGCompra. Arranca con saldo_pendiente=monto
    y estado_pago='pendiente'; si se registra como ya pagado, el mismo flujo
    de alta le crea de una vez su VGAbonoGasto por el monto completo (ver
    gastos_views._registrar_abono_gasto). Un gasto pagado en efectivo se
    descuenta del efectivo esperado del cuadre de caja del dia
    (reportes.efectivo_esperado_dia).
    """
    ESTADOS_PAGO = [
        ("pendiente", "Pendiente"),
        ("abonada_parcial", "Abonado parcialmente"),
        ("pagado", "Pagado"),
    ]
    categoria = models.ForeignKey(VGCategoriaGasto, on_delete=models.PROTECT, related_name="gastos")
    descripcion = models.CharField(
        max_length=255, help_text="Ej: Factura de luz de agosto, Alquiler de septiembre.",
    )
    proveedor_nombre = models.CharField(
        max_length=150, blank=True, help_text="A quien se le paga este gasto (opcional).",
    )
    numero_comprobante = models.CharField(max_length=100, blank=True)
    monto = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    saldo_pendiente = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    estado_pago = models.CharField(max_length=20, choices=ESTADOS_PAGO, default="pendiente")
    fecha_gasto = models.DateField(
        help_text="Fecha real del gasto/factura (puede ser distinta a cuando se registro en el sistema).",
    )
    notas = models.TextField(blank=True)
    tasa_cambio_referencia = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)

    class Meta:
        db_table = "vg_gastos"
        verbose_name = "Gasto"
        verbose_name_plural = "Gastos"
        ordering = ["-fecha_creacion"]

    def __str__(self):
        return f"{self.categoria} — {self.descripcion}"


class VGAbonoGasto(models.Model):
    """
    Pago del restaurante hacia un gasto operativo (egreso). Modelo aparte de
    VGPago por la misma razon que VGAbonoCompra: VGPago alimenta el cuadre de
    caja como dinero que ENTRA, mezclar egresos ahi lo contaminaria.
    """
    gasto = models.ForeignKey(VGGasto, on_delete=models.PROTECT, related_name="abonos")
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    metodo_pago = models.ForeignKey(VGMetodoPago, on_delete=models.PROTECT, related_name="abonos_gasto")
    referencia = models.CharField(max_length=100, blank=True)
    fecha_pago = models.DateTimeField(auto_now_add=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
    )
    tasa_cambio_referencia = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)

    class Meta:
        db_table = "vg_abonos_gasto"

    def __str__(self):
        return f"Abono {self.monto} — Gasto #{self.gasto_id}"
