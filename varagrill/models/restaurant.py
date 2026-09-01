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
    ip_impresora_secundaria = models.CharField(
        max_length=45, blank=True,
        help_text=(
            "IP de una segunda impresora que también recibe la comanda de esta categoría, en versión "
            "reducida (solo cantidad/peso + nota, sin guarniciones ni adicionales) — ej: Especialidad de "
            "la Casa imprimiendo la carne en cocina Y en la parrilla. Vacío = no duplica."
        ),
    )
    puerto_impresora_secundaria = models.PositiveIntegerField(
        default=9100,
        help_text="Puerto TCP de la impresora secundaria (ESC/POS estándar: 9100).",
    )
    arma_plato_automatico = models.BooleanField(
        default=False,
        help_text=(
            "Si está activo, al mesero agregar un producto de esta categoría al pedido se arma y cierra "
            "su propio 'plato' automáticamente, sin pasar por los botones 'Armar plato'/'Terminar'."
        ),
    )
    prioridad_comanda = models.BooleanField(
        default=False,
        help_text=(
            "Si está activo, los platos de esta categoría siempre salen primero en la comanda —antes que "
            "cualquier otro plato del pedido— y se resaltan con su propio encabezado 'PLATO N - CATEGORÍA', "
            "sin importar el orden en que el mesero los agregó ni cuántas líneas tengan. Pensado para "
            "entradas, que deben salir antes que el plato principal."
        ),
    )
    no_requiere_cocina = models.BooleanField(
        default=False,
        help_text=(
            "Si está activo, un pedido donde TODOS los productos sean de categorías marcadas así se "
            "registra directamente como 'entregado' — salta cocina y queda listo para cobrar de "
            "inmediato, sin imprimir comanda. Pensado para productos empacados para llevar (carnes al "
            "vacío, patacones, empanaditas...) que no necesitan preparación. Si el pedido combina esto "
            "con un plato normal, ese plato sigue el flujo de cocina de siempre."
        ),
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
    margen_ganancia_pct = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        help_text="Porcentaje de ganancia propio de este producto sobre su costo de receta (ej: 40.00 = 40%). Vacío usa el margen por defecto de VGConfiguracionCosteo.",
    )
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
    # Solo estas tres: el negocio ya no maneja kilos ni litros, todo se carga
    # directo en gramos/mililitros/unidad (ej. 100 kg de carne se registra
    # como 100000 g). Ver migración 00XX_solo_gramos_ml_unidad para el
    # reescalado de los datos que ya existían en kg/l.
    UNIDADES = [
        ("g", "Gramos"),
        ("ml", "Mililitros"),
        ("unidad", "Unidad"),
    ]
    nombre = models.CharField(max_length=150)
    unidad_medida = models.CharField(max_length=10, choices=UNIDADES)
    stock_actual = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    stock_minimo = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    # decimal_places=6 (antes 4): al pasar de "costo por kg" a "costo por
    # gramo" (÷1000), un ingrediente barato (ej. sal, hielo) puede quedar por
    # debajo de $0.01/g — con 4 decimales eso se truncaba a 0.
    costo_unitario = models.DecimalField(max_digits=14, decimal_places=6, default=0)
    contenido_envase = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text=(
            "Contenido del envase tal como viene etiquetado, en la misma unidad del "
            "ingrediente (g/ml/unidad) — ej. 1000 para una bolsa de 1kg. Junto con "
            "'Peso real' se usa para calcular el costo real por gramo/ml/unidad al "
            "confirmar una compra (ver compras_views.admin_compra_borrador_confirmar_view)."
        ),
    )
    peso_real = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text=(
            "Cuánto de ese envase queda realmente utilizable después de mermas de "
            "preparación (pelado, deshuesado, limpieza...). Igual al contenido del envase "
            "si no hay pérdida. Si falta este dato o 'Contenido del envase', el costo se "
            "calcula con la cantidad comprada tal cual, sin ajustar por merma."
        ),
    )
    precio_compra = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text=(
            "Precio pagado por el envase/paquete tal como viene etiquetado (el mismo envase "
            "de 'Contenido del envase'). Junto con 'Peso real' determina el costo real por "
            "gramo/ml/unidad (costo_unitario = precio_compra / peso_real), independiente del "
            "contenido nominal del envase — se recalcula automáticamente al crear/editar el "
            "ingrediente."
        ),
    )
    ultimo_proveedor = models.CharField(
        max_length=150, blank=True,
        help_text="Nombre del último proveedor que despachó este ingrediente (sin tabla propia: los proveedores cambian seguido).",
    )
    ingrediente_crudo_equivalente = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="empacados_equivalentes",
        help_text=(
            "Si este ingrediente es un producto empacado para reventa (ej. carne al vacío, patacones "
            "empacados), a qué ingrediente crudo se le repone el stock al abrir un paquete — ver la "
            "acción 'Reponer cocina' en el reporte de ingredientes. Vacío si este ingrediente no es un "
            "empacado."
        ),
    )
    rendimiento_ingrediente_crudo = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text=(
            "Cuánto (en la unidad del ingrediente crudo equivalente) rinde CADA paquete de este "
            "empacado — ej. 500 si cada paquete de churrasco al vacío trae 500g de carne cruda."
        ),
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


class VGGrupoOpcionProducto(models.Model):
    """
    Un grupo de opciones propio de un producto (ej: "Acompañante" en una sopa
    de costilla, con Arepas/Casabe para elegir). A diferencia de VGPreparacion
    con es_adicional=True (extras globales ofrecibles a cualquier plato), este
    grupo está ligado a UN producto específico y aparece como un paso
    obligatorio u opcional al tomar el pedido de ese plato.
    """
    producto = models.ForeignKey(VGProducto, on_delete=models.CASCADE, related_name="grupos_opciones")
    nombre = models.CharField(max_length=100, help_text="Ej: Acompañante, Término de la carne, Extras.")
    obligatorio = models.BooleanField(
        default=True,
        help_text="Si está activo, el mesero debe elegir al menos una opción de este grupo antes de agregar el plato al pedido. Sin efecto en grupos dinámicos (categoria_opciones): esos nunca bloquean, solo avisan.",
    )
    seleccion_multiple = models.BooleanField(
        default=False,
        help_text="Si está activo, se puede elegir más de una opción del grupo (ej: varios extras). Si no, es una sola (ej: arepas O casabe).",
    )
    categoria_opciones = models.ForeignKey(
        VGCategoriaProducto, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="grupos_opciones_dinamicos",
        help_text=(
            "Si se define, este grupo es dinámico: el mesero elige entre los productos "
            "disponibles de esta categoría en ese momento (ej. Guarniciones), en vez de una "
            "lista fija de opciones curadas por el analista. Deja vacío para el modo curado "
            "de siempre (usa las opciones de abajo, ligadas a una subreceta específica)."
        ),
    )
    maximo_selecciones = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Solo aplica a grupos dinámicos: tope de cuántas opciones puede elegir el mesero, sin importar cuántas haya disponibles en la categoría. Vacío = sin tope.",
    )
    gramos_base_racion = models.PositiveIntegerField(
        null=True, blank=True,
        help_text=(
            "Gramos del plato principal que equivalen a 1 ración completa del acompañante elegido "
            "(ej: 250 = 1 ración de guarnición por cada 250g de carne pedidos). Solo tiene efecto en "
            "productos vendidos por peso; si el peso no cae en un múltiplo exacto, se redondea a la "
            "ración más cercana (mínimo 1 ración). Vacío = el acompañante se descuenta a la par del "
            "peso del plato, sin lógica de raciones."
        ),
    )
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "vg_grupos_opcion_producto"
        verbose_name = "Grupo de opciones de producto"
        verbose_name_plural = "Grupos de opciones de producto"
        ordering = ["orden", "id"]

    def __str__(self):
        return f"{self.producto} — {self.nombre}"


class VGOpcionProducto(models.Model):
    """
    Una opción concreta dentro de un VGGrupoOpcionProducto (ej: "Arepas" dentro
    del grupo "Acompañante"). Se apoya en una VGPreparacion ya existente (su
    propia receta) para que elegir esta opción sepa qué descontar de
    inventario y cuánto cuesta, igual que el resto del sistema de recetas.
    """
    grupo = models.ForeignKey(VGGrupoOpcionProducto, on_delete=models.CASCADE, related_name="opciones")
    preparacion = models.ForeignKey(
        VGPreparacion, on_delete=models.PROTECT, related_name="usado_en_opciones_producto",
    )
    precio_adicional = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Cuánto se le suma al precio del plato si se elige esta opción (0 si es una sustitución sin costo).",
    )
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "vg_opciones_producto"
        verbose_name = "Opción de producto"
        verbose_name_plural = "Opciones de producto"
        ordering = ["orden", "id"]

    def __str__(self):
        return f"{self.grupo} — {self.preparacion.nombre}"


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
    ESTADOS_PAGO = [
        ("pendiente", "Pendiente"),
        ("abonada_parcial", "Abonada parcialmente"),
        ("pagada", "Pagada"),
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
    saldo_pendiente = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Deuda viva con el proveedor por este lote (cuenta por pagar). Baja con cada VGAbonoCompra.",
    )
    estado_pago = models.CharField(max_length=20, choices=ESTADOS_PAGO, default="pendiente")
    tasa_cambio_referencia = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)

    class Meta:
        db_table = "vg_compras"

    def __str__(self):
        return f"Compra #{self.pk} — {self.proveedor_nombre}"


class VGDetalleCompra(models.Model):
    compra = models.ForeignKey(VGCompra, on_delete=models.CASCADE, related_name="detalles")
    ingrediente = models.ForeignKey(VGIngrediente, on_delete=models.PROTECT, related_name="compras")
    cantidad = models.DecimalField(max_digits=10, decimal_places=2)
    costo_unitario = models.DecimalField(max_digits=14, decimal_places=6)

    class Meta:
        db_table = "vg_detalle_compras"

    @property
    def subtotal(self):
        return self.cantidad * self.costo_unitario

    def __str__(self):
        return f"{self.ingrediente} x {self.cantidad}"


class VGCompraBorrador(VGAuditoria):
    """
    Factura de proveedor a medio armar: el analista va agregando ingredientes uno por
    uno (ver VGDetalleCompraBorrador) a medida que los lee de la factura física, y esto
    queda guardado en el servidor entre sesiones — si cierra la pestaña o vuelve al día
    siguiente, el borrador sigue ahí. Al confirmar (ver compras_views.confirmar_view) se
    convierte en una VGCompra real y el borrador se elimina. Por decisión del negocio hay
    un único borrador "abierto" compartido a la vez entre todos los administradores.
    """
    ESTADOS = [("abierto", "Abierto"), ("confirmado", "Confirmado")]
    estado = models.CharField(max_length=20, choices=ESTADOS, default="abierto")

    class Meta:
        db_table = "vg_compras_borrador"

    def __str__(self):
        return f"Borrador de compra #{self.pk}"


class VGDetalleCompraBorrador(models.Model):
    borrador = models.ForeignKey(VGCompraBorrador, on_delete=models.CASCADE, related_name="detalles")
    ingrediente = models.ForeignKey(
        VGIngrediente, on_delete=models.PROTECT, related_name="detalles_compra_borrador",
    )
    cantidad = models.DecimalField(max_digits=10, decimal_places=2)
    precio_total = models.DecimalField(
        max_digits=12, decimal_places=2,
        help_text="Lo pagado por esa cantidad de ese ingrediente, según la factura del proveedor.",
    )
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "vg_detalle_compra_borrador"

    @property
    def costo_unitario(self):
        return (self.precio_total / self.cantidad) if self.cantidad else Decimal("0")

    def __str__(self):
        return f"{self.ingrediente} x {self.cantidad}"


class VGAbonoCompra(models.Model):
    """
    Pago del restaurante A un proveedor por una VGCompra (egreso). Es un modelo aparte
    de VGPago a propósito: VGPago representa dinero que ENTRA a caja y alimenta el
    cuadre de caja diario (reportes.py); mezclar egresos ahí contaminaría ese reporte.
    """
    compra = models.ForeignKey(VGCompra, on_delete=models.PROTECT, related_name="abonos")
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    metodo_pago = models.ForeignKey(
        VGMetodoPago, on_delete=models.PROTECT, related_name="abonos_compra",
    )
    referencia = models.CharField(max_length=100, blank=True)
    fecha_pago = models.DateTimeField(auto_now_add=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
    )
    tasa_cambio_referencia = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)

    class Meta:
        db_table = "vg_abonos_compra"

    def __str__(self):
        return f"Abono {self.monto} — Compra #{self.compra_id}"


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
    fecha_inicio_preparacion = models.DateTimeField(
        null=True, blank=True,
        help_text="Momento en que el pedido pasó a 'en_preparacion' (manual o al volver desde 'listo'). Base para el avance automático a 'listo' pasados los minutos configurados — ver _avanzar_pedidos_en_preparacion_vencidos en api_views.py.",
    )
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
    costo_unitario_venta = models.DecimalField(
        max_digits=12, decimal_places=4, null=True, blank=True,
        help_text="Costo de receta por unidad (o por kg si venta_por_peso), congelado en el momento del cobro con los costos de ingredientes vigentes ese día. Vacío para pedidos cobrados antes de que este campo existiera — el reporte de margen cae al costo actual para esos casos.",
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


class VGDetallePedidoOpcion(models.Model):
    """
    La opción elegida (de un VGGrupoOpcionProducto) para una línea de pedido,
    ej. "Acompañante: Arepas" sobre una sopa de costilla. grupo_nombre se
    guarda como snapshot (por si el grupo se renombra/borra después) igual
    que precio_unitario, que ya viene multiplicado por la cantidad/peso de la
    línea (el total que corresponde a esta elección en este pedido, no un
    precio unitario suelto que haya que volver a escalar al mostrarlo).

    Exactamente uno de preparacion/producto está definido: preparacion para el
    modo curado de siempre (grupo ligado a una subreceta específica, ej.
    arepas/casabe); producto cuando la elección viene de un grupo dinámico
    (categoria_opciones en VGGrupoOpcionProducto, ej. "elige 2 guarniciones de
    lo que haya disponible"). Guardar el producto elegido, y no solo su
    subreceta, deja que la impresión de comandas ruquee esa línea a la
    impresora de SU categoría (ej. Cocina) en vez de la del plato principal
    (ej. Parrilla) — ver impresion_termica.py.
    """
    detalle_pedido = models.ForeignKey(VGDetallePedido, on_delete=models.CASCADE, related_name="opciones")
    grupo_nombre = models.CharField(max_length=100)
    grupo = models.ForeignKey(
        VGGrupoOpcionProducto, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="detalles_elegidos",
        help_text="Referencia viva al grupo (además del snapshot grupo_nombre) para poder leer su configuración vigente, ej. gramos_base_racion, al momento de descontar inventario.",
    )
    preparacion = models.ForeignKey(
        VGPreparacion, on_delete=models.PROTECT, null=True, blank=True, related_name="usado_en_pedidos_opcion",
    )
    producto = models.ForeignKey(
        VGProducto, on_delete=models.PROTECT, null=True, blank=True, related_name="usado_en_pedidos_opcion",
    )
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        db_table = "vg_detalle_pedido_opcion"
        verbose_name = "Opción elegida de pedido"
        verbose_name_plural = "Opciones elegidas de pedido"
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(preparacion__isnull=False, producto__isnull=True)
                    | models.Q(preparacion__isnull=True, producto__isnull=False)
                ),
                name="detalle_pedido_opcion_un_solo_origen",
            ),
        ]

    @property
    def subtotal(self):
        return self.precio_unitario

    @property
    def nombre(self):
        return self.producto.nombre if self.producto_id else self.preparacion.nombre

    def __str__(self):
        return f"{self.grupo_nombre}: {self.nombre}"


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
    tasa_cambio_referencia = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)

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


class VGConfiguracionCosteo(VGAuditoria):
    """
    Configuración global de costeo de recetas: fila única (singleton, mismo
    criterio que VGImpresoraCaja.obtener_config()), no una por receta.

    rendimiento_receta_pct es un porcentaje que se le suma al costo bruto
    (suma de ingredientes/subrecetas) de CADA receta de producto (VGRecetaProducto
    — NO de cada subreceta/VGPreparacion, ver _compute_product_recipe_cost y
    _compute_product_unit_cost) para compensar mermas de cocina (ej. una carne
    que pierde peso al cocinarse): costo_con_rendimiento = costo_bruto x
    (1 + rendimiento_receta_pct/100).

    margen_ganancia_defecto_pct es el porcentaje de ganancia que se sugiere por
    defecto al crear un producto nuevo (precio sugerido = costo_con_rendimiento
    x (1 + margen/100)) cuando ese producto no define su propio
    VGProducto.margen_ganancia_pct.
    """
    rendimiento_receta_pct = models.DecimalField(
        max_digits=6, decimal_places=2, default=Decimal('0'),
        help_text="Porcentaje que se suma al costo de CADA receta de producto para compensar mermas de cocina. No aplica a subrecetas.",
    )
    margen_ganancia_defecto_pct = models.DecimalField(
        max_digits=6, decimal_places=2, default=Decimal('50'),
        help_text="Porcentaje de ganancia sugerido por defecto para productos nuevos que no definen su propio margen.",
    )

    class Meta:
        db_table = "vg_configuracion_costeo"
        verbose_name = "Configuración de costeo"
        verbose_name_plural = "Configuración de costeo"

    def __str__(self):
        return f"Rendimiento {self.rendimiento_receta_pct}% / Margen defecto {self.margen_ganancia_defecto_pct}%"

    @classmethod
    def obtener_config(cls):
        config = cls.objects.first()
        if config is None:
            config = cls.objects.create()
        return config
