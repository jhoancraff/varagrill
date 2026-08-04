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
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path

from varagrill.api_views import (
    LoginView,
    LogoutView,
    MesaListView,
    ProductoListView,
    SessionStatusView,
    admin_catalog_view,
    admin_promotions_view,
    admin_recipes_view,
    admin_users_view,
    kitchen_order_status_update_view,
    kitchen_orders_view,
    pedido_create_view,
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/mesas/', MesaListView.as_view(), name='mesa-list'),
    path('api/productos/', ProductoListView.as_view(), name='producto-list'),
    path('api/pedidos/', pedido_create_view, name='pedido-create'),
    path('api/admin/catalogo/', admin_catalog_view, name='admin-catalog'),
    path('api/admin/recetas/', admin_recipes_view, name='admin-recipes'),
    path('api/admin/promociones/', admin_promotions_view, name='admin-promotions'),
    path('api/admin/usuarios/', admin_users_view, name='admin-users'),
    path('api/pedidos/cocina/', kitchen_orders_view, name='kitchen-orders'),
    path('api/pedidos/<int:pedido_id>/estado/', kitchen_order_status_update_view, name='kitchen-order-status-update'),
    path('api/auth/login/', LoginView.as_view(), name='login'),
    path('api/auth/status/', SessionStatusView.as_view(), name='session-status'),
    path('api/auth/logout/', LogoutView.as_view(), name='logout'),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
