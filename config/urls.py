"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from pathlib import Path

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import Http404
from django.urls import path, re_path
from django.views.static import serve

from varagrill.api_views import (
    LoginView,
    LogoutView,
    MesaListView,
    ProductoListView,
    SessionStatusView,
    adicionales_disponibles_view,
    admin_catalog_view,
    admin_categorias_view,
    admin_chef_recommendations_view,
    admin_compras_view,
    admin_configuracion_costeo_view,
    admin_impresora_caja_view,
    admin_ingredientes_bulk_create_view,
    admin_ingredientes_import_view,
    admin_mesas_view,
    admin_products_view,
    admin_promotions_view,
    admin_recipes_view,
    admin_users_view,
    compra_detail_view,
    kitchen_order_status_update_view,
    kitchen_orders_view,
    mesa_atendida_mover_view,
    mesas_atendidas_view,
    pedido_create_view,
    pedido_detail_view,
    pedido_reimprimir_comanda_view,
    pedido_update_view,
    pedidos_cobro_view,
    promociones_activas_view,
    product_image_view,
    recomendaciones_chef_activas_view,
    reporte_margen_ganancia_view,
    tasa_cambio_view,
)
from varagrill.compras_views import (
    admin_compra_borrador_agregar_view,
    admin_compra_borrador_confirmar_view,
    admin_compra_borrador_descartar_view,
    admin_compra_borrador_quitar_view,
    admin_compra_borrador_view,
    compra_abono_view,
    cuentas_por_pagar_view,
)
from varagrill.contabilidad_views import (
    admin_metodos_pago_view,
    metodos_pago_activos_view,
    reporte_cuadre_caja_rango_view,
    reporte_cuadre_caja_view,
    reporte_disponibilidad_cuentas_view,
    reporte_estado_resultados_view,
    reporte_movimiento_productos_view,
)
from varagrill.gastos_views import (
    admin_categorias_gasto_view,
    admin_gastos_view,
    gasto_abono_view,
    gasto_detail_view,
)
from varagrill.facturacion_views import (
    clientes_buscar_view,
    cuentas_por_cobrar_view,
    datos_fiscales_view,
    factura_abono_view,
    factura_anular_view,
    factura_detail_view,
    facturas_view,
    prefactura_anular_view,
    prefactura_convertir_view,
    prefacturas_view,
)

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIST_DIR = BASE_DIR / 'frontend' / 'dist'


def serve_frontend(request, path='index.html'):
    if not FRONTEND_DIST_DIR.exists():
        raise Http404('Frontend dist not built yet.')

    final_path = path or 'index.html'
    if final_path == '':
        final_path = 'index.html'

    return serve(request, final_path, str(FRONTEND_DIST_DIR))


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/mesas/', MesaListView.as_view(), name='mesa-list'),
    path('api/productos/', ProductoListView.as_view(), name='producto-list'),
    path('api/productos/<int:product_id>/imagen/', product_image_view, name='producto-imagen'),
    path('api/adicionales/', adicionales_disponibles_view, name='adicionales-list'),
    path('api/pedidos/', pedido_create_view, name='pedido-create'),
    path('api/admin/catalogo/', admin_catalog_view, name='admin-catalog'),
    path('api/admin/catalogo/importar/', admin_ingredientes_import_view, name='admin-catalog-import'),
    path('api/admin/catalogo/importar-simple/', admin_ingredientes_bulk_create_view, name='admin-catalog-bulk-create'),
    path('api/admin/compras/', admin_compras_view, name='admin-compras'),
    path('api/admin/compras/<int:compra_id>/', compra_detail_view, name='admin-compra-detail'),
    path('api/admin/compras/<int:compra_id>/abonos/', compra_abono_view, name='admin-compra-abono'),
    path('api/admin/compras/borrador/', admin_compra_borrador_view, name='admin-compra-borrador'),
    path('api/admin/compras/borrador/agregar/', admin_compra_borrador_agregar_view, name='admin-compra-borrador-agregar'),
    path('api/admin/compras/borrador/quitar/', admin_compra_borrador_quitar_view, name='admin-compra-borrador-quitar'),
    path('api/admin/compras/borrador/descartar/', admin_compra_borrador_descartar_view, name='admin-compra-borrador-descartar'),
    path('api/admin/compras/borrador/confirmar/', admin_compra_borrador_confirmar_view, name='admin-compra-borrador-confirmar'),
    path('api/cuentas-por-pagar/', cuentas_por_pagar_view, name='cuentas-por-pagar'),
    path('api/admin/gastos/', admin_gastos_view, name='admin-gastos'),
    path('api/admin/gastos/<int:gasto_id>/', gasto_detail_view, name='admin-gasto-detail'),
    path('api/admin/gastos/<int:gasto_id>/abonos/', gasto_abono_view, name='admin-gasto-abono'),
    path('api/admin/categorias-gasto/', admin_categorias_gasto_view, name='admin-categorias-gasto'),
    path('api/admin/categorias/', admin_categorias_view, name='admin-categorias'),
    path('api/admin/impresora-caja/', admin_impresora_caja_view, name='admin-impresora-caja'),
    path('api/admin/recetas/', admin_recipes_view, name='admin-recipes'),
    path('api/admin/configuracion-costeo/', admin_configuracion_costeo_view, name='admin-configuracion-costeo'),
    path('api/admin/promociones/', admin_promotions_view, name='admin-promotions'),
    path('api/admin/recomendaciones-chef/', admin_chef_recommendations_view, name='admin-chef-recommendations'),
    path('api/admin/reportes/cuadre-caja/', reporte_cuadre_caja_view, name='admin-reporte-cuadre-caja'),
    path('api/admin/reportes/cuadre-caja-rango/', reporte_cuadre_caja_rango_view, name='admin-reporte-cuadre-caja-rango'),
    path('api/admin/reportes/disponibilidad-cuentas/', reporte_disponibilidad_cuentas_view, name='admin-reporte-disponibilidad-cuentas'),
    path('api/admin/reportes/margen-ganancia/', reporte_margen_ganancia_view, name='admin-reporte-margen-ganancia'),
    path('api/admin/reportes/estado-resultados/', reporte_estado_resultados_view, name='admin-reporte-estado-resultados'),
    path('api/admin/reportes/movimiento-productos/', reporte_movimiento_productos_view, name='admin-reporte-movimiento-productos'),
    path('api/admin/metodos-pago/', admin_metodos_pago_view, name='admin-metodos-pago'),
    path('api/metodos-pago/', metodos_pago_activos_view, name='metodos-pago-activos'),
    path('api/promociones/', promociones_activas_view, name='promociones-activas'),
    path('api/recomendaciones-chef/', recomendaciones_chef_activas_view, name='recomendaciones-chef-activas'),
    path('api/tasa-cambio/', tasa_cambio_view, name='tasa-cambio'),
    path('api/admin/usuarios/', admin_users_view, name='admin-users'),
    path('api/admin/mesas/', admin_mesas_view, name='admin-mesas'),
    path('api/admin/productos/', admin_products_view, name='admin-products'),
    path('api/pedidos/cocina/', kitchen_orders_view, name='kitchen-orders'),
    path('api/pedidos/mesas-atendidas/', mesas_atendidas_view, name='mesas-atendidas'),
    path('api/pedidos/mesas-atendidas/mover/', mesa_atendida_mover_view, name='mesas-atendidas-mover'),
    path('api/pedidos/cobro/', pedidos_cobro_view, name='pedidos-cobro'),
    path('api/pedidos/<int:pedido_id>/', pedido_detail_view, name='pedido-detail'),
    path('api/pedidos/<int:pedido_id>/actualizar/', pedido_update_view, name='pedido-update'),
    path('api/pedidos/<int:pedido_id>/estado/', kitchen_order_status_update_view, name='kitchen-order-status-update'),
    path('api/pedidos/<int:pedido_id>/reimprimir-comanda/', pedido_reimprimir_comanda_view, name='pedido-reimprimir-comanda'),
    path('api/clientes/buscar/', clientes_buscar_view, name='clientes-buscar'),
    path('api/admin/datos-fiscales/', datos_fiscales_view, name='admin-datos-fiscales'),
    path('api/prefacturas/', prefacturas_view, name='prefacturas'),
    path('api/prefacturas/<int:prefactura_id>/convertir/', prefactura_convertir_view, name='prefactura-convertir'),
    path('api/prefacturas/<int:prefactura_id>/anular/', prefactura_anular_view, name='prefactura-anular'),
    path('api/facturas/', facturas_view, name='facturas'),
    path('api/facturas/<int:factura_id>/', factura_detail_view, name='factura-detail'),
    path('api/facturas/<int:factura_id>/abonos/', factura_abono_view, name='factura-abono'),
    path('api/facturas/<int:factura_id>/anular/', factura_anular_view, name='factura-anular'),
    path('api/cuentas-por-cobrar/', cuentas_por_cobrar_view, name='cuentas-por-cobrar'),
    path('api/auth/login/', LoginView.as_view(), name='login'),
    path('api/auth/status/', SessionStatusView.as_view(), name='session-status'),
    path('api/auth/logout/', LogoutView.as_view(), name='logout'),
]

if FRONTEND_DIST_DIR.exists():
    urlpatterns.append(re_path(r'^(?P<path>.*)$', serve_frontend))

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)