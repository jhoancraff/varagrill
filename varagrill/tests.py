import json
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from unittest.mock import patch

from varagrill.models import (
    VGCategoriaGasto,
    VGCategoriaProducto,
    VGCliente,
    VGCompra,
    VGCompraBorrador,
    VGDetalleCompra,
    VGDetalleCompraBorrador,
    VGDetallePedido,
    VGDetallePedidoAdicional,
    VGFactura,
    VGGasto,
    VGIngrediente,
    VGMetodoPago,
    VGMovimientoInventario,
    VGPedido,
    VGPreparacion,
    VGProducto,
    VGRecetaPreparacion,
    VGRecetaProducto,
    VGRol,
    VGTasaCambio,
    VGUsuario,
)
from varagrill.api_views import _importar_ingredientes, _preview_ingrediente_row
from varagrill.unit_rescale import rescale_legacy_units


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
            'unidad': 'g',
            'proveedor': 'Proveedor Uno',
            'stock_minimo': '1.0',
            # El endpoint deriva costo_unitario de precio_total/cantidad (nunca
            # lee un costo_unitario recibido) -- 12.375 / 5.5 = 2.25.
            'precio_total': '12.375',
        }
        response = self.client.post(
            '/api/admin/catalogo/',
            data=json.dumps(inventory_payload),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        ingredient = VGIngrediente.objects.get(nombre='Tomate')
        self.assertEqual(ingredient.stock_actual, 5.5)
        self.assertEqual(ingredient.unidad_medida, 'g')
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
            unidad_medida='g',
            stock_actual='2.00',
            stock_minimo='1.00',
            costo_unitario='0.50',
            ultimo_proveedor='Inicial',
        )
        preparation = VGPreparacion.objects.create(
            nombre='Salsa base',
            rendimiento_cantidad='1.000',
            rendimiento_unidad='ml',
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
                'unidad': 'g',
                'proveedor': 'Proveedor Editado',
                'stock_minimo': '1.50',
                # 6.525 / 7.25 = 0.90 (el endpoint deriva costo_unitario de precio_total/cantidad).
                'precio_total': '6.525',
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
            unidad_medida='g',
            stock_actual='1.00',
            stock_minimo='1.00',
            costo_unitario='1.00',
        )
        preparation = VGPreparacion.objects.create(
            nombre='Salsa temporal',
            rendimiento_cantidad='1.000',
            rendimiento_unidad='ml',
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

    def test_crear_ingrediente_requiere_precio_compra(self):
        response = self.client.post(
            '/api/admin/catalogo/',
            data=json.dumps({
                'tipo': 'crear_ingrediente',
                'nombre': 'Aji dulce',
                'unidad': 'g',
                'contenido_envase': '500',
                'peso_real': '450',
                # precio_compra ausente a propósito.
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(VGIngrediente.objects.filter(nombre='Aji dulce').exists())

    def test_crear_ingrediente_deriva_costo_unitario_de_precio_compra(self):
        response = self.client.post(
            '/api/admin/catalogo/',
            data=json.dumps({
                'tipo': 'crear_ingrediente',
                'nombre': 'Costillas',
                'unidad': 'g',
                'contenido_envase': '1000',
                'peso_real': '850',
                'precio_compra': '4250',
                # Un costo_unitario mandado por el cliente se debe ignorar por completo.
                'costo_unitario': '999',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        ingredient = VGIngrediente.objects.get(nombre='Costillas')
        self.assertEqual(ingredient.precio_compra, Decimal('4250.00'))
        self.assertEqual(ingredient.costo_unitario, Decimal('5.000000'))

    def test_actualizar_ingrediente_recalcula_al_completar_triple(self):
        ingredient = VGIngrediente.objects.create(
            nombre='Queso amarillo',
            unidad_medida='g',
            stock_actual='0',
            costo_unitario='0.30',
        )
        response = self.client.post(
            '/api/admin/catalogo/',
            data=json.dumps({
                'tipo': 'actualizar_ingrediente',
                'id': ingredient.id,
                'nombre': 'Queso amarillo',
                'unidad': 'g',
                'contenido_envase': '2000',
                'peso_real': '2000',
                'precio_compra': '900',
                # También se ignora al completar el trío.
                'costo_unitario': '0.10',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        ingredient.refresh_from_db()
        self.assertEqual(ingredient.costo_unitario, Decimal('0.450000'))

    def test_actualizar_ingrediente_legacy_sin_precio_compra_respeta_costo_manual(self):
        """
        Regresión: el frontend real siempre manda contenido_envase/peso_real (con su
        valor guardado) pero puede mandar precio_compra vacío si el ingrediente es de
        antes de este campo. Editar otro dato (ej. proveedor) sin tocar precio de compra
        NO debe bloquear el guardado ni recalcular el costo.
        """
        ingredient = VGIngrediente.objects.create(
            nombre='Yuca',
            unidad_medida='g',
            stock_actual='0',
            costo_unitario='0.02',
            contenido_envase='1000',
            peso_real='1000',
        )
        response = self.client.post(
            '/api/admin/catalogo/',
            data=json.dumps({
                'tipo': 'actualizar_ingrediente',
                'id': ingredient.id,
                'nombre': 'Yuca',
                'unidad': 'g',
                'proveedor': 'Agromercado Andino',
                'contenido_envase': '1000',
                'peso_real': '1000',
                'precio_compra': None,
                'costo_unitario': '0.02',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        ingredient.refresh_from_db()
        self.assertEqual(ingredient.ultimo_proveedor, 'Agromercado Andino')
        self.assertEqual(ingredient.costo_unitario, Decimal('0.02'))
        self.assertIsNone(ingredient.precio_compra)

    def test_actualizar_ingrediente_envase_peso_parcial_rechazada(self):
        ingredient = VGIngrediente.objects.create(
            nombre='Pimienta blanca', unidad_medida='g', stock_actual='0', costo_unitario='0.05',
        )
        response = self.client.post(
            '/api/admin/catalogo/',
            data=json.dumps({
                'tipo': 'actualizar_ingrediente',
                'id': ingredient.id,
                'nombre': 'Pimienta blanca',
                'unidad': 'g',
                'contenido_envase': '500',
                # peso_real ausente: sigue siendo un par obligatorio, sin cambios.
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        ingredient.refresh_from_db()
        self.assertIsNone(ingredient.contenido_envase)

    def test_ingreso_administrativo_no_desincroniza_costo_unitario_existente(self):
        """
        Ver _costo_unitario_por_compra vs. la división simple: reponer stock desde
        "Ingreso administrativo" (tipo='inventario') sobre un ingrediente que ya tiene su
        trío completo debe respetar la merma, no pisarlo con precio_total/cantidad.
        """
        ingredient = VGIngrediente.objects.create(
            nombre='Punta trasera QA',
            unidad_medida='g',
            stock_actual='0',
            costo_unitario='5.00',
            contenido_envase='1000',
            peso_real='850',
            precio_compra='4250',
        )
        response = self.client.post(
            '/api/admin/catalogo/',
            data=json.dumps({
                'tipo': 'inventario',
                'ingrediente_id': ingredient.id,
                'nombre': 'Punta trasera QA',
                'cantidad': '2000',
                'unidad': 'g',
                'precio_total': '8500',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        ingredient.refresh_from_db()
        # Naive: 8500/2000 = 4.25. Ajustado por merma (850/1000): 8500/(2000*0.85) = 5.00.
        self.assertEqual(ingredient.costo_unitario, Decimal('5.000000'))


class ImportarIngredientesExcelTests(TestCase):
    def setUp(self):
        self.admin_role, _ = VGRol.objects.get_or_create(nombre_role='Administrador')
        self.admin = VGUsuario.objects.create_superuser(
            username='adminimportexcel',
            password='claveAdmin123',
            cedula='99999998',
            email='adminimportexcel@varagrill.test',
            id_role=self.admin_role,
        )

    def test_preview_ingrediente_nuevo_sin_trio_es_error(self):
        row = {
            'fila': 2, 'nombre': 'Chorizo', 'unidad': 'g', 'cantidad': '5000',
            'precio_total': '', 'contenido_envase': '', 'peso_real': '', 'precio_compra': '',
        }
        resultado = _preview_ingrediente_row(row)
        self.assertEqual(resultado['accion'], 'error')

    def test_importar_ingrediente_nuevo_sin_trio_no_crea_nada(self):
        resumen = _importar_ingredientes(
            [{'nombre': 'Chorizo', 'unidad': 'g', 'cantidad': '5000'}],
            self.admin,
        )
        self.assertEqual(resumen['creados'], 0)
        self.assertEqual(len(resumen['errores']), 1)
        self.assertFalse(VGIngrediente.objects.filter(nombre='Chorizo').exists())

    def test_importar_ingrediente_nuevo_con_trio_crea_y_deriva_costo(self):
        resumen = _importar_ingredientes(
            [{
                'nombre': 'Chorizo', 'unidad': 'g', 'cantidad': '5000',
                'contenido_envase': '1000', 'peso_real': '1000', 'precio_compra': '4500',
            }],
            self.admin,
        )
        self.assertEqual(resumen['creados'], 1)
        self.assertEqual(resumen['errores'], [])
        ingredient = VGIngrediente.objects.get(nombre='Chorizo')
        self.assertEqual(ingredient.stock_actual, Decimal('5000'))
        self.assertEqual(ingredient.precio_compra, Decimal('4500.00'))
        self.assertEqual(ingredient.costo_unitario, Decimal('4.500000'))

    def test_importar_ingrediente_existente_actualiza_precio_sin_tocar_stock(self):
        ingredient = VGIngrediente.objects.create(
            nombre='Papeleta', unidad_medida='g', stock_actual='5000', costo_unitario='0.01',
        )
        movimientos_antes = VGMovimientoInventario.objects.filter(ingrediente=ingredient).count()

        resumen = _importar_ingredientes(
            [{
                'nombre': 'Papeleta', 'unidad': 'g', 'cantidad': '',
                'contenido_envase': '1000', 'peso_real': '950', 'precio_compra': '950',
            }],
            self.admin,
        )
        self.assertEqual(resumen['errores'], [])
        self.assertEqual(resumen['actualizados'], 1)
        ingredient.refresh_from_db()
        self.assertEqual(ingredient.stock_actual, Decimal('5000'))
        self.assertEqual(ingredient.contenido_envase, Decimal('1000'))
        self.assertEqual(ingredient.peso_real, Decimal('950'))
        self.assertEqual(ingredient.precio_compra, Decimal('950.00'))
        self.assertEqual(ingredient.costo_unitario, Decimal('1.000000'))
        self.assertEqual(
            VGMovimientoInventario.objects.filter(ingrediente=ingredient).count(),
            movimientos_antes,
        )

    def test_importar_ingrediente_existente_trio_parcial_da_error(self):
        ingredient = VGIngrediente.objects.create(
            nombre='Cilantro', unidad_medida='g', stock_actual='500', costo_unitario='0.02',
        )
        resumen = _importar_ingredientes(
            [{'nombre': 'Cilantro', 'unidad': 'g', 'cantidad': '', 'peso_real': '900'}],
            self.admin,
        )
        self.assertEqual(resumen['actualizados'], 0)
        self.assertEqual(len(resumen['errores']), 1)
        ingredient.refresh_from_db()
        self.assertIsNone(ingredient.peso_real)
        self.assertEqual(ingredient.stock_actual, Decimal('500'))


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
    def test_create_order_triggers_notification_regardless_of_role(self, notify_mock):
        # pedido_create_view llama a _notify_cocina_event('NUEVA_COMANDAS', ...)
        # sin chequeo de rol -- cocina necesita enterarse de CUALQUIER pedido
        # nuevo, sin importar quién lo registró.
        payload = {
            'tipo_pedido': 'local',
            'cliente_nombre': 'Cliente de prueba',
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
        self.assertTrue(notify_mock.called)


class PedidoCobroInventoryDeductionTests(TestCase):
    """
    Al cobrar un pedido, el inventario debe descontarse según la receta de cada producto:
    ingredientes directos, subrecetas prorrateadas por rendimiento (incluyendo subrecetas
    anidadas), productos vinculados a una receta/subreceta, y adicionales.
    """

    def setUp(self):
        self.cajero_role, _ = VGRol.objects.get_or_create(nombre_role='Cajera')
        self.user = VGUsuario.objects.create_user(
            username='cajera',
            password='claveCajera123',
            cedula='33345680',
            email='cajera@varagrill.test',
            id_role=self.cajero_role,
        )
        self.client.force_login(self.user)
        self.category = VGCategoriaProducto.objects.create(nombre='Platos')
        self.metodo_pago, _ = VGMetodoPago.objects.get_or_create(
            nombre='Efectivo', defaults={'es_efectivo': True},
        )

    def _cobrar(self, pedido_ids):
        return self.client.post(
            '/api/pedidos/cobro/',
            data=json.dumps({'pedido_ids': pedido_ids, 'metodo_pago_id': self.metodo_pago.id}),
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
            usuario=self.user, tipo_pedido='local', estado='entregado', subtotal='6.00', total='6.00',
        )
        VGDetallePedido.objects.create(
            pedido=pedido, producto=plato, cantidad=2, precio_unitario='3.00', estado='entregado',
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
            usuario=self.user, tipo_pedido='local', estado='entregado', subtotal='8.00', total='8.00',
        )
        VGDetallePedido.objects.create(
            pedido=pedido, producto=plato, cantidad=1, precio_unitario='8.00', estado='entregado',
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
            usuario=self.user, tipo_pedido='local', estado='entregado', subtotal='6.00', total='6.00',
        )
        detalle = VGDetallePedido.objects.create(
            pedido=pedido, producto=plato, cantidad=1, precio_unitario='6.00', estado='entregado',
        )
        VGDetallePedidoAdicional.objects.create(
            detalle_pedido=detalle, preparacion=extra_queso, cantidad=100, precio_unitario='0.30',
        )

        response = self._cobrar([pedido.id])

        self.assertEqual(response.status_code, 201)
        queso.refresh_from_db()
        # 100g de "queso extra" a partir de un lote 1:1 -> 100g de queso descontados.
        self.assertEqual(queso.stock_actual, Decimal('1900.00'))

    def test_cobro_deducts_chistorra_chorizo_adicionales_por_unidad_and_salsa(self):
        chistorra = VGIngrediente.objects.create(
            nombre='Chistorra', unidad_medida='unidad', stock_actual='10', costo_unitario='0.70',
        )
        chorizo = VGIngrediente.objects.create(
            nombre='Chorizo', unidad_medida='unidad', stock_actual='12', costo_unitario='0.90',
        )
        tomate = VGIngrediente.objects.create(
            nombre='Tomate', unidad_medida='g', stock_actual='4000', costo_unitario='0.02',
        )

        adicional_chistorra = VGPreparacion.objects.create(
            nombre='Chistorra extra', rendimiento_cantidad='1.000', rendimiento_unidad='unidad', es_adicional=True,
        )
        VGRecetaPreparacion.objects.create(
            preparacion=adicional_chistorra, ingrediente=chistorra, cantidad_requerida='1.000',
        )

        adicional_chorizo = VGPreparacion.objects.create(
            nombre='Chorizo extra', rendimiento_cantidad='1.000', rendimiento_unidad='unidad', es_adicional=True,
        )
        VGRecetaPreparacion.objects.create(
            preparacion=adicional_chorizo, ingrediente=chorizo, cantidad_requerida='1.000',
        )

        salsa = VGPreparacion.objects.create(
            nombre='Salsa de la casa', rendimiento_cantidad='1000.000', rendimiento_unidad='g',
        )
        VGRecetaPreparacion.objects.create(
            preparacion=salsa, ingrediente=tomate, cantidad_requerida='300.000',
        )

        plato = VGProducto.objects.create(
            nombre='Plato con salsa', categoria=self.category, precio_venta='12.00', disponible=True,
        )
        VGRecetaProducto.objects.create(producto=plato, preparacion=salsa, cantidad_requerida='200.000')

        pedido = VGPedido.objects.create(
            usuario=self.user, tipo_pedido='local', estado='entregado', subtotal='12.00', total='12.00',
        )
        detalle = VGDetallePedido.objects.create(
            pedido=pedido, producto=plato, cantidad=1, precio_unitario='12.00', estado='entregado',
        )
        VGDetallePedidoAdicional.objects.create(
            detalle_pedido=detalle, preparacion=adicional_chistorra, cantidad=2, precio_unitario='1.40',
        )
        VGDetallePedidoAdicional.objects.create(
            detalle_pedido=detalle, preparacion=adicional_chorizo, cantidad=3, precio_unitario='2.40',
        )

        response = self._cobrar([pedido.id])

        self.assertEqual(response.status_code, 201)

        chistorra.refresh_from_db()
        chorizo.refresh_from_db()
        tomate.refresh_from_db()

        # 2 chistorra extra => 2 unidades; 3 chorizo extra => 3 unidades; la salsa usa 20% del lote de tomate.
        self.assertEqual(chistorra.stock_actual, Decimal('8.00'))
        self.assertEqual(chorizo.stock_actual, Decimal('9.00'))
        self.assertEqual(tomate.stock_actual, Decimal('3940.00'))


class UnidadesMedidaTests(TestCase):
    """
    El negocio ya no maneja kg/l: el catálogo de unidades solo admite
    gramos/mililitros/unidad, los formularios que crean ingredientes lo
    validan, y los datos que ya existían en kg/l se reescalan correctamente
    (misma cantidad física, mismo dinero total) al pasar a g/ml — ver
    varagrill/unit_rescale.py y la migración 0025_solo_gramos_ml_unidad.
    """

    def test_unidades_de_ingrediente_son_solo_gramos_mililitros_unidad(self):
        self.assertEqual(
            VGIngrediente.UNIDADES,
            [('g', 'Gramos'), ('ml', 'Mililitros'), ('unidad', 'Unidad')],
        )

    def test_crear_ingrediente_con_unidad_kg_es_rechazado(self):
        admin_role, _ = VGRol.objects.get_or_create(nombre_role='Administrador')
        admin = VGUsuario.objects.create_superuser(
            username='adminunidades',
            password='claveAdmin123',
            cedula='88888888',
            email='adminunidades@varagrill.test',
            id_role=admin_role,
        )
        self.client.force_login(admin)

        response = self.client.post(
            '/api/admin/compras/borrador/agregar/',
            data=json.dumps({
                'nombre': 'Ingrediente en kilos',
                'unidad': 'kg',
                'cantidad': '10',
                'precio_total': '20',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload['ok'])
        self.assertIn('g, ml o unidad', payload['message'])
        self.assertFalse(VGIngrediente.objects.filter(nombre='Ingrediente en kilos').exists())

    def test_rescale_legacy_units_convierte_kg_y_litros_manteniendo_el_dinero(self):
        # Ingrediente en kg, con stock/costo, una compra histórica y una receta que lo usa.
        carne = VGIngrediente.objects.create(
            nombre='Carne (legacy kg)', unidad_medida='kg',
            stock_actual='100.00', stock_minimo='10.00', costo_unitario='5.0000',
        )
        compra = VGCompra.objects.create(proveedor_nombre='Frigorifico X')
        detalle_compra = VGDetalleCompra.objects.create(
            compra=compra, ingrediente=carne, cantidad='50.00', costo_unitario='4.0000',
        )
        borrador = VGCompraBorrador.objects.create()
        detalle_borrador = VGDetalleCompraBorrador.objects.create(
            borrador=borrador, ingrediente=carne, cantidad='20.00', precio_total='80.00',
        )
        category = VGCategoriaProducto.objects.create(nombre='Platos legacy')
        plato = VGProducto.objects.create(
            nombre='Bistec (legacy)', categoria=category, precio_venta='10.00', disponible=True,
        )
        receta_directa = VGRecetaProducto.objects.create(
            producto=plato, ingrediente=carne, cantidad_requerida='0.200',
        )

        # Subreceta en litros que también usa el ingrediente en kg, y un plato
        # que a su vez usa esa subreceta -- para probar la cascada de las dos
        # direcciones (por ingrediente Y por preparación) en un solo test.
        salsa = VGPreparacion.objects.create(
            nombre='Salsa (legacy l)', rendimiento_cantidad='2.000', rendimiento_unidad='l',
        )
        receta_salsa = VGRecetaPreparacion.objects.create(
            preparacion=salsa, ingrediente=carne, cantidad_requerida='0.500',
        )
        receta_plato_salsa = VGRecetaProducto.objects.create(
            producto=plato, preparacion=salsa, cantidad_requerida='0.300',
        )

        # Ingrediente que YA estaba en gramos no debe tocarse.
        sal = VGIngrediente.objects.create(
            nombre='Sal (ya en g)', unidad_medida='g', stock_actual='500.00', costo_unitario='0.01',
        )

        counts = rescale_legacy_units(
            VGIngrediente=VGIngrediente,
            VGPreparacion=VGPreparacion,
            VGDetalleCompra=VGDetalleCompra,
            VGDetalleCompraBorrador=VGDetalleCompraBorrador,
            VGRecetaProducto=VGRecetaProducto,
            VGRecetaPreparacion=VGRecetaPreparacion,
        )

        self.assertEqual(counts, {
            'ingredientes': 1,
            'preparaciones': 1,
            'detalle_compra': 1,
            'detalle_compra_borrador': 1,
            'receta_producto': 2,
            'receta_preparacion': 1,
        })

        carne.refresh_from_db()
        self.assertEqual(carne.unidad_medida, 'g')
        self.assertEqual(carne.stock_actual, Decimal('100000.00'))
        self.assertEqual(carne.stock_minimo, Decimal('10000.00'))
        self.assertEqual(carne.costo_unitario, Decimal('0.005000'))
        # El valor total del inventario (cantidad x costo) no cambia.
        self.assertEqual(Decimal('100.00') * Decimal('5.0000'), Decimal('100000.00') * Decimal('0.005000'))

        detalle_compra.refresh_from_db()
        self.assertEqual(detalle_compra.cantidad, Decimal('50000.00'))
        self.assertEqual(detalle_compra.costo_unitario, Decimal('0.004000'))
        self.assertEqual(detalle_compra.subtotal, Decimal('50.00') * Decimal('4.0000'))  # $200, invariante

        detalle_borrador.refresh_from_db()
        self.assertEqual(detalle_borrador.cantidad, Decimal('20000.00'))
        self.assertEqual(detalle_borrador.precio_total, Decimal('80.00'))  # dinero total, no se toca
        self.assertEqual(detalle_borrador.costo_unitario, Decimal('80.00') / Decimal('20000.00'))

        receta_directa.refresh_from_db()
        self.assertEqual(receta_directa.cantidad_requerida, Decimal('200.000'))

        salsa.refresh_from_db()
        self.assertEqual(salsa.rendimiento_unidad, 'ml')
        self.assertEqual(salsa.rendimiento_cantidad, Decimal('2000.000'))

        receta_salsa.refresh_from_db()
        self.assertEqual(receta_salsa.cantidad_requerida, Decimal('500.000'))

        receta_plato_salsa.refresh_from_db()
        self.assertEqual(receta_plato_salsa.cantidad_requerida, Decimal('300.000'))

        sal.refresh_from_db()
        self.assertEqual(sal.unidad_medida, 'g')
        self.assertEqual(sal.stock_actual, Decimal('500.00'))
        self.assertEqual(sal.costo_unitario, Decimal('0.010000'))

        # Correr la función una segunda vez es un no-op: ya no queda nada en kg/l.
        second_pass_counts = rescale_legacy_units(
            VGIngrediente=VGIngrediente,
            VGPreparacion=VGPreparacion,
            VGDetalleCompra=VGDetalleCompra,
            VGDetalleCompraBorrador=VGDetalleCompraBorrador,
            VGRecetaProducto=VGRecetaProducto,
            VGRecetaPreparacion=VGRecetaPreparacion,
        )
        self.assertEqual(second_pass_counts, {
            'ingredientes': 0,
            'preparaciones': 0,
            'detalle_compra': 0,
            'detalle_compra_borrador': 0,
            'receta_producto': 0,
            'receta_preparacion': 0,
        })


def _set_tasa_actual(tasa):
    """
    Simula "la tasa BCV actual del sistema" para un test: obtener_tasa_actual()
    devuelve la VGTasaCambio con el fecha_actualizacion (auto_now) mas reciente,
    y no la refresca contra la fuente externa mientras no este vencida (6h) — así
    que crear/actualizar directamente la fila de hoy es suficiente para que la
    vea como "la tasa actual" sin tener que mockear la llamada de red.
    """
    fila, _created = VGTasaCambio.objects.update_or_create(
        fecha=timezone.localdate(), defaults={'tasa': Decimal(str(tasa)), 'fuente': 'BCV'},
    )
    return fila


class TasaCambioAutoAssignTests(TestCase):
    """
    Persistencia automática de tasa: crear un VGGasto, VGCompra o VGPago sin
    mandar tasa_cambio_referencia debe dejarlo con la tasa BCV actual del
    sistema en ese momento (ver tasa_cambio_para_registro/obtener_tasa_actual),
    nunca en NULL.
    """

    def setUp(self):
        self.admin_role, _ = VGRol.objects.get_or_create(nombre_role='Administrador')
        self.admin = VGUsuario.objects.create_superuser(
            username='tasa_admin', password='claveAdmin123', cedula='90000001',
            email='tasa_admin@varagrill.test', id_role=self.admin_role,
        )
        self.client.force_login(self.admin)
        self.metodo_pago = VGMetodoPago.objects.create(nombre='Efectivo test', moneda='USD', es_efectivo=True)
        self.categoria_gasto = VGCategoriaGasto.objects.create(nombre='Servicios test')
        self.tasa_actual = _set_tasa_actual('780.5000')

    def test_gasto_creation_auto_assigns_current_rate(self):
        response = self.client.post(
            '/api/admin/gastos/',
            data=json.dumps({
                'categoria_id': self.categoria_gasto.id,
                'descripcion': 'Factura de luz',
                'monto': '50.00',
                'fecha_gasto': timezone.localdate().isoformat(),
                # tasa_cambio_referencia deliberadamente omitida.
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        gasto = VGGasto.objects.get(descripcion='Factura de luz')
        self.assertEqual(gasto.tasa_cambio_referencia, self.tasa_actual.tasa)
        self.assertEqual(response.json()['gasto']['tasa_cambio_referencia'], str(self.tasa_actual.tasa))

    def test_compra_creation_auto_assigns_current_rate(self):
        # El alta de un ingrediente NUEVO por /api/admin/catalogo/ crea de una vez
        # un VGCompra (ver AdminCatalogApiTests) — no hace falta un flujo aparte.
        response = self.client.post(
            '/api/admin/catalogo/',
            data=json.dumps({
                'tipo': 'inventario',
                'nombre': 'Cebolla test',
                'ingrediente_id': '',
                'cantidad': '10',
                'unidad': 'kg',
                'proveedor': 'Proveedor tasa test',
                'stock_minimo': '1.0',
                'precio_total': '20.00',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        compra = VGCompra.objects.get(proveedor_nombre='Proveedor tasa test')
        self.assertEqual(compra.tasa_cambio_referencia, self.tasa_actual.tasa)

    def test_pago_creation_auto_assigns_current_rate(self):
        cliente = VGCliente.objects.create(nombre='Cliente tasa test')
        factura = VGFactura.objects.create(
            numero_factura=900001, numero_control=900001, cliente=cliente,
            total=Decimal('100.00'), saldo_pendiente=Decimal('100.00'),
        )

        response = self.client.post(
            f'/api/facturas/{factura.id}/abonos/',
            data=json.dumps({'monto': '100.00', 'metodo_pago_id': self.metodo_pago.id}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        pago = factura.pagos.get()
        self.assertEqual(pago.tasa_cambio_referencia, self.tasa_actual.tasa)


class TasaCambioInmutabilidadFinancieraTests(TestCase):
    """
    Un registro ya creado no debe cambiar de valor en bolívares cuando la tasa
    BCV vigente cambia después — tasa_cambio_referencia (y total_bs, derivado
    de ella) quedan congelados a la tasa que estaba activa al momento de
    crearlo.
    """

    def setUp(self):
        self.admin_role, _ = VGRol.objects.get_or_create(nombre_role='Administrador')
        self.admin = VGUsuario.objects.create_superuser(
            username='inmutable_admin', password='claveAdmin123', cedula='90000002',
            email='inmutable_admin@varagrill.test', id_role=self.admin_role,
        )
        self.client.force_login(self.admin)
        self.categoria_gasto = VGCategoriaGasto.objects.create(nombre='Alquiler test')

    def test_gasto_conserva_su_tasa_original_tras_cambiar_la_tasa_actual(self):
        tasa_x = _set_tasa_actual('750.0000')

        response = self.client.post(
            '/api/admin/gastos/',
            data=json.dumps({
                'categoria_id': self.categoria_gasto.id,
                'descripcion': 'Alquiler de septiembre',
                'monto': '200.00',
                'fecha_gasto': timezone.localdate().isoformat(),
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        gasto_id = response.json()['gasto']['id']

        # La tasa "actual" del sistema sube después de crear el gasto.
        tasa_y = _set_tasa_actual('900.0000')
        self.assertNotEqual(tasa_x.tasa, tasa_y.tasa)

        detail_response = self.client.get(f'/api/admin/gastos/{gasto_id}/')
        self.assertEqual(detail_response.status_code, 200)
        gasto_payload = detail_response.json()['gasto']

        esperado_bs = (Decimal('200.00') * tasa_x.tasa).quantize(Decimal('0.01'))
        self.assertEqual(gasto_payload['tasa_cambio_referencia'], str(tasa_x.tasa))
        self.assertEqual(gasto_payload['total_bs'], str(esperado_bs))

        # Y explícitamente NO el valor que daría recalcular con la tasa nueva.
        bs_con_tasa_nueva = (Decimal('200.00') * tasa_y.tasa).quantize(Decimal('0.01'))
        self.assertNotEqual(gasto_payload['total_bs'], str(bs_con_tasa_nueva))


class EstadoResultadosHistoricoAcumuladoTests(TestCase):
    """
    El total en bolívares de un reporte que abarca varios registros con tasas
    congeladas distintas debe ser la suma de cada uno convertido con SU PROPIA
    tasa (registro por registro) — no la suma en USD del período multiplicada
    por la tasa vigente al momento de pedir el reporte (ver
    reporte_estado_resultados_view / _calcular_margen_periodo en
    api_views.py/contabilidad_views.py).
    """

    def setUp(self):
        self.admin_role, _ = VGRol.objects.get_or_create(nombre_role='Administrador')
        self.admin = VGUsuario.objects.create_superuser(
            username='reporte_admin', password='claveAdmin123', cedula='90000003',
            email='reporte_admin@varagrill.test', id_role=self.admin_role,
        )
        self.client.force_login(self.admin)
        self.categoria_gasto = VGCategoriaGasto.objects.create(nombre='Nomina test')

    def test_gastos_total_bs_es_la_suma_registro_por_registro_no_usd_por_tasa_actual(self):
        hoy = timezone.localdate()

        tasa_x = _set_tasa_actual('700.0000')
        gasto_1 = VGGasto.objects.create(
            categoria=self.categoria_gasto, descripcion='Nomina quincena 1',
            monto=Decimal('300.00'), saldo_pendiente=Decimal('300.00'),
            fecha_gasto=hoy, tasa_cambio_referencia=tasa_x.tasa,
        )

        tasa_y = _set_tasa_actual('950.0000')
        gasto_2 = VGGasto.objects.create(
            categoria=self.categoria_gasto, descripcion='Nomina quincena 2',
            monto=Decimal('300.00'), saldo_pendiente=Decimal('300.00'),
            fecha_gasto=hoy, tasa_cambio_referencia=tasa_y.tasa,
        )

        response = self.client.get(
            f'/api/admin/reportes/estado-resultados/?desde={hoy.isoformat()}&hasta={hoy.isoformat()}',
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        esperado_bs = (
            gasto_1.monto * tasa_x.tasa + gasto_2.monto * tasa_y.tasa
        ).quantize(Decimal('0.01'))
        self.assertEqual(payload['gastos_total_bs'], str(esperado_bs))

        # El bug que se corrigió: sumar el USD del período y multiplicarlo por
        # la tasa vigente AL CONSULTAR dá un número distinto — probamos que el
        # endpoint ya NO devuelve ese valor.
        usd_total = gasto_1.monto + gasto_2.monto
        bs_con_tasa_actual_al_consultar = (usd_total * tasa_y.tasa).quantize(Decimal('0.01'))
        self.assertNotEqual(payload['gastos_total_bs'], str(bs_con_tasa_actual_al_consultar))
