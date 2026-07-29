from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import (
    VGUsuario, VGRol, VGMesa, VGCliente, VGCategoriaProducto, VGProducto,
    VGIngrediente, VGPreparacion, VGRecetaPreparacion, VGRecetaProducto,
    VGCompra, VGDetalleCompra, VGMovimientoInventario, VGPedido, VGDetallePedido, VGPago,
)


# ---------------------------------------------------------------------------
# VGUsuario ya ES el modelo de usuario (AbstractUser), así que sus campos
# extra van directo en el mismo formulario de "Agregar/editar usuario" de
# siempre — sin secciones aparte ni tablas unidas.
# (DjangoUserAdmin y admin.ModelAdmin/TabularInline son nombres del propio
# framework de Django; las clases que yo defino no usan "Admin"/"Inline".)
# ---------------------------------------------------------------------------
@admin.register(VGUsuario)
class VGUsuarioPanel(DjangoUserAdmin):
    model = VGUsuario
    list_display = DjangoUserAdmin.list_display + ("cedula", "id_role")
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Datos del restaurante", {"fields": ("cedula", "telefono", "fecha_nacimiento", "id_role")}),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ("Datos del restaurante", {"fields": ("cedula", "telefono", "fecha_nacimiento", "id_role")}),
    )


admin.site.register(VGRol)
admin.site.register(VGMesa)
admin.site.register(VGCliente)
admin.site.register(VGCategoriaProducto)
admin.site.register(VGMovimientoInventario)


class VGRecetaProductoSeccion(admin.TabularInline):
    model = VGRecetaProducto
    extra = 1


@admin.register(VGProducto)
class VGProductoPanel(admin.ModelAdmin):
    list_display = ("nombre", "categoria", "precio_venta", "disponible")
    list_filter = ("categoria", "disponible")
    search_fields = ("nombre",)
    inlines = [VGRecetaProductoSeccion]


class VGRecetaPreparacionSeccion(admin.TabularInline):
    model = VGRecetaPreparacion
    fk_name = "preparacion"
    extra = 1


@admin.register(VGPreparacion)
class VGPreparacionPanel(admin.ModelAdmin):
    list_display = ("nombre", "rendimiento_cantidad", "rendimiento_unidad")
    inlines = [VGRecetaPreparacionSeccion]


@admin.register(VGIngrediente)
class VGIngredientePanel(admin.ModelAdmin):
    list_display = ("nombre", "stock_actual", "stock_minimo", "unidad_medida")
    list_filter = ("unidad_medida",)


class VGDetalleCompraSeccion(admin.TabularInline):
    model = VGDetalleCompra
    extra = 1


@admin.register(VGCompra)
class VGCompraPanel(admin.ModelAdmin):
    list_display = ("id", "proveedor_nombre", "fecha_compra", "total", "estado")
    list_filter = ("estado",)
    inlines = [VGDetalleCompraSeccion]


class VGDetallePedidoSeccion(admin.TabularInline):
    model = VGDetallePedido
    extra = 1


class VGPagoSeccion(admin.TabularInline):
    model = VGPago
    extra = 0


@admin.register(VGPedido)
class VGPedidoPanel(admin.ModelAdmin):
    list_display = ("id", "mesa", "usuario", "estado", "total", "fecha_creacion")
    list_filter = ("estado", "tipo_pedido")
    inlines = [VGDetallePedidoSeccion, VGPagoSeccion]
