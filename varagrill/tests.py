import json
from decimal import Decimal

from django.test import TestCase
from unittest.mock import patch

from varagrill.models import (
    VGCategoriaProducto,
    VGCompra,
    VGDetalleCompra,
    VGDetallePedido,
    VGDetallePedidoAdicional,
    VGIngrediente,
    VGMovimientoInventario,
    VGPedido,
    VGPreparacion,
    VGProducto,
    VGRecetaPreparacion,
    VGRecetaProducto,
    VGRol,
    VGUsuario,
)


class LoginViewTests(TestCase):
    def test_login_creates_session_for_valid_user(self):
        mesero_role, _ = VGRol.objects.get_or_create(nombre_role='Mesero')
        VGUsuario.objects.create_user(
            username='chef',
            password='restaurante123',
            cedula='12345678',
            email='chef@varagrill.test',
            id_role=mesero_role,
        )

        response = self.client.post('/api/auth/login/', {
            'username': 'chef',
            'password': 'restaurante123',
        })

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['authenticated'])
        self.assertEqual(response.json()['user']['username'], 'chef')
        self.assertEqual(response.json()['user']['role'], 'Mesero')
        self.assertIn('_auth_user_id', self.client.session)

    def test_login_accepts_email_identifier(self):
        VGUsuario.objects.create_user(
            username='meseroemail',
            password='claveSegura789',
            cedula='12345670',
            email='mesero.email@varagrill.test',
        )

        response = self.client.post('/api/auth/login/', {
            'username': 'mesero.email@varagrill.test',
            'password': 'claveSegura789',
        })

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['authenticated'])
        self.assertEqual(response.json()['user']['username'], 'meseroemail')

    def test_login_accepts_case_insensitive_username(self):
        VGUsuario.objects.create_user(
            username='Jhoan',
            password='claveJhoan789',
            cedula='12345671',
            email='jhoan@varagrill.test',
        )

        response = self.client.post('/api/auth/login/', {
            'username': 'jhoan',
            'password': 'claveJhoan789',
        })

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['authenticated'])
        self.assertEqual(response.json()['user']['username'], 'Jhoan')

    def test_session_status_returns_authenticated_user_after_login(self):
        VGUsuario.objects.create_user(
            username='mesero',
            password='claveSegura123',
            cedula='12345679',
            email='mesero@varagrill.test',
        )

        self.client.post('/api/auth/login/', {
            'username': 'mesero',
            'password': 'claveSegura123',
        })

        response = self.client.get('/api/auth/status/')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['authenticated'])
        self.assertEqual(response.json()['user']['username'], 'mesero')

    def test_logout_clears_session_and_status(self):
        VGUsuario.objects.create_user(
            username='admincocina',
            password='claveAdmin456',
            cedula='12345680',
            email='admin@varagrill.test',
        )

        self.client.post('/api/auth/login/', {
            'username': 'admincocina',
            'password': 'claveAdmin456',
        })

        logout_response = self.client.post('/api/auth/logout/')
        status_response = self.client.get('/api/auth/status/')

        self.assertEqual(logout_response.status_code, 200)
        self.assertFalse(logout_response.json()['authenticated'])
        self.assertEqual(status_response.status_code, 200)
        self.assertFalse(status_response.json()['authenticated'])
        self.assertNotIn('_auth_user_id', self.client.session)


class AdminCatalogApiTests(TestCase):
    def setUp(self):
        self.admin_role, _ = VGRol.objects.get_or_create(nombre_role='Administrador')
        self.admin = VGUsuario.objects.create_superuser(
            username='admincatalogo',
            password='claveAdmin123',
            cedula='99999999',
            email='admincatalogo@varagrill.test',
            id_role=self.admin_role,
        )
        self.client.force_login(self.admin)

    def test_admin_catalog_endpoint_persists_inventory_recipes_and_beverages(self):
        inventory_payload = {
            'tipo': 'inventario',
            'nombre': 'Tomate',
            'ingrediente_id': '',
            'cantidad': '5.5',
            'unidad': 'kg',
            'proveedor': 'Proveedor Uno',
            'stock_minimo': '1.0',
            'costo_unitario': '2.25',
        }
        response = self.client.post(
            '/api/admin/catalogo/',
            data=json.dumps(inventory_payload),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        ingredient = VGIngrediente.objects.get(nombre='Tomate')
        self.assertEqual(ingredient.stock_actual, 5.5)
        self.assertEqual(ingredient.unidad_medida, 'kg')
        self.assertEqual(ingredient.ultimo_proveedor, 'Proveedor Uno')
        self.assertEqual(ingredient.stock_minimo, Decimal('1.0'))
        self.assertEqual(ingredient.costo_unitario, Decimal('2.25'))
        compra = VGCompra.objects.get(proveedor_nombre='Proveedor Uno')
        detalle = VGDetalleCompra.objects.get(compra=compra, ingrediente=ingredient)
        movimiento = VGMovimientoInventario.objects.get(ingrediente=ingredient, id_referencia=compra.id)
        self.assertEqual(compra.estado, 'recibido')
        self.assertEqual(detalle.cantidad, Decimal('5.5'))
        self.assertEqual(movimiento.tipo_movimiento, 'entrada')

        recipe_payload = {
            'tipo': 'recetas',
            'nombre': 'Salsa roja',
            'rendimiento_cantidad': '1.0',
            'rendimiento_unidad': 'l',
            'componentes': [
                {'tipo': 'ingrediente', 'nombre': 'Tomate', 'cantidad': '0.800'},
                {'tipo': 'sub_preparacion', 'nombre': 'Base de tomate', 'cantidad': '0.200'},
            ],
        }
        response = self.client.post(
            '/api/admin/catalogo/',
            data=json.dumps(recipe_payload),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        preparation = VGPreparacion.objects.get(nombre='Salsa roja')
        self.assertEqual(preparation.rendimiento_cantidad, 1.0)
        self.assertEqual(preparation.componentes.count(), 2)
        self.assertTrue(VGRecetaPreparacion.objects.filter(preparacion=preparation, ingrediente=ingredient).exists())
        sub_preparation = VGPreparacion.objects.get(nombre='Base de tomate')
        self.assertTrue(VGRecetaPreparacion.objects.filter(preparacion=preparation, sub_preparacion=sub_preparation).exists())

        beverage_payload = {
            'tipo': 'bebidas',
            'nombre': 'Jugo de naranja',
            'categoria': 'Jugos',
            'precio': '3.80',
        }
        response = self.client.post(
            '/api/admin/catalogo/',
            data=json.dumps(beverage_payload),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        category = VGCategoriaProducto.objects.get(nombre='Jugos')
        beverage = VGProducto.objects.get(nombre='Jugo de naranja')
        self.assertEqual(beverage.categoria, category)
        self.assertEqual(beverage.precio_venta, Decimal('3.80'))

        response = self.client.get('/api/admin/catalogo/')
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(item['nombre'] == 'Tomate' for item in payload['inventory']))
        self.assertTrue(any(item['nombre'] == 'Salsa roja' for item in payload['recipes']))
        self.assertTrue(any(item['nombre'] == 'Jugo de naranja' for item in payload['beverages']))

    def test_admin_catalog_endpoint_updates_existing_records(self):
        ingredient = VGIngrediente.objects.create(
            nombre='Cebolla',
            unidad_medida='kg',
            stock_actual='2.00',
            stock_minimo='1.00',
            costo_unitario='0.50',
            ultimo_proveedor='Inicial',
        )
        preparation = VGPreparacion.objects.create(
            nombre='Salsa base',
            rendimiento_cantidad='1.000',
            rendimiento_unidad='l',
        )
        category = VGCategoriaProducto.objects.create(nombre='Jugos')
        beverage = VGProducto.objects.create(
            nombre='Jugo de piña',
            categoria=category,
            precio_venta='2.50',
            disponible=True,
        )

        response = self.client.post(
            '/api/admin/catalogo/',
            data=json.dumps({
                'tipo': 'inventario',
                'id': ingredient.id,
                'ingrediente_id': ingredient.id,
                'nombre': 'Cebolla',
                'cantidad': '7.25',
                'unidad': 'kg',
                'proveedor': 'Proveedor Editado',
                'stock_minimo': '1.50',
                'costo_unitario': '0.90',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        ingredient.refresh_from_db()
        self.assertEqual(ingredient.stock_actual, Decimal('9.25'))
        self.assertEqual(ingredient.ultimo_proveedor, 'Proveedor Editado')
        self.assertEqual(ingredient.stock_minimo, Decimal('1.50'))
        self.assertEqual(ingredient.costo_unitario, Decimal('0.90'))
        self.assertTrue(VGCompra.objects.filter(proveedor_nombre='Proveedor Editado').exists())
        self.assertTrue(VGMovimientoInventario.objects.filter(ingrediente=ingredient, tipo_movimiento='entrada').exists())

        response = self.client.post(
            '/api/admin/catalogo/',
            data=json.dumps({
                'tipo': 'recetas',
                'id': preparation.id,
                'nombre': 'Salsa base',
                'rendimiento_cantidad': '2.500',
                'rendimiento_unidad': 'l',
                'componentes': [],
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        preparation.refresh_from_db()
        self.assertEqual(preparation.rendimiento_cantidad, Decimal('2.500'))

        response = self.client.post(
            '/api/admin/catalogo/',
            data=json.dumps({
                'tipo': 'bebidas',
                'id': beverage.id,
                'nombre': 'Jugo de piña',
                'categoria': 'Jugos',
                'precio': '4.20',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        beverage.refresh_from_db()
        self.assertEqual(beverage.precio_venta, Decimal('4.20'))

    def test_admin_catalog_endpoint_deletes_existing_records(self):
        ingredient = VGIngrediente.objects.create(
            nombre='Pimenton',
            unidad_medida='kg',
            stock_actual='1.00',
            stock_minimo='1.00',
            costo_unitario='1.00',
        )
        preparation = VGPreparacion.objects.create(
            nombre='Salsa temporal',
            rendimiento_cantidad='1.000',
            rendimiento_unidad='l',
        )
        category = VGCategoriaProducto.objects.create(nombre='Jugos')
        beverage = VGProducto.objects.create(
            nombre='Jugo de mango',
            categoria=category,
            precio_venta='2.50',
            disponible=True,
        )

        response = self.client.post(
            '/api/admin/catalogo/',
            data=json.dumps({'tipo': 'eliminar_inventario', 'id': ingredient.id}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(VGIngrediente.objects.filter(pk=ingredient.id).exists())

        response = self.client.post(
            '/api/admin/catalogo/',
            data=json.dumps({'tipo': 'eliminar_receta', 'id': preparation.id}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(VGPreparacion.objects.filter(pk=preparation.id).exists())

        response = self.client.post(
            '/api/admin/catalogo/',
            data=json.dumps({'tipo': 'eliminar_bebida', 'id': beverage.id}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(VGProducto.objects.filter(pk=beverage.id).exists())


class AdminUsersApiTests(TestCase):
    def setUp(self):
        self.admin_role, _ = VGRol.objects.get_or_create(nombre_role='Administrador')
        self.mesero_role, _ = VGRol.objects.get_or_create(nombre_role='Mesero')
        self.analista_role, _ = VGRol.objects.get_or_create(nombre_role='Analista')
        self.admin_user = VGUsuario.objects.create_user(
            username='adminusuarios',
            password='claveAdmin999',
            cedula='90000001',
            email='adminusuarios@varagrill.test',
            id_role=self.admin_role,
            is_staff=True,
        )
        self.target_user = VGUsuario.objects.create_user(
            username='meseroexistente',
            password='claveMesero111',
            cedula='90000002',
            email='mesero@varagrill.test',
            id_role=self.mesero_role,
        )

    def test_admin_users_endpoint_requires_admin_role(self):
        outsider = VGUsuario.objects.create_user(
            username='sinpermiso',
            password='claveSinPermiso1',
            cedula='90000003',
            email='sinpermiso@varagrill.test',
            id_role=self.mesero_role,
        )
        self.client.force_login(outsider)

        response = self.client.get('/api/admin/usuarios/')

        self.assertEqual(response.status_code, 401)

    def test_admin_users_endpoint_lists_roles_and_users(self):
        self.client.force_login(self.admin_user)

        response = self.client.get('/api/admin/usuarios/')
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(role['nombre_role'] == 'Administrador' for role in payload['roles']))
        self.assertTrue(any(user['username'] == 'meseroexistente' for user in payload['users']))

    def test_admin_users_endpoint_creates_updates_and_deletes_user(self):
        self.client.force_login(self.admin_user)

        create_response = self.client.post(
            '/api/admin/usuarios/',
            data=json.dumps({
                'action': 'create',
                'username': 'nuevoanalista',
                'password': 'ClaveNueva123',
                'first_name': 'Ana',
                'last_name': 'Lista',
                'email': 'ana@varagrill.test',
                'cedula': '90000004',
                'telefono': '04120000000',
                'fecha_nacimiento': '1995-01-10',
                'role_id': self.analista_role.id,
                'is_active': True,
            }),
            content_type='application/json',
        )
        self.assertEqual(create_response.status_code, 201)
        created_user = VGUsuario.objects.get(username='nuevoanalista')
        self.assertTrue(created_user.check_password('ClaveNueva123'))
        self.assertEqual(created_user.id_role, self.analista_role)

        update_response = self.client.post(
            '/api/admin/usuarios/',
            data=json.dumps({
                'action': 'update',
                'id': created_user.id,
                'username': 'nuevoanalista',
                'password': 'ClaveActualizada456',
                'first_name': 'Ana Maria',
                'last_name': 'Lista',
                'email': 'anamaria@varagrill.test',
                'cedula': '90000004',
                'telefono': '04125555555',
                'fecha_nacimiento': '1995-01-12',
                'role_id': self.admin_role.id,
                'is_active': False,
            }),
            content_type='application/json',
        )
        self.assertEqual(update_response.status_code, 200)
        created_user.refresh_from_db()
        self.assertEqual(created_user.first_name, 'Ana Maria')
        self.assertEqual(created_user.email, 'anamaria@varagrill.test')
        self.assertEqual(created_user.id_role, self.admin_role)
        self.assertTrue(created_user.is_staff)
        self.assertFalse(created_user.is_active)
        self.assertTrue(created_user.check_password('ClaveActualizada456'))

        delete_response = self.client.post(
            '/api/admin/usuarios/',
            data=json.dumps({'action': 'delete', 'id': created_user.id}),
            content_type='application/json',
        )
        self.assertEqual(delete_response.status_code, 200)
        self.assertFalse(VGUsuario.objects.filter(pk=created_user.id).exists())


class KitchenOrdersApiTests(TestCase):
    def setUp(self):
        self.mesero_role, _ = VGRol.objects.get_or_create(nombre_role='Mesero')
        self.admin_role, _ = VGRol.objects.get_or_create(nombre_role='Administrador')
        self.user = VGUsuario.objects.create_user(
            username='cocinero',
            password='claveCocina123',
            cedula='22345680',
            email='cocina@varagrill.test',
            id_role=self.mesero_role,
        )
        self.client.force_login(self.user)

        self.category = VGCategoriaProducto.objects.create(nombre='Platos')
        self.product = VGProducto.objects.create(
            nombre='Pabellon criollo',
            categoria=self.category,
            precio_venta='11.50',
            disponible=True,
        )

    def _create_order(self, estado='pendiente'):
        pedido = VGPedido.objects.create(
            usuario=self.user,
            tipo_pedido='local',
            estado=estado,
            subtotal='11.50',
            total='11.50',
        )
        VGDetallePedido.objects.create(
            pedido=pedido,
            producto=self.product,
            cantidad=1,
            precio_unitario='11.50',
            estado='pendiente',
            notas='Sin cebolla',
        )
        return pedido

    def test_kitchen_orders_endpoint_returns_active_orders(self):
        pedido = self._create_order(estado='pendiente')

        response = self.client.get('/api/pedidos/cocina/?estado=activos')
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['ok'])
        self.assertEqual(len(payload['orders']), 1)
        self.assertEqual(payload['orders'][0]['id'], pedido.id)
        self.assertEqual(payload['orders'][0]['items'][0]['producto'], 'Pabellon criollo')

    def test_kitchen_orders_counts_use_full_queryset_not_limit(self):
        self._create_order(estado='pendiente')
        self._create_order(estado='pendiente')
        self._create_order(estado='en_preparacion')

        response = self.client.get('/api/pedidos/cocina/?estado=activos&limit=1')
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['ok'])
        self.assertEqual(len(payload['orders']), 1)
        self.assertEqual(payload['counts']['pendiente'], 2)
        self.assertEqual(payload['counts']['en_preparacion'], 1)

    def test_kitchen_order_status_update_changes_order_and_items(self):
        pedido = self._create_order(estado='pendiente')

        response = self.client.post(
            f'/api/pedidos/{pedido.id}/estado/',
            data='{"estado": "en_preparacion"}',
            content_type='application/json',
        )

        pedido.refresh_from_db()
        detalle = pedido.detalles.first()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(pedido.estado, 'en_preparacion')
        self.assertEqual(detalle.estado, 'en_preparacion')

    def test_kitchen_order_status_rejects_invalid_transition(self):
        pedido = self._create_order(estado='pendiente')

        response = self.client.post(
            f'/api/pedidos/{pedido.id}/estado/',
            data='{"estado": "entregado"}',
            content_type='application/json',
        )

        pedido.refresh_from_db()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(pedido.estado, 'pendiente')

    @patch('varagrill.api_views._notify_cocina_event')
    def test_create_order_triggers_notification_only_for_mesero(self, notify_mock):
        payload = {
            'tipo_pedido': 'local',
            'items': [
                {
                    'product_id': self.product.id,
                    'cantidad': 1,
                    'notas': '',
                },
            ],
        }

        response = self.client.post(
            '/api/pedidos/',
            data=json.dumps(payload),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(notify_mock.called)

        notify_mock.reset_mock()
        self.user.id_role = self.admin_role
        self.user.save(update_fields=['id_role'])

        response = self.client.post(
            '/api/pedidos/',
            data=json.dumps(payload),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertFalse(notify_mock.called)


class PedidoCobroInventoryDeductionTests(TestCase):
    """
    Al cobrar un pedido, el inventario debe descontarse según la receta de cada producto:
    ingredientes directos, subrecetas prorrateadas por rendimiento (incluyendo subrecetas
    anidadas), productos vinculados a una receta/subreceta, y adicionales.
    """

    def setUp(self):
        self.cajero_role, _ = VGRol.objects.get_or_create(nombre_role='Cajero')
        self.user = VGUsuario.objects.create_user(
            username='cajera',
            password='claveCajera123',
            cedula='33345680',
            email='cajera@varagrill.test',
            id_role=self.cajero_role,
        )
        self.client.force_login(self.user)
        self.category = VGCategoriaProducto.objects.create(nombre='Platos')

    def _cobrar(self, pedido_ids):
        return self.client.post(
            '/api/pedidos/cobro/',
            data=json.dumps({'pedido_ids': pedido_ids, 'metodo_pago': 'efectivo'}),
            content_type='application/json',
        )

    def test_cobro_deducts_direct_ingredient_from_stock(self):
        arroz = VGIngrediente.objects.create(
            nombre='Arroz', unidad_medida='g', stock_actual='5000', costo_unitario='0.01',
        )
        plato = VGProducto.objects.create(
            nombre='Arroz blanco', categoria=self.category, precio_venta='3.00', disponible=True,
        )
        VGRecetaProducto.objects.create(producto=plato, ingrediente=arroz, cantidad_requerida='150.000')

        pedido = VGPedido.objects.create(
            usuario=self.user, tipo_pedido='local', estado='listo', subtotal='6.00', total='6.00',
        )
        VGDetallePedido.objects.create(
            pedido=pedido, producto=plato, cantidad=2, precio_unitario='3.00', estado='listo',
        )

        response = self._cobrar([pedido.id])

        self.assertEqual(response.status_code, 201)
        arroz.refresh_from_db()
        # 150g x 2 platos = 300g descontados de 5000g
        self.assertEqual(arroz.stock_actual, Decimal('4700.00'))
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, 'pagado')
        movimiento = VGMovimientoInventario.objects.get(ingrediente=arroz, id_referencia=pedido.id)
        self.assertEqual(movimiento.tipo_movimiento, 'salida')
        self.assertEqual(movimiento.cantidad, Decimal('300.00'))

    def test_cobro_prorates_subreceta_by_rendimiento_including_nested(self):
        tomate = VGIngrediente.objects.create(
            nombre='Tomate', unidad_medida='g', stock_actual='10000', costo_unitario='0.01',
        )
        base = VGPreparacion.objects.create(
            nombre='Base de tomate', rendimiento_cantidad='500.000', rendimiento_unidad='g',
        )
        VGRecetaPreparacion.objects.create(preparacion=base, ingrediente=tomate, cantidad_requerida='500.000')

        salsa = VGPreparacion.objects.create(
            nombre='Salsa de la casa', rendimiento_cantidad='1000.000', rendimiento_unidad='g',
        )
        VGRecetaPreparacion.objects.create(preparacion=salsa, sub_preparacion=base, cantidad_requerida='400.000')

        plato = VGProducto.objects.create(
            nombre='Pasta con salsa', categoria=self.category, precio_venta='8.00', disponible=True,
        )
        # El plato lleva 200g de una salsa cuyo lote rinde 1000g (usa 1/5 del lote).
        VGRecetaProducto.objects.create(producto=plato, preparacion=salsa, cantidad_requerida='200.000')

        pedido = VGPedido.objects.create(
            usuario=self.user, tipo_pedido='local', estado='listo', subtotal='8.00', total='8.00',
        )
        VGDetallePedido.objects.create(
            pedido=pedido, producto=plato, cantidad=1, precio_unitario='8.00', estado='listo',
        )

        response = self._cobrar([pedido.id])

        self.assertEqual(response.status_code, 201)
        tomate.refresh_from_db()
        # 200g de salsa -> 1/5 del lote de 1000g -> 1/5 de 400g de base -> 80g de base
        # 80g de base -> 80/500 del lote de base -> 16% de 500g de tomate -> 80g de tomate
        self.assertEqual(tomate.stock_actual, Decimal('9920.00'))

    def test_cobro_deducts_ingredients_for_producto_vinculado_a_receta(self):
        pollo = VGIngrediente.objects.create(
            nombre='Pollo', unidad_medida='g', stock_actual='3000', costo_unitario='0.02',
        )
        recetas_category = VGCategoriaProducto.objects.get_or_create(nombre='Recetas')[0]
        receta_maestra = VGProducto.objects.create(
            nombre='Pollo a la plancha (receta)', categoria=recetas_category, precio_venta='0', disponible=False,
        )
        VGRecetaProducto.objects.create(producto=receta_maestra, ingrediente=pollo, cantidad_requerida='250.000')

        plato_vendible = VGProducto.objects.create(
            nombre='Pollo a la plancha', categoria=self.category, precio_venta='9.50', disponible=True,
            receta_vinculada=receta_maestra,
        )

        pedido = VGPedido.objects.create(
            usuario=self.user, tipo_pedido='local', estado='entregado', subtotal='9.50', total='9.50',
        )
        VGDetallePedido.objects.create(
            pedido=pedido, producto=plato_vendible, cantidad=1, precio_unitario='9.50', estado='entregado',
        )

        response = self._cobrar([pedido.id])

        self.assertEqual(response.status_code, 201)
        pollo.refresh_from_db()
        self.assertEqual(pollo.stock_actual, Decimal('2750.00'))

    def test_cobro_deducts_ingredients_for_adicional(self):
        queso = VGIngrediente.objects.create(
            nombre='Queso', unidad_medida='g', stock_actual='2000', costo_unitario='0.03',
        )
        extra_queso = VGPreparacion.objects.create(
            nombre='Queso extra', rendimiento_cantidad='1000.000', rendimiento_unidad='g', es_adicional=True,
        )
        VGRecetaPreparacion.objects.create(preparacion=extra_queso, ingrediente=queso, cantidad_requerida='1000.000')

        plato = VGProducto.objects.create(
            nombre='Hamburguesa', categoria=self.category, precio_venta='6.00', disponible=True,
        )

        pedido = VGPedido.objects.create(
            usuario=self.user, tipo_pedido='local', estado='listo', subtotal='6.00', total='6.00',
        )
        detalle = VGDetallePedido.objects.create(
            pedido=pedido, producto=plato, cantidad=1, precio_unitario='6.00', estado='listo',
        )
        VGDetallePedidoAdicional.objects.create(
            detalle_pedido=detalle, preparacion=extra_queso, cantidad=100, precio_unitario='0.30',
        )

        response = self._cobrar([pedido.id])

        self.assertEqual(response.status_code, 201)
        queso.refresh_from_db()
        # 100g de "queso extra" a partir de un lote 1:1 -> 100g de queso descontados.
        self.assertEqual(queso.stock_actual, Decimal('1900.00'))
