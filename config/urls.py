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
    admin_ingredientes_import_view,
    admin_mesas_view,
    admin_products_view,
    admin_promotions_view,
    admin_recipes_view,
    admin_users_view,
    kitchen_order_status_update_view,
    kitchen_orders_view,
    pedido_create_view,
    pedido_detail_view,
    pedido_update_view,
    pedidos_cobro_view,
    promociones_activas_view,
    product_image_view,
    recomendaciones_chef_activas_view,
    tasa_cambio_view,
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
    path('api/admin/categorias/', admin_categorias_view, name='admin-categorias'),
    path('api/admin/recetas/', admin_recipes_view, name='admin-recipes'),
    path('api/admin/promociones/', admin_promotions_view, name='admin-promotions'),
    path('api/admin/recomendaciones-chef/', admin_chef_recommendations_view, name='admin-chef-recommendations'),
    path('api/promociones/', promociones_activas_view, name='promociones-activas'),
    path('api/recomendaciones-chef/', recomendaciones_chef_activas_view, name='recomendaciones-chef-activas'),
    path('api/tasa-cambio/', tasa_cambio_view, name='tasa-cambio'),
    path('api/admin/usuarios/', admin_users_view, name='admin-users'),
    path('api/admin/mesas/', admin_mesas_view, name='admin-mesas'),
    path('api/admin/productos/', admin_products_view, name='admin-products'),
    path('api/pedidos/cocina/', kitchen_orders_view, name='kitchen-orders'),
    path('api/pedidos/cobro/', pedidos_cobro_view, name='pedidos-cobro'),
    path('api/pedidos/<int:pedido_id>/', pedido_detail_view, name='pedido-detail'),
    path('api/pedidos/<int:pedido_id>/actualizar/', pedido_update_view, name='pedido-update'),
    path('api/pedidos/<int:pedido_id>/estado/', kitchen_order_status_update_view, name='kitchen-order-status-update'),
    path('api/auth/login/', LoginView.as_view(), name='login'),
    path('api/auth/status/', SessionStatusView.as_view(), name='session-status'),
    path('api/auth/logout/', LogoutView.as_view(), name='logout'),
]

if FRONTEND_DIST_DIR.exists():
    urlpatterns.append(re_path(r'^(?P<path>.*)$', serve_frontend))

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)