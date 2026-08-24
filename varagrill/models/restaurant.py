from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator
from django.db import models

from .base import VGAuditoria
from .contabilidad import VGMetodoPago


# ---------------------------------------------------------------------------
# Usuarios y roles — extiende auth.User en vez de reemplazarlo
# ---------------------------------------------------------------------------
class VGRol(VGAuditoria):
    nombre_role = models.CharField(max_length=50, unique=True)
    descripcion = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "vg_roles"
        verbose_name = "Rol"
        verbose_name_plural = "Roles"

    def __str__(self):
        return self.nombre_role


class VGUsuario(AbstractUser):
    """
    Reemplaza a auth.User. Hereda username, first_name, last_name, email,
    password, is_staff, is_active, is_superuser, date_joined, etc., y le
    agrega los campos propios del restaurante en la misma tabla.
    Requiere AUTH_USER_MODEL = "<tu_app>.VGUsuario" en settings.py, definido
    ANTES de correr la primera migración del proyecto.
    """
    cedula = models.CharField(max_length=20, unique=True)
    telefono = models.CharField(max_length=20, blank=True)
    fecha_nacimiento = models.DateField(null=True, blank=True)
    id_role = models.ForeignKey(
        VGRol, on_delete=models.PROTECT, null=True, blank=True, related_name="usuarios",
    )

    class Meta:
        db_table = "vg_usuarios"
        verbose_name = "Usuario"
        verbose_name_plural = "Usuarios"

    def __str__(self):
        return self.get_full_name() or self.username


# ---------------------------------------------------------------------------
# Mesas y clientes
# ---------------------------------------------------------------------------
class VGMesa(VGAuditoria):
    ESTADOS = [
        ("libre", "Libre"),
        ("ocupada", "Ocupada"),
        ("reservada", "Reservada"),
        ("mantenimiento", "Mantenimiento"),
    ]
    numero = models.PositiveIntegerField(unique=True)
    capacidad = models.PositiveSmallIntegerField(default=4)
    ubicacion = models.CharField(max_length=100, blank=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default="libre")

    class Meta:
        db_table = "vg_mesas"

    def __str__(self):
        return f"Mesa {self.numero}"


class VGCliente(models.Model):
    TIPOS_DOCUMENTO = [
        ("V", "Cédula (V)"),
        ("E", "Cédula de extranjero (E)"),
        ("J", "RIF jurídico (J)"),
        ("G", "RIF gubernamental (G)"),
        ("P", "Pasaporte (P)"),
    ]
    nombre = models.CharField(max_length=150)
    telefono = models.CharField(max_length=20, blank=True)
    correo = models.EmailField(blank=True)
    tipo_documento = models.CharField(max_length=1, choices=TIPOS_DOCUMENTO, blank=True)
    numero_documento = models.CharField(
        max_length=20, blank=True,
        help_text="Cédula o RIF sin el prefijo (ej: 12345678). Vacío para consumidor final sin datos fiscales.",
    )
    direccion_fiscal = models.CharField(max_length=255, blank=True)
    fecha_registro = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "vg_clientes"
        constraints = [
            models.UniqueConstraint(
                fields=["tipo_documento", "numero_documento"],
                condition=~models.Q(numero_documento=""),
                name="uniq_cliente_documento",
            ),
        ]

    def __str__(self):
        return self.nombre


# ---------------------------------------------------------------------------
# Menú
# ---------------------------------------------------------------------------
class VGCategoriaProducto(VGAuditoria):
    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.CharField(max_length=255, blank=True)
    ip_impresora = models.CharField(
        max_length=45, blank=True,
        help_text="IP en la red local de la impresora térmica que imprime las comandas de esta categoría. Vacío = no imprime.",
    )
    puerto_impresora = models.PositiveIntegerField(
        default=9100,
        help_text="Puerto TCP de impresión cruda de la impresora (ESC/POS estándar: 9100).",
    )

    class Meta:
        db_table = "vg_categorias_productos"
        verbose_name = "Categoría de producto"
        verbose_name_plural = "Categorías de productos"

    def __str__(self):
        return self.nombre


class VGProducto(VGAuditoria):
    nombre = models.CharField(max_length=150)
    descripcion = models.TextField(blank=True)
    categoria = models.ForeignKey(VGCategoriaProducto, on_delete=models.PROTECT, related_name="productos")
    precio_venta = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    costo_estimado = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    imagen_url = models.URLField(blank=True)
    disponible = models.BooleanField(default=True)
    tiempo_preparacion_min = models.PositiveSmallIntegerField(default=0)
    venta_por_peso = models.BooleanField(
        default=False,
        help_text="Si está activo, precio_venta es el precio por KILOGRAMO y el pedido registra los gramos vendidos en vez de unidades (ej: cortes de carne).",
    )
    receta_vinculada = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="productos_vinculados",
        help_text="Receta del catálogo (VGProducto de categoría 'Recetas') que compone este producto vendible.",
    )
    subreceta_vinculada = models.ForeignKey(
        "VGPreparacion", on_delete=models.SET_NULL, null=True, blank=True, related_name="productos_vinculados",
        help_text="Subreceta que compone este producto vendible.",
    )

    class Meta:
        db_table = "vg_productos"
        constraints = [
            models.CheckConstraint(
                condition=~(
                    models.Q(receta_vinculada__isnull=False) & models.Q(subreceta_vinculada__isnull=False)
                ),
                name="producto_vinculo_unico",
            ),
        ]

    def __str__(self):
        return self.nombre

    def nombres_composicion(self):
        if self.receta_vinculada_id:
            return [
                (componente.ingrediente.nombre if componente.ingrediente_id else componente.preparacion.nombre)
                for componente in self.receta_vinculada.receta.all()
            ]
        if self.subreceta_vinculada_id:
            return [
                (componente.ingrediente.nombre if componente.ingrediente_id else componente.sub_preparacion.nombre)
                for componente in self.subreceta_vinculada.componentes.all()
            ]
        return []


# ---------------------------------------------------------------------------
# Inventario
# ---------------------------------------------------------------------------
class VGIngrediente(VGAuditoria):
    UNIDADES = [
        ("kg", "Kilogramos"),
        ("g", "Gramos"),
        ("l", "Litros"),
        ("ml", "Mililitros"),
        ("unidad", "Unidad"),
    ]
    nombre = models.CharField(max_length=150)
    unidad_medida = models.CharField(max_length=10, choices=UNIDADES)
    stock_actual = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    stock_minimo = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    costo_unitario = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    ultimo_proveedor = models.CharField(
        max_length=150, blank=True,
        help_text="Nombre del último proveedor que despachó este ingrediente (sin tabla propia: los proveedores cambian seguido).",
    )

    class Meta:
        db_table = "vg_ingredientes"

    def __str__(self):
        return self.nombre


class VGPreparacion(VGAuditoria):
    """
    Una elaboración intermedia (salsa, base, marinado, aderezo...) que no se
    vende directamente, pero tiene su propia receta y se usa como componente
    dentro de la receta de un producto — o dentro de otra preparación.
    """
    nombre = models.CharField(max_length=150)
    rendimiento_cantidad = models.DecimalField(
        max_digits=10, decimal_places=3,
        help_text="Cuánto produce una tanda de esta receta (ej: 1 tanda = 2 litros de salsa).",
    )
    rendimiento_unidad = models.CharField(max_length=10, choices=VGIngrediente.UNIDADES)
    es_adicional = models.BooleanField(
        default=False,
        help_text="Si está activo, el mesero puede ofrecer esta preparación como un extra pagado en cualquier plato.",
    )
    margen_ganancia = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        help_text="Porcentaje de ganancia sobre el costo unitario (ej: 40.00 = 40%). Solo aplica cuando es_adicional=True.",
    )

    class Meta:
        db_table = "vg_preparaciones"
        verbose_name = "Preparación"
        verbose_name_plural = "Preparaciones"

    def __str__(self):
        return self.nombre


class VGRecetaPreparacion(models.Model):
    """
    Componentes de una VGPreparacion. Cada fila es un ingrediente crudo O
    otra preparación (nunca ambos) — así una salsa puede llevar otra
    sub-salsa dentro, con la profundidad de anidado que haga falta.
    """
    preparacion = models.ForeignKey(VGPreparacion, on_delete=models.CASCADE, related_name="componentes")
    ingrediente = models.ForeignKey(
        VGIngrediente, on_delete=models.PROTECT, null=True, blank=True, related_name="usado_en_preparaciones",
    )
    sub_preparacion = models.ForeignKey(
        VGPreparacion, on_delete=models.PROTECT, null=True, blank=True, related_name="usado_en",
    )
    cantidad_requerida = models.DecimalField(max_digits=10, decimal_places=3)

    class Meta:
        db_table = "vg_receta_preparacion"
        verbose_name = "Componente de preparación"
        verbose_name_plural = "Componentes de preparación"
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(ingrediente__isnull=False, sub_preparacion__isnull=True)
                    | models.Q(ingrediente__isnull=True, sub_preparacion__isnull=False)
                ),
                name="receta_preparacion_un_solo_componente",
            ),
        ]

    def __str__(self):
        componente = self.ingrediente or self.sub_preparacion
        return f"{self.preparacion} — {componente} ({self.cantidad_requerida})"


class VGRecetaProducto(models.Model):
    """
    Componentes de un VGProducto. Igual que en VGRecetaPreparacion: cada
    fila es un ingrediente crudo O una preparación (nunca ambos) — un plato
    puede llevar arroz directo y, aparte, una cucharada de una salsa que ya
    tiene su propia receta.
    """
    producto = models.ForeignKey(VGProducto, on_delete=models.CASCADE, related_name="receta")
    ingrediente = models.ForeignKey(
        VGIngrediente, on_delete=models.PROTECT, null=True, blank=True, related_name="usado_en",
    )
    preparacion = models.ForeignKey(
        VGPreparacion, on_delete=models.PROTECT, null=True, blank=True, related_name="usado_en_productos",
    )
    cantidad_requerida = models.DecimalField(max_digits=10, decimal_places=3)

    class Meta:
        db_table = "vg_receta_producto"
        verbose_name = "Ingrediente de receta"
        verbose_name_plural = "Recetas de productos"
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(ingrediente__isnull=False, preparacion__isnull=True)
                    | models.Q(ingrediente__isnull=True, preparacion__isnull=False)
                ),
                name="receta_producto_un_solo_componente",
            ),
            models.UniqueConstraint(
                fields=["producto", "ingrediente"], condition=models.Q(ingrediente__isnull=False),
                name="uniq_producto_ingrediente",
            ),
            models.UniqueConstraint(
                fields=["producto", "preparacion"], condition=models.Q(preparacion__isnull=False),
                name="uniq_producto_preparacion",
            ),
        ]

    def __str__(self):
        componente = self.ingrediente or self.preparacion
        return f"{self.producto} — {componente} ({self.cantidad_requerida})"


class VGCompra(VGAuditoria):
    ESTADOS = [
        ("pendiente", "Pendiente"),
        ("recibido", "Recibido"),
        ("cancelado", "Cancelado"),
    ]
    proveedor_nombre = models.CharField(max_length=150)
    numero_factura_proveedor = models.CharField(
        max_length=100, blank=True,
        help_text="Número de la factura física del proveedor, para poder rastrear de dónde vino este lote.",
    )
    fecha_factura = models.DateField(
        null=True, blank=True,
        help_text="Fecha real de la factura del proveedor (puede ser distinta a cuándo se cargó al sistema).",
    )
    fecha_compra = models.DateTimeField(auto_now_add=True)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    estado = models.CharField(max_length=20, choices=ESTADOS, default="pendiente")

    class Meta:
        db_table = "vg_compras"

    def __str__(self):
        return f"Compra #{self.pk} — {self.proveedor_nombre}"


class VGDetalleCompra(models.Model):
    compra = models.ForeignKey(VGCompra, on_delete=models.CASCADE, related_name="detalles")
    ingrediente = models.ForeignKey(VGIngrediente, on_delete=models.PROTECT, related_name="compras")
    cantidad = models.DecimalField(max_digits=10, decimal_places=2)
    costo_unitario = models.DecimalField(max_digits=12, decimal_places=4)

    class Meta:
        db_table = "vg_detalle_compras"

    @property
    def subtotal(self):
        return self.cantidad * self.costo_unitario

    def __str__(self):
        return f"{self.ingrediente} x {self.cantidad}"


class VGMovimientoInventario(models.Model):
    TIPOS = [
        ("entrada", "Entrada"),
        ("salida", "Salida"),
        ("ajuste", "Ajuste"),
    ]
    ingrediente = models.ForeignKey(VGIngrediente, on_delete=models.PROTECT, related_name="movimientos")
    tipo_movimiento = models.CharField(max_length=10, choices=TIPOS)
    cantidad = models.DecimalField(max_digits=10, decimal_places=2)
    motivo = models.CharField(max_length=255, blank=True)
    id_referencia = models.PositiveIntegerField(null=True, blank=True)
    compra = models.ForeignKey(
        VGCompra, on_delete=models.SET_NULL, null=True, blank=True, related_name="movimientos",
        help_text="Lote de compra que originó este movimiento (solo entradas ligadas a una compra documentada).",
    )
    fecha_movimiento = models.DateTimeField(auto_now_add=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
    )

    class Meta:
        db_table = "vg_movimientos_inventario"

    def __str__(self):
        return f"{self.tipo_movimiento} — {self.ingrediente} ({self.cantidad})"


# ---------------------------------------------------------------------------
# Pedidos y pagos
# ---------------------------------------------------------------------------
class VGPedido(VGAuditoria):
    TIPOS = [
        ("local", "Local"),
        ("llevar", "Para llevar"),
        ("delivery", "Delivery"),
    ]
    ESTADOS = [
        ("pendiente", "Pendiente"),
        ("en_preparacion", "En preparación"),
        ("listo", "Listo"),
        ("entregado", "Entregado"),
        ("pagado", "Pagado"),
        ("cancelado", "Cancelado"),
    ]
    mesa = models.ForeignKey(VGMesa, on_delete=models.SET_NULL, null=True, blank=True, related_name="pedidos")
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="pedidos_atendidos",
    )
    cliente = models.ForeignKey(VGCliente, on_delete=models.SET_NULL, null=True, blank=True, related_name="pedidos")
    tipo_pedido = models.CharField(max_length=10, choices=TIPOS, default="local")
    estado = models.CharField(max_length=20, choices=ESTADOS, default="pendiente")
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    impuesto = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    descuento = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    propina = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    notas = models.TextField(blank=True)

    class Meta:
        db_table = "vg_pedidos"

    def __str__(self):
        return f"Pedido #{self.pk}"


class VGDetallePedido(models.Model):
    ESTADOS = [
        ("pendiente", "Pendiente"),
        ("en_preparacion", "En preparación"),
        ("listo", "Listo"),
        ("entregado", "Entregado"),
    ]
    pedido = models.ForeignKey(VGPedido, on_delete=models.CASCADE, related_name="detalles")
    producto = models.ForeignKey(VGProducto, on_delete=models.PROTECT, related_name="detalles_pedido")
    cantidad = models.PositiveSmallIntegerField(default=1)
    precio_unitario = models.DecimalField(
        max_digits=10, decimal_places=2,
        help_text="Precio por unidad, o precio por kilogramo si producto.venta_por_peso.",
    )
    peso_gramos = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Gramos vendidos cuando producto.venta_por_peso está activo (ej: 250.00). Vacío para productos por unidad.",
    )
    grupo_armado = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Agrupa varias líneas de este mismo pedido en un 'plato armado' (ej: carne + guarniciones). Sin agrupar si está vacío.",
    )
    estado = models.CharField(max_length=20, choices=ESTADOS, default="pendiente")
    notas = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "vg_detalle_pedidos"

    @property
    def subtotal(self):
        peso_factor = (self.peso_gramos / Decimal("1000")) if self.peso_gramos else Decimal("1")
        return self.cantidad * self.precio_unitario * peso_factor

    def __str__(self):
        return f"{self.producto} x {self.cantidad}"


class VGDetallePedidoAdicional(models.Model):
    """
    Un adicional (VGPreparacion con es_adicional=True) que el mesero agregó a una
    línea de pedido, ej. "100g de salsa rosada extra" sobre un plato. El precio_unitario
    se guarda como snapshot del precio de venta calculado al momento del pedido, para
    que un cambio posterior de costo/margen no altere pedidos ya facturados.
    """
    detalle_pedido = models.ForeignKey(VGDetallePedido, on_delete=models.CASCADE, related_name="adicionales")
    preparacion = models.ForeignKey(VGPreparacion, on_delete=models.PROTECT, related_name="usado_en_pedidos")
    cantidad = models.PositiveSmallIntegerField(default=1)
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = "vg_detalle_pedido_adicional"
        verbose_name = "Adicional de pedido"
        verbose_name_plural = "Adicionales de pedido"

    @property
    def subtotal(self):
        return self.cantidad * self.precio_unitario

    def __str__(self):
        return f"{self.preparacion} x {self.cantidad}"


# ---------------------------------------------------------------------------
# Promociones y recomendaciones del chef
# ---------------------------------------------------------------------------
class VGPromocion(VGAuditoria):
    TIPOS_DESCUENTO = [
        ("porcentaje", "Porcentaje"),
        ("monto_fijo", "Monto fijo"),
    ]
    titulo = models.CharField(max_length=150)
    descripcion = models.TextField(blank=True)
    producto = models.ForeignKey(
        VGProducto, on_delete=models.SET_NULL, null=True, blank=True, related_name="promociones",
    )
    imagen_url = models.URLField(blank=True)
    tipo_descuento = models.CharField(max_length=20, choices=TIPOS_DESCUENTO, default="porcentaje")
    valor_descuento = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    duracion_dias = models.PositiveIntegerField(
        default=1, validators=[MinValueValidator(1)],
        help_text="Cantidad de días que el analista definió para la promoción, contados desde fecha_inicio.",
    )
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField(
        null=True, blank=True,
        help_text="Calculada como fecha_inicio + duracion_dias.",
    )
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "vg_promociones"
        verbose_name = "Promoción"
        verbose_name_plural = "Promociones"

    def __str__(self):
        return self.titulo


class VGRecomendacionChef(VGAuditoria):
    producto = models.ForeignKey(
        VGProducto, on_delete=models.CASCADE, related_name="recomendaciones_chef",
    )
    comentario_chef = models.TextField(blank=True)
    imagen_url = models.URLField(blank=True)
    fecha = models.DateField(help_text="Día para el que aplica esta recomendación.")
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "vg_recomendaciones_chef"
        verbose_name = "Recomendación del chef"
        verbose_name_plural = "Recomendaciones del chef"
        constraints = [
            models.UniqueConstraint(
                fields=["producto", "fecha"], name="uniq_recomendacion_producto_fecha",
            ),
        ]

    def __str__(self):
        return f"{self.producto} — {self.fecha}"


# ---------------------------------------------------------------------------
# Tasa de cambio (BCV)
# ---------------------------------------------------------------------------
class VGTasaCambio(models.Model):
    """
    Cache de la tasa oficial BCV (Bs. por USD). Se guarda una fila por día;
    tasa_cambio.obtener_tasa_actual() la refresca sola contra un proveedor
    externo cuando la última fila queda vieja, así no hay que consultar la
    fuente externa en cada request.
    """
    fecha = models.DateField(unique=True)
    tasa = models.DecimalField(max_digits=10, decimal_places=4, validators=[MinValueValidator(0)])
    fuente = models.CharField(max_length=50, default="BCV")
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "vg_tasas_cambio"
        verbose_name = "Tasa de cambio"
        verbose_name_plural = "Tasas de cambio"
        ordering = ["-fecha"]

    def __str__(self):
        return f"{self.fecha} — Bs. {self.tasa}/USD"


class VGPago(models.Model):
    """
    Un pago siempre está ligado a un VGPedido (cobro directo del mesero,
    flujo de hoy) O a una VGFactura (abono de cuentas por cobrar, flujo de
    caja/contabilidad) — nunca a ninguno de los dos, nunca a ambos. Así el
    mismo modelo sirve de abono para el módulo de facturación sin duplicar
    lógica, y el cuadre de caja diario (varagrill/reportes.py) sigue
    sumando por fecha/método sin importar el origen del pago.
    """
    ESTADOS = [
        ("completado", "Completado"),
        ("anulado", "Anulado"),
    ]
    pedido = models.ForeignKey(
        VGPedido, on_delete=models.PROTECT, null=True, blank=True, related_name="pagos",
    )
    factura = models.ForeignKey(
        "varagrill.VGFactura", on_delete=models.PROTECT, null=True, blank=True, related_name="pagos",
    )
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    metodo_pago = models.ForeignKey(
        VGMetodoPago, on_delete=models.PROTECT, related_name="pagos",
    )
    fecha_pago = models.DateTimeField(auto_now_add=True)
    referencia = models.CharField(max_length=100, blank=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default="completado")
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
    )

    class Meta:
        db_table = "vg_pagos"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(pedido__isnull=False) | models.Q(factura__isnull=False),
                name="pago_tiene_pedido_o_factura",
            ),
        ]

    def __str__(self):
        if self.pedido_id:
            return f"Pago {self.monto} — Pedido #{self.pedido_id}"
        return f"Pago {self.monto} — Factura #{self.factura_id}"


class VGImpresoraCaja(VGAuditoria):
    """
    Configuración de la impresora térmica de caja (recibo con detalle y montos que se le
    entrega al cliente al cobrar). A diferencia de las impresoras de cocina —una por
    categoría, ESC/POS crudo por socket directo al puerto 9100, ver
    VGCategoriaProducto.ip_impresora/impresion_termica.py—, esta es una impresora USB
    conectada a la PC de caja y compartida en red vía el "LPD Print Service" de Windows,
    que habla el protocolo LPD/RFC 1179 (ver impresion_lpd.py) en vez de aceptar bytes
    crudos en el socket.

    Se modela como fila única (singleton): la vista de administración siempre lee/edita
    la primera fila (ver obtener_config()), no hace falta elegir "cuál" impresora de caja
    porque solo puede haber una.
    """
    ip = models.CharField(
        max_length=45, blank=True,
        help_text="IP de la PC de caja donde está compartida la impresora.",
    )
    puerto = models.PositiveIntegerField(
        default=515,
        help_text="Puerto del LPD Print Service de Windows (estándar LPD: 515).",
    )
    cola = models.CharField(
        max_length=100, blank=True,
        help_text="Nombre exacto de la cola/impresora tal como quedó compartida en Windows.",
    )
    activo = models.BooleanField(
        default=False,
        help_text="Si está apagado, cobrar un pedido no intenta imprimir el recibo de caja.",
    )

    class Meta:
        db_table = "vg_impresora_caja"
        verbose_name = "Impresora de caja"
        verbose_name_plural = "Impresora de caja"

    def __str__(self):
        return f"Impresora de caja ({self.ip}:{self.puerto})" if self.ip else "Impresora de caja (sin configurar)"

    @classmethod
    def obtener_config(cls):
        return cls.objects.first()
