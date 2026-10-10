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
    VGNotaEntrega,
    VGPedido,
    VGPreparacion,
    VGProducto,
    VGRecetaPreparacion,
    VGRecetaProducto,
    VGRol,
    VGTasaCambio,
    VGUsuario,
)
from varagrill.api_views import _importar_ingredientes, _load_preparation_cost_map, _preview_ingrediente_row
from varagrill.unit_rescale import rescale_legacy_units


class NotasEntregaHistorialTests(TestCase):
    def setUp(self):
        admin_role, _ = VGRol.objects.get_or_create(nombre_role='Administrador')
        admin = VGUsuario.objects.create_superuser(
            username='notas_historial_admin',
            password='claveAdmin123',
            cedula='99000001',
            email='notas_historial_admin@varagrill.test',
            id_role=admin_role,
        )
        self.client.force_login(admin)
        self.metodo_pago = VGMetodoPago.objects.create(nombre='Efectivo historial test', moneda='USD')

    @patch('varagrill.facturacion_views.obtener_tasa_actual', return_value=None)
    def test_date_filter_returns_more_than_200_notes(self, _obtener_tasa_actual):
        VGNotaEntrega.objects.bulk_create([
            VGNotaEntrega(metodo_pago=self.metodo_pago)
            for _ in range(205)
        ])
        fecha = timezone.localdate().isoformat()

        response = self.client.get('/api/notas-entrega/', {'desde': fecha, 'hasta': fecha})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['notas_entrega']), 205)


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

    def test_subrecipe_cost_uses_price_fields_when_ingredient_cost_is_stale_zero(self):
        ingredient = VGIngrediente.objects.create(
            nombre='Queso con costo desincronizado', unidad_medida='g', costo_unitario='0',
            contenido_envase='1000', peso_real='800', precio_compra='400',
        )
        preparation = VGPreparacion.objects.create(
            nombre='Salsa con queso desincronizado', rendimiento_cantidad='1000', rendimiento_unidad='g',
        )
        VGRecetaPreparacion.objects.create(
            preparacion=preparation, ingrediente=ingredient, cantidad_requerida='200',
        )

        costs = _load_preparation_cost_map()[preparation.id]

        self.assertEqual(costs['costo_total'], Decimal('100.000000'))
        self.assertEqual(costs['costo_unitario'], Decimal('0.100000'))

        response = self.client.get('/api/admin/catalogo/')
        self.assertEqual(response.status_code, 200)
        inventory_item = next(item for item in response.json()['inventory'] if item['id'] == ingredient.id)
        self.assertEqual(Decimal(inventory_item['costo_unitario']), Decimal('0.500000'))

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

    def test_importar_ingrediente_existente_suma_cantidad_al_stock(self):
        # -5 + 10 = 5, no 10: "cantidad" es lo que la carga suma, nunca el valor final.
        ingredient = VGIngrediente.objects.create(
            nombre='Cerveza', unidad_medida='unidad', stock_actual='-5', costo_unitario='1.00',
        )
        resumen = _importar_ingredientes(
            [{'nombre': 'Cerveza', 'unidad': 'unidad', 'cantidad': '10'}],
            self.admin,
        )
        self.assertEqual(resumen['errores'], [])
        self.assertEqual(resumen['actualizados'], 1)
        ingredient.refresh_from_db()
        self.assertEqual(ingredient.stock_actual, Decimal('5'))
        movimiento = VGMovimientoInventario.objects.filter(ingrediente=ingredient).latest('fecha_movimiento')
        self.assertEqual(movimiento.cantidad, Decimal('10'))
        self.assertEqual(movimiento.tipo_movimiento, 'entrada')

    def test_importar_ingrediente_existente_cantidad_negativa_resta_del_stock(self):
        ingredient = VGIngrediente.objects.create(
            nombre='Ron', unidad_medida='unidad', stock_actual='10', costo_unitario='1.00',
        )
        resumen = _importar_ingredientes(
            [{'nombre': 'Ron', 'unidad': 'unidad', 'cantidad': '-3'}],
            self.admin,
        )
        self.assertEqual(resumen['errores'], [])
        self.assertEqual(resumen['actualizados'], 1)
        ingredient.refresh_from_db()
        self.assertEqual(ingredient.stock_actual, Decimal('7'))
        movimiento = VGMovimientoInventario.objects.filter(ingrediente=ingredient).latest('fecha_movimiento')
        self.assertEqual(movimiento.cantidad, Decimal('-3'))
        self.assertEqual(movimiento.tipo_movimiento, 'ajuste')


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
            data=json.dumps({
                'pedido_ids': pedido_ids, 'metodo_pago_id': self.metodo_pago.id,
                # La nota de entrega exige los datos del cliente (cedula + nombre).
                'cliente_numero_documento': '99000111', 'cliente_nombre': 'Cliente Test',
            }),
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
        self.assertEqual(compra.moneda_origen, 'USD')

        tasa_nueva = _set_tasa_actual('900.0000')
        cuentas_response = self.client.get('/api/cuentas-por-pagar/')
        self.assertEqual(cuentas_response.status_code, 200)
        cuenta = next(
            cuenta for cuenta in cuentas_response.json()['compras']
            if cuenta['id'] == compra.id and cuenta['tipo'] == 'compra'
        )
        bs_actual = (compra.total * tasa_nueva.tasa).quantize(Decimal('0.01'))
        self.assertEqual(cuenta['saldo_pendiente_bs'], str(bs_actual))

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
    BCV vigente cambia después — tasa_cambio_referencia queda congelada a la
    tasa que estaba activa al momento de crearlo. La única excepción
    deliberada es el bolívar EQUIVALENTE de un gasto en dólares mientras sigue
    pendiente (ver moneda_origen y _serialize_gasto en gastos_views.py): como
    esa deuda aun no se pagó, su equivalente en bs debe reflejar lo que
    costaría saldarla HOY, no lo que costaba el día que se registró — a
    diferencia de un gasto registrado directamente en bolívares, que sí queda
    fijo en ese monto (reportado 2026-09).
    """

    def setUp(self):
        self.admin_role, _ = VGRol.objects.get_or_create(nombre_role='Administrador')
        self.admin = VGUsuario.objects.create_superuser(
            username='inmutable_admin', password='claveAdmin123', cedula='90000002',
            email='inmutable_admin@varagrill.test', id_role=self.admin_role,
        )
        self.client.force_login(self.admin)
        self.categoria_gasto = VGCategoriaGasto.objects.create(nombre='Alquiler test')

    def test_gasto_en_usd_recalcula_su_bs_a_la_tasa_actual_mientras_este_pendiente(self):
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

        # tasa_cambio_referencia (la que se congeló al registrar el gasto) no
        # cambia nunca — eso sigue siendo inmutable.
        self.assertEqual(gasto_payload['tasa_cambio_referencia'], str(tasa_x.tasa))

        # Pero total_bs/saldo_pendiente_bs de un gasto en USD SI se recalculan
        # con la tasa vigente mientras siga pendiente.
        bs_con_tasa_nueva = (Decimal('200.00') * tasa_y.tasa).quantize(Decimal('0.01'))
        self.assertEqual(gasto_payload['total_bs'], str(bs_con_tasa_nueva))
        self.assertEqual(gasto_payload['saldo_pendiente_bs'], str(bs_con_tasa_nueva))

    def test_gasto_en_bs_mantiene_su_monto_en_bolivares_fijo(self):
        tasa_x = _set_tasa_actual('750.0000')

        response = self.client.post(
            '/api/admin/gastos/',
            data=json.dumps({
                'categoria_id': self.categoria_gasto.id,
                'descripcion': 'Jabón',
                'monto_bs': '2000.00',
                'fecha_gasto': timezone.localdate().isoformat(),
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        gasto_id = response.json()['gasto']['id']

        _set_tasa_actual('900.0000')

        detail_response = self.client.get(f'/api/admin/gastos/{gasto_id}/')
        self.assertEqual(detail_response.status_code, 200)
        gasto_payload = detail_response.json()['gasto']

        self.assertEqual(gasto_payload['moneda_origen'], 'VES')
        self.assertEqual(gasto_payload['tasa_cambio_referencia'], str(tasa_x.tasa))
        self.assertEqual(gasto_payload['total_bs'], '2000.00')
        self.assertEqual(gasto_payload['saldo_pendiente_bs'], '2000.00')


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

    def test_ventas_suma_cobrado_de_notas_pagadas_y_parciales(self):
        hoy = timezone.localdate()
        metodo = VGMetodoPago.objects.create(nombre='Efectivo notas estado test', moneda='USD')
        VGNotaEntrega.objects.create(
            metodo_pago=metodo, total=Decimal('12.00'), saldo_pendiente=Decimal('0'),
            estado='pagada', tasa_cambio_referencia=Decimal('100.0000'),
        )
        VGNotaEntrega.objects.create(
            metodo_pago=metodo, total=Decimal('20.00'), saldo_pendiente=Decimal('20.00'),
            estado='pendiente_pago', tasa_cambio_referencia=Decimal('100.0000'),
        )
        VGNotaEntrega.objects.create(
            metodo_pago=metodo, total=Decimal('30.00'), saldo_pendiente=Decimal('5.00'),
            estado='abonada_parcial', tasa_cambio_referencia=Decimal('100.0000'),
        )
        VGNotaEntrega.objects.create(
            metodo_pago=metodo, total=Decimal('40.00'), saldo_pendiente=Decimal('0'),
            estado='anulada', tasa_cambio_referencia=Decimal('100.0000'),
        )

        response = self.client.get(
            f'/api/admin/reportes/estado-resultados/?desde={hoy.isoformat()}&hasta={hoy.isoformat()}',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['ventas_total'], '37.00')
        self.assertEqual(response.json()['ventas_total_bs'], '3700.00')


# ---------------------------------------------------------------------------
# Lotes de punto de venta (POS) — cierre de lotes y acreditacion con un clic
# ---------------------------------------------------------------------------
from datetime import timedelta  # noqa: E402

from django.db import IntegrityError, transaction  # noqa: E402

from varagrill import lotes_pos  # noqa: E402
from varagrill.models import VGCierreCaja, VGLotePOS, VGPago  # noqa: E402
from varagrill.reportes import disponibilidad_por_cuenta, flujo_bancario_mensual, pos_por_cobrar_transitorio  # noqa: E402


class LotesPOSBase(TestCase):
    def setUp(self):
        self.admin_role, _ = VGRol.objects.get_or_create(nombre_role='Administrador')
        self.cajera_role, _ = VGRol.objects.get_or_create(nombre_role='Cajera')
        self.admin = VGUsuario.objects.create_superuser(
            username='pos_admin', password='claveAdmin123', cedula='91000001',
            email='pos_admin@varagrill.test', id_role=self.admin_role,
        )
        self.cajera = VGUsuario.objects.create_user(
            username='pos_cajera', password='claveCajera123', cedula='91000002',
            email='pos_cajera@varagrill.test', id_role=self.cajera_role,
        )
        self.hoy = timezone.localdate()
        self.tasa_hoy = _set_tasa_actual('100.0000')
        self.pos = VGMetodoPago.objects.create(
            nombre='Punto Banesco', moneda='VES', cuenta_bancaria='Banesco', es_punto_venta=True,
        )
        self.otro_pos = VGMetodoPago.objects.create(
            nombre='Punto Mercantil', moneda='VES', cuenta_bancaria='Mercantil', es_punto_venta=True,
        )

    def pago(self, monto_usd='100', tasa='100.0000', metodo=None, usuario=None):
        pedido = VGPedido.objects.create(
            usuario=usuario or self.admin, tipo_pedido='local', estado='entregado',
            subtotal=monto_usd, total=monto_usd,
        )
        pago = VGPago.objects.create(
            pedido=pedido, monto=Decimal(monto_usd), metodo_pago=metodo or self.pos,
            estado='completado', tasa_cambio_referencia=Decimal(tasa), creado_por=usuario or self.admin,
        )
        lotes_pos.asignar_pago_a_lote(pago, usuario or self.admin)
        pago.refresh_from_db()
        return pago

    def cerrar(self, lote):
        return lotes_pos.cerrar_lote(lote, self.admin)

    def acreditar(self, lote):
        return lotes_pos.acreditar_lote(lote, self.admin)

    def saldo_banco(self, nombre, fecha=None):
        _cuentas, bancos = disponibilidad_por_cuenta(fecha or self.hoy)
        return next(b for b in bancos if b['nombre'] == nombre)


class LotePOSCicloTests(LotesPOSBase):
    def test_cobro_pos_crea_y_reutiliza_el_lote_abierto(self):
        p1 = self.pago('40')
        p2 = self.pago('60')
        self.assertEqual(p1.lote_pos_id, p2.lote_pos_id)
        lote = VGLotePOS.objects.get(pk=p1.lote_pos_id)
        self.assertEqual(lote.estado, 'abierto')
        self.assertEqual(lote.monto_bruto_usd, Decimal('100.000000'))
        self.assertEqual(lote.monto_bruto_sistema_bs, Decimal('10000.00'))

    def test_metodo_que_no_es_pos_no_genera_lote(self):
        efectivo = VGMetodoPago.objects.create(nombre='Efectivo USD test', es_efectivo=True)
        pago = self.pago('10', metodo=efectivo)
        self.assertIsNone(pago.lote_pos_id)
        self.assertEqual(VGLotePOS.objects.count(), 0)

    def test_no_pueden_existir_dos_lotes_abiertos_del_mismo_metodo(self):
        self.pago('10')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                VGLotePOS.objects.create(numero=999, metodo_pago=self.pos, fecha_operacion=self.hoy)

    def test_cierre_parcial_el_siguiente_cobro_abre_otro_lote(self):
        primero = self.pago('50').lote_pos
        self.cerrar(primero)
        segundo = self.pago('30').lote_pos
        self.assertNotEqual(primero.pk, segundo.pk)
        primero.refresh_from_db()
        self.assertEqual(primero.estado, 'cerrado')
        self.assertEqual(segundo.estado, 'abierto')
        self.assertEqual(primero.monto_bruto_usd, Decimal('50.000000'))

    def test_no_se_cierra_un_lote_vacio(self):
        pago = self.pago('10')
        pago.estado = 'anulado'
        pago.save(update_fields=['estado'])
        lotes_pos.pago_anulado(pago)
        with self.assertRaises(lotes_pos.LoteError):
            self.cerrar(pago.lote_pos)

    def test_anular_un_pago_recalcula_la_sumatoria_del_lote_abierto(self):
        p1 = self.pago('40')
        p2 = self.pago('60')
        p2.estado = 'anulado'
        p2.save(update_fields=['estado'])
        lotes_pos.pago_anulado(p2)
        lote = VGLotePOS.objects.get(pk=p1.lote_pos_id)
        self.assertEqual(lote.monto_bruto_usd, Decimal('40.000000'))
        self.assertEqual(lote.monto_bruto_sistema_bs, Decimal('4000.00'))

    def test_reabrir_y_anular_exigen_motivo_y_no_aplican_a_acreditados(self):
        lote = self.cerrar(self.pago('10').lote_pos)
        with self.assertRaises(lotes_pos.LoteError):
            lotes_pos.reabrir_lote(lote, self.admin, '')
        lote = lotes_pos.reabrir_lote(lote, self.admin, 'Cierre por error')
        self.assertEqual(lote.estado, 'abierto')
        self.assertIn('Cierre por error', lote.notas)

        lote = self.acreditar(self.cerrar(lote))
        with self.assertRaises(lotes_pos.LoteError):
            lotes_pos.reabrir_lote(lote, self.admin, 'x')
        with self.assertRaises(lotes_pos.LoteError):
            lotes_pos.anular_lote(lote, self.admin, 'x')

    def test_anular_lote_cerrado_mueve_sus_cobros_al_lote_abierto(self):
        cerrado = self.cerrar(self.pago('25').lote_pos)
        lotes_pos.anular_lote(cerrado, self.admin, 'Lote duplicado')
        cerrado.refresh_from_db()
        self.assertEqual(cerrado.estado, 'anulado')
        abierto = VGLotePOS.objects.get(metodo_pago=self.pos, estado='abierto')
        self.assertEqual(abierto.monto_bruto_usd, Decimal('25.000000'))

    def test_cobro_de_lote_cerrado_no_cambia_de_cuenta(self):
        pago = self.pago('10')
        self.cerrar(pago.lote_pos)
        pago.refresh_from_db()
        self.assertIn('lote POS', lotes_pos.validar_cambio_metodo_pago(pago))


class AcreditacionLotePOSTests(LotesPOSBase):
    def test_metodo_vacio_del_mismo_banco_no_oculta_el_saldo_en_bs(self):
        metodo_sin_movimientos = VGMetodoPago.objects.create(
            nombre='Transferencia Banesco', moneda='VES', cuenta_bancaria='Banesco',
        )

        banco = self.saldo_banco('Banesco')

        self.assertEqual(banco['saldo_disponible_bs'], Decimal('0'))
        metodo = next(m for m in banco['metodos'] if m['id'] == metodo_sin_movimientos.id)
        self.assertEqual(metodo['saldo_disponible_bs'], Decimal('0'))

    def test_disponibilidad_solo_suma_cuando_se_acredita_el_lote(self):
        lote = self.pago('100').lote_pos

        # Abierto: nada disponible, todo por acreditar.
        banco = self.saldo_banco('Banesco')
        self.assertEqual(banco['saldo_disponible'], Decimal('0'))
        self.assertEqual(banco['por_acreditar_usd'], Decimal('100.000000'))

        lote = self.cerrar(lote)
        banco = self.saldo_banco('Banesco')
        self.assertEqual(banco['saldo_disponible'], Decimal('0'))
        self.assertEqual(banco['por_acreditar_usd'], Decimal('100.000000'))
        self.assertEqual(len(banco['lotes_por_acreditar']), 1)

        # Un clic: el monto del lote suma completo a la cuenta, en USD y en Bs.
        lote = self.acreditar(lote)
        self.assertEqual(lote.estado, 'acreditado')
        self.assertEqual(lote.fecha_abono_real, self.hoy)
        self.assertEqual(lote.acreditado_por, self.admin)
        banco = self.saldo_banco('Banesco')
        self.assertEqual(banco['saldo_disponible'], Decimal('100.000000'))
        self.assertEqual(banco['saldo_disponible_bs'], Decimal('10000.00'))
        self.assertEqual(banco['por_acreditar_usd'], Decimal('0'))

    def test_solo_se_acredita_un_lote_cerrado_y_una_sola_vez(self):
        lote = self.pago('100').lote_pos
        with self.assertRaises(lotes_pos.LoteError):
            self.acreditar(lote)  # abierto: primero se cierra
        lote = self.acreditar(self.cerrar(lote))
        with self.assertRaises(lotes_pos.LoteError):
            self.acreditar(lote)  # doble clic: no suma dos veces
        self.assertEqual(self.saldo_banco('Banesco')['saldo_disponible'], Decimal('100.000000'))

    def test_acreditado_se_ve_solo_desde_su_fecha(self):
        self.acreditar(self.cerrar(self.pago('100').lote_pos))
        ayer = self.hoy - timedelta(days=1)
        self.assertEqual(self.saldo_banco('Banesco', ayer)['saldo_disponible'], Decimal('0'))
        self.assertEqual(self.saldo_banco('Banesco', self.hoy)['saldo_disponible'], Decimal('100.000000'))

    def test_revertir_acreditacion_quita_el_monto_del_saldo(self):
        lote = self.acreditar(self.cerrar(self.pago('100').lote_pos))
        with self.assertRaises(lotes_pos.LoteError):
            lotes_pos.revertir_acreditacion(lote, self.admin, '')
        lote = lotes_pos.revertir_acreditacion(lote, self.admin, 'Click por error')
        self.assertEqual(lote.estado, 'cerrado')
        self.assertIn('Click por error', lote.notas)
        self.assertEqual(self.saldo_banco('Banesco')['saldo_disponible'], Decimal('0'))
        self.assertEqual(self.saldo_banco('Banesco')['por_acreditar_usd'], Decimal('100.000000'))

    def test_transitorio_pos_por_cobrar(self):
        self.cerrar(self.pago('100').lote_pos)
        self.pago('50', metodo=self.otro_pos)  # lote abierto de otro banco
        data = pos_por_cobrar_transitorio(self.hoy)
        self.assertEqual(data['total_usd'], Decimal('150.000000'))
        self.assertEqual({item['banco'] for item in data['por_banco']}, {'Banesco', 'Mercantil'})

    def test_flujo_bancario_cuenta_el_lote_una_sola_vez_el_dia_que_se_acredita(self):
        self.assertEqual(flujo_bancario_mensual(self.hoy.year, self.hoy.month, 'Banesco')['total_entrada'], Decimal('0'))
        lote = self.cerrar(self.pago('100').lote_pos)
        self.assertEqual(flujo_bancario_mensual(self.hoy.year, self.hoy.month, 'Banesco')['total_entrada'], Decimal('0'))
        self.acreditar(lote)
        flujo = flujo_bancario_mensual(self.hoy.year, self.hoy.month, 'Banesco')
        dia = next(d for d in flujo['dias'] if d['fecha'] == self.hoy)
        self.assertEqual(dia['entrada'], Decimal('100.000000'))
        self.assertEqual(flujo['total_entrada'], Decimal('100.000000'))

    def test_backfill_historico_no_altera_el_saldo_conocido(self):
        metodo = VGMetodoPago.objects.create(nombre='Punto viejo', moneda='VES', cuenta_bancaria='Provincial')
        for monto, dias_atras in (('40', 20), ('60', 15)):
            pedido = VGPedido.objects.create(usuario=self.admin, tipo_pedido='local', estado='entregado', subtotal=monto, total=monto)
            pago = VGPago.objects.create(
                pedido=pedido, monto=Decimal(monto), metodo_pago=metodo, estado='completado',
                tasa_cambio_referencia=Decimal('100'),
            )
            VGPago.objects.filter(pk=pago.pk).update(fecha_pago=timezone.now() - timedelta(days=dias_atras))
        antes = self.saldo_banco('Provincial')['saldo_disponible']
        self.assertEqual(antes, Decimal('100.000000'))

        metodo.es_punto_venta = True
        metodo.save()
        self.assertEqual(lotes_pos.backfill_historico_metodo(metodo), 2)
        self.assertEqual(self.saldo_banco('Provincial')['saldo_disponible'], antes)
        self.assertEqual(VGLotePOS.objects.filter(metodo_pago=metodo, estado='acreditado').count(), 2)
        # Idempotente: ya no quedan cobros sin lote.
        self.assertEqual(lotes_pos.backfill_historico_metodo(metodo), 0)


class CierreCajaPOSApiTests(LotesPOSBase):
    def post_cuadre(self, **payload):
        return self.client.post(
            '/api/admin/reportes/cuadre-caja/', data=json.dumps({'fecha': self.hoy.isoformat(), **payload}),
            content_type='application/json',
        )

    def test_cerrar_caja_autoclausura_lotes_y_persiste_el_snapshot(self):
        lote = self.pago('100').lote_pos
        self.client.force_login(self.cajera)

        response = self.post_cuadre(action='cerrar_caja')
        self.assertEqual(response.status_code, 201, response.content)
        cierre = VGCierreCaja.objects.get(fecha=self.hoy)
        lote.refresh_from_db()
        self.assertEqual(lote.estado, 'cerrado')
        self.assertFalse(cierre.conteo_efectivo_realizado)
        self.assertEqual(cierre.diferencia, Decimal('0'))
        self.assertEqual(cierre.pos_por_acreditar_usd, Decimal('100.000000'))
        self.assertFalse(VGLotePOS.objects.filter(estado='abierto').exists())

        # El snapshot del cierre es inmutable: acreditar despues no lo cambia.
        self.acreditar(lote)
        cierre.refresh_from_db()
        self.assertEqual(cierre.pos_por_acreditar_usd, Decimal('100.000000'))

    def test_cerrar_caja_sin_lotes(self):
        self.client.force_login(self.cajera)
        self.assertEqual(self.post_cuadre(action='cerrar_caja').status_code, 201)

    def test_cuadre_trae_el_bloque_pos_y_la_disponibilidad_real(self):
        self.pago('100')
        self.client.force_login(self.admin)
        data = self.client.get(f'/api/admin/reportes/cuadre-caja/?fecha={self.hoy.isoformat()}').json()
        self.assertEqual(data['pos']['cobrado_dia_usd'], '100.000000')
        self.assertEqual(data['pos']['por_acreditar_usd'], '100.000000')
        self.assertEqual(data['pos']['acreditado_hoy_usd'], '0')
        self.assertEqual(Decimal(data['pos']['disponibilidad_real_usd']), Decimal('0'))

    def test_endpoint_lotes_cierra_y_acredita_con_un_clic(self):
        lote = self.pago('100').lote_pos
        self.client.force_login(self.cajera)

        def post(**payload):
            return self.client.post('/api/admin/lotes-pos/', data=json.dumps(payload), content_type='application/json')

        r = post(action='cerrar_lote', lote_id=lote.id)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()['lote']['estado'], 'cerrado')

        r = post(action='acreditar_lote', lote_id=lote.id)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()['lote']['estado'], 'acreditado')
        self.assertEqual(self.saldo_banco('Banesco')['saldo_disponible'], Decimal('100.000000'))

        # Revertir, reabrir y anular son de administrador/contador, no de la cajera.
        self.assertEqual(post(action='revertir_acreditacion', lote_id=lote.id, motivo='x').status_code, 401)
        self.client.force_login(self.admin)
        self.assertEqual(post(action='revertir_acreditacion', lote_id=lote.id, motivo='x').status_code, 200)

        listado = self.client.get('/api/admin/lotes-pos/').json()
        self.assertTrue(any(item['id'] == lote.id and item['estado'] == 'cerrado' for item in listado['lotes']))

    def test_marcar_punto_venta_valida_y_hace_backfill(self):
        self.client.force_login(self.admin)

        def post(**payload):
            return self.client.post('/api/admin/metodos-pago/', data=json.dumps(payload), content_type='application/json')

        usd = VGMetodoPago.objects.create(nombre='Zelle test', moneda='USD')
        self.assertEqual(post(action='marcar_punto_venta', id=usd.id, es_punto_venta=True).status_code, 400)

        nuevo = VGMetodoPago.objects.create(nombre='Punto Provincial', moneda='VES', cuenta_bancaria='Provincial')
        r = post(action='marcar_punto_venta', id=nuevo.id, es_punto_venta=True)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()['metodo_pago']['es_punto_venta'])

        # Con un lote sin acreditar no se le puede quitar la marca.
        nuevo.refresh_from_db()
        self.pago('10', metodo=nuevo)
        self.assertEqual(post(action='marcar_punto_venta', id=nuevo.id, es_punto_venta=False).status_code, 400)


class ImpresionCierreLotePOSTests(LotesPOSBase):
    def test_ticket_lista_cada_cobro_y_el_total_en_bs(self):
        from varagrill.impresion_lpd import _build_cierre_lote_pos_bytes
        self.pago('40')
        lote = self.pago('60').lote_pos
        lote = self.cerrar(lote)
        texto = _build_cierre_lote_pos_bytes(lote).decode('cp1252', errors='replace')
        self.assertIn('CIERRE DE LOTE POS', texto)
        self.assertIn(f'LOTE-{lote.numero:06d}', texto)
        self.assertIn('COBROS DEL LOTE (2)', texto)
        self.assertIn('Bs.4.000,00', texto)   # 40 USD x 100
        self.assertIn('Bs.6.000,00', texto)   # 60 USD x 100
        self.assertIn('TOTAL Bs.', texto)
        self.assertIn('10.000,00', texto)
        self.assertIn('REIMPRESION', _build_cierre_lote_pos_bytes(lote, es_reimpresion=True).decode('cp1252', errors='replace'))

    def test_cerrar_lote_imprime_y_un_fallo_de_impresora_no_tumba_el_cierre(self):
        from unittest.mock import patch
        lote = self.pago('100').lote_pos
        self.client.force_login(self.cajera)

        def post(**payload):
            return self.client.post('/api/admin/lotes-pos/', data=json.dumps(payload), content_type='application/json')

        with patch('varagrill.contabilidad_views.imprimir_cierre_lote_pos', return_value=(False, 'No hay una impresora de caja activa configurada.')) as impresora:
            r = post(action='cerrar_lote', lote_id=lote.id)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()['lote']['estado'], 'cerrado')
        self.assertFalse(r.json()['impresion']['ok'])
        self.assertIn('No se pudo imprimir', r.json()['message'])
        impresora.assert_called_once()

        with patch('varagrill.contabilidad_views.imprimir_cierre_lote_pos', return_value=(True, None)) as impresora:
            r = post(action='imprimir_lote', lote_id=lote.id)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(impresora.call_args.kwargs['es_reimpresion'])

        with patch('varagrill.contabilidad_views.imprimir_cierre_lote_pos', return_value=(False, 'sin impresora')):
            self.assertEqual(post(action='imprimir_lote', lote_id=lote.id).status_code, 502)

    def test_cerrar_caja_imprime_los_lotes_que_se_cierran_solos(self):
        from unittest.mock import patch
        self.pago('100')
        self.client.force_login(self.cajera)
        with patch('varagrill.contabilidad_views.imprimir_cierre_lote_pos', return_value=(True, None)) as impresora:
            r = self.client.post(
                '/api/admin/reportes/cuadre-caja/',
                data=json.dumps({'action': 'cerrar_caja', 'fecha': self.hoy.isoformat()}), content_type='application/json',
            )
        self.assertEqual(r.status_code, 201, r.content)
        impresora.assert_called_once()
        self.assertIn('Se imprimió el detalle', r.json()['message'])


class MontoBsDelLoteInmutableTests(LotesPOSBase):
    """El monto en Bs de un lote es lo que se cobro en el punto: la tasa BCV no lo toca nunca."""

    def test_cambiar_la_tasa_bcv_no_mueve_ningun_monto_en_bs(self):
        from varagrill.impresion_lpd import _build_cierre_lote_pos_bytes
        from varagrill.models import VGTasaCambio

        # Cobros en Bs: 1.234,56 y 8.765,44 (suman 10.000,00), tasa del dia 100.
        pedido = VGPedido.objects.create(usuario=self.admin, tipo_pedido='local', estado='entregado', subtotal='1', total='1')
        for bs in ('1234.56', '8765.44'):
            usd = (Decimal(bs) / Decimal('100')).quantize(Decimal('0.000001'))
            pago = VGPago.objects.create(
                pedido=pedido, monto=usd, metodo_pago=self.pos, estado='completado',
                tasa_cambio_referencia=Decimal('100.0000'), creado_por=self.admin,
            )
            lotes_pos.asignar_pago_a_lote(pago, self.admin)
        lote = VGLotePOS.objects.get(metodo_pago=self.pos, estado='abierto')
        self.assertEqual(lote.monto_bruto_sistema_bs, Decimal('10000.00'))
        lote = self.cerrar(lote)

        # El BCV se dispara: hoy y en los dias siguientes.
        _set_tasa_actual('250.0000')
        VGTasaCambio.objects.create(fecha=self.hoy + timedelta(days=1), tasa=Decimal('400.0000'))

        lote.refresh_from_db()
        self.assertEqual(lote.monto_bruto_sistema_bs, Decimal('10000.00'))
        self.assertIn('10.000,00', _build_cierre_lote_pos_bytes(lote).decode('cp1252', errors='replace'))

        lote = self.acreditar(lote)
        self.assertEqual(lote.monto_bruto_sistema_bs, Decimal('10000.00'))
        self.assertEqual(self.saldo_banco('Banesco')['saldo_disponible_bs'], Decimal('10000.00'))
        flujo = flujo_bancario_mensual(self.hoy.year, self.hoy.month, 'Banesco')
        dia = next(d for d in flujo['dias'] if d['fecha'] == self.hoy)
        self.assertEqual(dia['entrada_bs'], Decimal('10000.00'))

        self.client.force_login(self.admin)
        detalle = self.client.get(f'/api/admin/lotes-pos/?lote_id={lote.id}').json()['lote']
        self.assertEqual(detalle['monto_bs'], '10000.00')
        self.assertEqual(sum(Decimal(pago['monto_bs']) for pago in detalle['pagos']), Decimal('10000.00'))


class EfectivoPorMonedaTests(LotesPOSBase):
    def test_separa_el_efectivo_en_bs_y_dolares_y_suma_el_esperado(self):
        from varagrill.models import VGAbonoGasto
        from varagrill.reportes import efectivo_esperado_dia, efectivo_esperado_por_moneda

        efectivo_bs = VGMetodoPago.objects.create(nombre='Efectivo Bs test', moneda='VES', es_efectivo=True)
        efectivo_usd = VGMetodoPago.objects.create(nombre='Efectivo USD test2', moneda='USD', es_efectivo=True)
        # Cobros: Bs 5.000 (tasa 100 = $50) y $20 en dolares. El punto de venta NO cuenta como efectivo.
        self.pago('50', tasa='100.0000', metodo=efectivo_bs)
        self.pago('20', metodo=efectivo_usd)
        self.pago('99', metodo=self.pos)
        # Gasto pagado en efectivo en bolivares: Bs 1.000 ($10 a tasa 100) y otro en dolares: $5.
        categoria = VGCategoriaGasto.objects.create(nombre='Aseo test')
        for monto, metodo, tasa in (('10', efectivo_bs, '100.0000'), ('5', efectivo_usd, None)):
            gasto = VGGasto.objects.create(
                categoria=categoria, descripcion='Gasto en efectivo', monto=Decimal(monto), saldo_pendiente=0,
                estado_pago='pagado', fecha_gasto=self.hoy,
            )
            VGAbonoGasto.objects.create(
                gasto=gasto, monto=Decimal(monto), metodo_pago=metodo, tasa_cambio_referencia=Decimal(tasa) if tasa else None,
            )

        datos = efectivo_esperado_por_moneda(self.hoy)
        self.assertEqual(datos['bs'], Decimal('4000.00'))      # 5.000 − 1.000
        self.assertEqual(datos['usd'], Decimal('15.000000'))   # 20 − 5
        self.assertEqual(datos['usd'] + datos['bs_en_usd'], efectivo_esperado_dia(self.hoy))

        # El BCV cambia: los bolivares en la gaveta no se mueven.
        _set_tasa_actual('900.0000')
        self.assertEqual(efectivo_esperado_por_moneda(self.hoy)['bs'], Decimal('4000.00'))

        self.client.force_login(self.cajera)
        data = self.client.get(f'/api/admin/reportes/cuadre-caja/?fecha={self.hoy.isoformat()}').json()
        self.assertEqual(data['efectivo_por_moneda']['bs'], '4000.00')
        self.assertEqual(data['efectivo_por_moneda']['usd'], '15.000000')


class DeshacerPuntoDeVentaTests(LotesPOSBase):
    """Si un cobro entra a un lote (o un metodo se marca POS) por error, se puede deshacer sin descuadrar nada."""

    def post_metodos(self, **payload):
        return self.client.post('/api/admin/metodos-pago/', data=json.dumps(payload), content_type='application/json')

    def test_cobro_en_punto_por_error_se_saca_del_lote_abierto_cambiando_la_cuenta(self):
        pago_movil = VGMetodoPago.objects.create(nombre='Pago movil test', moneda='VES', cuenta_bancaria='Banesco')
        pago = self.pago('50')  # se cobro con el punto por error
        lote = pago.lote_pos
        self.assertEqual(self.saldo_banco('Banesco')['saldo_disponible'], Decimal('0'))

        self.client.force_login(self.cajera)
        r = self.client.post(
            '/api/admin/reportes/cuadre-caja/',
            data=json.dumps({
                'action': 'cambiar_metodo_pago', 'fecha': self.hoy.isoformat(), 'tipo': 'pago', 'id': pago.id,
                'metodo_pago_id': pago_movil.id, 'motivo': 'Era pago movil',
            }), content_type='application/json',
        )
        self.assertEqual(r.status_code, 200, r.content)
        pago.refresh_from_db()
        lote.refresh_from_db()
        self.assertIsNone(pago.lote_pos_id)
        self.assertEqual(lote.monto_bruto_usd, Decimal('0'))
        # Ya es un cobro normal: suma al saldo del banco de una vez.
        self.assertEqual(self.saldo_banco('Banesco')['saldo_disponible'], Decimal('50.000000'))

    def test_si_el_lote_ya_se_cerro_primero_se_reabre(self):
        pago_movil = VGMetodoPago.objects.create(nombre='Pago movil test', moneda='VES', cuenta_bancaria='Banesco')
        pago = self.pago('50')
        lote = self.cerrar(pago.lote_pos)
        pago.refresh_from_db()
        self.assertIn('Mover cobro', lotes_pos.validar_cambio_metodo_pago(pago))
        lotes_pos.reabrir_lote(lote, self.admin, 'Cobro con metodo equivocado')
        pago.refresh_from_db()
        self.assertIsNone(lotes_pos.validar_cambio_metodo_pago(pago))
        pago.metodo_pago = pago_movil
        pago.save(update_fields=['metodo_pago'])
        lotes_pos.aplicar_cambio_metodo_pago(pago, self.admin)
        pago.refresh_from_db()
        self.assertIsNone(pago.lote_pos_id)

    def test_quitar_la_marca_de_punto_de_venta_no_duplica_saldo_ni_flujo(self):
        lote = self.acreditar(self.cerrar(self.pago('100').lote_pos))
        self.assertEqual(self.saldo_banco('Banesco')['saldo_disponible'], Decimal('100.000000'))

        self.client.force_login(self.admin)
        r = self.post_metodos(action='marcar_punto_venta', id=self.pos.id, es_punto_venta=False)
        self.assertEqual(r.status_code, 200, r.content)

        # El cobro vuelve a contar como cobro normal: el saldo sigue en 100, no 200.
        self.assertEqual(self.saldo_banco('Banesco')['saldo_disponible'], Decimal('100.000000'))
        flujo = flujo_bancario_mensual(self.hoy.year, self.hoy.month, 'Banesco')
        self.assertEqual(flujo['total_entrada'], Decimal('100.000000'))

    def test_no_se_quita_la_marca_con_lotes_sin_acreditar(self):
        self.pago('100')
        self.client.force_login(self.admin)
        self.assertEqual(self.post_metodos(action='marcar_punto_venta', id=self.pos.id, es_punto_venta=False).status_code, 400)

    def test_marcar_un_metodo_por_error_y_desmarcarlo_deja_los_saldos_como_estaban(self):
        efectivo = VGMetodoPago.objects.create(nombre='Pago movil test', moneda='VES', cuenta_bancaria='Mercantil')
        self.pago('70', metodo=efectivo)
        antes = self.saldo_banco('Mercantil')['saldo_disponible']
        self.assertEqual(antes, Decimal('70.000000'))

        self.client.force_login(self.admin)
        self.post_metodos(action='marcar_punto_venta', id=efectivo.id, es_punto_venta=True)
        # Hoy el cobro paso al lote abierto: deja de estar disponible hasta acreditar.
        self.assertEqual(self.saldo_banco('Mercantil')['saldo_disponible'], Decimal('0'))
        lote = VGLotePOS.objects.get(metodo_pago=efectivo, estado='abierto')
        self.acreditar(self.cerrar(lote))
        self.assertEqual(self.saldo_banco('Mercantil')['saldo_disponible'], antes)
        self.assertEqual(self.post_metodos(action='marcar_punto_venta', id=efectivo.id, es_punto_venta=False).status_code, 200)
        self.assertEqual(self.saldo_banco('Mercantil')['saldo_disponible'], antes)


class MoverCobroDeLoteCerradoTests(LotesPOSBase):
    """Se dan cuenta al final del dia de que un cobro no va en el lote cerrado, y el metodo ya tiene otro lote abierto."""

    def escenario(self):
        correcto = self.pago('30')
        equivocado = self.pago('20')
        lote_a = self.cerrar(correcto.lote_pos)          # el punto cerro con ambos cobros adentro
        nuevo = self.pago('10')                          # y siguio cobrando: lote B abierto
        lote_b = nuevo.lote_pos
        self.assertNotEqual(lote_a.pk, lote_b.pk)
        return lote_a, lote_b, equivocado

    def test_pasa_al_lote_abierto_sin_reabrir_el_cerrado(self):
        lote_a, lote_b, pago = self.escenario()
        self.assertEqual(lote_a.monto_bruto_usd, Decimal('50.000000'))

        # Reabrir no se puede mientras haya otro lote abierto...
        with self.assertRaises(lotes_pos.LoteError):
            lotes_pos.reabrir_lote(lote_a, self.admin, 'x')
        # ...pero mover el cobro si.
        lotes_pos.mover_pago_de_lote(pago, self.admin, 'Se cobro despues del cierre del punto')

        lote_a.refresh_from_db()
        lote_b.refresh_from_db()
        pago.refresh_from_db()
        self.assertEqual(lote_a.estado, 'cerrado')
        self.assertEqual(lote_a.monto_bruto_usd, Decimal('30.000000'))
        self.assertEqual(lote_a.monto_bruto_sistema_bs, Decimal('3000.00'))
        self.assertEqual(pago.lote_pos_id, lote_b.pk)
        self.assertEqual(lote_b.monto_bruto_usd, Decimal('30.000000'))
        self.assertIn('Se cobro despues del cierre', lote_a.notas)
        self.assertIn('Se cobro despues del cierre', lote_b.notas)
        # Sigue sin acreditar: nada suma al saldo todavia.
        self.assertEqual(self.saldo_banco('Banesco')['saldo_disponible'], Decimal('0'))
        self.assertEqual(self.saldo_banco('Banesco')['por_acreditar_usd'], Decimal('60.000000'))  # A: 30 + B: 10 + 20 movidos

    def test_cambia_la_cuenta_y_suma_al_saldo_si_el_destino_no_es_punto(self):
        lote_a, _lote_b, pago = self.escenario()
        pago_movil = VGMetodoPago.objects.create(nombre='Pago movil test', moneda='VES', cuenta_bancaria='Banesco')
        lotes_pos.mover_pago_de_lote(pago, self.admin, 'Era pago movil', pago_movil)
        pago.refresh_from_db()
        lote_a.refresh_from_db()
        self.assertIsNone(pago.lote_pos_id)
        self.assertEqual(pago.metodo_pago_id, pago_movil.id)
        self.assertEqual(lote_a.monto_bruto_usd, Decimal('30.000000'))
        self.assertEqual(self.saldo_banco('Banesco')['saldo_disponible'], Decimal('20.000000'))
        from varagrill.models import VGCorreccionMetodoPago
        self.assertTrue(VGCorreccionMetodoPago.objects.filter(tipo='pago', registro_id=pago.id, motivo='Era pago movil').exists())

    def test_un_lote_que_se_queda_sin_cobros_se_anula(self):
        pago = self.pago('20')
        lote = self.cerrar(pago.lote_pos)
        lotes_pos.mover_pago_de_lote(pago, self.admin, 'Todo el lote era un error')
        lote.refresh_from_db()
        self.assertEqual(lote.estado, 'anulado')
        self.assertEqual(VGLotePOS.objects.get(metodo_pago=self.pos, estado='abierto').monto_bruto_usd, Decimal('20.000000'))

    def test_reglas_motivo_y_estado(self):
        lote_a, lote_b, pago = self.escenario()
        with self.assertRaises(lotes_pos.LoteError):
            lotes_pos.mover_pago_de_lote(pago, self.admin, '')
        # Un cobro de un lote abierto usa "cambiar cuenta" del cuadre, no esta accion.
        abierto = lote_b.pagos.first()
        with self.assertRaises(lotes_pos.LoteError):
            lotes_pos.mover_pago_de_lote(abierto, self.admin, 'x')
        # Acreditado: primero se revierte.
        self.acreditar(lote_a)
        with self.assertRaises(lotes_pos.LoteError):
            lotes_pos.mover_pago_de_lote(pago, self.admin, 'x')

    def test_endpoint_solo_administrador(self):
        lote_a, lote_b, pago = self.escenario()

        def post(**payload):
            return self.client.post('/api/admin/lotes-pos/', data=json.dumps(payload), content_type='application/json')

        self.client.force_login(self.cajera)
        self.assertEqual(post(action='mover_pago', lote_id=lote_a.id, pago_id=pago.id, motivo='x').status_code, 401)
        self.client.force_login(self.admin)
        r = post(action='mover_pago', lote_id=lote_a.id, pago_id=pago.id, motivo='Fuera del lote cerrado')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()['lote']['monto_usd'], '30.000000')
        # Un cobro que no es de ese lote se rechaza.
        self.assertEqual(post(action='mover_pago', lote_id=lote_a.id, pago_id=lote_b.pagos.first().id, motivo='x').status_code, 400)


# ---------------------------------------------------------------------------
# Notas de credito de proveedor sobre facturas de compra
# ---------------------------------------------------------------------------
class NotaCreditoCompraTests(TestCase):
    def setUp(self):
        from varagrill.models import VGAbonoCompra  # noqa: F401
        admin_role, _ = VGRol.objects.get_or_create(nombre_role='Administrador')
        cajera_role, _ = VGRol.objects.get_or_create(nombre_role='Cajera')
        self.admin = VGUsuario.objects.create_superuser(
            username='nc_admin', password='claveAdmin123', cedula='92000001', email='nc_admin@varagrill.test', id_role=admin_role,
        )
        self.cajera = VGUsuario.objects.create_user(
            username='nc_cajera', password='claveCajera123', cedula='92000002', email='nc_cajera@varagrill.test', id_role=cajera_role,
        )
        self.metodo = VGMetodoPago.objects.create(nombre='Efectivo NC test', moneda='USD', es_efectivo=True)
        self.client.force_login(self.admin)

    def compra(self, total='100', abonado='0', moneda='USD', total_bs=None, tasa='100.0000'):
        from varagrill.models import VGAbonoCompra
        total = Decimal(total)
        abonado = Decimal(abonado)
        compra = VGCompra.objects.create(
            proveedor_nombre='Proveedor NC', numero_factura_proveedor='F-1', estado='recibido',
            total=total, saldo_pendiente=total - abonado, estado_pago='pendiente' if abonado == 0 else 'abonada_parcial',
            tasa_cambio_referencia=Decimal(tasa), moneda_origen=moneda,
            total_bs_factura=Decimal(total_bs) if total_bs else None,
        )
        if abonado:
            VGAbonoCompra.objects.create(compra=compra, monto=abonado, metodo_pago=self.metodo, tasa_cambio_referencia=Decimal(tasa))
        return compra

    def nota(self, compra, **payload):
        payload.setdefault('motivo', 'La administradora cargó mal el monto')
        return self.client.post(
            f'/api/admin/compras/{compra.id}/notas-credito/', data=json.dumps(payload), content_type='application/json',
        )

    def test_baja_el_total_y_el_saldo_y_conserva_el_total_original(self):
        compra = self.compra('100', abonado='30')
        r = self.nota(compra, monto='20', numero_documento_proveedor='NC-998')
        self.assertEqual(r.status_code, 201, r.content)
        compra.refresh_from_db()
        self.assertEqual(compra.total, Decimal('80.000000'))
        self.assertEqual(compra.saldo_pendiente, Decimal('50.000000'))
        self.assertEqual(compra.estado_pago, 'abonada_parcial')
        datos = r.json()['compra']
        self.assertEqual(datos['total_original'], '100.000000')
        self.assertEqual(datos['monto_notas_credito'], '20.000000')
        self.assertEqual(datos['notas_credito'][0]['codigo'], 'NCC-000001')
        self.assertEqual(datos['notas_credito'][0]['numero_documento_proveedor'], 'NC-998')
        # Los abonos ya hechos no se tocan.
        self.assertEqual(compra.abonos.count(), 1)

    def test_no_puede_superar_lo_que_aun_se_debe(self):
        compra = self.compra('100', abonado='30')
        r = self.nota(compra, monto='70.50')
        self.assertEqual(r.status_code, 400)
        self.assertIn('no puede ser mayor', r.json()['message'])
        compra.refresh_from_db()
        self.assertEqual(compra.total, Decimal('100.000000'))

    def test_una_factura_saldada_no_admite_nota_de_credito(self):
        compra = self.compra('100', abonado='100')
        compra.estado_pago = 'pagada'
        compra.save()
        self.assertEqual(self.nota(compra, monto='5').status_code, 409)

    def test_si_la_nota_salda_la_deuda_el_total_queda_en_lo_abonado(self):
        compra = self.compra('100', abonado='30')
        r = self.nota(compra, monto='70')
        self.assertEqual(r.status_code, 201, r.content)
        compra.refresh_from_db()
        self.assertEqual(compra.saldo_pendiente, Decimal('0'))
        self.assertEqual(compra.total, Decimal('30.000000'))
        self.assertEqual(compra.estado_pago, 'pagada')

    def test_motivo_y_monto_son_obligatorios_y_solo_una_moneda(self):
        compra = self.compra('100')
        self.assertEqual(self.nota(compra, monto='5', motivo='').status_code, 400)
        self.assertEqual(self.nota(compra).status_code, 400)  # sin monto
        self.assertEqual(self.nota(compra, monto='5', monto_bs='500').status_code, 400)
        self.assertEqual(self.nota(compra, monto='-5').status_code, 400)

    def test_factura_en_bolivares_rebaja_el_monto_exacto_en_bs(self):
        compra = self.compra('100', moneda='VES', total_bs='10000.00', tasa='100.0000')
        r = self.nota(compra, monto_bs='2500')
        self.assertEqual(r.status_code, 201, r.content)
        compra.refresh_from_db()
        self.assertEqual(compra.total, Decimal('75.000000'))
        self.assertEqual(compra.total_bs_factura, Decimal('7500.00'))
        datos = r.json()['compra']
        self.assertEqual(datos['total_bs'], '7500.00')
        self.assertEqual(datos['saldo_pendiente_bs'], '7500.00')

    def test_nota_que_salda_una_factura_en_bs_no_deja_centimos_fantasma(self):
        compra = self.compra('100', abonado='40', moneda='VES', total_bs='10000.00', tasa='100.0000')
        r = self.nota(compra, monto_bs='6000')
        self.assertEqual(r.status_code, 201, r.content)
        compra.refresh_from_db()
        self.assertEqual(compra.estado_pago, 'pagada')
        self.assertEqual(compra.total_bs_factura, Decimal('4000.00'))
        self.assertEqual(r.json()['compra']['saldo_pendiente_bs'], '0.00')

    def test_anular_devuelve_el_monto_al_total_y_al_saldo(self):
        compra = self.compra('100', abonado='30', moneda='VES', total_bs='10000.00', tasa='100.0000')
        nota_id = self.nota(compra, monto_bs='2000').json()['nota_credito']['id']
        compra.refresh_from_db()
        self.assertEqual(compra.saldo_pendiente, Decimal('50.000000'))

        url = f'/api/admin/compras/notas-credito/{nota_id}/anular/'
        post = lambda **p: self.client.post(url, data=json.dumps(p), content_type='application/json')  # noqa: E731
        self.assertEqual(post(motivo='').status_code, 400)
        r = post(motivo='Se registró en la factura equivocada')
        self.assertEqual(r.status_code, 200, r.content)
        compra.refresh_from_db()
        self.assertEqual(compra.total, Decimal('100.000000'))
        self.assertEqual(compra.saldo_pendiente, Decimal('70.000000'))
        self.assertEqual(compra.total_bs_factura, Decimal('10000.00'))
        self.assertEqual(r.json()['compra']['monto_notas_credito'], '0')
        self.assertEqual(post(motivo='otra vez').status_code, 409)

    def test_anular_una_nota_que_habia_saldado_la_factura_la_reabre(self):
        compra = self.compra('100', abonado='30')
        nota_id = self.nota(compra, monto='70').json()['nota_credito']['id']
        self.client.post(
            f'/api/admin/compras/notas-credito/{nota_id}/anular/', data=json.dumps({'motivo': 'Error'}), content_type='application/json',
        )
        compra.refresh_from_db()
        self.assertEqual(compra.estado_pago, 'abonada_parcial')
        self.assertEqual(compra.saldo_pendiente, Decimal('70.000000'))

    def test_dos_notas_acumulan_y_cada_una_tiene_su_numero(self):
        compra = self.compra('100')
        self.nota(compra, monto='10')
        r = self.nota(compra, monto='15')
        compra.refresh_from_db()
        self.assertEqual(compra.total, Decimal('75.000000'))
        self.assertEqual(r.json()['nota_credito']['codigo'], 'NCC-000002')
        listado = self.client.get(f'/api/admin/compras/{compra.id}/notas-credito/').json()
        self.assertEqual(len(listado['notas_credito']), 2)

    def test_solo_administrador(self):
        compra = self.compra('100')
        self.client.force_login(self.cajera)
        self.assertEqual(self.nota(compra, monto='5').status_code, 401)

    def test_la_cuenta_por_pagar_muestra_el_total_rebajado(self):
        compra = self.compra('100')
        self.nota(compra, monto='25')
        data = self.client.get('/api/cuentas-por-pagar/').json()
        fila = next(item for item in data['compras'] if item['tipo'] == 'compra' and item['id'] == compra.id)
        self.assertEqual(fila['total'], '75.000000')
        self.assertEqual(fila['total_original'], '100.000000')

    def test_reporte_por_rango_con_totales_y_proveedor(self):
        a = self.compra('100')
        b = self.compra('200', moneda='VES', total_bs='20000.00', tasa='100.0000')
        self.nota(a, monto='10')
        nota_b = self.nota(b, monto_bs='5000').json()['nota_credito']
        anulada = self.nota(a, monto='30').json()['nota_credito']
        self.client.post(
            f"/api/admin/compras/notas-credito/{anulada['id']}/anular/", data=json.dumps({'motivo': 'Error'}), content_type='application/json',
        )

        hoy = timezone.localdate().isoformat()
        data = self.client.get(f'/api/admin/reportes/notas-credito-compra/?desde={hoy}&hasta={hoy}').json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['cantidad_vigentes'], 2)
        self.assertEqual(Decimal(data['total_usd']), Decimal('60.000000'))      # 10 + 50 (Bs 5.000 a tasa 100)
        self.assertEqual(Decimal(data['total_bs']), Decimal('6000.00'))          # 1.000 (10 x 100) + 5.000
        self.assertEqual(len(data['notas']), 3)                                  # la anulada se lista pero no suma
        self.assertEqual(len(data['por_proveedor']), 1)
        self.assertEqual(data['por_proveedor'][0]['cantidad'], 2)
        self.assertEqual(next(n for n in data['notas'] if n['id'] == nota_b['id'])['monto_bs'], '5000.00')

        solo_anuladas = self.client.get(f'/api/admin/reportes/notas-credito-compra/?desde={hoy}&hasta={hoy}&estado=anulada').json()
        self.assertEqual([n['estado'] for n in solo_anuladas['notas']], ['anulada'])
        self.assertEqual(Decimal(solo_anuladas['total_usd']), Decimal('0'))

        vacio = self.client.get('/api/admin/reportes/notas-credito-compra/?desde=2020-01-01&hasta=2020-01-31').json()
        self.assertEqual(vacio['notas'], [])

    def test_reporte_solo_administrador_y_valida_fechas(self):
        self.assertEqual(self.client.get('/api/admin/reportes/notas-credito-compra/?desde=2026-02-01&hasta=2026-01-01').status_code, 400)
        self.client.force_login(self.cajera)
        self.assertEqual(self.client.get('/api/admin/reportes/notas-credito-compra/').status_code, 401)


# ---------------------------------------------------------------------------
# Abono a una factura de compra con la tasa propia de quien paga
# ---------------------------------------------------------------------------
class AbonoCompraTasaPropiaTests(TestCase):
    def setUp(self):
        admin_role, _ = VGRol.objects.get_or_create(nombre_role='Administrador')
        self.admin = VGUsuario.objects.create_superuser(
            username='tp_admin', password='claveAdmin123', cedula='93000001', email='tp_admin@varagrill.test', id_role=admin_role,
        )
        self.metodo = VGMetodoPago.objects.create(nombre='Banco VES tasa propia', moneda='VES')
        self.client.force_login(self.admin)

    def compra(self, total='100', tasa='480.0000', total_bs='48000.00', moneda='VES'):
        total = Decimal(total)
        return VGCompra.objects.create(
            proveedor_nombre='Proveedor tasa propia', numero_factura_proveedor='TP-1', estado='recibido',
            total=total, saldo_pendiente=total, estado_pago='pendiente',
            tasa_cambio_referencia=Decimal(tasa), moneda_origen=moneda,
            total_bs_factura=Decimal(total_bs) if total_bs else None,
        )

    def abonar(self, compra, **payload):
        payload.setdefault('metodo_pago_id', self.metodo.id)
        return self.client.post(
            f'/api/admin/compras/{compra.id}/abonos/', data=json.dumps(payload), content_type='application/json',
        )

    def test_en_dolares_con_tasa_propia_los_bs_son_monto_por_esa_tasa(self):
        compra = self.compra()
        r = self.abonar(compra, monto='50', tasa_cambio='482.5')
        self.assertEqual(r.status_code, 201, r.content)
        abono = r.json()['abono']
        self.assertEqual(abono['tasa_cambio_referencia'], '482.5000')
        self.assertTrue(abono['tasa_manual'])
        self.assertEqual(abono['monto_bs'], '24125.00')
        # La deuda en dolares baja solo por los dolares.
        compra.refresh_from_db()
        self.assertEqual(compra.saldo_pendiente, Decimal('50.000000'))
        self.assertEqual(compra.estado_pago, 'abonada_parcial')

    def test_en_bolivares_con_tasa_propia_descuenta_bs_entre_la_tasa(self):
        compra = self.compra()
        r = self.abonar(compra, monto_bs='24100', tasa_cambio='482')
        self.assertEqual(r.status_code, 201, r.content)
        compra.refresh_from_db()
        self.assertEqual(compra.saldo_pendiente, Decimal('50.000000'))
        self.assertEqual(r.json()['abono']['monto_bs'], '24100.00')

    def test_sin_tasa_se_comporta_como_siempre(self):
        compra = self.compra()
        # En bolivares sin tasa: la de la factura, como antes.
        r = self.abonar(compra, monto_bs='4800')
        self.assertEqual(r.status_code, 201, r.content)
        abono = r.json()['abono']
        self.assertFalse(abono['tasa_manual'])
        self.assertEqual(Decimal(abono['tasa_cambio_referencia']), Decimal('480.0000'))
        # En dolares sin tasa: la del BCV de hoy (no se marca como tasa propia).
        r = self.abonar(compra, monto='5')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertFalse(r.json()['abono']['tasa_manual'])

    def test_tasa_invalida_se_rechaza(self):
        compra = self.compra()
        self.assertEqual(self.abonar(compra, monto='10', tasa_cambio='0').status_code, 400)
        self.assertEqual(self.abonar(compra, monto='10', tasa_cambio='abc').status_code, 400)
        self.assertEqual(compra.abonos.count(), 0)

    def test_una_tasa_mas_alta_no_perdona_dolares_que_aun_se_deben(self):
        # 99.80 a 482 son 48.103,60 Bs: mas que los 48.000 de la factura. Sin cuidado, el
        # "perdon de residuo" compararia Bs contra Bs y cerraria una factura con $0.20 vivos.
        compra = self.compra()
        r = self.abonar(compra, monto='99.80', tasa_cambio='482')
        self.assertEqual(r.status_code, 201, r.content)
        compra.refresh_from_db()
        self.assertEqual(compra.saldo_pendiente, Decimal('0.200000'))
        self.assertEqual(compra.estado_pago, 'abonada_parcial')

    def test_total_y_saldo_en_bs_separan_lo_pagado_de_lo_que_falta(self):
        compra = self.compra()
        datos = self.abonar(compra, monto='50', tasa_cambio='482').json()['compra']
        # Lo pagado son los Bs que salieron del banco; lo que falta, $50 a la tasa de la factura.
        self.assertEqual(datos['saldo_pendiente_bs'], '24000.00')
        self.assertEqual(datos['total_bs'], '48100.00')

    def test_saldada_a_tasa_propia_el_total_en_bs_es_lo_que_salio_del_banco(self):
        compra = self.compra()
        datos = self.abonar(compra, monto='100', tasa_cambio='482').json()['compra']
        compra.refresh_from_db()
        self.assertEqual(compra.estado_pago, 'pagada')
        self.assertEqual(datos['total_bs'], '48200.00')
        self.assertEqual(datos['saldo_pendiente_bs'], '0.00')

    def test_los_bs_pagados_no_cambian_cuando_se_mueve_el_bcv(self):
        from datetime import timedelta
        from django.utils import timezone
        from varagrill.models.restaurant import VGTasaCambio
        # Factura en dolares: lo que falta sigue al BCV de hoy, pero lo ya pagado queda fijo.
        compra = self.compra(moneda='USD', total_bs=None)
        VGTasaCambio.objects.update_or_create(fecha=timezone.localdate(), defaults={'tasa': Decimal('480')})
        self.abonar(compra, monto='60', tasa_cambio='482')
        antes = self.client.get(f'/api/admin/compras/{compra.id}/').json()['compra']
        abono_antes = antes['abonos'][0]
        # El BCV sube mucho al dia siguiente.
        VGTasaCambio.objects.update_or_create(fecha=timezone.localdate() + timedelta(days=1), defaults={'tasa': Decimal('900')})
        despues = self.client.get(f'/api/admin/compras/{compra.id}/').json()['compra']
        abono_despues = despues['abonos'][0]
        self.assertEqual(abono_antes['monto_bs'], '28920.00')
        self.assertEqual(abono_despues['monto_bs'], '28920.00')
        self.assertEqual(abono_despues['tasa_cambio_referencia'], '482.0000')
        # Saldada despues, el total en Bs es exactamente lo que salio del banco.
        self.abonar(compra, monto='40', tasa_cambio='490')
        VGTasaCambio.objects.update_or_create(fecha=timezone.localdate() + timedelta(days=1), defaults={'tasa': Decimal('1500')})
        final = self.client.get(f'/api/admin/compras/{compra.id}/').json()['compra']
        self.assertEqual(final['estado_pago'], 'pagada')
        self.assertEqual(final['total_bs'], '48520.00')  # 28.920 + 19.600


# ---------------------------------------------------------------------------
# Reporte de margen de ganancia por producto (en vivo)
# ---------------------------------------------------------------------------
class MargenProductosReporteTests(TestCase):
    def setUp(self):
        from varagrill.models import VGCategoriaProducto, VGConfiguracionCosteo, VGIngrediente, VGProducto, VGRecetaProducto
        admin_role, _ = VGRol.objects.get_or_create(nombre_role='Administrador')
        cajera_role, _ = VGRol.objects.get_or_create(nombre_role='Cajera')
        self.admin = VGUsuario.objects.create_superuser(
            username='mp_admin', password='claveAdmin123', cedula='94000001', email='mp_admin@varagrill.test', id_role=admin_role,
        )
        self.cajera = VGUsuario.objects.create_user(
            username='mp_cajera', password='claveCajera123', cedula='94000002', email='mp_cajera@varagrill.test', id_role=cajera_role,
        )
        config = VGConfiguracionCosteo.obtener_config()
        config.rendimiento_receta_pct = Decimal('50')
        config.margen_ganancia_defecto_pct = Decimal('60')
        config.save()
        self.categoria = VGCategoriaProducto.objects.create(nombre='Entradas MP test')
        self.ingrediente = VGIngrediente.objects.create(nombre='Maiz MP test', unidad_medida='g', costo_unitario='0.98')
        self.producto = VGProducto.objects.create(nombre='Maiz Dorado MP test', categoria=self.categoria, precio_venta='4.00')
        VGRecetaProducto.objects.create(producto=self.producto, ingrediente=self.ingrediente, cantidad_requerida='1')
        self.client.force_login(self.admin)

    def fila(self, producto=None):
        r = self.client.get('/api/admin/reportes/margen-productos/')
        self.assertEqual(r.status_code, 200, r.content)
        producto = producto or self.producto
        return next(f for f in r.json()['productos'] if f['producto_id'] == producto.id)

    def test_calcula_las_columnas_del_reporte(self):
        f = self.fila()
        self.assertEqual(Decimal(f['costo_receta']), Decimal('0.98'))
        self.assertEqual(Decimal(f['margen_produccion_pct']), Decimal('50'))
        self.assertEqual(Decimal(f['costo_a_tomar']), Decimal('1.47'))
        self.assertEqual(Decimal(f['margen_ganancia_pct']), Decimal('60'))
        self.assertFalse(f['margen_ganancia_propio'])
        self.assertEqual(Decimal(f['precio_sugerido']), Decimal('2.35'))   # 1.47 x 1.6 = 2.352
        self.assertEqual(Decimal(f['precio_real']), Decimal('4.00'))
        self.assertEqual(Decimal(f['ganancia']), Decimal('2.53'))          # 4 - 1.47
        self.assertEqual(Decimal(f['ganancia_pct']), Decimal('172.11'))    # 2.53 / 1.47
        self.assertTrue(f['tiene_receta'])

    def test_el_margen_propio_del_producto_manda_sobre_el_defecto(self):
        self.producto.margen_ganancia_pct = Decimal('100')
        self.producto.save()
        f = self.fila()
        self.assertTrue(f['margen_ganancia_propio'])
        self.assertEqual(Decimal(f['margen_ganancia_pct']), Decimal('100'))
        self.assertEqual(Decimal(f['precio_sugerido']), Decimal('2.94'))   # 1.47 x 2

    def test_si_cambia_el_costo_del_ingrediente_cambia_la_fila(self):
        self.ingrediente.costo_unitario = Decimal('1.40')
        self.ingrediente.save()
        f = self.fila()
        self.assertEqual(Decimal(f['costo_receta']), Decimal('1.40'))
        self.assertEqual(Decimal(f['costo_a_tomar']), Decimal('2.10'))
        self.assertEqual(Decimal(f['precio_sugerido']), Decimal('3.36'))
        self.assertEqual(Decimal(f['ganancia']), Decimal('1.90'))

    def test_si_cambia_la_cantidad_de_la_receta_cambia_la_fila(self):
        componente = self.producto.receta.first()
        componente.cantidad_requerida = Decimal('2')
        componente.save()
        self.assertEqual(Decimal(self.fila()['costo_receta']), Decimal('1.96'))

    def test_el_margen_de_produccion_tambien_aplica_a_productos_ligados_a_una_subreceta(self):
        from varagrill.models import VGPreparacion, VGProducto, VGRecetaPreparacion
        sub = VGPreparacion.objects.create(nombre='Salsa MP test', rendimiento_cantidad='1000', rendimiento_unidad='g')
        VGRecetaPreparacion.objects.create(preparacion=sub, ingrediente=self.ingrediente, cantidad_requerida='1')
        ligado = VGProducto.objects.create(nombre='Salsa vendida MP test', categoria=self.categoria, precio_venta='3.00', subreceta_vinculada=sub)
        f = self.fila(ligado)
        self.assertEqual(Decimal(f['margen_produccion_pct']), Decimal('50'))
        self.assertEqual(Decimal(f['costo_receta']), Decimal('0.98'))
        self.assertEqual(Decimal(f['costo_a_tomar']), Decimal('1.47'))
        # Si cambia el ingrediente de esa subreceta, cambia tambien.
        self.ingrediente.costo_unitario = Decimal('2')
        self.ingrediente.save()
        self.assertEqual(Decimal(self.fila(ligado)['costo_a_tomar']), Decimal('3.00'))

    def test_subir_o_bajar_el_margen_de_produccion_mueve_el_costo_a_tomar(self):
        from varagrill.models import VGConfiguracionCosteo
        config = VGConfiguracionCosteo.obtener_config()
        for pct, esperado in (('100', '1.96'), ('20', '1.176'), ('0', '0.98')):
            config.rendimiento_receta_pct = Decimal(pct)
            config.save()
            f = self.fila()
            self.assertEqual(Decimal(f['margen_produccion_pct']), Decimal(pct))
            self.assertEqual(Decimal(f['costo_receta']), Decimal('0.98'))   # el costo puro no se mueve
            self.assertEqual(Decimal(f['costo_a_tomar']).quantize(Decimal('0.001')), Decimal(esperado))

    def test_producto_sin_receta_se_marca_y_no_inventa_porcentaje(self):
        from varagrill.models import VGProducto
        vacio = VGProducto.objects.create(nombre='Sin receta MP test', categoria=self.categoria, precio_venta='5.00')
        f = self.fila(vacio)
        self.assertFalse(f['tiene_receta'])
        self.assertEqual(Decimal(f['costo_a_tomar']), Decimal('0'))
        self.assertIsNone(f['ganancia_pct'])

    def test_la_lista_de_productos_trae_el_costo_de_receta_en_vivo(self):
        from varagrill.models import VGConfiguracionCosteo, VGPreparacion, VGProducto, VGRecetaPreparacion
        # El margen de produccion NO entra en esta columna: es el costo de la receta.
        self.assertEqual(VGConfiguracionCosteo.obtener_config().rendimiento_receta_pct, Decimal('50'))
        sub = VGPreparacion.objects.create(nombre='Salsa lista MP test', rendimiento_cantidad='1000', rendimiento_unidad='g')
        VGRecetaPreparacion.objects.create(preparacion=sub, ingrediente=self.ingrediente, cantidad_requerida='1')
        ligado = VGProducto.objects.create(nombre='Con subreceta lista MP test', categoria=self.categoria, precio_venta='3.00', subreceta_vinculada=sub)
        vacio = VGProducto.objects.create(nombre='Sin nada lista MP test', categoria=self.categoria, precio_venta='5.00')
        cero_ing = type(self.ingrediente).objects.create(nombre='Agua MP test', unidad_medida='g', costo_unitario='0')
        en_cero = VGProducto.objects.create(nombre='Receta en cero lista MP test', categoria=self.categoria, precio_venta='2.00')
        type(self.producto.receta.first()).objects.create(producto=en_cero, ingrediente=cero_ing, cantidad_requerida='1')

        def filas():
            r = self.client.get('/api/admin/productos/')
            self.assertEqual(r.status_code, 200, r.content)
            return {p['id']: p for p in r.json()['products']}

        f = filas()
        self.assertTrue(f[self.producto.id]['tiene_receta'])
        self.assertEqual(Decimal(f[self.producto.id]['costo_receta']), Decimal('0.98'))
        self.assertEqual(Decimal(f[self.producto.id]['costo_con_margen_produccion']), Decimal('1.47'))   # 0.98 x 1.5
        self.assertTrue(f[ligado.id]['tiene_receta'])
        self.assertEqual(Decimal(f[ligado.id]['costo_receta']), Decimal('0.98'))
        self.assertEqual(Decimal(f[ligado.id]['costo_con_margen_produccion']), Decimal('1.47'))   # tambien los de subreceta
        self.assertFalse(f[vacio.id]['tiene_receta'])
        self.assertEqual(Decimal(f[vacio.id]['costo_receta']), Decimal('0'))
        self.assertTrue(f[en_cero.id]['tiene_receta'])
        self.assertEqual(Decimal(f[en_cero.id]['costo_receta']), Decimal('0'))
        # En vivo: si cambia el ingrediente, cambia la lista.
        self.ingrediente.costo_unitario = Decimal('1.20')
        self.ingrediente.save()
        f = filas()
        self.assertEqual(Decimal(f[self.producto.id]['costo_receta']), Decimal('1.20'))
        self.assertEqual(Decimal(f[ligado.id]['costo_receta']), Decimal('1.20'))
        self.assertEqual(Decimal(f[self.producto.id]['costo_con_margen_produccion']), Decimal('1.80'))
        # Y si cambia el margen de produccion, cambia la segunda columna pero no la primera.
        config = VGConfiguracionCosteo.obtener_config()
        config.rendimiento_receta_pct = Decimal('10')
        config.save()
        f = filas()
        self.assertEqual(Decimal(f[self.producto.id]['costo_receta']), Decimal('1.20'))
        self.assertEqual(Decimal(f[self.producto.id]['costo_con_margen_produccion']), Decimal('1.32'))

    def test_senala_los_ingredientes_sin_costo_aunque_esten_dentro_de_una_subreceta(self):
        from varagrill.models import VGIngrediente, VGPreparacion, VGProducto, VGRecetaPreparacion, VGRecetaProducto
        sin_precio = VGIngrediente.objects.create(nombre='Platano sin precio MP test', unidad_medida='g', costo_unitario='0')
        sin_precio_2 = VGIngrediente.objects.create(nombre='Sal sin precio MP test', unidad_medida='g', costo_unitario='0')
        interna = VGPreparacion.objects.create(nombre='Interna MP test', rendimiento_cantidad='1000', rendimiento_unidad='g')
        VGRecetaPreparacion.objects.create(preparacion=interna, ingrediente=sin_precio_2, cantidad_requerida='1')
        sub = VGPreparacion.objects.create(nombre='Externa MP test', rendimiento_cantidad='1000', rendimiento_unidad='g')
        VGRecetaPreparacion.objects.create(preparacion=sub, ingrediente=sin_precio, cantidad_requerida='1')
        VGRecetaPreparacion.objects.create(preparacion=sub, ingrediente=self.ingrediente, cantidad_requerida='1')
        VGRecetaPreparacion.objects.create(preparacion=sub, sub_preparacion=interna, cantidad_requerida='1')
        ligado = VGProducto.objects.create(nombre='Con faltantes MP test', categoria=self.categoria, precio_venta='3.00', subreceta_vinculada=sub)
        directo = VGProducto.objects.create(nombre='Directo sin precio MP test', categoria=self.categoria, precio_venta='2.00')
        VGRecetaProducto.objects.create(producto=directo, ingrediente=sin_precio, cantidad_requerida='5')

        f = self.fila(ligado)
        self.assertEqual(f['ingredientes_sin_costo'], ['Platano sin precio MP test', 'Sal sin precio MP test'])
        # El costo mostrado es solo el de lo que si tiene precio (0.98 del maiz).
        self.assertEqual(Decimal(f['costo_receta']), Decimal('0.98'))
        self.assertEqual(self.fila(directo)['ingredientes_sin_costo'], ['Platano sin precio MP test'])
        # Un producto completo no trae avisos.
        self.assertEqual(self.fila()['ingredientes_sin_costo'], [])
        # Y la lista de productos trae el mismo aviso.
        r = self.client.get('/api/admin/productos/')
        self.assertEqual(r.status_code, 200, r.content)
        por_id = {p['id']: p for p in r.json()['products']}
        self.assertEqual(por_id[directo.id]['ingredientes_sin_costo'], ['Platano sin precio MP test'])
        self.assertEqual(por_id[self.producto.id]['ingredientes_sin_costo'], [])

    def test_no_incluye_la_categoria_recetas(self):
        from varagrill.models import VGCategoriaProducto, VGProducto
        recetas = VGCategoriaProducto.objects.create(nombre='Recetas')
        receta = VGProducto.objects.create(nombre='Receta maestra MP test', categoria=recetas, precio_venta='0')
        r = self.client.get('/api/admin/reportes/margen-productos/')
        self.assertEqual(r.status_code, 200, r.content)
        ids = {f['producto_id'] for f in r.json()['productos']}
        self.assertNotIn(receta.id, ids)
        self.assertIn(self.producto.id, ids)
        self.assertNotIn('Recetas', {f['categoria'] for f in r.json()['productos']})

    def test_solo_administradores_y_solo_lectura(self):
        self.assertEqual(self.client.post('/api/admin/reportes/margen-productos/').status_code, 405)
        self.client.force_login(self.cajera)
        self.assertEqual(self.client.get('/api/admin/reportes/margen-productos/').status_code, 401)


# ---------------------------------------------------------------------------
# Reporte DETALLADO de margen de ganancia (venta por venta): costo + margen de produccion y totales
# ---------------------------------------------------------------------------
class MargenDetalladoReporteTests(TestCase):
    def setUp(self):
        from varagrill.models import VGCategoriaProducto, VGConfiguracionCosteo, VGIngrediente, VGPreparacion, VGProducto, VGRecetaPreparacion, VGRecetaProducto
        admin_role, _ = VGRol.objects.get_or_create(nombre_role='Administrador')
        self.admin = VGUsuario.objects.create_superuser(
            username='md_admin', password='claveAdmin123', cedula='95000001', email='md_admin@varagrill.test', id_role=admin_role,
        )
        config = VGConfiguracionCosteo.obtener_config()
        config.rendimiento_receta_pct = Decimal('50')
        config.save()
        categoria = VGCategoriaProducto.objects.create(nombre='Cat MD test')
        self.ingrediente = VGIngrediente.objects.create(nombre='Maiz MD test', unidad_medida='g', costo_unitario='0.98')
        self.receta_producto = VGProducto.objects.create(nombre='Plato con receta MD test', categoria=categoria, precio_venta='4.00')
        VGRecetaProducto.objects.create(producto=self.receta_producto, ingrediente=self.ingrediente, cantidad_requerida='1')
        sub = VGPreparacion.objects.create(nombre='Subreceta MD test', rendimiento_cantidad='1000', rendimiento_unidad='g')
        VGRecetaPreparacion.objects.create(preparacion=sub, ingrediente=self.ingrediente, cantidad_requerida='1')
        self.sub_producto = VGProducto.objects.create(
            nombre='Plato con subreceta MD test', categoria=categoria, precio_venta='4.00', subreceta_vinculada=sub,
        )
        self.client.force_login(self.admin)

    def venta(self, producto, cantidad=1, costo=None, margen=None, precio='4.00'):
        pedido = VGPedido.objects.create(usuario=self.admin, tipo_pedido='local', estado='pagado', subtotal=precio, total=precio)
        return VGDetallePedido.objects.create(
            pedido=pedido, producto=producto, cantidad=cantidad, precio_unitario=precio, estado='entregado',
            costo_unitario_venta=Decimal(costo) if costo is not None else None,
            margen_produccion_pct_venta=Decimal(margen) if margen is not None else None,
        )

    def reporte(self, desde=None, hasta=None):
        hoy = timezone.localdate().isoformat()
        r = self.client.get(f'/api/admin/reportes/margen-ganancia/?desde={desde or hoy}&hasta={hasta or hoy}')
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()

    def fila(self, data, producto):
        seccion = next(s for s in data['secciones'] if s['producto_id'] == producto.id)
        return seccion['filas'][0]

    def test_venta_de_receta_con_margen_congelado_separa_el_costo_puro(self):
        # El costo guardado (1.47) ya trae el 50% sumado: el costo puro es 0.98.
        self.venta(self.receta_producto, cantidad=2, costo='1.47', margen='50')
        f = self.fila(self.reporte(), self.receta_producto)
        self.assertEqual(Decimal(f['costo_unitario']), Decimal('0.98'))
        self.assertEqual(Decimal(f['costo']), Decimal('1.96'))
        self.assertEqual(Decimal(f['costo_con_margen']), Decimal('2.94'))
        self.assertEqual(Decimal(f['ganancia_monto']), Decimal('5.06'))      # 8.00 - 2.94
        self.assertFalse(f['margen_estimado'])
        self.assertFalse(f['costo_estimado'])

    def test_venta_de_subreceta_no_trae_margen_dentro_y_se_le_suma(self):
        self.venta(self.sub_producto, costo='0.98', margen='50')
        f = self.fila(self.reporte(), self.sub_producto)
        self.assertEqual(Decimal(f['costo_unitario']), Decimal('0.98'))
        self.assertEqual(Decimal(f['costo_con_margen']), Decimal('1.47'))
        self.assertEqual(Decimal(f['ganancia_monto']), Decimal('2.53'))

    def test_el_margen_congelado_no_cambia_si_despues_cambia_la_configuracion(self):
        from varagrill.models import VGConfiguracionCosteo
        self.venta(self.receta_producto, costo='1.47', margen='50')
        config = VGConfiguracionCosteo.obtener_config()
        config.rendimiento_receta_pct = Decimal('200')
        config.save()
        f = self.fila(self.reporte(), self.receta_producto)
        self.assertEqual(Decimal(f['costo_con_margen']), Decimal('1.47'))
        self.assertFalse(f['margen_estimado'])

    def test_venta_vieja_sin_margen_guardado_usa_el_de_hoy_y_se_marca(self):
        self.venta(self.receta_producto, costo='1.00', margen=None)
        f = self.fila(self.reporte(), self.receta_producto)
        self.assertEqual(Decimal(f['costo_unitario']), Decimal('1.00'))
        self.assertEqual(Decimal(f['costo_con_margen']), Decimal('1.50'))
        self.assertTrue(f['margen_estimado'])
        self.assertFalse(f['costo_estimado'])

    def test_venta_sin_costo_congelado_se_estima_con_el_costo_puro_de_hoy(self):
        self.venta(self.receta_producto, costo=None, margen=None)
        f = self.fila(self.reporte(), self.receta_producto)
        self.assertEqual(Decimal(f['costo_unitario']), Decimal('0.98'))
        self.assertEqual(Decimal(f['costo_con_margen']), Decimal('1.47'))
        self.assertTrue(f['costo_estimado'])
        self.assertTrue(f['margen_estimado'])

    def test_los_totales_suman_todas_las_ventas_aunque_el_plato_se_repita(self):
        self.venta(self.receta_producto, cantidad=1, costo='1.47', margen='50')
        self.venta(self.receta_producto, cantidad=2, costo='1.47', margen='50')
        self.venta(self.sub_producto, cantidad=1, costo='0.98', margen='50')
        data = self.reporte()
        t = data['totales']
        self.assertEqual(data['total_lineas'], 3)
        self.assertEqual(Decimal(t['ingreso_total']), Decimal('16.00'))            # 4 + 8 + 4
        self.assertEqual(Decimal(t['costo_total']), Decimal('3.92'))               # 0.98 x 4 unidades
        self.assertEqual(Decimal(t['costo_con_margen_total']), Decimal('5.88'))    # 1.47 x 4 unidades
        self.assertEqual(Decimal(t['ganancia_monto']), Decimal('10.12'))           # 16 - 5.88
        seccion = next(s for s in data['secciones'] if s['producto_id'] == self.receta_producto.id)
        self.assertEqual(seccion['total_lineas'], 2)
        self.assertEqual(Decimal(seccion['total_costo_con_margen']), Decimal('4.41'))   # 3 platos x 1.47

    def test_respeta_las_fechas_elegidas(self):
        detalle = self.venta(self.receta_producto, costo='1.47', margen='50')
        ayer = timezone.now() - timedelta(days=3)
        VGPedido.objects.filter(pk=detalle.pedido_id).update(fecha_creacion=ayer)
        hoy = timezone.localdate()
        self.assertEqual(self.reporte()['total_lineas'], 0)
        rango = self.reporte(desde=(hoy - timedelta(days=5)).isoformat(), hasta=hoy.isoformat())
        self.assertEqual(rango['total_lineas'], 1)

    def test_al_cobrar_se_congela_el_margen_de_produccion_de_ese_dia(self):
        from varagrill.api_views import _load_preparation_cost_map, _snapshot_costo_venta_detalles
        from varagrill.models import VGConfiguracionCosteo, VGIngrediente
        detalle = self.venta(self.receta_producto, costo=None, margen=None)
        ingredient_costs = {i.id: i.costo_unitario for i in VGIngrediente.objects.all()}
        _snapshot_costo_venta_detalles(detalle.pedido, ingredient_costs, _load_preparation_cost_map())
        detalle.refresh_from_db()
        self.assertEqual(detalle.costo_unitario_venta, Decimal('1.4700'))
        self.assertEqual(detalle.margen_produccion_pct_venta, Decimal('50.00'))
        # Y al volver a leer el reporte, el costo puro se recupera sin contar el margen dos veces.
        f = self.fila(self.reporte(), self.receta_producto)
        self.assertEqual(Decimal(f['costo_unitario']), Decimal('0.98'))
        self.assertEqual(Decimal(f['costo_con_margen']), Decimal('1.47'))
        self.assertFalse(f['margen_estimado'])


class ReporteInventarioPdfTests(TestCase):
    URL = '/api/admin/reportes/inventario-pdf/'

    def setUp(self):
        admin_role, _ = VGRol.objects.get_or_create(nombre_role='Administrador')
        cajera_role, _ = VGRol.objects.get_or_create(nombre_role='Cajera')
        self.admin = VGUsuario.objects.create_superuser(
            username='pdf_admin', password='claveAdmin123', cedula='95000001', email='pdf_admin@varagrill.test', id_role=admin_role,
        )
        self.cajera = VGUsuario.objects.create_user(
            username='pdf_cajera', password='claveCajera123', cedula='95000002', email='pdf_cajera@varagrill.test', id_role=cajera_role,
        )

    def test_solo_administradores_pueden_descargarlo(self):
        self.assertEqual(self.client.get(self.URL).status_code, 401)
        self.client.force_login(self.cajera)
        self.assertEqual(self.client.get(self.URL).status_code, 401)

    def test_responde_un_pdf_descargable(self):
        from varagrill.models import VGIngrediente
        VGIngrediente.objects.create(nombre='Carne PDF test', unidad_medida='g', stock_actual='1500', costo_unitario='0.0068')
        self.client.force_login(self.admin)
        r = self.client.get(self.URL)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'application/pdf')
        self.assertIn('attachment; filename="inventario-actual-', r['Content-Disposition'])
        self.assertTrue(r.content.startswith(b'%PDF'))

    def test_un_inventario_vacio_tambien_genera_pdf(self):
        from varagrill.models import VGIngrediente
        VGIngrediente.objects.all().delete()
        self.client.force_login(self.admin)
        r = self.client.get(self.URL)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.content.startswith(b'%PDF'))

    def test_usa_el_costo_efectivo_y_omite_los_ingredientes_ocultos(self):
        from unittest import mock
        from varagrill.models import VGIngrediente
        # costo_unitario desincronizado (0.5) pero el envase dice 10 / 1000 = 0.01 por gramo
        VGIngrediente.objects.create(
            nombre='Harina PDF test', unidad_medida='g', stock_actual='2000', costo_unitario='0.5',
            contenido_envase='1000', peso_real='1000', precio_compra='10.00',
        )
        VGIngrediente.objects.create(id=285, nombre='Oculto PDF test', unidad_medida='g', stock_actual='1', costo_unitario='1')
        self.client.force_login(self.admin)
        with mock.patch('varagrill.reportes_pdf_views.generar_pdf_inventario', return_value=b'%PDF-falso') as generar:
            r = self.client.get(self.URL)
        self.assertEqual(r.status_code, 200)
        enviados = {i['nombre']: i for i in generar.call_args.args[0]}
        self.assertNotIn('Oculto PDF test', enviados)
        self.assertEqual(Decimal(enviados['Harina PDF test']['costo_unitario']), Decimal('0.01'))

    def test_calcula_valor_total_orden_y_total_del_inventario(self):
        from varagrill.pdf_reportes import armar_filas_inventario
        filas, total = armar_filas_inventario([
            {'nombre': 'zanahoria', 'unidad_medida': 'g', 'stock_actual': Decimal('100'), 'costo_unitario': Decimal('0.00125')},
            {'nombre': 'Aceite', 'unidad_medida': 'ml', 'stock_actual': Decimal('6000'), 'costo_unitario': Decimal('0.0065')},
            {'nombre': '7UP', 'unidad_medida': 'unidad', 'stock_actual': Decimal('48'), 'costo_unitario': Decimal('0.58')},
        ])
        self.assertEqual([f['nombre'] for f in filas], ['7UP', 'Aceite', 'zanahoria'])
        self.assertEqual([f['unidad'] for f in filas], ['Unidad', 'Mililitros', 'Gramos'])
        self.assertEqual([f['valor_total'] for f in filas], [Decimal('27.84'), Decimal('39.00'), Decimal('0.13')])
        self.assertEqual(total, Decimal('66.97'))

    def test_formato_de_numeros_como_el_resto_del_sistema(self):
        from varagrill.pdf_reportes import formatear_numero
        self.assertEqual(formatear_numero(Decimal('1234.5')), '1.234,50')
        self.assertEqual(formatear_numero(Decimal('0.0068'), 2, 6), '0,0068')
        self.assertEqual(formatear_numero(Decimal('0.58'), 2, 6), '0,58')
        self.assertEqual(formatear_numero(Decimal('0'), 2, 6), '0,00')
        self.assertEqual(formatear_numero(Decimal('1022819.95'), 0, 2), '1.022.819,95')
        self.assertEqual(formatear_numero(Decimal('6000'), 0, 2), '6.000')
        self.assertEqual(formatear_numero(Decimal('-3239.27')), '-3.239,27')


class BaseReportesPdfTests(TestCase):
    """Lo comun a todos los reportes PDF (pdf_reportes/base.py y las ayudas de reportes_pdf_views.py)."""

    def columnas(self):
        from varagrill.pdf_reportes import Columna
        return [Columna('Concepto', 0.6), Columna('Monto ($)', 0.4, 'derecha')]

    def test_genera_pdf_vertical_y_horizontal(self):
        from varagrill.pdf_reportes import generar_pdf_tabla
        filas = [['Alquiler', '500,00'], ['Luz', '120,50']]
        vertical = generar_pdf_tabla(titulo='Gastos', columnas=self.columnas(), filas=filas)
        horizontal = generar_pdf_tabla(titulo='Gastos', columnas=self.columnas(), filas=filas, orientacion='horizontal')
        self.assertTrue(vertical.startswith(b'%PDF'))
        self.assertTrue(horizontal.startswith(b'%PDF'))
        # A4 vertical es 595 x 842 pt; apaisado es 842 x 595.
        self.assertIn(b'/MediaBox [ 0 0 595.2', vertical)
        self.assertIn(b'/MediaBox [ 0 0 841.8', horizontal)

    def test_acepta_resumen_total_subtitulo_y_textos_con_simbolos(self):
        from varagrill.pdf_reportes import escapar, generar_pdf_tabla
        pdf = generar_pdf_tabla(
            titulo='Gastos <del mes> & más',
            subtitulo='Del 01/10/2026 al 08/10/2026',
            columnas=self.columnas(),
            filas=[['Pan & Queso <extra>', '10,00']],
            resumen=(f'<b>1</b> gasto de {escapar("Café & Té")}', 'Total: <b>$ 10,00</b>'),
            fila_total=['Total', '$ 10,00'],
        )
        self.assertTrue(pdf.startswith(b'%PDF'))

    def test_una_tabla_vacia_tambien_genera_pdf(self):
        from varagrill.pdf_reportes import generar_pdf_tabla
        pdf = generar_pdf_tabla(titulo='Vacio', columnas=self.columnas(), filas=[], fila_total=['Total', '$ 0,00'])
        self.assertTrue(pdf.startswith(b'%PDF'))

    def test_una_tabla_larga_ocupa_varias_paginas(self):
        from varagrill.pdf_reportes import generar_pdf_tabla
        pdf = generar_pdf_tabla(titulo='Largo', columnas=self.columnas(), filas=[[f'Fila {i}', '1,00'] for i in range(200)])
        import re
        self.assertGreater(len(re.findall(rb'/Type /Page(?!s)', pdf)), 3)

    def test_rechaza_descripciones_incorrectas(self):
        from varagrill.pdf_reportes import Columna, generar_pdf_tabla
        with self.assertRaises(ValueError):
            generar_pdf_tabla(titulo='X', columnas=[Columna('A', 0.5), Columna('B', 0.2)], filas=[])  # no suman 1
        with self.assertRaises(ValueError):
            generar_pdf_tabla(titulo='X', columnas=self.columnas(), filas=[['solo una celda']])
        with self.assertRaises(ValueError):
            generar_pdf_tabla(titulo='X', columnas=self.columnas(), filas=[], orientacion='diagonal')
        with self.assertRaises(ValueError):
            generar_pdf_tabla(titulo='X', columnas=[Columna('A', 1, 'arriba')], filas=[])

    def test_responder_pdf_arma_el_nombre_y_evita_el_cache(self):
        import datetime
        from varagrill.reportes_pdf_views import responder_pdf
        r = responder_pdf(b'%PDF-x', 'gastos', datetime.date(2026, 10, 8))
        self.assertEqual(r['Content-Type'], 'application/pdf')
        self.assertEqual(r['Content-Disposition'], 'attachment; filename="gastos-2026-10-08.pdf"')
        self.assertEqual(r['Cache-Control'], 'no-store')

    def test_pdf_solo_admin_rechaza_metodos_que_no_son_get(self):
        admin_role, _ = VGRol.objects.get_or_create(nombre_role='Administrador')
        admin = VGUsuario.objects.create_superuser(
            username='base_pdf_admin', password='claveAdmin123', cedula='95000003', email='base_pdf_admin@varagrill.test', id_role=admin_role,
        )
        self.client.force_login(admin)
        self.assertEqual(self.client.post('/api/admin/reportes/inventario-pdf/').status_code, 405)


class ReporteGastosPdfTests(TestCase):
    URL = '/api/admin/reportes/gastos-pdf/'

    def setUp(self):
        from datetime import date
        from varagrill.models import VGAbonoGasto, VGCategoriaGasto, VGGasto, VGMetodoPago
        admin_role, _ = VGRol.objects.get_or_create(nombre_role='Administrador')
        cajera_role, _ = VGRol.objects.get_or_create(nombre_role='Cajera')
        self.admin = VGUsuario.objects.create_superuser(
            username='gpdf_admin', password='claveAdmin123', cedula='95000011', email='gpdf_admin@varagrill.test', id_role=admin_role,
        )
        self.cajera = VGUsuario.objects.create_user(
            username='gpdf_cajera', password='claveCajera123', cedula='95000012', email='gpdf_cajera@varagrill.test', id_role=cajera_role,
        )
        _set_tasa_actual('900.0000')
        self.nomina = VGCategoriaGasto.objects.create(nombre='Nomina PDF test')
        self.servicios = VGCategoriaGasto.objects.create(nombre='Servicios PDF test')
        self.metodo = VGMetodoPago.objects.create(nombre='Banco PDF test', moneda='VES')

        # $100 pagados con un abono a tasa 800 -> Bs 80.000 congelados (aunque hoy la tasa sea 900)
        self.pagado_usd = VGGasto.objects.create(
            categoria=self.nomina, descripcion='Quincena 1', monto=Decimal('100'), saldo_pendiente=0, estado_pago='pagado',
            fecha_gasto=date(2026, 9, 5), tasa_cambio_referencia=Decimal('800.0000'),
        )
        VGAbonoGasto.objects.create(gasto=self.pagado_usd, monto=Decimal('100'), metodo_pago=self.metodo, tasa_cambio_referencia=Decimal('800.0000'))
        # Gasto cargado en bolivares: Bs 20.000 a tasa 800 = $25
        self.en_bs = VGGasto.objects.create(
            categoria=self.servicios, descripcion='Internet', monto=Decimal('25'), saldo_pendiente=0, estado_pago='pagado',
            fecha_gasto=date(2026, 9, 20), tasa_cambio_referencia=Decimal('800.0000'), moneda_origen='VES',
        )
        VGAbonoGasto.objects.create(gasto=self.en_bs, monto=Decimal('25'), metodo_pago=self.metodo, tasa_cambio_referencia=Decimal('800.0000'))
        # Fuera del rango de septiembre
        self.octubre = VGGasto.objects.create(
            categoria=self.nomina, descripcion='De octubre', monto=Decimal('50'), saldo_pendiente=50,
            fecha_gasto=date(2026, 10, 2), tasa_cambio_referencia=Decimal('900.0000'),
        )

    def descargar(self, desde='2026-09-01', hasta='2026-09-30'):
        from unittest import mock
        self.client.force_login(self.admin)
        with mock.patch('varagrill.reportes_pdf_views.generar_pdf_gastos', return_value=b'%PDF-falso') as generar:
            r = self.client.get(f'{self.URL}?fecha_desde={desde}&fecha_hasta={hasta}')
        return r, generar

    def test_solo_administradores_pueden_descargarlo(self):
        self.assertEqual(self.client.get(self.URL).status_code, 401)
        self.client.force_login(self.cajera)
        self.assertEqual(self.client.get(self.URL).status_code, 401)

    def test_rechaza_un_rango_invertido(self):
        self.client.force_login(self.admin)
        r = self.client.get(f'{self.URL}?fecha_desde=2026-09-30&fecha_hasta=2026-09-01')
        self.assertEqual(r.status_code, 400)
        self.assertIn('fecha inicial', r.json()['message'])

    def test_responde_un_pdf_real_con_el_rango_en_el_nombre(self):
        self.client.force_login(self.admin)
        r = self.client.get(f'{self.URL}?fecha_desde=2026-09-01&fecha_hasta=2026-09-30')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'application/pdf')
        self.assertEqual(r['Content-Disposition'], 'attachment; filename="gastos-2026-09-01-al-2026-09-30.pdf"')
        self.assertTrue(r.content.startswith(b'%PDF'))

    def test_un_rango_sin_gastos_tambien_genera_pdf(self):
        self.client.force_login(self.admin)
        r = self.client.get(f'{self.URL}?fecha_desde=2025-01-01&fecha_hasta=2025-01-31')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.content.startswith(b'%PDF'))

    def test_incluye_solo_los_gastos_del_rango_con_los_montos_de_la_pantalla(self):
        r, generar = self.descargar()
        self.assertEqual(r.status_code, 200)
        gastos, desde, hasta = generar.call_args.args[:3]
        por_descripcion = {g['descripcion']: g for g in gastos}
        self.assertEqual(set(por_descripcion), {'Quincena 1', 'Internet'})
        self.assertEqual((str(desde), str(hasta)), ('2026-09-01', '2026-09-30'))
        # Bs congelados con la tasa del abono (800), no con la de hoy (900)
        self.assertEqual(Decimal(por_descripcion['Quincena 1']['total_bs']), Decimal('80000.00'))
        self.assertEqual(Decimal(por_descripcion['Internet']['total_bs']), Decimal('20000.00'))

    def test_agrupa_por_categoria_con_totales_en_bs_y_dolares(self):
        from datetime import date
        from varagrill.pdf_reportes import armar_bloques_gastos
        gastos = [
            {'id': 3, 'categoria_nombre': 'Servicios', 'descripcion': 'Luz', 'estado_pago': 'pagado', 'fecha_gasto': date(2026, 9, 9),
             'monto': '10', 'total_bs': '8000.00', 'moneda_origen': 'USD', 'tasa_cambio_referencia': '800.0000'},
            {'id': 2, 'categoria_nombre': 'nomina', 'descripcion': 'Quincena 2', 'estado_pago': 'pagado', 'fecha_gasto': date(2026, 9, 20),
             'monto': '100', 'total_bs': '82000.00', 'moneda_origen': 'USD', 'tasa_cambio_referencia': '820.0000'},
            {'id': 1, 'categoria_nombre': 'nomina', 'descripcion': 'Quincena 1', 'estado_pago': 'pagado', 'fecha_gasto': date(2026, 9, 5),
             'monto': '100', 'total_bs': '80000.00', 'moneda_origen': 'USD', 'tasa_cambio_referencia': '800.0000'},
        ]
        bloques = armar_bloques_gastos(gastos)
        self.assertEqual([b['categoria'] for b in bloques], ['nomina', 'Servicios'])
        nomina = bloques[0]
        # dentro de la categoria, por fecha
        self.assertEqual([f['descripcion'] for f in nomina['filas']], ['Quincena 1', 'Quincena 2'])
        self.assertEqual(nomina['total_bs'], Decimal('162000.00'))
        self.assertEqual(nomina['total_usd'], Decimal('200.00'))
        self.assertEqual(bloques[1]['total_bs'], Decimal('8000.00'))

    def test_la_tasa_es_la_del_gasto_y_marca_los_que_no_estan_pagados(self):
        from datetime import date
        from varagrill.pdf_reportes import armar_bloques_gastos
        from varagrill.pdf_reportes.gastos import tasa_del_gasto
        # En dolares: tasa = bolivares / dolares (promedio ponderado si hubo abonos con tasas distintas)
        usd = {'monto': '100', 'total_bs': '81000.00', 'moneda_origen': 'USD', 'tasa_cambio_referencia': '800.0000'}
        self.assertEqual(tasa_del_gasto(usd), Decimal('810'))
        # En bolivares conserva la tasa del dia en que se registro
        ves = {'monto': '25', 'total_bs': '20000.00', 'moneda_origen': 'VES', 'tasa_cambio_referencia': '800.0000'}
        self.assertEqual(tasa_del_gasto(ves), Decimal('800.0000'))
        bloques = armar_bloques_gastos([
            {'id': 1, 'categoria_nombre': 'Aseo', 'descripcion': 'Jabon', 'estado_pago': 'pendiente', 'fecha_gasto': date(2026, 9, 8),
             'monto': '5', 'total_bs': '4500.00', 'moneda_origen': 'USD', 'tasa_cambio_referencia': '800.0000'},
            {'id': 2, 'categoria_nombre': 'Aseo', 'descripcion': 'Cloro', 'estado_pago': 'abonada_parcial', 'fecha_gasto': date(2026, 9, 9),
             'monto': '5', 'total_bs': '4500.00', 'moneda_origen': 'USD', 'tasa_cambio_referencia': '800.0000'},
        ])
        self.assertEqual([f['descripcion'] for f in bloques[0]['filas']], ['Jabon (pendiente)', 'Cloro (abonado parcial)'])

    def test_un_gasto_sin_tasa_no_suma_en_bs_pero_si_en_dolares(self):
        from datetime import date
        from varagrill.pdf_reportes import armar_bloques_gastos
        bloque = armar_bloques_gastos([
            {'id': 1, 'categoria_nombre': 'Aseo', 'descripcion': 'Sin tasa', 'estado_pago': 'pagado', 'fecha_gasto': date(2026, 9, 8),
             'monto': '5', 'total_bs': None, 'moneda_origen': 'USD', 'tasa_cambio_referencia': None},
            {'id': 2, 'categoria_nombre': 'Aseo', 'descripcion': 'Con tasa', 'estado_pago': 'pagado', 'fecha_gasto': date(2026, 9, 9),
             'monto': '10', 'total_bs': '8000.00', 'moneda_origen': 'USD', 'tasa_cambio_referencia': '800.0000'},
        ])[0]
        self.assertEqual(bloque['sin_tasa'], 1)
        self.assertEqual(bloque['total_bs'], Decimal('8000.00'))
        self.assertEqual(bloque['total_usd'], Decimal('15.00'))


class TasaCuentaPrefacturaTests(TestCase):
    """
    La nota de entrega (y la factura) heredan la tasa de la pre-factura que se le dio al cliente mientras
    siga vigente y dentro de la ventana (60 min), aunque la tasa BCV cambie en el medio. Ver tasa_cuenta.py.
    """

    def setUp(self):
        from varagrill.models import VGPreFactura
        self.VGPreFactura = VGPreFactura
        cajera_role, _ = VGRol.objects.get_or_create(nombre_role='Cajera')
        self.user = VGUsuario.objects.create_user(
            username='tc_cajera', password='claveCajera123', cedula='96000001', email='tc_cajera@varagrill.test', id_role=cajera_role,
        )
        self.client.force_login(self.user)
        self.category = VGCategoriaProducto.objects.create(nombre='Platos TC')
        self.plato = VGProducto.objects.create(nombre='Plato TC', categoria=self.category, precio_venta='10.00', disponible=True)
        self.efectivo = VGMetodoPago.objects.create(nombre='Efectivo TC', moneda='USD', es_efectivo=True)
        self.banco_bs = VGMetodoPago.objects.create(nombre='Banco Bs TC', moneda='VES')
        _set_tasa_actual('100.0000')

    def pedido(self, total='10.00'):
        pedido = VGPedido.objects.create(usuario=self.user, tipo_pedido='local', estado='entregado', subtotal=total, total=total)
        VGDetallePedido.objects.create(pedido=pedido, producto=self.plato, cantidad=1, precio_unitario=total, estado='entregado')
        return pedido

    def prefactura(self, pedidos, **extra):
        r = self.client.post('/api/prefacturas/', data=json.dumps({'pedido_ids': [p.id for p in pedidos], **extra}), content_type='application/json')
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()

    def cobrar(self, pedidos, **extra):
        r = self.client.post('/api/pedidos/cobro/', data=json.dumps({
            'pedido_ids': [p.id for p in pedidos], 'metodo_pago_id': self.efectivo.id,
            'cliente_numero_documento': '96000111', 'cliente_nombre': 'Cliente TC', **extra,
        }), content_type='application/json')
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()['nota_entrega']

    def tasa_de_la_nota(self, nota):
        from varagrill.models import VGNotaEntrega
        return VGNotaEntrega.objects.get(pk=nota['id']).tasa_cambio_referencia

    def envejecer(self, prefactura_id, minutos):
        from datetime import timedelta
        pasado = timezone.now() - timedelta(minutes=minutos)
        self.VGPreFactura.objects.filter(pk=prefactura_id).update(tasa_fijada_en=pasado, fecha_emision=pasado)

    def test_la_nota_conserva_la_tasa_de_la_prefactura_aunque_la_tasa_suba(self):
        pedido = self.pedido()
        pf = self.prefactura([pedido])['prefactura']
        _set_tasa_actual('120.0000')
        nota = self.cobrar([pedido])
        self.assertEqual(self.tasa_de_la_nota(nota), Decimal('100.0000'))
        self.assertEqual(nota['tasa_origen'], 'prefactura')
        self.assertEqual(nota['tasa_prefactura'], pf['codigo'])
        self.assertEqual(nota['tasa_cambio_referencia'], '100.0000')

    def test_la_nota_conserva_la_tasa_de_la_prefactura_aunque_la_tasa_baje(self):
        pedido = self.pedido()
        self.prefactura([pedido])
        _set_tasa_actual('80.0000')
        self.assertEqual(self.tasa_de_la_nota(self.cobrar([pedido])), Decimal('100.0000'))

    def test_pasada_la_ventana_se_usa_la_tasa_actual_y_se_avisa(self):
        pedido = self.pedido()
        pf = self.prefactura([pedido])['prefactura']
        self.envejecer(pf['id'], 61)
        _set_tasa_actual('120.0000')
        nota = self.cobrar([pedido])
        self.assertEqual(self.tasa_de_la_nota(nota), Decimal('120.0000'))
        self.assertEqual(nota['tasa_origen'], 'actual')
        self.assertTrue(nota['tasa_prefactura_vencida'])

    def test_dentro_de_la_ventana_todavia_vale(self):
        pedido = self.pedido()
        pf = self.prefactura([pedido])['prefactura']
        self.envejecer(pf['id'], 59)
        _set_tasa_actual('120.0000')
        self.assertEqual(self.tasa_de_la_nota(self.cobrar([pedido])), Decimal('100.0000'))

    def test_sin_prefactura_se_usa_la_tasa_actual_como_siempre(self):
        pedido = self.pedido()
        _set_tasa_actual('120.0000')
        nota = self.cobrar([pedido])
        self.assertEqual(self.tasa_de_la_nota(nota), Decimal('120.0000'))
        self.assertEqual(nota['tasa_origen'], 'actual')
        self.assertFalse(nota['tasa_prefactura_vencida'])

    def test_una_prefactura_anulada_se_ignora(self):
        pedido = self.pedido()
        pf = self.prefactura([pedido])['prefactura']
        self.assertEqual(self.client.post(f'/api/prefacturas/{pf["id"]}/anular/').status_code, 200)
        _set_tasa_actual('120.0000')
        self.assertEqual(self.tasa_de_la_nota(self.cobrar([pedido])), Decimal('120.0000'))

    def test_si_la_prefactura_cubre_solo_una_parte_de_lo_que_se_cobra_no_aplica(self):
        a, b = self.pedido(), self.pedido()
        self.prefactura([a])
        _set_tasa_actual('120.0000')
        self.assertEqual(self.tasa_de_la_nota(self.cobrar([a, b])), Decimal('120.0000'))

    def test_si_la_prefactura_cubre_mas_de_lo_que_se_cobra_si_aplica(self):
        a, b = self.pedido(), self.pedido()
        self.prefactura([a, b])
        _set_tasa_actual('120.0000')
        self.assertEqual(self.tasa_de_la_nota(self.cobrar([a])), Decimal('100.0000'))

    def test_la_cajera_puede_elegir_cobrar_a_la_tasa_actual(self):
        pedido = self.pedido()
        self.prefactura([pedido])
        _set_tasa_actual('120.0000')
        nota = self.cobrar([pedido], usar_tasa_actual=True)
        self.assertEqual(self.tasa_de_la_nota(nota), Decimal('120.0000'))
        self.assertEqual(nota['tasa_origen'], 'actual')

    def test_generar_la_prefactura_dos_veces_conserva_la_tasa_de_la_primera(self):
        pedido = self.pedido()
        primera = self.prefactura([pedido])
        _set_tasa_actual('120.0000')
        segunda = self.prefactura([pedido])
        self.assertFalse(primera['tasa_reutilizada'])
        self.assertTrue(segunda['tasa_reutilizada'])
        self.assertEqual(segunda['prefactura']['tasa_cambio_referencia'], '100.0000')
        self.assertNotEqual(primera['prefactura']['id'], segunda['prefactura']['id'])
        self.assertEqual(
            self.VGPreFactura.objects.get(pk=primera['prefactura']['id']).tasa_fijada_en,
            self.VGPreFactura.objects.get(pk=segunda['prefactura']['id']).tasa_fijada_en,
        )

    def test_renovar_la_tasa_congela_la_de_hoy_y_la_nota_usa_la_mas_reciente(self):
        pedido = self.pedido()
        self.prefactura([pedido])
        _set_tasa_actual('110.0000')
        renovada = self.prefactura([pedido], renovar_tasa=True)
        self.assertFalse(renovada['tasa_reutilizada'])
        self.assertEqual(renovada['prefactura']['tasa_cambio_referencia'], '110.0000')
        _set_tasa_actual('130.0000')
        self.assertEqual(self.tasa_de_la_nota(self.cobrar([pedido])), Decimal('110.0000'))

    def test_reimprimir_no_estira_la_tasa_vieja_mas_alla_de_la_ventana(self):
        pedido = self.pedido()
        primera = self.prefactura([pedido])['prefactura']
        self.envejecer(primera['id'], 50)
        segunda = self.prefactura([pedido])
        self.assertTrue(segunda['tasa_reutilizada'])
        # la copia hereda la hora de congelado de la primera: a los 61 min ya no vale ninguna de las dos
        self.envejecer(primera['id'], 61)
        self.envejecer(segunda['prefactura']['id'], 61)
        _set_tasa_actual('120.0000')
        tercera = self.prefactura([pedido])
        self.assertFalse(tercera['tasa_reutilizada'])
        self.assertEqual(tercera['prefactura']['tasa_cambio_referencia'], '120.0000')

    def test_el_abono_en_bolivares_saldando_la_nota_cuadra_con_lo_que_se_cotizo(self):
        from varagrill.models import VGNotaEntrega, VGPago
        pedido = self.pedido('10.00')
        self.prefactura([pedido])          # el cliente ve $10 = Bs 1.000 a tasa 100
        _set_tasa_actual('120.0000')       # la tasa sube mientras espera
        nota = self.cobrar([pedido])
        r = self.client.post(
            f'/api/notas-entrega/{nota["id"]}/abonos/',
            data=json.dumps({'monto': '1000.00', 'metodo_pago_id': self.banco_bs.id, 'referencia': 'REF-TC-1'}),
            content_type='application/json',
        )
        self.assertEqual(r.status_code, 201, r.content)
        nota_db = VGNotaEntrega.objects.get(pk=nota['id'])
        self.assertEqual(nota_db.estado, 'pagada')
        self.assertEqual(nota_db.saldo_pendiente, Decimal('0'))
        pago = VGPago.objects.get(nota_entrega=nota_db)
        self.assertEqual(pago.tasa_cambio_referencia, Decimal('100.0000'))
        self.assertEqual((pago.monto * pago.tasa_cambio_referencia).quantize(Decimal('0.01')), Decimal('1000.00'))

    def test_el_listado_de_cobro_trae_las_prefacturas_con_tasa_vigente(self):
        pedido = self.pedido()
        pf = self.prefactura([pedido])['prefactura']
        r = self.client.get('/api/pedidos/cobro/')
        self.assertEqual(r.status_code, 200)
        vigentes = r.json()['prefacturas_tasa_vigente']
        self.assertEqual(len(vigentes), 1)
        self.assertEqual(vigentes[0]['codigo'], pf['codigo'])
        self.assertEqual(Decimal(vigentes[0]['tasa']), Decimal('100.0000'))
        self.assertEqual(vigentes[0]['pedido_ids'], [pedido.id])
        self.assertIn(vigentes[0]['minutos_restantes'], (59, 60))
        self.envejecer(pf['id'], 61)
        self.assertEqual(self.client.get('/api/pedidos/cobro/').json()['prefacturas_tasa_vigente'], [])

    def test_convertir_la_prefactura_en_factura_conserva_su_tasa(self):
        pedido = self.pedido()
        pf = self.prefactura([pedido])['prefactura']
        _set_tasa_actual('120.0000')
        r = self.client.post(f'/api/prefacturas/{pf["id"]}/convertir/')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()['factura']['tasa_cambio_referencia'], '100.0000')

    def test_convertir_una_prefactura_vencida_usa_la_tasa_actual(self):
        pedido = self.pedido()
        pf = self.prefactura([pedido])['prefactura']
        self.envejecer(pf['id'], 61)
        _set_tasa_actual('120.0000')
        r = self.client.post(f'/api/prefacturas/{pf["id"]}/convertir/')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()['factura']['tasa_cambio_referencia'], '120.0000')


class ReporteFacturadoPdfTests(TestCase):
    URL = '/api/admin/reportes/facturado-pdf/'

    def setUp(self):
        from datetime import datetime
        from varagrill.models import VGMetodoPago, VGNotaEntrega, VGPago
        admin_role, _ = VGRol.objects.get_or_create(nombre_role='Administrador')
        cajera_role, _ = VGRol.objects.get_or_create(nombre_role='Cajera')
        self.admin = VGUsuario.objects.create_superuser(
            username='fpdf_admin', password='claveAdmin123', cedula='95000021', email='fpdf_admin@varagrill.test', id_role=admin_role,
        )
        self.cajera = VGUsuario.objects.create_user(
            username='fpdf_cajera', password='claveCajera123', cedula='95000022', email='fpdf_cajera@varagrill.test', id_role=cajera_role,
        )
        self.efectivo = VGMetodoPago.objects.create(nombre='Efectivo PDF test', moneda='USD', es_efectivo=True)
        self.banco = VGMetodoPago.objects.create(nombre='Pago movil PDF test', moneda='VES', cuenta_bancaria='Banesco')

        def nota(total, estado, saldo, dia, hora):
            creada = VGNotaEntrega.objects.create(
                metodo_pago=self.efectivo, total=Decimal(total), saldo_pendiente=Decimal(saldo),
                estado=estado, tasa_cambio_referencia=Decimal('100.0000'),
            )
            # fecha_emision es auto_now_add: se mueve de dia con update().
            fecha = timezone.make_aware(datetime(2026, 9, dia, hora, 30))
            VGNotaEntrega.objects.filter(pk=creada.pk).update(fecha_emision=fecha)
            return creada

        def pago(nota_entrega, metodo, monto, referencia=''):
            return VGPago.objects.create(
                nota_entrega=nota_entrega, monto=Decimal(monto), metodo_pago=metodo, estado='completado',
                tasa_cambio_referencia=Decimal('100.0000'), referencia=referencia, creado_por=self.admin,
            )

        # Dia 10: una pagada en dos abonos (efectivo + pago movil) y una sin pagar
        self.pagada = nota('30.00', 'pagada', '0', 10, 12)
        pago(self.pagada, self.efectivo, '10.00')
        pago(self.pagada, self.banco, '20.00', referencia='REF-998877')
        self.pendiente = nota('12.50', 'pendiente_pago', '12.50', 10, 19)
        # Dia 11: una anulada (el cuadre de caja tambien la suma al facturado)
        self.anulada = nota('40.00', 'anulada', '0', 11, 13)
        # Fuera del rango que se consulta
        self.fuera = nota('99.00', 'pagada', '0', 20, 9)

    def pedir(self, desde='2026-09-10', hasta='2026-09-11', usuario=None):
        from unittest import mock
        self.client.force_login(usuario or self.admin)
        with mock.patch('varagrill.reportes_pdf_views.generar_pdf_facturado', return_value=b'%PDF-falso') as generar:
            r = self.client.get(f'{self.URL}?desde={desde}&hasta={hasta}')
        return r, generar

    def test_lo_pueden_descargar_administradores_y_cajeras(self):
        self.assertEqual(self.client.get(self.URL).status_code, 401)
        for usuario in (self.admin, self.cajera):
            r, _ = self.pedir(usuario=usuario)
            self.assertEqual(r.status_code, 200, usuario.username)

    def test_solo_acepta_get(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(self.URL).status_code, 405)

    def test_rechaza_rango_invertido_y_rango_demasiado_largo(self):
        self.client.force_login(self.admin)
        invertido = self.client.get(f'{self.URL}?desde=2026-09-11&hasta=2026-09-10')
        self.assertEqual(invertido.status_code, 400)
        largo = self.client.get(f'{self.URL}?desde=2026-01-01&hasta=2026-09-10')
        self.assertEqual(largo.status_code, 400)
        self.assertIn('92', largo.json()['message'])
        basura = self.client.get(f'{self.URL}?fecha=no-es-fecha')
        self.assertEqual(basura.status_code, 400)

    def test_nombre_del_archivo_para_un_dia_y_para_un_rango(self):
        self.client.force_login(self.admin)
        dia = self.client.get(f'{self.URL}?fecha=2026-09-10')
        self.assertEqual(dia['Content-Disposition'], 'attachment; filename="facturado-2026-09-10.pdf"')
        rango = self.client.get(f'{self.URL}?desde=2026-09-10&hasta=2026-09-11')
        self.assertEqual(rango['Content-Disposition'], 'attachment; filename="facturado-2026-09-10-al-2026-09-11.pdf"')
        for r in (dia, rango):
            self.assertEqual(r['Content-Type'], 'application/pdf')
            self.assertTrue(r.content.startswith(b'%PDF'))

    def test_un_dia_sin_notas_tambien_genera_pdf(self):
        self.client.force_login(self.admin)
        r = self.client.get(f'{self.URL}?fecha=2025-01-01')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.content.startswith(b'%PDF'))

    def test_incluye_solo_las_notas_del_rango_y_su_total_es_el_del_cuadre(self):
        r, generar = self.pedir()
        self.assertEqual(r.status_code, 200)
        notas, desde, hasta = generar.call_args.args[:3]
        self.assertEqual({n['id'] for n in notas}, {self.pagada.id, self.pendiente.id, self.anulada.id})
        self.assertEqual((str(desde), str(hasta)), ('2026-09-10', '2026-09-11'))

        # El total que imprime el PDF es el "Facturado" que muestra el cuadre por rango.
        cuadre = self.client.get('/api/admin/reportes/cuadre-caja-rango/?desde=2026-09-10&hasta=2026-09-11').json()
        total_pdf = sum((Decimal(n['total']) for n in notas), Decimal('0'))
        self.assertEqual(total_pdf, Decimal(cuadre['resumen_ventas']['total_vendido']))
        self.assertEqual(total_pdf, Decimal('82.50'))

    def test_arma_un_bloque_por_dia_con_una_fila_por_abono(self):
        from varagrill.pdf_reportes import armar_dias_facturado
        r, generar = self.pedir()
        notas = generar.call_args.args[0]
        dias = armar_dias_facturado(notas)

        self.assertEqual([str(d['fecha']) for d in dias], ['2026-09-10', '2026-09-11'])
        dia10, dia11 = dias
        # la pagada en dos abonos ocupa dos filas, la pendiente una
        self.assertEqual(len(dia10['filas']), 3)
        self.assertEqual(dia10['cantidad'], 2)
        self.assertEqual(dia10['total'], Decimal('42.50'))
        primera, segunda, pendiente = dia10['filas']
        self.assertTrue(primera[0].endswith('(abono 1 de 2)'))
        self.assertEqual(segunda[0], 'Abono 2 de 2')
        self.assertEqual(primera[1], '12:30')
        self.assertEqual(primera[3], '30,00')
        self.assertEqual(primera[4], 'Pagada')
        self.assertEqual(primera[5], 'Efectivo PDF test ($)')
        self.assertEqual(primera[8], '10,00')
        self.assertEqual(primera[9], '—')  # en dolares no hay tasa
        self.assertEqual(primera[10], '—')
        # el abono en bolivares trae banco, referencia y los Bs con la tasa del pago (20 x 100)
        self.assertEqual(segunda[5], 'Pago movil PDF test (Bs)')
        self.assertEqual(segunda[6], 'Banesco')
        self.assertEqual(segunda[7], 'REF-998877')
        self.assertEqual(segunda[9], '100,00')
        self.assertEqual(segunda[10], '2.000,00')
        # sin pagos: estado Pendiente y guiones
        self.assertEqual(pendiente[4], 'Pendiente')
        self.assertEqual(pendiente[5:], ['—', '—', '—', '—', '—', '—'])
        # la anulada se muestra como tal y cuenta en el total del dia
        self.assertEqual(dia11['filas'][0][4], 'Anulada')
        self.assertEqual((dia11['anuladas'], dia11['total_anuladas'], dia11['total']), (1, Decimal('40.00'), Decimal('40.00')))

    def test_la_hora_se_agrupa_en_hora_local_no_en_utc(self):
        from datetime import datetime
        from varagrill.models import VGNotaEntrega
        # 10:30 pm en Caracas ya es el dia siguiente en UTC: tiene que seguir en el dia 12.
        tarde = VGNotaEntrega.objects.create(
            metodo_pago=self.efectivo, total=Decimal('5.00'), saldo_pendiente=Decimal('5.00'),
            estado='pendiente_pago', tasa_cambio_referencia=Decimal('100.0000'),
        )
        VGNotaEntrega.objects.filter(pk=tarde.pk).update(
            fecha_emision=timezone.make_aware(datetime(2026, 9, 12, 22, 30)),
        )
        r, generar = self.pedir(desde='2026-09-12', hasta='2026-09-12')
        notas = generar.call_args.args[0]
        self.assertEqual([n['id'] for n in notas], [tarde.id])
        self.assertEqual(str(notas[0]['fecha_emision'].date()), '2026-09-12')


class ReporteCuentasPorPagarPdfTests(TestCase):
    URL = '/api/admin/reportes/cuentas-por-pagar-pdf/'

    def setUp(self):
        from datetime import date, datetime
        from varagrill.models import VGAbonoCompra, VGCategoriaGasto, VGCompra, VGGasto, VGMetodoPago
        admin_role, _ = VGRol.objects.get_or_create(nombre_role='Administrador')
        cajera_role, _ = VGRol.objects.get_or_create(nombre_role='Cajera')
        self.admin = VGUsuario.objects.create_superuser(
            username='cxp_admin', password='claveAdmin123', cedula='95000031', email='cxp_admin@varagrill.test', id_role=admin_role,
        )
        self.cajera = VGUsuario.objects.create_user(
            username='cxp_cajera', password='claveCajera123', cedula='95000032', email='cxp_cajera@varagrill.test', id_role=cajera_role,
        )
        _set_tasa_actual('900.0000')
        self.metodo = VGMetodoPago.objects.create(nombre='Banco CxP PDF test', moneda='VES')
        servicios = VGCategoriaGasto.objects.create(nombre='Servicios CxP test')

        def compra(proveedor, total, saldo, estado_pago, fecha_factura, pagada_el=None):
            creada = VGCompra.objects.create(
                proveedor_nombre=proveedor, numero_factura_proveedor=f'F-{proveedor[-1]}', estado='recibido',
                total=Decimal(total), saldo_pendiente=Decimal(saldo), estado_pago=estado_pago,
                tasa_cambio_referencia=Decimal('800.0000'), moneda_origen='VES',
                total_bs_factura=Decimal(total) * Decimal('800'), fecha_factura=fecha_factura,
            )
            if pagada_el:
                VGCompra.objects.filter(pk=creada.pk).update(fecha_actualizacion=timezone.make_aware(datetime(*pagada_el, 10, 0)))
            return creada

        def gasto(descripcion, monto, estado_pago, fecha_gasto, pagado_el=None):
            creado = VGGasto.objects.create(
                categoria=servicios, descripcion=descripcion, monto=Decimal(monto),
                saldo_pendiente=Decimal('0') if estado_pago == 'pagado' else Decimal(monto),
                estado_pago=estado_pago, fecha_gasto=fecha_gasto, tasa_cambio_referencia=Decimal('800.0000'),
            )
            if pagado_el:
                VGGasto.objects.filter(pk=creado.pk).update(fecha_actualizacion=timezone.make_aware(datetime(*pagado_el, 10, 0)))
            return creado

        self.lote_a = compra('Prov A', '100', '100', 'pendiente', date(2026, 9, 5))
        self.lote_b = compra('Prov B', '200', '50', 'abonada_parcial', date(2026, 9, 20))
        VGAbonoCompra.objects.create(
            compra=self.lote_b, monto=Decimal('150'), metodo_pago=self.metodo, tasa_cambio_referencia=Decimal('800.0000'),
        )
        # facturado en agosto pero pagado en septiembre
        self.lote_c = compra('Prov C', '80', '0', 'pagada', date(2026, 8, 10), pagada_el=(2026, 9, 15))
        self.gasto_d = gasto('Luz septiembre', '30', 'pendiente', date(2026, 9, 12))
        self.gasto_e = gasto('Agua agosto', '25', 'pagado', date(2026, 8, 30), pagado_el=(2026, 9, 2))
        self.gasto_f = gasto('Luz octubre', '40', 'pendiente', date(2026, 10, 2))

    def pedir(self, **filtros):
        from unittest import mock
        self.client.force_login(self.admin)
        consulta = '&'.join(f'{k}={v}' for k, v in filtros.items())
        with mock.patch('varagrill.reportes_pdf_views.generar_pdf_cuentas_por_pagar', return_value=b'%PDF-falso') as generar:
            r = self.client.get(f'{self.URL}?{consulta}')
        return r, generar

    def ids(self, generar):
        return {(c['tipo'], c['id']) for c in generar.call_args.args[0]}

    def lote(self, c):
        return ('compra', c.id)

    def gasto(self, g):
        return ('gasto', g.id)

    def test_solo_administradores(self):
        self.assertEqual(self.client.get(self.URL).status_code, 401)
        self.client.force_login(self.cajera)
        self.assertEqual(self.client.get(self.URL).status_code, 401)

    def test_rechaza_filtros_invalidos(self):
        self.client.force_login(self.admin)
        for consulta in ('tipo=otro', 'estado=otro', 'desde=nada', 'desde=2026-09-30&hasta=2026-09-01'):
            self.assertEqual(self.client.get(f'{self.URL}?{consulta}').status_code, 400, consulta)

    def test_por_defecto_trae_lo_pendiente_de_lotes_y_gastos(self):
        r, generar = self.pedir()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            self.ids(generar),
            {self.lote(self.lote_a), self.lote(self.lote_b), self.gasto(self.gasto_d), self.gasto(self.gasto_f)},
        )

    def test_pagadas_se_filtran_por_la_fecha_en_que_se_pagaron(self):
        r, generar = self.pedir(estado='pagadas', desde='2026-09-01', hasta='2026-09-30')
        self.assertEqual(self.ids(generar), {self.lote(self.lote_c), self.gasto(self.gasto_e)})
        # facturadas en agosto, pero pagadas en septiembre: no entran en un rango de agosto
        r, generar = self.pedir(estado='pagadas', desde='2026-08-01', hasta='2026-08-31')
        self.assertEqual(self.ids(generar), set())

    def test_pendientes_se_filtran_por_la_fecha_de_la_cuenta(self):
        r, generar = self.pedir(estado='pendientes', desde='2026-09-01', hasta='2026-09-30')
        self.assertEqual(
            self.ids(generar), {self.lote(self.lote_a), self.lote(self.lote_b), self.gasto(self.gasto_d)},
        )

    def test_un_solo_extremo_del_rango_tambien_filtra(self):
        r, generar = self.pedir(estado='pendientes', desde='2026-09-15')
        self.assertEqual(self.ids(generar), {self.lote(self.lote_b), self.gasto(self.gasto_f)})
        r, generar = self.pedir(estado='pendientes', hasta='2026-09-10')
        self.assertEqual(self.ids(generar), {self.lote(self.lote_a)})

    def test_filtra_por_tipo(self):
        r, generar = self.pedir(tipo='compra')
        self.assertEqual({t for t, _ in self.ids(generar)}, {'compra'})
        self.assertEqual(len(self.ids(generar)), 2)
        r, generar = self.pedir(tipo='gasto')
        self.assertEqual(self.ids(generar), {self.gasto(self.gasto_d), self.gasto(self.gasto_f)})

    def test_todos_junta_pendientes_y_pagadas_del_rango(self):
        r, generar = self.pedir(estado='todos', desde='2026-09-01', hasta='2026-09-30')
        self.assertEqual(
            self.ids(generar),
            {
                self.lote(self.lote_a), self.lote(self.lote_b), self.lote(self.lote_c),
                self.gasto(self.gasto_d), self.gasto(self.gasto_e),
            },
        )

    def test_los_montos_son_los_de_la_pantalla(self):
        r, generar = self.pedir(tipo='compra', estado='pendientes')
        por_id = {c['id']: c for c in generar.call_args.args[0]}
        b = por_id[self.lote_b.id]
        pantalla = next(
            c for c in self.client.get('/api/cuentas-por-pagar/').json()['compras']
            if c['tipo'] == 'compra' and c['id'] == self.lote_b.id
        )
        self.assertEqual((b['total'], b['saldo'], b['total_bs'], b['saldo_bs']),
                         (pantalla['total'], pantalla['saldo_pendiente'], pantalla['total_bs'], pantalla['saldo_pendiente_bs']))
        self.assertEqual(b['estado'], 'abonada_parcial')
        self.assertEqual(Decimal(b['saldo']), Decimal('50'))
        self.assertEqual(Decimal(b['saldo_bs']), Decimal('40000.00'))  # 50 x 800

    def test_nombre_del_archivo_segun_los_filtros(self):
        self.client.force_login(self.admin)
        for consulta, esperado in (
            ('estado=pagadas&tipo=gasto&desde=2026-09-01&hasta=2026-09-30', 'cuentas-por-pagar-pagadas-gastos-2026-09-01-al-2026-09-30.pdf'),
            ('estado=todos&tipo=compra&desde=2026-09-01', 'cuentas-por-pagar-todas-lotes-desde-2026-09-01.pdf'),
        ):
            r = self.client.get(f'{self.URL}?{consulta}')
            self.assertEqual(r['Content-Disposition'], f'attachment; filename="{esperado}"')
            self.assertTrue(r.content.startswith(b'%PDF'))

    def test_arma_un_bloque_por_tipo_con_totales_que_cuadran(self):
        from datetime import date
        from varagrill.pdf_reportes import armar_bloques_cuentas
        base = {'estado': 'pendiente', 'fecha_pago': None, 'detalle': ''}
        cuentas = [
            {**base, 'tipo': 'gasto', 'id': 7, 'titulo': 'Aseo', 'fecha': date(2026, 9, 9), 'total': '10.004', 'total_bs': '9000.00', 'saldo': '10.004', 'saldo_bs': '9000.00'},
            {**base, 'tipo': 'compra', 'id': 2, 'titulo': 'Prov', 'fecha': date(2026, 9, 20), 'total': '20.005', 'total_bs': '18000.00', 'saldo': '5.00', 'saldo_bs': '4500.00'},
            {**base, 'tipo': 'compra', 'id': 1, 'titulo': 'Prov', 'fecha': date(2026, 9, 5), 'total': '10', 'total_bs': None, 'saldo': '10', 'saldo_bs': None},
        ]
        bloques = armar_bloques_cuentas(cuentas)
        self.assertEqual([b['tipo'] for b in bloques], ['compra', 'gasto'])
        lotes = bloques[0]
        # ordenados por fecha; el total suma los montos ya redondeados a 2 decimales
        self.assertEqual([f[0] for f in lotes['filas']], ['#1', '#2'])
        self.assertEqual(lotes['total'], Decimal('30.01'))
        self.assertEqual(lotes['saldo'], Decimal('15.00'))
        # la cuenta sin tasa no suma en Bs y queda marcada
        self.assertEqual(lotes['total_bs'], Decimal('18000.00'))
        self.assertEqual(lotes['sin_tasa'], 1)
        self.assertEqual(lotes['filas'][0][6], '—')

    def test_responde_un_pdf_real_aunque_no_haya_cuentas(self):
        self.client.force_login(self.admin)
        for consulta in ('', 'estado=todos', 'estado=pagadas&desde=2025-01-01&hasta=2025-01-31'):
            r = self.client.get(f'{self.URL}?{consulta}')
            self.assertEqual(r.status_code, 200, consulta)
            self.assertEqual(r['Content-Type'], 'application/pdf')
            self.assertTrue(r.content.startswith(b'%PDF'), consulta)
