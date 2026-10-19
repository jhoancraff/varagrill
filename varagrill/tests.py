import json
from types import SimpleNamespace
from datetime import date, datetime
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from unittest.mock import MagicMock, patch

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


class ReporteCuentasPorCobrarPdfTests(TestCase):
    URL = '/api/admin/reportes/cuentas-por-cobrar-pdf/'

    def setUp(self):
        from datetime import datetime
        from varagrill.models import VGCliente, VGMetodoPago, VGNotaEntrega, VGPago
        admin_role, _ = VGRol.objects.get_or_create(nombre_role='Administrador')
        cajera_role, _ = VGRol.objects.get_or_create(nombre_role='Cajera')
        self.admin = VGUsuario.objects.create_superuser(
            username='cxc_admin', password='claveAdmin123', cedula='95000041', email='cxc_admin@varagrill.test', id_role=admin_role,
        )
        self.cajera = VGUsuario.objects.create_user(
            username='cxc_cajera', password='claveCajera123', cedula='95000042', email='cxc_cajera@varagrill.test', id_role=cajera_role,
        )
        _set_tasa_actual('900.0000')
        self.metodo = VGMetodoPago.objects.create(nombre='Efectivo CxC PDF test', moneda='USD', es_efectivo=True)
        self.maria = VGCliente.objects.create(nombre='Maria', apellido='Gomez', tipo_documento='V', numero_documento='11111111')
        self.pedro = VGCliente.objects.create(nombre='Pedro', apellido='Perez', tipo_documento='V', numero_documento='22222222')

        def nota(cliente, total, saldo, estado, dia):
            creada = VGNotaEntrega.objects.create(
                cliente=cliente, metodo_pago=self.metodo, total=Decimal(total), saldo_pendiente=Decimal(saldo),
                estado=estado, moneda='VES', tasa_cambio_referencia=Decimal('800.0000'),
            )
            # fecha_emision es auto_now_add: se mueve de fecha con update().
            fecha = timezone.make_aware(datetime(*dia, 12, 0))
            VGNotaEntrega.objects.filter(pk=creada.pk).update(fecha_emision=fecha)
            return creada

        self.pend_maria = nota(self.maria, '50.00', '50.00', 'pendiente_pago', (2026, 9, 5))
        self.abon_maria = nota(self.maria, '40.00', '10.00', 'abonada_parcial', (2026, 9, 20))
        self.pend_sin = nota(None, '15.00', '15.00', 'pendiente_pago', (2026, 9, 25))
        self.pagada_pedro = nota(self.pedro, '30.00', '0', 'pagada', (2026, 9, 10))
        pago = VGPago.objects.create(
            nota_entrega=self.pagada_pedro, monto=Decimal('30.00'), metodo_pago=self.metodo, estado='completado',
            creado_por=self.admin,
        )
        VGPago.objects.filter(pk=pago.pk).update(fecha_pago=timezone.make_aware(datetime(2026, 9, 11, 9, 0)))
        # anulada: nunca es una cuenta por cobrar, aunque conserve saldo
        self.anulada = nota(self.pedro, '20.00', '20.00', 'anulada', (2026, 9, 12))
        self.octubre = nota(self.pedro, '12.00', '12.00', 'pendiente_pago', (2026, 10, 2))

    def pedir(self, **filtros):
        from unittest import mock
        self.client.force_login(self.admin)
        consulta = '&'.join(f'{k}={v}' for k, v in filtros.items())
        with mock.patch('varagrill.reportes_pdf_views.generar_pdf_cuentas_por_cobrar', return_value=b'%PDF-falso') as generar:
            r = self.client.get(f'{self.URL}?{consulta}')
        return r, generar

    def ids(self, generar):
        return {n['id'] for n in generar.call_args.args[0]}

    def test_lo_pueden_descargar_administradores_y_cajeras(self):
        self.assertEqual(self.client.get(self.URL).status_code, 401)
        for usuario in (self.admin, self.cajera):
            self.client.force_login(usuario)
            self.assertEqual(self.client.get(self.URL).status_code, 200, usuario.username)

    def test_rechaza_filtros_invalidos(self):
        self.client.force_login(self.admin)
        for consulta in ('estado=otro', 'desde=nada', 'desde=2026-09-30&hasta=2026-09-01'):
            self.assertEqual(self.client.get(f'{self.URL}?{consulta}').status_code, 400, consulta)

    def test_por_defecto_trae_solo_lo_pendiente_y_nunca_las_anuladas(self):
        r, generar = self.pedir()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            self.ids(generar),
            {self.pend_maria.id, self.abon_maria.id, self.pend_sin.id, self.octubre.id},
        )

    def test_pagadas_y_todas(self):
        r, generar = self.pedir(estado='pagadas')
        self.assertEqual(self.ids(generar), {self.pagada_pedro.id})
        r, generar = self.pedir(estado='todas')
        self.assertEqual(
            self.ids(generar),
            {self.pend_maria.id, self.abon_maria.id, self.pend_sin.id, self.octubre.id, self.pagada_pedro.id},
        )

    def test_filtra_por_rango_de_fecha_de_emision(self):
        r, generar = self.pedir(desde='2026-09-01', hasta='2026-09-30')
        self.assertEqual(self.ids(generar), {self.pend_maria.id, self.abon_maria.id, self.pend_sin.id})
        r, generar = self.pedir(desde='2026-09-15')
        self.assertEqual(self.ids(generar), {self.abon_maria.id, self.pend_sin.id, self.octubre.id})

    def test_filtra_por_cliente(self):
        for texto in ('maria', 'GOMEZ', 'maria%20gomez'):
            r, generar = self.pedir(estado='todas', cliente=texto)
            self.assertEqual(self.ids(generar), {self.pend_maria.id, self.abon_maria.id}, texto)
        r, generar = self.pedir(estado='todas', cliente='nadie')
        self.assertEqual(self.ids(generar), set())

    def test_el_saldo_en_bs_es_el_de_la_pantalla_con_la_tasa_de_cobro_de_hoy(self):
        r, generar = self.pedir()
        por_id = {n['id']: n for n in generar.call_args.args[0]}
        fiado = por_id[self.pend_maria.id]
        pantalla = self.client.get(f'/api/notas-entrega/{self.pend_maria.id}/').json()['nota_entrega']
        # nota de un dia anterior: se cobra a la tasa BCV de hoy (900), no a la congelada (800)
        self.assertEqual(Decimal(fiado['tasa']), Decimal('900.0000'))
        self.assertEqual(Decimal(fiado['saldo_bs']), Decimal('45000.00'))
        self.assertEqual((fiado['tasa'], fiado['saldo_bs']), (pantalla['tasa_cobro_vigente'], pantalla['saldo_pendiente_bs_vigente']))
        self.assertGreater(fiado['dias'], 0)
        self.assertEqual(fiado['cliente'], 'Maria Gomez')
        self.assertEqual(por_id[self.pend_sin.id]['cliente'], '')

    def test_una_pagada_trae_la_fecha_de_pago_y_no_tiene_saldo(self):
        r, generar = self.pedir(estado='pagadas')
        pagada = generar.call_args.args[0][0]
        self.assertEqual(str(pagada['fecha_pago']), '2026-09-11')
        self.assertEqual(Decimal(pagada['saldo']), Decimal('0'))
        self.assertIsNone(pagada['dias'])
        self.assertIsNone(pagada['saldo_bs'])

    def test_agrupa_por_cliente_con_sin_cliente_al_final_y_totales_que_cuadran(self):
        from datetime import date
        from varagrill.pdf_reportes import armar_bloques_clientes
        base = {'estado': 'pendiente_pago', 'fecha_pago': None, 'dias': 3}
        notas = [
            {**base, 'id': 3, 'codigo': 'C', 'cliente': '', 'fecha': date(2026, 9, 3), 'total': '10.004', 'saldo': '10.004', 'tasa': '900', 'saldo_bs': '9000.00'},
            # dos clientes distintos con el mismo nombre no se mezclan (se agrupa por id)
            {**base, 'id': 2, 'codigo': 'B', 'cliente_id': 8, 'cliente': 'Ana Lopez', 'fecha': date(2026, 9, 9), 'total': '20.005', 'saldo': '5.00', 'tasa': '900', 'saldo_bs': '4500.00'},
            {**base, 'id': 1, 'codigo': 'A', 'cliente_id': 5, 'cliente': 'Ana Lopez', 'fecha': date(2026, 9, 1), 'total': '10', 'saldo': '10', 'tasa': None, 'saldo_bs': None},
            {**base, 'id': 4, 'codigo': 'D', 'cliente': 'Zoe', 'fecha': date(2026, 9, 2), 'total': '1', 'saldo': '1', 'tasa': '900', 'saldo_bs': '900.00'},
        ]
        bloques = armar_bloques_clientes(notas)
        self.assertEqual([b['cliente'] for b in bloques], ['Ana Lopez', 'Ana Lopez', 'Zoe', 'Sin cliente'])
        self.assertEqual([b['filas'][0][0] for b in bloques], ['A', 'B', 'D', 'C'])
        ana = bloques[0]
        self.assertEqual(ana['saldo'], Decimal('10.00'))
        self.assertEqual(ana['sin_tasa'], 1)  # tiene saldo y no tiene tasa: no suma en Bs
        self.assertEqual(ana['saldo_bs'], Decimal('0'))
        self.assertEqual(ana['filas'][0][7], '—')
        sin = bloques[-1]
        self.assertEqual(sin['total'], Decimal('10.00'))
        self.assertEqual(sin['filas'][0][7], '900,00')

    def test_responde_un_pdf_real_con_el_nombre_segun_los_filtros(self):
        self.client.force_login(self.admin)
        r = self.client.get(f'{self.URL}?estado=todas&desde=2026-09-01&hasta=2026-09-30')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'application/pdf')
        self.assertEqual(r['Content-Disposition'], 'attachment; filename="cuentas-por-cobrar-todas-2026-09-01-al-2026-09-30.pdf"')
        self.assertTrue(r.content.startswith(b'%PDF'))
        vacio = self.client.get(f'{self.URL}?cliente=nadie')
        self.assertEqual(vacio.status_code, 200)
        self.assertTrue(vacio.content.startswith(b'%PDF'))


class DeliveryZonasInicialesTests(TestCase):
    def test_la_migracion_deja_las_tres_zonas_inactivas_y_sin_precio(self):
        from varagrill.models import VGZonaDelivery
        zonas = {z.nombre: z for z in VGZonaDelivery.objects.all()}
        self.assertEqual(set(zonas), {'Cerca', 'Media', 'Lejos'})
        for zona in zonas.values():
            self.assertFalse(zona.activo)
            self.assertEqual(zona.tarifa, Decimal('0'))


class DeliveryCargoTests(TestCase):
    """
    El delivery se cobra como un cargo propio del pedido (no como producto ni ingrediente), con tres
    tarifas por zona que el administrador configura y que la cajera puede cambiar. Ver delivery.py.
    """

    def setUp(self):
        from varagrill.models import VGZonaDelivery
        admin_role, _ = VGRol.objects.get_or_create(nombre_role='Administrador')
        cajera_role, _ = VGRol.objects.get_or_create(nombre_role='Cajera')
        mesero_role, _ = VGRol.objects.get_or_create(nombre_role='Mesero')
        self.admin = VGUsuario.objects.create_superuser(
            username='dl_admin', password='claveAdmin123', cedula='97000001', email='dl_admin@varagrill.test', id_role=admin_role,
        )
        self.cajera = VGUsuario.objects.create_user(
            username='dl_cajera', password='claveCajera123', cedula='97000002', email='dl_cajera@varagrill.test', id_role=cajera_role,
        )
        self.mesero = VGUsuario.objects.create_user(
            username='dl_mesero', password='claveMesero123', cedula='97000003', email='dl_mesero@varagrill.test', id_role=mesero_role,
        )
        categoria = VGCategoriaProducto.objects.create(nombre='Platos DL', no_requiere_cocina=True)
        self.plato = VGProducto.objects.create(nombre='Plato DL', categoria=categoria, precio_venta='10.00', disponible=True)
        self.efectivo = VGMetodoPago.objects.create(nombre='Efectivo DL', moneda='USD', es_efectivo=True)
        _set_tasa_actual('100.0000')
        # La migracion deja Cerca/Media/Lejos inactivas y en 0: el admin les pone precio y las activa.
        VGZonaDelivery.objects.filter(nombre='Cerca').update(tarifa=Decimal('1.00'), activo=True)
        VGZonaDelivery.objects.filter(nombre='Media').update(tarifa=Decimal('2.00'), activo=True)
        self.cerca = VGZonaDelivery.objects.get(nombre='Cerca')
        self.media = VGZonaDelivery.objects.get(nombre='Media')
        self.lejos = VGZonaDelivery.objects.get(nombre='Lejos')  # sigue inactiva

    def post(self, url, payload=None, usuario=None):
        self.client.force_login(usuario or self.cajera)
        return self.client.post(url, data=json.dumps(payload or {}), content_type='application/json')

    def crear(self, usuario=None, tipo='delivery', **extra):
        payload = {
            'tipo_pedido': tipo, 'cliente_nombre': 'Cliente DL',
            'items': [{'product_id': self.plato.id, 'cantidad': 2}],
            **extra,
        }
        return self.post('/api/pedidos/', payload, usuario)

    def pedido(self, respuesta):
        self.assertEqual(respuesta.status_code, 201, respuesta.content)
        return VGPedido.objects.get(pk=respuesta.json()['pedido']['id'])

    # --- registrar el pedido -------------------------------------------------------------------
    def test_con_zona_cobra_la_tarifa_y_la_suma_al_total(self):
        pedido = self.pedido(self.crear(zona_delivery_id=self.media.id))
        self.assertEqual(pedido.subtotal, Decimal('20.00'))
        self.assertEqual(pedido.cargo_delivery, Decimal('2.00'))
        self.assertEqual(pedido.total, Decimal('22.00'))
        self.assertEqual((pedido.zona_delivery_id, pedido.zona_delivery_nombre, pedido.tarifa_delivery), (self.media.id, 'Media', Decimal('2.00')))

    def test_la_cajera_puede_cambiar_el_monto_y_queda_la_tarifa_original(self):
        pedido = self.pedido(self.crear(zona_delivery_id=self.media.id, cargo_delivery='1.50'))
        self.assertEqual(pedido.cargo_delivery, Decimal('1.50'))
        self.assertEqual(pedido.total, Decimal('21.50'))
        self.assertEqual(pedido.tarifa_delivery, Decimal('2.00'))

    def test_la_cajera_puede_poner_un_monto_sin_zona_incluso_cero(self):
        pedido = self.pedido(self.crear(cargo_delivery='3.25'))
        self.assertEqual((pedido.cargo_delivery, pedido.total, pedido.zona_delivery_id), (Decimal('3.25'), Decimal('23.25'), None))
        gratis = self.pedido(self.crear(zona_delivery_id=self.media.id, cargo_delivery='0'))
        self.assertEqual((gratis.cargo_delivery, gratis.total), (Decimal('0.00'), Decimal('20.00')))

    def test_un_mesero_solo_puede_mandar_la_tarifa_de_la_zona(self):
        r = self.crear(usuario=self.mesero, zona_delivery_id=self.media.id, cargo_delivery='0.50')
        self.assertEqual(r.status_code, 400)
        self.assertIn('caja o administracion', r.json()['message'])
        ok = self.pedido(self.crear(usuario=self.mesero, zona_delivery_id=self.media.id, cargo_delivery='2.00'))
        self.assertEqual(ok.cargo_delivery, Decimal('2.00'))

    def test_un_pedido_que_no_es_delivery_nunca_cobra_envio(self):
        pedido = self.pedido(self.crear(tipo='llevar', zona_delivery_id=self.media.id, cargo_delivery='5'))
        self.assertEqual((pedido.cargo_delivery, pedido.total, pedido.zona_delivery_id), (Decimal('0.00'), Decimal('20.00'), None))

    def test_una_ronda_agregada_al_delivery_no_repite_el_cargo(self):
        original = self.pedido(self.crear(zona_delivery_id=self.media.id))
        ronda = self.pedido(self.crear(zona_delivery_id=self.media.id, grupo_pedido_id=original.id))
        self.assertEqual((ronda.cargo_delivery, ronda.total), (Decimal('0.00'), Decimal('20.00')))
        self.assertEqual(original.cargo_delivery, Decimal('2.00'))

    def test_rechaza_zonas_inactivas_inexistentes_y_montos_invalidos(self):
        for extra in ({'zona_delivery_id': self.lejos.id}, {'zona_delivery_id': 999999}, {'zona_delivery_id': 'abc'},
                      {'cargo_delivery': '-1'}, {'cargo_delivery': 'mucho'}):
            r = self.crear(**extra)
            self.assertEqual(r.status_code, 400, extra)

    def test_delivery_sin_zona_ni_monto_no_cobra_envio_como_antes(self):
        pedido = self.pedido(self.crear())
        self.assertEqual((pedido.cargo_delivery, pedido.total), (Decimal('0.00'), Decimal('20.00')))

    # --- editar / quitar items ------------------------------------------------------------------
    def test_editar_el_pedido_conserva_el_cargo_y_cambiar_a_llevar_lo_quita(self):
        pedido = self.pedido(self.crear(zona_delivery_id=self.media.id))
        # un pedido de categoria sin cocina nace 'entregado'; se fuerza 'pendiente' para poder editarlo
        VGPedido.objects.filter(pk=pedido.pk).update(estado='pendiente')
        base = {'tipo_pedido': 'delivery', 'cliente_nombre': 'Cliente DL', 'items': [{'product_id': self.plato.id, 'cantidad': 3}]}
        r = self.post(f'/api/pedidos/{pedido.id}/actualizar/', base)
        self.assertEqual(r.status_code, 200, r.content)
        pedido.refresh_from_db()
        self.assertEqual((pedido.subtotal, pedido.cargo_delivery, pedido.total), (Decimal('30.00'), Decimal('2.00'), Decimal('32.00')))
        VGPedido.objects.filter(pk=pedido.pk).update(estado='pendiente')
        r = self.post(f'/api/pedidos/{pedido.id}/actualizar/', {**base, 'tipo_pedido': 'llevar'})
        self.assertEqual(r.status_code, 200, r.content)
        pedido.refresh_from_db()
        self.assertEqual((pedido.cargo_delivery, pedido.total, pedido.zona_delivery_id), (Decimal('0.00'), Decimal('30.00'), None))

    def test_quitar_un_item_no_pierde_el_cargo(self):
        r = self.post('/api/pedidos/', {
            'tipo_pedido': 'delivery', 'cliente_nombre': 'Cliente DL', 'zona_delivery_id': self.media.id,
            'items': [{'product_id': self.plato.id, 'cantidad': 1}, {'product_id': self.plato.id, 'cantidad': 1, 'notas': 'otro'}],
        })
        pedido = self.pedido(r)
        self.assertEqual(pedido.total, Decimal('22.00'))
        detalle = pedido.detalles.first()
        r = self.post(f'/api/pedidos/{pedido.id}/items/{detalle.id}/eliminar/', {'motivo': 'se equivoco'})
        self.assertIn(r.status_code, (200, 201), r.content)
        pedido.refresh_from_db()
        self.assertEqual((pedido.subtotal, pedido.total), (Decimal('10.00'), Decimal('12.00')))

    # --- cambiar el cargo ya registrado ---------------------------------------------------------
    def test_caja_puede_cambiar_el_cargo_de_un_pedido_ya_registrado(self):
        pedido = self.pedido(self.crear(zona_delivery_id=self.media.id))
        r = self.post(f'/api/pedidos/{pedido.id}/delivery/', {'cargo_delivery': '1'})
        self.assertEqual(r.status_code, 200, r.content)
        pedido.refresh_from_db()
        self.assertEqual((pedido.cargo_delivery, pedido.total, pedido.zona_delivery_nombre, pedido.tarifa_delivery),
                         (Decimal('1.00'), Decimal('21.00'), 'Media', Decimal('2.00')))
        r = self.post(f'/api/pedidos/{pedido.id}/delivery/', {'zona_delivery_id': self.cerca.id})
        pedido.refresh_from_db()
        self.assertEqual((pedido.cargo_delivery, pedido.total, pedido.zona_delivery_nombre), (Decimal('1.00'), Decimal('21.00'), 'Cerca'))

    def test_cambiar_el_cargo_valida_permiso_tipo_estado_y_ronda(self):
        pedido = self.pedido(self.crear(zona_delivery_id=self.media.id))
        self.assertEqual(self.post(f'/api/pedidos/{pedido.id}/delivery/', {'cargo_delivery': '1'}, self.mesero).status_code, 401)
        self.assertEqual(self.post(f'/api/pedidos/{pedido.id}/delivery/', {}).status_code, 400)
        self.assertEqual(self.post(f'/api/pedidos/{pedido.id}/delivery/', {'cargo_delivery': '-3'}).status_code, 400)
        ronda = self.pedido(self.crear(grupo_pedido_id=pedido.id))
        self.assertEqual(self.post(f'/api/pedidos/{ronda.id}/delivery/', {'cargo_delivery': '1'}).status_code, 400)
        llevar = self.pedido(self.crear(tipo='llevar'))
        self.assertEqual(self.post(f'/api/pedidos/{llevar.id}/delivery/', {'cargo_delivery': '1'}).status_code, 400)
        VGPedido.objects.filter(pk=pedido.pk).update(estado='pagado')
        self.assertEqual(self.post(f'/api/pedidos/{pedido.id}/delivery/', {'cargo_delivery': '1'}).status_code, 409)

    # --- cobro, nota, cuenta del cliente y ticket ----------------------------------------------
    def test_la_nota_de_entrega_incluye_el_delivery_como_linea_aparte(self):
        from varagrill.impresion_lpd import _build_recibo_bytes
        pedido = self.pedido(self.crear(zona_delivery_id=self.media.id))
        r = self.post('/api/pedidos/cobro/', {
            'pedido_ids': [pedido.id], 'metodo_pago_id': self.efectivo.id,
            'cliente_numero_documento': '97000111', 'cliente_nombre': 'Cliente DL',
        })
        self.assertEqual(r.status_code, 201, r.content)
        nota = r.json()['nota_entrega']
        self.assertEqual(Decimal(nota['total']), Decimal('22.00'))

        detalle = self.client.get(f'/api/notas-entrega/{nota["id"]}/').json()['nota_entrega']
        self.assertEqual(Decimal(detalle['cargo_delivery']), Decimal('2.00'))
        self.assertEqual(detalle['zona_delivery'], 'Media')
        # no es un item: la lista de productos de la nota no lo trae
        self.assertEqual({item['producto'] for item in detalle['items']}, {'Plato DL'})

        # el ticket suma: Subtotal 20 + Delivery (Media) 2 = TOTAL 22
        pedido.refresh_from_db()
        ticket = _build_recibo_bytes([pedido], self.efectivo, 'REF', Decimal('22.00'), Decimal('100.0000'), titulo='NOTA DE ENTREGA', codigo='X')
        texto = ticket.decode('cp1252', errors='replace')
        self.assertIn('Delivery (Media): $2.00', texto)
        self.assertIn('Subtotal: $20.00', texto)
        self.assertIn('TOTAL: $22.00', texto)

    def test_la_cuenta_del_cliente_trae_el_delivery_como_linea(self):
        pedido = self.pedido(self.crear(zona_delivery_id=self.media.id))
        r = self.post('/api/prefacturas/', {'pedido_ids': [pedido.id]})
        self.assertEqual(r.status_code, 201, r.content)
        prefactura = r.json()['prefactura']
        lineas = {linea['descripcion']: linea for linea in prefactura['lineas']}
        self.assertIn('Delivery (Media)', lineas)
        self.assertEqual(Decimal(lineas['Delivery (Media)']['precio_unitario']), Decimal('2.00'))
        # los precios incluyen IVA: la cuenta del cliente suma lo mismo que el total del pedido (20 + 2 de delivery)
        self.assertEqual(Decimal(prefactura['total']), Decimal('22.00'))

    def test_el_delivery_no_aparece_en_cocina(self):
        pedido = self.pedido(self.crear(zona_delivery_id=self.media.id))
        pedido.refresh_from_db()
        self.assertEqual([d.producto.nombre for d in pedido.detalles.all()], ['Plato DL'])

    # --- zonas ----------------------------------------------------------------------------------
    def test_las_zonas_activas_las_ve_cualquier_usuario_con_sesion(self):
        self.client.logout()
        self.assertEqual(self.client.get('/api/delivery/zonas/').status_code, 401)
        self.client.force_login(self.mesero)
        r = self.client.get('/api/delivery/zonas/').json()
        self.assertEqual([z['nombre'] for z in r['zonas']], ['Cerca', 'Media'])
        self.assertFalse(r['puede_cambiar_monto'])
        self.client.force_login(self.cajera)
        self.assertTrue(self.client.get('/api/delivery/zonas/').json()['puede_cambiar_monto'])
        # solo el admin ve las inactivas
        self.assertEqual(len(self.client.get('/api/delivery/zonas/?todas=1').json()['zonas']), 2)
        self.client.force_login(self.admin)
        self.assertEqual(len(self.client.get('/api/delivery/zonas/?todas=1').json()['zonas']), 3)

    def test_el_admin_crea_edita_y_activa_zonas(self):
        r = self.post('/api/delivery/zonas/', {'action': 'update', 'id': self.lejos.id, 'nombre': 'Lejos', 'tarifa': '3.5'}, self.cajera)
        self.assertEqual(r.status_code, 401)
        r = self.post('/api/delivery/zonas/', {'action': 'update', 'id': self.lejos.id, 'nombre': 'Lejos', 'tarifa': '3.5'}, self.admin)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()['zona']['tarifa'], '3.50')
        r = self.post('/api/delivery/zonas/', {'action': 'toggle', 'id': self.lejos.id}, self.admin)
        self.assertTrue(r.json()['zona']['activo'])
        r = self.post('/api/delivery/zonas/', {'action': 'create', 'nombre': 'Centro', 'tarifa': '0.75'}, self.admin)
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(self.post('/api/delivery/zonas/', {'action': 'create', 'nombre': 'centro', 'tarifa': '1'}, self.admin).status_code, 400)
        self.assertEqual(self.post('/api/delivery/zonas/', {'action': 'create', 'nombre': 'Otra', 'tarifa': '-1'}, self.admin).status_code, 400)
        self.assertEqual(self.post('/api/delivery/zonas/', {'action': 'create', 'nombre': ' ', 'tarifa': '1'}, self.admin).status_code, 400)

    def test_cambiar_la_tarifa_no_toca_los_pedidos_ya_registrados(self):
        pedido = self.pedido(self.crear(zona_delivery_id=self.media.id))
        self.post('/api/delivery/zonas/', {'action': 'update', 'id': self.media.id, 'nombre': 'Intermedia', 'tarifa': '9'}, self.admin)
        pedido.refresh_from_db()
        self.assertEqual((pedido.cargo_delivery, pedido.zona_delivery_nombre, pedido.total), (Decimal('2.00'), 'Media', Decimal('22.00')))


class EstadoResultadosCostoDeVentasTests(TestCase):
    """
    Estado de resultados: ventas − costo de lo vendido = utilidad bruta; utilidad bruta − gastos = utilidad
    neta. Las compras a proveedores (lotes) no suman. Ver reporte_estado_resultados_view.
    """

    URL = '/api/admin/reportes/estado-resultados/'

    def setUp(self):
        admin_role, _ = VGRol.objects.get_or_create(nombre_role='Administrador')
        self.admin = VGUsuario.objects.create_superuser(
            username='er_admin', password='claveAdmin123', cedula='98000001', email='er_admin@varagrill.test', id_role=admin_role,
        )
        self.client.force_login(self.admin)
        self.hoy = timezone.localdate()
        self.categoria = VGCategoriaProducto.objects.create(nombre='Platos ER')
        self.plato = VGProducto.objects.create(nombre='Plato ER', categoria=self.categoria, precio_venta='10.00', disponible=True)
        self.metodo = VGMetodoPago.objects.create(nombre='Efectivo ER', moneda='USD', es_efectivo=True)
        _set_tasa_actual('100.0000')

    def venta(self, cantidad=2, precio='10.00', costo='4.00', margen=None, estado='pagada', saldo='0', total=None, tasa='100.0000'):
        """Una nota de entrega con un pedido de `cantidad` platos; `costo` es el costo congelado al cobrar."""
        subtotal = Decimal(precio) * cantidad
        pedido = VGPedido.objects.create(
            usuario=self.admin, tipo_pedido='llevar', estado='pagado', subtotal=subtotal, total=subtotal,
        )
        VGDetallePedido.objects.create(
            pedido=pedido, producto=self.plato, cantidad=cantidad, precio_unitario=Decimal(precio), estado='entregado',
            costo_unitario_venta=Decimal(costo) if costo is not None else None,
            margen_produccion_pct_venta=Decimal(margen) if margen is not None else None,
        )
        nota = VGNotaEntrega.objects.create(
            metodo_pago=self.metodo, total=Decimal(total) if total is not None else subtotal, saldo_pendiente=Decimal(saldo),
            estado=estado, tasa_cambio_referencia=Decimal(tasa),
        )
        nota.pedidos.set([pedido])
        return nota

    def reporte(self):
        r = self.client.get(f'{self.URL}?desde={self.hoy.isoformat()}&hasta={self.hoy.isoformat()}')
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()

    def test_ventas_menos_costo_da_la_utilidad_bruta_y_menos_gastos_la_neta(self):
        self.venta(cantidad=2, precio='10.00', costo='4.00')   # vende 20, cuesta 8
        self.venta(cantidad=1, precio='30.00', costo='12.50')  # vende 30, cuesta 12.50
        categoria = VGCategoriaGasto.objects.create(nombre='Servicios ER')
        VGGasto.objects.create(
            categoria=categoria, descripcion='Luz', monto=Decimal('15.00'), saldo_pendiente=0, estado_pago='pagado',
            fecha_gasto=self.hoy, tasa_cambio_referencia=Decimal('100.0000'),
        )
        data = self.reporte()
        self.assertEqual(data['ventas_total'], '50.00')
        self.assertEqual(data['costo_ventas'], '20.50')
        self.assertEqual(data['utilidad_bruta'], '29.50')
        self.assertEqual(data['utilidad_bruta_pct'], '59.00')
        self.assertEqual(data['gastos_total'], '15.00')
        self.assertEqual(data['utilidad_neta'], '14.50')
        self.assertEqual(data['utilidad_neta_pct'], '29.00')
        self.assertEqual(data['costo_lineas_estimadas'], 0)
        # en bolivares: venta y costo a la tasa de esa misma venta
        self.assertEqual(data['costo_ventas_bs'], '2050.00')
        self.assertEqual(data['utilidad_bruta_bs'], '2950.00')
        self.assertEqual(data['utilidad_neta_bs'], '1450.00')

    def test_las_compras_a_proveedores_no_suman_ni_aparecen_en_el_desglose(self):
        from varagrill.models import VGAbonoCompra, VGCompra
        compra = VGCompra.objects.create(
            proveedor_nombre='Proveedor ER', estado='recibido', total=Decimal('500'), saldo_pendiente=Decimal('0'),
            estado_pago='pagada', tasa_cambio_referencia=Decimal('100.0000'), moneda_origen='USD',
        )
        VGAbonoCompra.objects.create(
            compra=compra, monto=Decimal('500'), metodo_pago=self.metodo, tasa_cambio_referencia=Decimal('100.0000'),
        )
        self.venta(cantidad=1, precio='10.00', costo='4.00')
        data = self.reporte()
        self.assertEqual(data['gastos_total'], '0.00')
        self.assertEqual(data['gastos_por_categoria'], [])
        self.assertEqual(data['utilidad_neta'], '6.00')

    def test_una_nota_abonada_a_medias_cuenta_la_misma_fraccion_de_la_venta_y_del_costo(self):
        # vende 40, cobro 10 (25%): vende 10 y su costo es el 25% de 16
        self.venta(cantidad=2, precio='20.00', costo='8.00', estado='abonada_parcial', saldo='30.00')
        data = self.reporte()
        self.assertEqual(data['ventas_total'], '10.00')
        self.assertEqual(data['costo_ventas'], '4.00')
        self.assertEqual(data['utilidad_bruta'], '6.00')

    def test_las_notas_pendientes_y_anuladas_no_suman_ni_venta_ni_costo(self):
        self.venta(estado='pendiente_pago', saldo='20.00')
        self.venta(estado='anulada', saldo='0')
        data = self.reporte()
        self.assertEqual((data['ventas_total'], data['costo_ventas'], data['utilidad_bruta']), ('0.00', '0.00', '0.00'))

    def test_el_costo_congelado_con_margen_de_produccion_no_se_suma_dos_veces(self):
        # receta: el costo congelado (11) ya trae el 10% de margen; costo puro 10, con margen 11
        self.venta(cantidad=1, precio='20.00', costo='11.00', margen='10.00')
        self.assertEqual(self.reporte()['costo_ventas'], '11.00')

    def test_una_venta_sin_costo_congelado_usa_el_costo_actual_y_queda_marcada_como_estimada(self):
        self.venta(cantidad=1, precio='20.00', costo=None)
        data = self.reporte()
        self.assertEqual(data['costo_lineas_estimadas'], 1)
        self.assertEqual(data['ventas_total'], '20.00')

    def test_el_costo_coincide_con_el_reporte_de_margen_por_plato(self):
        self.venta(cantidad=3, precio='10.00', costo='4.00', margen='10.00')
        self.venta(cantidad=1, precio='25.00', costo='9.90')
        estado = self.reporte()
        r = self.client.get(f'/api/admin/reportes/margen-ganancia/?desde={self.hoy.isoformat()}&hasta={self.hoy.isoformat()}')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(estado['costo_ventas'], r.json()['totales']['costo_con_margen_total'])

    def test_avisa_de_los_productos_vendidos_sin_costo_configurado(self):
        # costo congelado 0: es el plato sin receta ni ingredientes anclados (el caso de las ventas viejas)
        self.venta(cantidad=2, precio='10.00', costo='0.00')   # vende 20, costo 0
        self.venta(cantidad=1, precio='30.00', costo='12.50')  # con costo: no entra al aviso
        data = self.reporte()
        aviso = data['ventas_sin_costo']
        self.assertEqual(aviso['total'], '20.00')
        self.assertEqual(aviso['pct_de_ventas'], '40.00')
        self.assertEqual(len(aviso['productos']), 1)
        fila = aviso['productos'][0]
        self.assertEqual(fila['producto_id'], self.plato.id)
        self.assertEqual(fila['nombre'], 'Plato ER')
        self.assertEqual(fila['motivo'], 'sin_receta')
        self.assertEqual(fila['unidades'], '2.00')
        self.assertEqual(fila['ventas'], '20.00')

    def test_sin_ventas_sin_costo_el_aviso_viene_vacio(self):
        self.venta(cantidad=1, precio='10.00', costo='4.00')
        aviso = self.reporte()['ventas_sin_costo']
        self.assertEqual(aviso, {'total': '0.00', 'pct_de_ventas': '0.00', 'productos': []})

    def test_el_aviso_cuenta_solo_la_parte_cobrada_de_una_nota_abonada(self):
        # vende 40, cobro 10 (25%): de esa venta sin costo, 10 cuentan
        self.venta(cantidad=2, precio='20.00', costo='0.00', estado='abonada_parcial', saldo='30.00')
        aviso = self.reporte()['ventas_sin_costo']
        self.assertEqual(aviso['total'], '10.00')
        self.assertEqual(aviso['pct_de_ventas'], '100.00')

    def test_distingue_el_producto_con_receta_cuyo_costo_es_cero(self):
        from varagrill.models import VGIngrediente, VGRecetaProducto
        ingrediente = VGIngrediente.objects.create(
            nombre='Ingrediente ER', unidad_medida='g', stock_actual=Decimal('1000'), costo_unitario=Decimal('0'),
        )
        VGRecetaProducto.objects.create(producto=self.plato, ingrediente=ingrediente, cantidad_requerida=Decimal('100'))
        self.venta(cantidad=1, precio='10.00', costo='0.00')
        fila = self.reporte()['ventas_sin_costo']['productos'][0]
        self.assertEqual(fila['motivo'], 'costo_cero')

    def test_el_cargo_de_delivery_no_cuenta_como_venta_sin_costo(self):
        # nota de 15: 10 del plato (con costo) + 5 de delivery (no es un producto)
        self.venta(cantidad=1, precio='10.00', costo='4.00', total='15.00')
        data = self.reporte()
        self.assertEqual(data['ventas_total'], '15.00')
        self.assertEqual(data['ventas_sin_costo']['productos'], [])


class ReporteMargenPorPlatoPdfTests(TestCase):
    """PDF del margen de ganancia por plato (el detallado): mismos numeros que la pantalla, agrupado por plato."""

    URL = '/api/admin/reportes/margen-por-plato-pdf/'
    URL_PANTALLA = '/api/admin/reportes/margen-ganancia/'

    def setUp(self):
        admin_role, _ = VGRol.objects.get_or_create(nombre_role='Administrador')
        cajera_role, _ = VGRol.objects.get_or_create(nombre_role='Cajera')
        self.admin = VGUsuario.objects.create_superuser(
            username='mpdf_admin', password='claveAdmin123', cedula='96000001', email='mpdf_admin@varagrill.test', id_role=admin_role,
        )
        self.cajera = VGUsuario.objects.create_user(
            username='mpdf_cajera', password='claveCajera123', cedula='96000002', email='mpdf_cajera@varagrill.test', id_role=cajera_role,
        )
        self.hoy = timezone.localdate().isoformat()
        categoria = VGCategoriaProducto.objects.create(nombre='Platos MPDF')
        self.arepa = VGProducto.objects.create(nombre='Arepa MPDF', categoria=categoria, precio_venta='10.00', disponible=True)
        self.pizza = VGProducto.objects.create(nombre='Pizza MPDF', categoria=categoria, precio_venta='30.00', disponible=True)
        self.venta(self.arepa, cantidad=2, precio='10.00', costo='4.00')   # vende 20, cuesta 8
        self.venta(self.arepa, cantidad=1, precio='10.00', costo='4.00')   # vende 10, cuesta 4
        self.venta(self.pizza, cantidad=1, precio='30.00', costo='12.50')  # vende 30, cuesta 12.50

    def venta(self, producto, cantidad, precio, costo):
        subtotal = Decimal(precio) * cantidad
        pedido = VGPedido.objects.create(usuario=self.admin, tipo_pedido='llevar', estado='pagado', subtotal=subtotal, total=subtotal)
        VGDetallePedido.objects.create(
            pedido=pedido, producto=producto, cantidad=cantidad, precio_unitario=Decimal(precio), estado='entregado',
            costo_unitario_venta=Decimal(costo), margen_produccion_pct_venta=Decimal('0'),
        )

    def pedir(self, usuario=None, **params):
        from unittest import mock
        self.client.force_login(usuario or self.admin)
        params.setdefault('desde', self.hoy)
        params.setdefault('hasta', self.hoy)
        with mock.patch('varagrill.reportes_pdf_views.generar_pdf_margen_por_plato', return_value=b'%PDF-falso') as generar:
            r = self.client.get(self.URL, params)
        return r, generar

    def test_solo_lo_descarga_un_administrador_y_solo_por_get(self):
        self.assertEqual(self.client.get(self.URL).status_code, 401)
        r, _ = self.pedir(usuario=self.cajera)
        self.assertEqual(r.status_code, 401)
        r, _ = self.pedir()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.post(self.URL).status_code, 405)

    def test_rechaza_rango_invertido_rango_largo_y_plato_invalido(self):
        for params in (
            {'desde': '2026-09-11', 'hasta': '2026-09-10'},
            {'desde': '2026-01-01', 'hasta': '2026-12-31'},
            {'desde': 'no-es-fecha', 'hasta': '2026-09-10'},
            {'producto_id': 'abc'},
        ):
            r, generar = self.pedir(**params)
            self.assertEqual(r.status_code, 400, params)
            generar.assert_not_called()

    def test_un_plato_sin_ventas_en_el_rango_da_404(self):
        otro = VGProducto.objects.create(nombre='Sin ventas MPDF', categoria=self.arepa.categoria, precio_venta='5.00', disponible=True)
        r, generar = self.pedir(producto_id=otro.id)
        self.assertEqual(r.status_code, 404)
        generar.assert_not_called()

    def test_el_pdf_lleva_los_mismos_totales_y_secciones_que_la_pantalla(self):
        self.client.force_login(self.admin)
        pantalla = self.client.get(self.URL_PANTALLA, {'desde': self.hoy, 'hasta': self.hoy}).json()
        r, generar = self.pedir()
        self.assertEqual(r.status_code, 200)
        secciones, totales, total_lineas, desde, hasta = generar.call_args.args
        self.assertEqual(secciones, pantalla['secciones'])
        self.assertEqual(totales, pantalla['totales'])
        self.assertEqual(total_lineas, pantalla['total_lineas'])
        self.assertEqual(totales['ingreso_total'], '60.00')
        self.assertEqual(totales['costo_con_margen_total'], '24.50')
        self.assertEqual(totales['ganancia_monto'], '35.50')
        self.assertEqual({s['nombre'] for s in secciones}, {'Arepa MPDF', 'Pizza MPDF'})

    def test_con_producto_id_solo_va_ese_plato_con_sus_propios_totales(self):
        r, generar = self.pedir(producto_id=self.arepa.id)
        self.assertEqual(r.status_code, 200)
        secciones, totales, total_lineas, _desde, _hasta = generar.call_args.args
        self.assertEqual([s['nombre'] for s in secciones], ['Arepa MPDF'])
        self.assertEqual(total_lineas, 2)
        self.assertEqual(totales['ingreso_total'], '30.00')
        self.assertEqual(totales['costo_con_margen_total'], '12.00')
        self.assertEqual(totales['ganancia_monto'], '18.00')

    def test_genera_un_pdf_de_verdad_con_nombre_de_archivo_del_rango(self):
        self.client.force_login(self.admin)
        r = self.client.get(self.URL, {'desde': self.hoy, 'hasta': self.hoy})
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.assertEqual(r['Content-Type'], 'application/pdf')
        self.assertTrue(r.content.startswith(b'%PDF'))
        self.assertIn('margen-por-plato', r['Content-Disposition'])

    def test_los_platos_con_muchas_ventas_se_parten_en_bloques_con_su_nombre(self):
        from varagrill.pdf_reportes.margen_por_plato import FILAS_POR_BLOQUE, armar_secciones_margen_por_plato
        cantidad = FILAS_POR_BLOQUE * 2 + 5
        fila = {
            'detalle_id': 1, 'pedido_id': 7, 'nota_entrega_codigo': None, 'fecha_hora': '2026-10-01T12:00:00-04:00',
            'cantidad': '1', 'peso_gramos': None, 'unidad': 'unidad', 'ingreso': '10.00', 'costo': '4.00',
            'costo_con_margen': '4.00', 'ganancia_monto': '6.00', 'ganancia_pct': '60.00',
            'costo_estimado': False, 'margen_estimado': False,
        }
        seccion = {
            'producto_id': 1, 'nombre': 'Plato largo', 'categoria': 'Platos', 'filas': [dict(fila) for _ in range(cantidad)],
            'total_unidades': str(cantidad), 'total_kg': '0', 'total_ingreso': '10.00', 'total_costo': '4.00',
            'total_costo_con_margen': '4.00', 'total_ganancia_monto': '6.00', 'total_ganancia_pct': '60.00',
            'total_lineas': cantidad, 'tiene_costo_estimado': False, 'tiene_margen_estimado': False,
        }
        totales = {
            'ingreso_total': '10.00', 'costo_total': '4.00', 'costo_con_margen_total': '4.00',
            'ganancia_monto': '6.00', 'ganancia_pct': '60.00',
        }
        bloques = armar_secciones_margen_por_plato([seccion], totales)[1:]  # el primero es el resumen
        self.assertEqual(len(bloques), 3)
        self.assertEqual([b.titulo for b in bloques], ['Plato largo', 'Plato largo (continúa)', 'Plato largo (continúa)'])
        self.assertEqual(sum(len(b.filas) for b in bloques), cantidad)
        self.assertEqual([b.fila_total is not None for b in bloques], [False, False, True])


class MovimientoInventarioReporteTests(TestCase):
    """Reporte de movimiento de inventario: ingredientes con movimiento, su origen y el detalle de pedido/nota."""

    URL = '/api/admin/reportes/movimiento-inventario/'

    def setUp(self):
        from datetime import timedelta
        from varagrill.models import VGCompra, VGMetodoPago, VGMovimientoInventario, VGNotaEntrega
        admin_role, _ = VGRol.objects.get_or_create(nombre_role='Administrador')
        cajera_role, _ = VGRol.objects.get_or_create(nombre_role='Cajera')
        self.admin = VGUsuario.objects.create_superuser(
            username='mi_admin', password='claveAdmin123', cedula='97000001', email='mi_admin@varagrill.test', id_role=admin_role,
        )
        self.cajera = VGUsuario.objects.create_user(
            username='mi_cajera', password='claveCajera123', cedula='97000002', email='mi_cajera@varagrill.test', id_role=cajera_role,
        )
        self.hoy = timezone.localdate()
        self.ayer = self.hoy - timedelta(days=1)
        self.carne = VGIngrediente.objects.create(nombre='Carne MI', unidad_medida='g', stock_actual=Decimal('1000'), costo_unitario=Decimal('0.02'))
        self.queso = VGIngrediente.objects.create(nombre='Queso MI', unidad_medida='g', stock_actual=Decimal('500'), costo_unitario=Decimal('0.03'))
        self.sin_mov = VGIngrediente.objects.create(nombre='Sal MI', unidad_medida='g', stock_actual=Decimal('100'), costo_unitario=Decimal('0.01'))

        categoria = VGCategoriaProducto.objects.create(nombre='Platos MI')
        self.hamburguesa = VGProducto.objects.create(nombre='Hamburguesa MI', categoria=categoria, precio_venta='10.00', disponible=True)
        self.papas = VGProducto.objects.create(nombre='Papas MI', categoria=categoria, precio_venta='4.00', disponible=True)
        self.pedido = VGPedido.objects.create(usuario=self.admin, tipo_pedido='llevar', estado='pagado', subtotal=Decimal('24'), total=Decimal('24'))
        VGDetallePedido.objects.create(pedido=self.pedido, producto=self.hamburguesa, cantidad=2, precio_unitario=Decimal('10.00'), estado='entregado')
        VGDetallePedido.objects.create(pedido=self.pedido, producto=self.papas, cantidad=1, precio_unitario=Decimal('4.00'), estado='entregado')
        metodo = VGMetodoPago.objects.create(nombre='Efectivo MI', moneda='USD', es_efectivo=True)
        self.nota = VGNotaEntrega.objects.create(
            metodo_pago=metodo, total=Decimal('24'), saldo_pendiente=Decimal('0'), estado='pagada', tasa_cambio_referencia=Decimal('100.0000'),
        )
        self.nota.pedidos.set([self.pedido])
        compra = VGCompra.objects.create(
            proveedor_nombre='Proveedor MI', estado='recibido', total=Decimal('50'), saldo_pendiente=Decimal('0'),
            estado_pago='pagada', tasa_cambio_referencia=Decimal('100.0000'), moneda_origen='USD',
        )

        def mov(ingrediente, tipo, cantidad, motivo, referencia=None, compra_obj=None, dia=None):
            m = VGMovimientoInventario.objects.create(
                ingrediente=ingrediente, tipo_movimiento=tipo, cantidad=Decimal(cantidad), motivo=motivo,
                id_referencia=referencia, compra=compra_obj, creado_por=self.admin,
            )
            if dia is not None:
                from datetime import datetime
                VGMovimientoInventario.objects.filter(pk=m.pk).update(
                    fecha_movimiento=timezone.make_aware(datetime(dia.year, dia.month, dia.day, 12, 0)),
                )
            return m

        self.venta = mov(self.carne, 'salida', '300', f'Venta — Pedido #{self.pedido.id}', referencia=self.pedido.id)
        mov(self.queso, 'salida', '40', f'Venta — Pedido #{self.pedido.id}', referencia=self.pedido.id)
        mov(self.carne, 'entrada', '500', f'Compra registrada #{compra.id}', referencia=compra.id, compra_obj=compra)
        mov(self.carne, 'ajuste', '-20', 'Ajuste de inventario #7', referencia=7)
        mov(self.carne, 'entrada', '300', f'Reversion por anulacion de Nota de entrega {self.nota.codigo}', referencia=self.nota.id)
        # rollback: no cuenta en el reporte
        mov(self.carne, 'ajuste', '999', 'ROLLBACK inventario por correccion del rango 2026-09-02 a 2026-09-21. Original #1', referencia=1)
        # de ayer: fuera del rango "hoy"
        mov(self.carne, 'salida', '77', 'Venta — Pedido #1', referencia=1, dia=self.ayer)

    def pedir(self, ruta='', usuario=None, **params):
        self.client.force_login(usuario or self.admin)
        params.setdefault('desde', self.hoy.isoformat())
        params.setdefault('hasta', self.hoy.isoformat())
        return self.client.get(self.URL + ruta, params)

    def test_solo_un_administrador_y_solo_por_get(self):
        self.assertEqual(self.client.get(self.URL).status_code, 401)
        self.assertEqual(self.pedir(usuario=self.cajera).status_code, 401)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(self.URL).status_code, 405)

    def test_resumen_por_ingrediente_sin_rollback_y_solo_los_que_tuvieron_movimiento(self):
        data = self.pedir().json()
        self.assertTrue(data['ok'])
        por_nombre = {i['nombre']: i for i in data['ingredientes']}
        self.assertEqual(set(por_nombre), {'Carne MI', 'Queso MI'})  # Sal MI no tuvo movimiento
        carne = por_nombre['Carne MI']
        self.assertEqual(Decimal(carne['entradas']), Decimal('800'))   # compra 500 + reversion 300
        self.assertEqual(Decimal(carne['salidas']), Decimal('300'))
        self.assertEqual(Decimal(carne['ajustes']), Decimal('-20'))    # el ROLLBACK (999) no cuenta
        self.assertEqual(Decimal(carne['neto']), Decimal('480'))
        self.assertEqual(carne['movimientos'], 4)
        self.assertEqual(data['total_movimientos'], 5)  # 4 de la carne + 1 del queso (sin el ROLLBACK)

    def test_el_rango_deja_fuera_otros_dias(self):
        ayer = self.pedir(desde=self.ayer.isoformat(), hasta=self.ayer.isoformat()).json()
        self.assertEqual([i['nombre'] for i in ayer['ingredientes']], ['Carne MI'])
        self.assertEqual(Decimal(ayer['ingredientes'][0]['salidas']), Decimal('77'))
        self.assertEqual(self.pedir(desde='2026-01-02', hasta='2026-01-01').status_code, 400)

    def test_filtra_por_nombre_y_por_tipo(self):
        solo_queso = self.pedir(q='quesito').json()['ingredientes']
        self.assertEqual(solo_queso, [])
        solo_queso = self.pedir(q='queso').json()['ingredientes']
        self.assertEqual([i['nombre'] for i in solo_queso], ['Queso MI'])
        salidas = self.pedir(tipo='salida').json()['ingredientes']
        self.assertEqual({i['nombre']: Decimal(i['salidas']) for i in salidas}, {'Carne MI': Decimal('300'), 'Queso MI': Decimal('40')})
        self.assertTrue(all(Decimal(i['entradas']) == 0 and Decimal(i['ajustes']) == 0 for i in salidas))

    def test_detalle_del_ingrediente_con_su_origen(self):
        data = self.pedir(f'ingrediente/{self.carne.id}/').json()
        self.assertEqual(data['total'], 4)
        self.assertFalse(data['truncado'])
        self.assertFalse(any('ROLLBACK' in m['motivo'] for m in data['movimientos']))
        origenes = {m['motivo'].split(' ')[0]: m['origen'] for m in data['movimientos']}
        self.assertEqual(origenes['Venta'], {'tipo': 'pedido', 'id': self.pedido.id, 'etiqueta': f'Pedido #{self.pedido.id}'})
        self.assertEqual(origenes['Reversion']['tipo'], 'nota_entrega')
        self.assertEqual(origenes['Reversion']['id'], self.nota.id)
        self.assertEqual(origenes['Compra']['tipo'], 'compra')
        self.assertEqual(origenes['Ajuste']['tipo'], 'ajuste')
        self.assertEqual(data['movimientos'][0]['usuario'], self.admin.username)

    def test_el_pedido_trae_sus_productos_y_la_nota_de_entrega(self):
        r = self.pedir(f'pedido/{self.pedido.id}/')
        self.assertEqual(r.status_code, 200, r.content)
        pedido = r.json()['pedido']
        self.assertEqual(pedido['id'], self.pedido.id)
        self.assertEqual(
            sorted((p['producto'], p['cantidad']) for p in pedido['productos']),
            [('Hamburguesa MI', 2), ('Papas MI', 1)],
        )
        self.assertEqual([n['codigo'] for n in pedido['notas_entrega']], [self.nota.codigo])
        self.assertEqual(pedido['notas_entrega'][0]['estado'], 'pagada')
        self.assertEqual(pedido['notas_entrega'][0]['pedidos'], [self.pedido.id])
        self.assertEqual(self.pedir('pedido/99999999/').status_code, 404)

    def test_la_nota_trae_sus_pedidos_con_productos(self):
        r = self.pedir(f'nota-entrega/{self.nota.id}/')
        self.assertEqual(r.status_code, 200, r.content)
        data = r.json()
        self.assertEqual(data['nota']['codigo'], self.nota.codigo)
        self.assertEqual([p['id'] for p in data['pedidos']], [self.pedido.id])
        self.assertEqual(len(data['pedidos'][0]['productos']), 2)
        self.assertEqual(self.pedir('nota-entrega/99999999/').status_code, 404)


class ComidaEmpleadosTests(TestCase):
    """Comida de empleados: descuenta del inventario sin vender ni facturar, y se puede anular."""

    URL = '/api/admin/comida-empleados/'

    def setUp(self):
        from datetime import timedelta
        from varagrill.models import VGPreparacion, VGRecetaPreparacion
        admin_role, _ = VGRol.objects.get_or_create(nombre_role='Administrador')
        contador_role, _ = VGRol.objects.get_or_create(nombre_role='Contador')
        cajera_role, _ = VGRol.objects.get_or_create(nombre_role='Cajera')
        self.admin = VGUsuario.objects.create_superuser(
            username='ce_admin', password='claveAdmin123', cedula='98100001', email='ce_admin@varagrill.test', id_role=admin_role,
        )
        self.contador = VGUsuario.objects.create_user(
            username='ce_contador', password='claveConta123', cedula='98100002', email='ce_contador@varagrill.test', id_role=contador_role,
        )
        self.cajera = VGUsuario.objects.create_user(
            username='ce_cajera', password='claveCajera123', cedula='98100003', email='ce_cajera@varagrill.test', id_role=cajera_role,
        )
        self.hoy = timezone.localdate()
        self.ayer = self.hoy - timedelta(days=1)
        _set_tasa_actual('100.0000')  # sin salir a internet a buscar la tasa del BCV

        self.arroz = VGIngrediente.objects.create(nombre='Arroz CE', unidad_medida='g', stock_actual=Decimal('1000'), costo_unitario=Decimal('0.01'))
        self.pollo = VGIngrediente.objects.create(nombre='Pollo CE', unidad_medida='g', stock_actual=Decimal('500'), costo_unitario=Decimal('0.02'))
        self.sal = VGIngrediente.objects.create(nombre='Sal CE', unidad_medida='g', stock_actual=Decimal('100'), costo_unitario=Decimal('0.01'))

        categoria = VGCategoriaProducto.objects.create(nombre='Recetas')
        self.receta = VGProducto.objects.create(
            nombre='Arroz con pollo CE', categoria=categoria, precio_venta='0', disponible=False, apta_comida_empleados=True,
        )
        VGRecetaProducto.objects.create(producto=self.receta, ingrediente=self.arroz, cantidad_requerida=Decimal('100'))
        VGRecetaProducto.objects.create(producto=self.receta, ingrediente=self.pollo, cantidad_requerida=Decimal('150'))
        self.receta_no_apta = VGProducto.objects.create(
            nombre='Receta de la carta CE', categoria=categoria, precio_venta='0', disponible=False, apta_comida_empleados=False,
        )
        VGRecetaProducto.objects.create(producto=self.receta_no_apta, ingrediente=self.arroz, cantidad_requerida=Decimal('10'))

        # subreceta: un lote de 1000 g lleva 600 g de arroz y 40 g de sal
        self.subreceta = VGPreparacion.objects.create(nombre='Arroz base CE', rendimiento_cantidad=Decimal('1000'), rendimiento_unidad='g')
        VGRecetaPreparacion.objects.create(preparacion=self.subreceta, ingrediente=self.arroz, cantidad_requerida=Decimal('600'))
        VGRecetaPreparacion.objects.create(preparacion=self.subreceta, ingrediente=self.sal, cantidad_requerida=Decimal('40'))
        # receta que lleva 200 g de esa subreceta por porcion
        self.receta_anidada = VGProducto.objects.create(
            nombre='Plato con arroz base CE', categoria=categoria, precio_venta='0', disponible=False, apta_comida_empleados=True,
        )
        VGRecetaProducto.objects.create(producto=self.receta_anidada, preparacion=self.subreceta, cantidad_requerida=Decimal('200'))

    def post(self, ruta='', usuario=None, **cuerpo):
        self.client.force_login(usuario or self.admin)
        return self.client.post(self.URL + ruta, data=json.dumps(cuerpo), content_type='application/json')

    def get(self, ruta='', usuario=None, **params):
        self.client.force_login(usuario or self.admin)
        return self.client.get(self.URL + ruta, params)

    def stock(self, ingrediente):
        ingrediente.refresh_from_db()
        return ingrediente.stock_actual

    def test_solo_administradores_y_contadores(self):
        self.assertEqual(self.client.get(self.URL).status_code, 401)
        self.assertEqual(self.get(usuario=self.cajera).status_code, 401)
        self.assertEqual(self.get(usuario=self.contador).status_code, 200)
        self.assertEqual(self.get(usuario=self.admin).status_code, 200)

    def test_opciones_solo_recetas_marcadas_y_todas_las_subrecetas_e_ingredientes(self):
        data = self.get('opciones/').json()
        self.assertEqual({r['nombre'] for r in data['recetas']}, {'Arroz con pollo CE', 'Plato con arroz base CE'})
        self.assertEqual([s['nombre'] for s in data['subrecetas']], ['Arroz base CE'])
        self.assertTrue({'Arroz CE', 'Pollo CE', 'Sal CE'} <= {i['nombre'] for i in data['ingredientes']})
        self.assertTrue(data['puede_fecha_pasada'])
        self.assertFalse(self.get('opciones/', usuario=self.contador).json()['puede_fecha_pasada'])

    def test_previsualizar_no_toca_el_stock_y_avisa_si_no_alcanza(self):
        r = self.post('previsualizar/', tipo='receta', origen_id=self.receta.id, cantidad='4')
        self.assertEqual(r.status_code, 200, r.content)
        data = r.json()
        por_nombre = {l['nombre']: l for l in data['lineas']}
        self.assertEqual(Decimal(por_nombre['Arroz CE']['cantidad']), Decimal('400'))
        self.assertEqual(Decimal(por_nombre['Pollo CE']['cantidad']), Decimal('600'))
        self.assertEqual(Decimal(por_nombre['Pollo CE']['stock_despues']), Decimal('-100'))
        self.assertEqual(data['sin_stock'], ['Pollo CE'])
        self.assertEqual(Decimal(data['costo_total']), Decimal('16.00'))  # 400 x 0.01 + 600 x 0.02
        self.assertEqual(self.stock(self.pollo), Decimal('500'))
        from varagrill.models import VGComidaEmpleados
        self.assertEqual(VGComidaEmpleados.objects.count(), 0)

    def test_registrar_una_receta_descuenta_el_inventario_y_deja_los_movimientos(self):
        from varagrill.models import VGComidaEmpleados, VGMovimientoInventario
        r = self.post(tipo='receta', origen_id=self.receta.id, cantidad='3', turno='almuerzo', nota='Almuerzo del personal')
        self.assertEqual(r.status_code, 201, r.content)
        comida = r.json()['comida']
        self.assertEqual(comida['estado'], 'registrada')
        self.assertEqual(comida['turno_label'], 'Almuerzo')
        self.assertEqual(Decimal(comida['costo_total']), Decimal('12.00'))  # 300 x 0.01 + 450 x 0.02
        self.assertEqual(self.stock(self.arroz), Decimal('700'))
        self.assertEqual(self.stock(self.pollo), Decimal('50'))
        movimientos = VGMovimientoInventario.objects.filter(id_referencia=comida['id'], tipo_movimiento='salida')
        self.assertEqual(movimientos.count(), 2)
        self.assertTrue(all(m.motivo.startswith('Comida de empleados') for m in movimientos))
        self.assertEqual(VGComidaEmpleados.objects.get(pk=comida['id']).detalles.count(), 2)

    def test_si_no_alcanza_pide_confirmacion_y_con_ella_deja_el_stock_en_negativo(self):
        r = self.post(tipo='receta', origen_id=self.receta.id, cantidad='4')
        self.assertEqual(r.status_code, 409, r.content)
        self.assertEqual(r.json()['code'], 'stock_insuficiente')
        self.assertEqual(r.json()['sin_stock'], ['Pollo CE'])
        self.assertEqual(self.stock(self.pollo), Decimal('500'))
        r = self.post(tipo='receta', origen_id=self.receta.id, cantidad='4', confirmar_stock_insuficiente=True)
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(self.stock(self.pollo), Decimal('-100'))

    def test_una_subreceta_se_descuenta_segun_su_rendimiento(self):
        r = self.post(tipo='subreceta', origen_id=self.subreceta.id, cantidad='500')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()['comida']['unidad'], 'g')
        self.assertEqual(self.stock(self.arroz), Decimal('700'))  # 500 g es medio lote: 300 g de arroz
        self.assertEqual(self.stock(self.sal), Decimal('80'))     # y 20 g de sal

    def test_una_receta_con_subreceta_anidada_descuenta_hasta_el_ingrediente_crudo(self):
        r = self.post(tipo='receta', origen_id=self.receta_anidada.id, cantidad='5')
        self.assertEqual(r.status_code, 201, r.content)
        # 5 porciones x 200 g de subreceta = 1000 g = un lote: 600 g de arroz y 40 g de sal
        self.assertEqual(self.stock(self.arroz), Decimal('400'))
        self.assertEqual(self.stock(self.sal), Decimal('60'))

    def test_un_ingrediente_suelto(self):
        r = self.post(tipo='ingrediente', origen_id=self.arroz.id, cantidad='250')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()['comida']['unidad'], 'g')
        self.assertEqual(self.stock(self.arroz), Decimal('750'))

    def test_validaciones_de_lo_que_se_elige(self):
        self.assertEqual(self.post(tipo='receta', origen_id=self.receta_no_apta.id, cantidad='2').status_code, 400)
        self.assertEqual(self.post(tipo='receta', origen_id=99999999, cantidad='2').status_code, 400)
        self.assertEqual(self.post(tipo='ingrediente', origen_id=self.arroz.id, cantidad='0').status_code, 400)
        self.assertEqual(self.post(tipo='ingrediente', origen_id=self.arroz.id, cantidad='abc').status_code, 400)
        self.assertEqual(self.post(tipo='otra-cosa', origen_id=1, cantidad='1').status_code, 400)
        self.assertEqual(self.stock(self.arroz), Decimal('1000'))

    def test_la_fecha_pasada_solo_la_registra_un_administrador(self):
        from datetime import timedelta
        from varagrill.models import VGMovimientoInventario
        r = self.post(usuario=self.contador, tipo='ingrediente', origen_id=self.arroz.id, cantidad='10', fecha=self.ayer.isoformat())
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.post(tipo='ingrediente', origen_id=self.arroz.id, cantidad='10', fecha=(self.hoy + timedelta(days=30)).isoformat()).status_code, 400)
        r = self.post(tipo='ingrediente', origen_id=self.arroz.id, cantidad='10', fecha=self.ayer.isoformat())
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()['comida']['fecha'], self.ayer.isoformat())
        mov = VGMovimientoInventario.objects.get(id_referencia=r.json()['comida']['id'])
        self.assertEqual(timezone.localtime(mov.fecha_movimiento).date(), self.ayer)
        # el contador si registra la de hoy
        self.assertEqual(self.post(usuario=self.contador, tipo='ingrediente', origen_id=self.arroz.id, cantidad='10').status_code, 201)

    def test_avisa_si_ya_hay_una_comida_ese_dia_y_turno_pero_deja_registrar_varias(self):
        self.post(tipo='ingrediente', origen_id=self.arroz.id, cantidad='10', turno='almuerzo')
        previa = self.post('previsualizar/', tipo='ingrediente', origen_id=self.arroz.id, cantidad='10', turno='almuerzo').json()
        self.assertEqual(len(previa['ya_registradas']), 1)
        otro_turno = self.post('previsualizar/', tipo='ingrediente', origen_id=self.arroz.id, cantidad='10', turno='cena').json()
        self.assertEqual(otro_turno['ya_registradas'], [])
        self.assertEqual(self.post(tipo='ingrediente', origen_id=self.arroz.id, cantidad='10', turno='almuerzo').status_code, 201)

    def test_anular_repone_exactamente_lo_descontado(self):
        from varagrill.models import VGMovimientoInventario
        comida = self.post(tipo='receta', origen_id=self.receta.id, cantidad='3').json()['comida']
        self.assertEqual(self.post(f'{comida["id"]}/anular/', usuario=self.contador, motivo='Error').status_code, 403)
        self.assertEqual(self.post(f'{comida["id"]}/anular/', motivo='').status_code, 400)
        r = self.post(f'{comida["id"]}/anular/', motivo='Se registró por error')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()['comida']['estado'], 'anulada')
        self.assertEqual(self.stock(self.arroz), Decimal('1000'))
        self.assertEqual(self.stock(self.pollo), Decimal('500'))
        self.assertEqual(VGMovimientoInventario.objects.filter(id_referencia=comida['id'], tipo_movimiento='entrada').count(), 2)
        self.assertEqual(self.post(f'{comida["id"]}/anular/', motivo='otra vez').status_code, 400)

    def test_el_historial_suma_solo_las_registradas(self):
        a = self.post(tipo='ingrediente', origen_id=self.arroz.id, cantidad='100').json()['comida']  # 1.00
        b = self.post(tipo='ingrediente', origen_id=self.pollo.id, cantidad='100').json()['comida']  # 2.00
        self.post(f'{b["id"]}/anular/', motivo='prueba')
        data = self.get(desde=self.hoy.isoformat(), hasta=self.hoy.isoformat()).json()
        self.assertEqual({c['id']: c['estado'] for c in data['comidas']}, {a['id']: 'registrada', b['id']: 'anulada'})
        self.assertEqual(data['total_registradas'], 1)
        self.assertEqual(Decimal(data['costo_total']), Decimal('1.00'))
        detalle = self.get(f'{a["id"]}/').json()['comida']
        self.assertEqual([l['nombre'] for l in detalle['lineas']], ['Arroz CE'])

    def test_el_estado_de_resultados_resta_la_alimentacion_del_personal(self):
        self.post(tipo='receta', origen_id=self.receta.id, cantidad='3')  # costo 12.00
        self.client.force_login(self.admin)
        r = self.client.get('/api/admin/reportes/estado-resultados/', {'desde': self.hoy.isoformat(), 'hasta': self.hoy.isoformat()})
        self.assertEqual(r.status_code, 200, r.content)
        data = r.json()
        self.assertEqual(data['comida_empleados']['total'], '12.00')
        self.assertEqual(data['comida_empleados']['cantidad'], 1)
        self.assertEqual(data['utilidad_neta'], '-12.00')

    def test_el_movimiento_de_inventario_enlaza_con_la_comida(self):
        comida = self.post(tipo='receta', origen_id=self.receta.id, cantidad='3').json()['comida']
        self.client.force_login(self.admin)
        r = self.client.get(f'/api/admin/reportes/movimiento-inventario/ingrediente/{self.arroz.id}/', {'desde': self.hoy.isoformat(), 'hasta': self.hoy.isoformat()})
        origen = r.json()['movimientos'][0]['origen']
        self.assertEqual(origen, {'tipo': 'comida_empleados', 'id': comida['id'], 'etiqueta': f'Comida de empleados #{comida["id"]}'})

    def test_el_check_de_la_receta_se_guarda_y_se_conserva_al_editar(self):
        self.client.force_login(self.admin)
        cuerpo = {
            'action': 'create', 'nombre': 'Sopa CE', 'descripcion': '',
            'componentes': [{'tipo': 'ingrediente', 'referencia_id': self.sal.id, 'cantidad': '5'}],
            'apta_comida_empleados': True,
        }
        r = self.client.post('/api/admin/recetas/', data=json.dumps(cuerpo), content_type='application/json')
        self.assertEqual(r.status_code, 201, r.content)
        receta = r.json()['recipe']
        self.assertTrue(receta['apta_comida_empleados'])
        cuerpo.update({'action': 'update', 'id': receta['id']})
        cuerpo.pop('apta_comida_empleados')  # si no lo manda, conserva el valor
        r = self.client.post('/api/admin/recetas/', data=json.dumps(cuerpo), content_type='application/json')
        self.assertTrue(r.json()['recipe']['apta_comida_empleados'])
        cuerpo['apta_comida_empleados'] = False
        r = self.client.post('/api/admin/recetas/', data=json.dumps(cuerpo), content_type='application/json')
        self.assertFalse(r.json()['recipe']['apta_comida_empleados'])


class ComandaNoImpresaTests(TestCase):
    """Si una impresora no responde, el pedido igual queda registrado pero la respuesta avisa que la comanda NO salió."""

    COCINA = '192.168.1.246'
    PARRILLA = '192.168.1.200'

    def setUp(self):
        mesero_role, _ = VGRol.objects.get_or_create(nombre_role='Mesero')
        self.user = VGUsuario.objects.create_user(
            username='mesero_imp', password='claveMesero123', cedula='96000001', email='mesero_imp@test.test', id_role=mesero_role,
        )
        self.client.force_login(self.user)
        self.cat_cocina = VGCategoriaProducto.objects.create(nombre='Cocina IMP', ip_impresora=self.COCINA, puerto_impresora=9100)
        self.cat_parrilla = VGCategoriaProducto.objects.create(nombre='Parrilla IMP', ip_impresora=self.PARRILLA, puerto_impresora=9100)
        self.plato = VGProducto.objects.create(nombre='Plato IMP', categoria=self.cat_cocina, precio_venta='10.00', disponible=True)
        self.carne = VGProducto.objects.create(nombre='Carne IMP', categoria=self.cat_parrilla, precio_venta='12.00', disponible=True)
        self.conexiones = []
        self.caidas = set()

        def conectar(direccion, timeout=None):
            host = direccion[0]
            self.conexiones.append(host)
            if host in self.caidas:
                raise ConnectionRefusedError('rechazada')
            return MagicMock()

        patcher = patch('varagrill.impresion_termica.socket.create_connection', side_effect=conectar)
        patcher.start()
        self.addCleanup(patcher.stop)
        sleep_patcher = patch('varagrill.impresion_termica.time.sleep')
        sleep_patcher.start()
        self.addCleanup(sleep_patcher.stop)

    def _pedido(self, estado='pendiente'):
        pedido = VGPedido.objects.create(
            usuario=self.user, tipo_pedido='llevar', estado=estado, subtotal='22.00', total='22.00',
        )
        self.detalle_plato = VGDetallePedido.objects.create(pedido=pedido, producto=self.plato, cantidad=1, precio_unitario='10.00', estado='pendiente')
        self.detalle_carne = VGDetallePedido.objects.create(pedido=pedido, producto=self.carne, cantidad=1, precio_unitario='12.00', estado='pendiente')
        return pedido

    def _estado(self, pedido, estado='en_preparacion'):
        return self.client.post(
            f'/api/pedidos/{pedido.id}/estado/', data=json.dumps({'estado': estado}), content_type='application/json',
        )

    def test_si_todo_imprime_la_respuesta_lo_dice(self):
        pedido = self._pedido()
        r = self._estado(pedido)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['impresion'], {'ok': True, 'fallidas': []})
        self.assertEqual(sorted(self.conexiones), [self.PARRILLA, self.COCINA])

    def test_si_una_impresora_falla_el_pedido_queda_registrado_y_la_respuesta_avisa(self):
        self.caidas = {self.COCINA}
        pedido = self._pedido()
        r = self._estado(pedido)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['ok'])
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, 'en_preparacion')
        impresion = r.json()['impresion']
        self.assertFalse(impresion['ok'])
        self.assertEqual(len(impresion['fallidas']), 1)
        falla = impresion['fallidas'][0]
        self.assertEqual(falla['nombre'], 'Cocina IMP')
        self.assertEqual(falla['destino'], f'{self.COCINA}:9100')
        self.assertIn('rechazó', falla['motivo'])

    def test_una_categoria_sin_ip_no_cuenta_como_fallo(self):
        VGCategoriaProducto.objects.all().update(ip_impresora='')
        pedido = self._pedido()
        r = self._estado(pedido)
        self.assertEqual(r.json()['impresion'], {'ok': True, 'fallidas': []})
        self.assertEqual(self.conexiones, [])

    def test_un_cambio_de_estado_que_no_imprime_no_trae_aviso(self):
        pedido = self._pedido(estado='pendiente')
        r = self._estado(pedido, 'cancelado')
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.json()['impresion'])
        self.assertEqual(self.conexiones, [])

    def test_reimprimir_la_comanda_devuelve_502_con_la_impresora_que_fallo(self):
        pedido = self._pedido(estado='en_preparacion')
        self.caidas = {self.PARRILLA}
        r = self.client.post(f'/api/pedidos/{pedido.id}/reimprimir-comanda/')
        self.assertEqual(r.status_code, 502)
        self.assertFalse(r.json()['ok'])
        self.assertIn('Parrilla IMP', r.json()['message'])
        self.assertEqual([f['nombre'] for f in r.json()['impresion']['fallidas']], ['Parrilla IMP'])

    def test_reintentar_con_destinos_solo_reenvia_a_las_que_fallaron(self):
        pedido = self._pedido(estado='en_preparacion')
        self.caidas = {self.PARRILLA}
        self.client.post(f'/api/pedidos/{pedido.id}/reimprimir-comanda/')
        self.caidas = set()
        self.conexiones.clear()
        r = self.client.post(
            f'/api/pedidos/{pedido.id}/reimprimir-comanda/',
            data=json.dumps({'destinos': [f'{self.PARRILLA}:9100']}), content_type='application/json',
        )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['ok'])
        self.assertEqual(self.conexiones, [self.PARRILLA])  # la cocina no recibe un duplicado

    def test_reimprimir_un_renglon_devuelve_502_si_la_impresora_no_responde(self):
        pedido = self._pedido(estado='en_preparacion')
        pedido.fecha_inicio_preparacion = timezone.now()
        pedido.save(update_fields=['fecha_inicio_preparacion'])
        self.caidas = {self.PARRILLA}
        r = self.client.post(f'/api/pedidos/{pedido.id}/items/{self.detalle_carne.id}/reimprimir/')
        self.assertEqual(r.status_code, 502)
        self.assertIn('Parrilla IMP', r.json()['message'])


class CobroSinPermisoTests(TestCase):
    """/api/pedidos/cobro/: sin sesion 401, con sesion pero sin permiso (mesero) 403, cajera y admin 200."""

    URL = '/api/pedidos/cobro/'

    def _usuario(self, rol, cedula):
        role, _ = VGRol.objects.get_or_create(nombre_role=rol)
        return VGUsuario.objects.create_user(
            username=f'cobro_{rol.lower()}', password='claveCobro123', cedula=cedula,
            email=f'cobro_{rol.lower()}@varagrill.test', id_role=role,
        )

    def test_sin_sesion_es_401(self):
        self.assertEqual(self.client.get(self.URL).status_code, 401)

    def test_un_mesero_recibe_403_no_401(self):
        self.client.force_login(self._usuario('Mesero', '95000001'))
        r = self.client.get(self.URL)
        self.assertEqual(r.status_code, 403)
        self.assertFalse(r.json()['ok'])

    def test_cajera_y_administrador_pueden_consultar(self):
        for rol, cedula in (('Cajera', '95000002'), ('Administrador', '95000003')):
            self.client.force_login(self._usuario(rol, cedula))
            r = self.client.get(self.URL)
            self.assertEqual(r.status_code, 200, rol)
            self.assertTrue(r.json()['ok'])


from varagrill.models import VGMovimientoBancario  # noqa: E402


# ---------------------------------------------------------------------------
# Conciliacion bancaria por movimiento (extracto del banco vs. registros del sistema)
# ---------------------------------------------------------------------------
def _xlsx_bytes(hojas):
    """Un .xlsx minimo: hojas = [(nombre, [[celda, ...], ...])]; str -> texto, int/float/Decimal -> numero."""
    import io
    import zipfile
    from xml.sax.saxutils import escape

    def col(i):
        return chr(ord('A') + i)

    libro, rels, tipos, hojas_xml = [], [], [], []
    for n, (nombre, filas) in enumerate(hojas, start=1):
        libro.append(f'<sheet name="{escape(nombre)}" sheetId="{n}" r:id="rId{n}"/>')
        rels.append(f'<Relationship Id="rId{n}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{n}.xml"/>')
        tipos.append(f'<Override PartName="/xl/worksheets/sheet{n}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
        xml_filas = []
        for r, fila in enumerate(filas, start=1):
            celdas = []
            for c, valor in enumerate(fila):
                ref = f'{col(c)}{r}'
                if valor is None:
                    continue
                if isinstance(valor, (int, float, Decimal)):
                    celdas.append(f'<c r="{ref}"><v>{valor}</v></c>')
                else:
                    celdas.append(f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(valor))}</t></is></c>')
            xml_filas.append(f'<row r="{r}">{"".join(celdas)}</row>')
        hojas_xml.append(f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{"".join(xml_filas)}</sheetData></worksheet>')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as z:
        z.writestr('[Content_Types].xml', '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/>' + ''.join(tipos) + '</Types>')
        z.writestr('xl/workbook.xml', '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>' + ''.join(libro) + '</sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels', '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + ''.join(rels) + '</Relationships>')
        for n, xml in enumerate(hojas_xml, start=1):
            z.writestr(f'xl/worksheets/sheet{n}.xml', xml)
    return buffer.getvalue()


ENCABEZADO_BANCO = ['Fecha', 'Referencia', 'Descripción', 'Tipo', 'Monto', 'Saldo', 'Observacion']


class BancoExcelParserTests(TestCase):
    """Lector del extracto del banco: el formato real del Banco Plaza (texto en formato español, una hoja por día)."""

    def parsear(self, hojas, nombre='extracto.xlsx'):
        from varagrill.banco_excel import parsear_extracto
        return parsear_extracto(_xlsx_bytes(hojas), nombre)

    def test_lee_el_formato_del_banco_plaza_con_varias_hojas_y_columnas_sueltas(self):
        r = self.parsear([
            ('01oct26-', [
                ENCABEZADO_BANCO + [None, 'Gastos ', -169089.35],
                ['01/10/2026 23:20:08', '000038526', 'COMPRA MAESTRO', 'Débito', '-36.828,00', '828.169,56', 'gasolina planta electrica'],
                ['01/10/2026 23:09:48', '045613614', 'TRF BANESC V020657311 HAMADE D', 'Crédito', '25.346,92', '864.997,56', 'pago movil entrada negocio'],
            ]),
            ('02oct26', [
                ['Fecha', 'Referencia', 'Descripción', 'Tipo', 'Monto', 'Saldo', 'observacion '],
                ['02/10/2026 08:00:35', '940100612', 'POS MAE 88013794 001 0061 0110', 'Crédito', '100.074,03', '928.243,59', None],
                ['02/10/2026 08:30:00', '548488258', 'DOM POS DGL 88013794 0001 0110', 'Débito', '-2.599,68', '1.006.010,40', 'comision'],
            ]),
            ('19oct', [[None, None]]),
        ])
        movs = r['movimientos']
        self.assertEqual(len(movs), 4)
        self.assertEqual(r['errores'], [])
        self.assertEqual(r['hojas_omitidas'], [])  # una hoja vacia no cuenta como omitida
        primero = movs[0]
        self.assertEqual(primero['tipo'], 'debito')
        self.assertEqual(primero['monto'], Decimal('36828.00'))        # el monto siempre queda positivo
        self.assertEqual(primero['saldo'], Decimal('828169.56'))
        self.assertEqual(primero['fecha'], datetime(2026, 10, 1, 23, 20, 8))
        self.assertEqual(primero['observacion'], 'gasolina planta electrica')
        self.assertEqual([m['clase'] for m in movs], ['compra_tarjeta', 'transferencia_recibida', 'pos', 'comision'])
        self.assertEqual(movs[2]['observacion'], '')

    def test_acepta_numeros_y_fechas_de_excel_y_csv(self):
        r = self.parsear([('hoja', [
            ['Fecha', 'Monto', 'Descripcion'],
            [46296.5, -1234.5, 'TDY ENVIO A BNC 4125486135'],
        ])])
        m = r['movimientos'][0]
        self.assertEqual(m['monto'], Decimal('1234.5'))
        self.assertEqual(m['tipo'], 'debito')                          # sin columna Tipo manda el signo
        self.assertEqual(m['clase'], 'pago_movil_enviado')
        self.assertEqual(m['fecha'].date(), date(2026, 10, 1))

        from varagrill.banco_excel import parsear_extracto
        csv = 'Fecha;Referencia;Descripcion;Tipo;Monto\n01/10/2026 10:00:00;123;TDY RECIB DE VZLA 4245940617;Credito;1.733,12\n'
        m = parsear_extracto(csv.encode('utf-8'), 'extracto.csv')['movimientos'][0]
        self.assertEqual((m['tipo'], m['monto'], m['clase']), ('credito', Decimal('1733.12'), 'pago_movil_recibido'))

    def test_una_transferencia_y_su_comision_comparten_referencia_y_no_se_toman_por_repetidas(self):
        r = self.parsear([('d', [
            ENCABEZADO_BANCO,
            ['01/10/2026 11:05:53', '019331385', 'TRF PROVIN V020040168 ALFREDO', 'Débito', '-50.150,00', '749.560,69', ''],
            ['01/10/2026 11:05:53', '019331385', 'COM TRF 019331385', 'Débito', '-150,45', '799.710,69', ''],
            ['01/10/2026 11:05:53', '019331385', 'COM TRF 019331385', 'Débito', '-150,45', '799.710,69', ''],
        ])])
        self.assertEqual(len(r['movimientos']), 2)
        self.assertEqual(r['repetidas_en_archivo'], 1)
        self.assertEqual({m['clase'] for m in r['movimientos']}, {'transferencia_enviada', 'comision'})

    def test_reporta_las_filas_ilegibles_y_los_archivos_invalidos(self):
        r = self.parsear([('d', [
            ENCABEZADO_BANCO,
            ['no es fecha', '1', 'X', 'Débito', '-10,00', '5,00', ''],
            ['01/10/2026 10:00:00', '2', 'Y', 'Débito', 'abc', '5,00', ''],
            ['01/10/2026 10:00:00', '3', 'Z', 'Crédito', '10,00', '15,00', ''],
        ])])
        self.assertEqual(len(r['movimientos']), 1)
        self.assertEqual([e['fila'] for e in r['errores']], [2, 3])

        from varagrill.banco_excel import ExtractoInvalido, parsear_extracto
        with self.assertRaises(ExtractoInvalido):
            parsear_extracto(b'esto no es un excel', 'x.xlsx')
        with self.assertRaises(ExtractoInvalido):
            parsear_extracto(_xlsx_bytes([('d', [['Nombre', 'Cantidad'], ['a', 1]])]), 'x.xlsx')

    def test_los_saltos_del_saldo_avisan_que_puede_faltar_una_linea(self):
        completo = [
            ENCABEZADO_BANCO,
            ['01/10/2026 10:00:00', '1', 'A', 'Crédito', '100,00', '1.100,00', ''],
            ['01/10/2026 11:00:00', '2', 'B', 'Débito', '-50,00', '1.050,00', ''],
            ['01/10/2026 12:00:00', '3', 'C', 'Crédito', '25,00', '1.075,00', ''],
        ]
        self.assertEqual(self.parsear([('d', completo)])['saltos_saldo'], 0)
        con_hueco = [completo[0], completo[1], completo[3]]  # falta la fila B
        self.assertEqual(self.parsear([('d', con_hueco)])['saltos_saldo'], 1)


class ConciliacionBancariaMotorTests(TestCase):
    """Cruce de movimientos del banco contra pagos, gastos, compras y comisiones del sistema."""

    CUENTA = 'Banco Prueba'

    def setUp(self):
        from varagrill.models import VGAbonoCompra, VGAbonoGasto, VGCategoriaGasto, VGCompra, VGExtractoBancario, VGGasto, VGLotePOS, VGMetodoPago, VGMovimientoBancario
        self.M = SimpleNamespace(
            AbonoCompra=VGAbonoCompra, AbonoGasto=VGAbonoGasto, Compra=VGCompra, Extracto=VGExtractoBancario,
            Gasto=VGGasto, Lote=VGLotePOS, Mov=VGMovimientoBancario,
        )
        rol, _ = VGRol.objects.get_or_create(nombre_role='Administrador')
        self.admin = VGUsuario.objects.create_superuser(
            username='conc_admin', password='claveConc123', cedula='94000001', email='conc@test.test', id_role=rol,
        )
        # Dos espacios sobrantes a proposito: asi vienen de la base real ("Banco plaza natural   ").
        self.pm = VGMetodoPago.objects.create(nombre='PM Prueba', moneda='VES', cuenta_bancaria='Banco Prueba  ')
        self.pos = VGMetodoPago.objects.create(nombre='POS Prueba', moneda='VES', cuenta_bancaria='Banco Prueba', es_punto_venta=True)
        self.cat = VGCategoriaGasto.objects.get_or_create(nombre='Servicios')[0]
        self.cat_comision = VGCategoriaGasto.objects.get_or_create(nombre='comision')[0]
        self.extracto = VGExtractoBancario.objects.create(cuenta_bancaria=self.CUENTA)
        self.n = 0

    # ---- ayudantes
    def dt(self, dia, hora=12):
        return timezone.make_aware(datetime(2026, 10, dia, hora, 0))

    def mov(self, tipo, monto, ref='', desc='', dia=5, clase=None, obs=''):
        from varagrill.banco_excel import clasificar
        self.n += 1
        return self.M.Mov.objects.create(
            extracto=self.extracto, cuenta_bancaria=self.CUENTA, fecha=self.dt(dia), referencia=ref,
            descripcion=desc, tipo=tipo, monto=Decimal(monto), observacion=obs,
            clase=clase or clasificar(desc, tipo), huella=f'h{self.n}',
        )

    def pago(self, bs, ref='', dia=5, metodo=None):
        pedido = VGPedido.objects.create(usuario=self.admin, tipo_pedido='llevar', estado='pagado', subtotal=Decimal('1'), total=Decimal('1'))
        p = VGPago.objects.create(
            pedido=pedido, monto=Decimal(bs) / Decimal('100'), metodo_pago=metodo or self.pm, estado='completado',
            tasa_cambio_referencia=Decimal('100'), referencia=ref,
        )
        VGPago.objects.filter(pk=p.pk).update(fecha_pago=self.dt(dia))
        return p

    def gasto(self, bs, comprobante='', descripcion='Flete', dia=5, categoria=None, proveedor=''):
        g = self.M.Gasto.objects.create(
            categoria=categoria or self.cat, descripcion=descripcion, proveedor_nombre=proveedor, numero_comprobante=comprobante,
            monto=Decimal(bs) / Decimal('100'), saldo_pendiente=0, estado_pago='pagado',
            fecha_gasto=date(2026, 10, dia), tasa_cambio_referencia=Decimal('100'),
        )
        a = self.M.AbonoGasto.objects.create(gasto=g, monto=g.monto, metodo_pago=self.pm, tasa_cambio_referencia=Decimal('100'))
        self.M.AbonoGasto.objects.filter(pk=a.pk).update(fecha_pago=self.dt(dia))
        return g, a

    def conciliar(self, desde=1, hasta=31):
        from varagrill import conciliacion_bancaria as motor
        return motor.conciliar(self.CUENTA, date(2026, 10, desde), date(2026, 10, hasta), self.admin)

    # ---- importacion
    def test_importar_omite_lo_ya_cargado_aunque_los_archivos_se_solapen(self):
        from varagrill import conciliacion_bancaria as motor
        from varagrill.banco_excel import parsear_extracto
        dia1 = ['01/10/2026 10:00:00', '1', 'COMPRA MAESTRO', 'Débito', '-100,00', '900,00', '']
        dia2 = ['02/10/2026 10:00:00', '2', 'COMPRA MAESTRO', 'Débito', '-50,00', '850,00', '']
        primero = parsear_extracto(_xlsx_bytes([('d', [ENCABEZADO_BANCO, dia1])]), 'dia1.xlsx')
        mes = parsear_extracto(_xlsx_bytes([('d', [ENCABEZADO_BANCO, dia1, dia2])]), 'mes.xlsx')
        e1 = motor.importar_extracto('Banco Prueba ', primero, 'dia1.xlsx', self.admin)
        e2 = motor.importar_extracto(self.CUENTA, mes, 'mes.xlsx', self.admin)
        self.assertEqual((e1.movimientos_nuevos, e2.movimientos_nuevos, e2.duplicados_omitidos), (1, 1, 1))
        self.assertEqual(self.M.Mov.objects.filter(cuenta_bancaria=self.CUENTA).count(), 2)

    def test_una_cuenta_en_dolares_no_se_puede_conciliar_todavia(self):
        from varagrill import conciliacion_bancaria as motor
        VGMetodoPago.objects.create(nombre='Zelle Prueba', moneda='USD', cuenta_bancaria='Banco USD')
        cuentas = {c['nombre']: c for c in motor.cuentas_disponibles()}
        self.assertTrue(cuentas['Banco Prueba']['soportada'])
        self.assertFalse(cuentas['Banco USD']['soportada'])
        with self.assertRaises(motor.CuentaNoSoportada):
            motor.conciliar('Banco USD', date(2026, 10, 1), date(2026, 10, 31), self.admin)

    # ---- creditos
    def test_credito_con_sufijo_de_referencia_y_monto_casi_igual_se_concilia_solo(self):
        m = self.mov('credito', '5000.00', ref='000123456', desc='TDY RECIB DE VZLA 4245940617')
        p = self.pago('5000.90', ref='3456')  # 90 centimos de diferencia por el redondeo de la tasa
        self.assertEqual(self.conciliar()['conciliado'], 1)
        m.refresh_from_db()
        v = m.vinculos.get()
        self.assertEqual((m.estado, v.estado, v.metodo, v.origen_tipo, v.origen_id), ('conciliado', 'confirmado', 'referencia', 'pago', p.id))
        self.assertEqual(v.diferencia, Decimal('0.90'))

    def test_credito_con_monto_exacto_sin_referencia_se_sugiere_y_se_confirma_a_mano(self):
        from varagrill import conciliacion_bancaria as motor
        m = self.mov('credito', '1234.50', ref='999', desc='TDY RECIB DE VZLA 4245940617')
        p = self.pago('1234.50', ref='')
        self.assertEqual(self.conciliar()['por_revisar'], 1)
        m.refresh_from_db()
        v = m.vinculos.get()
        self.assertEqual((m.estado, v.estado, v.metodo), ('por_revisar', 'sugerido', 'monto_fecha'))
        motor.confirmar_vinculo(v, self.admin)
        m.refresh_from_db()
        self.assertEqual(m.estado, 'conciliado')
        # el mismo pago no puede conciliar otro movimiento
        otro = self.mov('credito', '1234.50', ref='888', desc='TDY RECIB DE VZLA 4141111111', dia=6)
        self.assertEqual(self.conciliar()['sin_coincidencia'], 1)
        otro.refresh_from_db()
        self.assertEqual(otro.estado, 'sin_coincidencia')
        self.assertEqual(p.id, v.origen_id)

    def test_credito_sin_ningun_registro_queda_sin_coincidencia(self):
        m = self.mov('credito', '777.00', ref='1', desc='TRF BANESC V020657311 HAMADE D')
        self.pago('99999.00', ref='5555')
        self.assertEqual(self.conciliar(), {'sin_coincidencia': 1})
        m.refresh_from_db()
        self.assertEqual(m.estado, 'sin_coincidencia')

    # ---- debitos
    def test_debito_con_la_referencia_del_comprobante_del_gasto_se_concilia_solo(self):
        m = self.mov('debito', '5000.00', ref='000025559', desc='TRF PROVIN V020040168 ALFREDO')
        g, a = self.gasto('5000.00', comprobante='000025559')
        self.assertEqual(self.conciliar()['conciliado'], 1)
        v = m.vinculos.get()
        self.assertEqual((v.origen_tipo, v.origen_id, v.metodo, v.estado), ('abono_gasto', a.id, 'referencia', 'confirmado'))

    def test_referencia_que_coincide_con_un_monto_muy_distinto_avisa_de_un_posible_error_de_captura(self):
        m = self.mov('debito', '737185.40', ref='000025559', desc='TRF B.PLUS J506500175')
        self.gasto('32643.80', comprobante='000025559')
        self.assertEqual(self.conciliar()['por_revisar'], 1)
        v = m.vinculos.get()
        self.assertEqual((v.estado, v.puntaje), ('sugerido', 60))
        self.assertIn('difiere', v.nota)

    def test_debito_sin_referencia_se_sugiere_por_monto_y_nombre_del_proveedor(self):
        c = self.M.Compra.objects.create(proveedor_nombre='Despacho Alfredo', estado='recibido', total=Decimal('80'), saldo_pendiente=0)
        a = self.M.AbonoCompra.objects.create(compra=c, monto=Decimal('80'), metodo_pago=self.pm, tasa_cambio_referencia=Decimal('100'))
        self.M.AbonoCompra.objects.filter(pk=a.pk).update(fecha_pago=self.dt(5))
        m = self.mov('debito', '8000.00', ref='555', desc='TRF VZLA V030067809 X', obs='Despacho alfredo')
        self.assertEqual(self.conciliar()['por_revisar'], 1)
        v = m.vinculos.get()
        self.assertEqual((v.origen_tipo, v.origen_id, v.metodo, v.puntaje), ('abono_compra', a.id, 'monto_fecha', 90))

    def test_un_registro_solo_se_sugiere_a_un_movimiento(self):
        a = self.mov('debito', '3000.00', ref='1', desc='COMPRA MAESTRO', dia=5)
        b = self.mov('debito', '3000.00', ref='2', desc='COMPRA MAESTRO', dia=5)
        self.gasto('3000.00', descripcion='Hielo')
        self.assertEqual(self.conciliar(), {'por_revisar': 1, 'sin_coincidencia': 1})
        self.assertEqual(sorted(m.estado for m in self.M.Mov.objects.all()), ['por_revisar', 'sin_coincidencia'])

    def test_rechazar_una_sugerencia_no_la_vuelve_a_proponer(self):
        from varagrill import conciliacion_bancaria as motor
        m = self.mov('debito', '3000.00', ref='1', desc='COMPRA MAESTRO')
        self.gasto('3000.00', descripcion='Hielo')
        self.conciliar()
        motor.rechazar_vinculo(m.vinculos.get(estado='sugerido'), self.admin)
        m.refresh_from_db()
        self.assertEqual(m.estado, 'sin_coincidencia')
        self.assertFalse(m.vinculos.filter(estado='sugerido').exists())
        self.conciliar()  # correrlo otra vez tampoco lo reabre
        m.refresh_from_db()
        self.assertEqual(m.estado, 'sin_coincidencia')

    def test_elegir_a_mano_un_candidato_y_ver_los_candidatos(self):
        from varagrill import conciliacion_bancaria as motor
        m = self.mov('debito', '4000.00', ref='1', desc='COMPRA MAESTRO', dia=5)
        g, a = self.gasto('4300.00', descripcion='Carbon', dia=6)  # monto parecido (7%) pero no lo bastante para sugerirlo solo
        self.conciliar()
        self.assertEqual(self.M.Mov.objects.get(pk=m.pk).estado, 'sin_coincidencia')
        candidatos = motor.candidatos_para(m)
        self.assertEqual([(c.tipo, c.id) for c, _ in candidatos], [('abono_gasto', a.id)])
        motor.vincular_manual(m, 'abono_gasto', a.id, self.admin)
        m.refresh_from_db()
        v = m.vinculos.get()
        self.assertEqual((m.estado, v.estado, v.metodo), ('conciliado', 'confirmado', 'manual'))
        with self.assertRaises(motor.AccionInvalida):
            motor.vincular_manual(self.mov('debito', '4000.00', ref='2', desc='COMPRA MAESTRO', dia=6), 'abono_gasto', a.id, self.admin)

    def test_ignorar_pide_motivo_y_reabrir_lo_devuelve_al_cruce(self):
        from varagrill import conciliacion_bancaria as motor
        m = self.mov('debito', '123.00', ref='1', desc='OTRO CARGO')
        with self.assertRaises(motor.AccionInvalida):
            motor.ignorar_movimiento(m, '  ', self.admin)
        motor.ignorar_movimiento(m, 'Cargo del banco ya contabilizado', self.admin)
        self.assertEqual(self.conciliar(), {})  # lo ignorado no se cruza
        motor.reabrir_movimiento(m, self.admin)
        m.refresh_from_db()
        self.assertEqual(m.estado, 'sin_coincidencia')

    def test_confirmar_probables_en_bloque_solo_toma_las_sugerencias_sin_dudas(self):
        from varagrill import conciliacion_bancaria as motor
        limpio = self.mov('debito', '3000.00', ref='1', desc='COMPRA MAESTRO')
        self.gasto('3000.00', descripcion='Hielo')
        dudoso = self.mov('debito', '9000.00', ref='2', desc='COMPRA MAESTRO')
        self.gasto('9000.00', descripcion='Aceite A')
        self.gasto('9000.00', descripcion='Aceite B')  # dos registros con el mismo monto: hay que elegir
        self.conciliar()
        self.assertEqual(motor.confirmar_probables(self.CUENTA, date(2026, 10, 1), date(2026, 10, 31), self.admin), 1)
        limpio.refresh_from_db()
        dudoso.refresh_from_db()
        self.assertEqual((limpio.estado, dudoso.estado), ('conciliado', 'por_revisar'))

    # ---- comisiones, POS, reverso
    def test_las_comisiones_del_dia_se_comparan_en_suma_contra_el_gasto_de_comision(self):
        a = self.mov('debito', '10.00', ref='1', desc='COM TRF 019331385')
        b = self.mov('debito', '15.50', ref='2', desc='TDY COM.P2P BNC 4125486135')
        self.gasto('25.50', descripcion='comision bancaria', categoria=self.cat_comision)
        self.assertEqual(self.conciliar(), {'conciliado': 2})
        for m in (a, b):
            m.refresh_from_db()
            v = m.vinculos.get()
            self.assertEqual((m.estado, v.metodo, v.estado), ('conciliado', 'comision_dia', 'confirmado'))

    def test_comisiones_cuya_suma_no_coincide_van_a_revision_y_sin_gasto_quedan_sin_coincidencia(self):
        a = self.mov('debito', '10.00', ref='1', desc='COM TRF 019331385', dia=5)
        self.gasto('30.00', descripcion='comision bancaria', categoria=self.cat_comision, dia=5)
        b = self.mov('debito', '12.00', ref='2', desc='DOM POS DGL 88013794', dia=6)  # ese dia no hay gasto
        self.assertEqual(self.conciliar(), {'por_revisar': 1, 'sin_coincidencia': 1})
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual((a.estado, b.estado), ('por_revisar', 'sin_coincidencia'))
        self.assertIn('difiere', a.vinculos.get().nota)

    def test_el_pos_no_se_vincula_pero_se_compara_por_dia_de_acreditacion(self):
        from varagrill import conciliacion_bancaria as motor
        m = self.mov('credito', '990.00', ref='940100562', desc='POS MAE 88013794 001 0056 3009', dia=7)
        self.M.Lote.objects.create(
            numero=1, metodo_pago=self.pos, fecha_operacion=date(2026, 10, 6), estado='acreditado',
            fecha_abono_real=date(2026, 10, 7), monto_bruto_sistema_bs=Decimal('1000.00'),
        )
        self.assertEqual(self.conciliar(), {'pos': 1})
        m.refresh_from_db()
        self.assertEqual(m.estado, 'pendiente')
        fila = motor.resumen_pos(self.CUENTA, date(2026, 10, 1), date(2026, 10, 31))[0]
        self.assertEqual((fila['banco'], fila['sistema'], fila['diferencia'], fila['porcentaje']),
                         (Decimal('990.00'), Decimal('1000.00'), Decimal('-10.00'), Decimal('-1.00')))

    def test_registros_del_sistema_que_no_estan_en_el_banco(self):
        from varagrill import conciliacion_bancaria as motor
        self.mov('credito', '500.00', ref='4444', desc='TDY RECIB DE VZLA 4245940617')
        conciliado = self.pago('500.00', ref='4444')
        faltante = self.pago('777.00', ref='5555', dia=6)
        self.conciliar()
        filas = motor.registros_sin_movimiento(self.CUENTA, date(2026, 10, 1), date(2026, 10, 31))
        self.assertEqual([(f['sentido'], f['candidato'].id) for f in filas], [('credito', faltante.id)])
        self.assertNotIn(conciliado.id, [f['candidato'].id for f in filas])


class ConciliacionBancariaViewsTests(TestCase):
    """Permisos (solo administrador y contador), importacion por API, acciones y PDF."""

    BASE = '/api/admin/conciliacion-bancaria/'

    def setUp(self):
        for nombre in ('Administrador', 'Contador', 'Mesero', 'Cajera'):
            VGRol.objects.get_or_create(nombre_role=nombre)
        crear = lambda user, rol, ced: VGUsuario.objects.create_user(
            username=user, password='claveConc123', cedula=ced, email=f'{user}@test.test', id_role=VGRol.objects.get(nombre_role=rol),
        )
        self.admin = crear('vc_admin', 'Administrador', '93000001')
        self.contador = crear('vc_contador', 'Contador', '93000002')
        self.mesero = crear('vc_mesero', 'Mesero', '93000003')
        self.cajera = crear('vc_cajera', 'Cajera', '93000004')
        VGMetodoPago.objects.create(nombre='PM Vista', moneda='VES', cuenta_bancaria='Banco Vista')
        self.archivo = _xlsx_bytes([('01oct', [
            ENCABEZADO_BANCO,
            ['01/10/2026 10:00:00', '000111222', 'COMPRA MAESTRO', 'Débito', '-100,00', '900,00', 'hielo'],
            ['01/10/2026 11:00:00', '000111333', 'TDY RECIB DE VZLA 4245940617', 'Crédito', '250,00', '1.150,00', ''],
        ])])

    def subir(self, accion, usuario=None, cuenta='Banco Vista'):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.client.force_login(usuario or self.admin)
        return self.client.post(self.BASE + 'importar/', {
            'action': accion, 'cuenta': cuenta, 'archivo': SimpleUploadedFile('banco.xlsx', self.archivo),
        })

    def test_solo_administrador_y_contador_pueden_entrar(self):
        urls = [self.BASE + 'cuentas/', self.BASE + 'movimientos/?cuenta=Banco Vista&desde=2026-10-01&hasta=2026-10-31']
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 401)             # sin sesion
        for usuario in (self.mesero, self.cajera):
            self.client.force_login(usuario)
            for url in urls:
                self.assertEqual(self.client.get(url).status_code, 403, usuario.username)
            self.assertEqual(self.subir('preview', usuario).status_code, 403)
        for usuario in (self.admin, self.contador):
            self.client.force_login(usuario)
            self.assertEqual(self.client.get(urls[0]).status_code, 200, usuario.username)

    def test_la_vista_previa_no_guarda_y_la_confirmacion_si_y_no_duplica_al_repetir(self):
        r = self.subir('preview')
        self.assertEqual(r.status_code, 200, r.content)
        resumen = r.json()['resumen']
        self.assertEqual((resumen['leidos'], resumen['nuevos'], resumen['ya_cargados']), (2, 2, 0))
        self.assertEqual((resumen['debitos'], resumen['creditos']), ('100.00', '250.00'))
        self.assertEqual(VGMovimientoBancario.objects.count(), 0)

        r = self.subir('confirm')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(VGMovimientoBancario.objects.count(), 2)

        resumen = self.subir('preview').json()['resumen']
        self.assertEqual((resumen['nuevos'], resumen['ya_cargados']), (0, 2))
        self.subir('confirm')
        self.assertEqual(VGMovimientoBancario.objects.count(), 2)

    def test_cuenta_o_archivo_invalidos_dan_400(self):
        self.assertEqual(self.subir('preview', cuenta='No existe').status_code, 400)
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.client.force_login(self.admin)
        r = self.client.post(self.BASE + 'importar/', {'action': 'preview', 'cuenta': 'Banco Vista', 'archivo': SimpleUploadedFile('x.xlsx', b'basura')})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.client.post(self.BASE + 'importar/', {'action': 'preview', 'cuenta': 'Banco Vista'}).status_code, 400)

    def test_listar_movimientos_ignorar_y_reabrir_por_api(self):
        self.subir('confirm')
        url = self.BASE + 'movimientos/?cuenta=Banco Vista&desde=2026-10-01&hasta=2026-10-31'
        data = self.client.get(url).json()
        self.assertEqual(data['resumen']['total'], 2)
        self.assertEqual(data['resumen']['estados']['sin_coincidencia']['cantidad'], 2)
        mov = data['movimientos'][0]
        self.assertEqual((mov['clase'], mov['tipo'], mov['monto']), ('compra_tarjeta', 'debito', '100.00'))

        accion = self.BASE + f'movimientos/{mov["id"]}/accion/'
        r = self.client.post(accion, data=json.dumps({'accion': 'ignorar', 'motivo': ''}), content_type='application/json')
        self.assertEqual(r.status_code, 400)
        r = self.client.post(accion, data=json.dumps({'accion': 'ignorar', 'motivo': 'Cargo ya registrado'}), content_type='application/json')
        self.assertEqual(r.json()['movimiento']['estado'], 'ignorado')
        r = self.client.post(accion, data=json.dumps({'accion': 'reabrir'}), content_type='application/json')
        self.assertEqual(r.json()['movimiento']['estado'], 'sin_coincidencia')
        self.assertEqual(self.client.post(accion, data=json.dumps({'accion': 'volar'}), content_type='application/json').status_code, 400)
        mesero_url = self.BASE + 'movimientos/999999/accion/'
        self.assertEqual(self.client.post(mesero_url, data='{}', content_type='application/json').status_code, 404)

    def test_el_pdf_lo_descargan_solo_administrador_y_contador(self):
        self.subir('confirm')
        url = self.BASE + 'pdf/?cuenta=Banco Vista&desde=2026-10-01&hasta=2026-10-31'
        for usuario in (self.admin, self.contador):
            self.client.force_login(usuario)
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200, usuario.username)
            self.assertEqual(r['Content-Type'], 'application/pdf')
            self.assertTrue(r.content.startswith(b'%PDF'))
        self.client.force_login(self.mesero)
        self.assertIn(self.client.get(url).status_code, (401, 403))
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self.BASE + 'pdf/?cuenta=Banco Vista&desde=2026-10-31&hasta=2026-10-01').status_code, 400)


class ConciliacionCierreDiarioTests(TestCase):
    """Cierre diario de la conciliacion: la constancia de que el dia se reviso, con su foto de numeros y su bloqueo."""

    CUENTA = 'Banco Cierre'

    def setUp(self):
        from varagrill import conciliacion_bancaria as motor
        from varagrill.models import VGCierreConciliacion, VGExtractoBancario
        self.motor = motor
        self.Cierre = VGCierreConciliacion
        rol, _ = VGRol.objects.get_or_create(nombre_role='Administrador')
        self.admin = VGUsuario.objects.create_superuser(
            username='cierre_admin', password='claveCierre123', cedula='92000001', email='cierre@test.test', id_role=rol,
        )
        VGMetodoPago.objects.create(nombre='PM Cierre', moneda='VES', cuenta_bancaria='Banco Cierre')
        self.extracto = VGExtractoBancario.objects.create(cuenta_bancaria=self.CUENTA)
        self.n = 0

    def mov(self, dia, tipo='credito', monto='100.00', saldo=None, estado='conciliado', desc='TDY RECIB DE VZLA 4245940617', hora=12, clase=None):
        from varagrill.banco_excel import clasificar
        self.n += 1
        return VGMovimientoBancario.objects.create(
            extracto=self.extracto, cuenta_bancaria=self.CUENTA,
            fecha=timezone.make_aware(datetime(2026, 10, dia, hora, self.n % 60)), referencia=str(self.n), descripcion=desc,
            tipo=tipo, monto=Decimal(monto), saldo=Decimal(saldo) if saldo is not None else None,
            clase=clase or clasificar(desc, tipo), huella=f'c{self.n}', estado=estado,
        )

    def cerrar(self, dia, nota='', usuario=None):
        return self.motor.cerrar_dia(self.CUENTA, date(2026, 10, dia), nota, usuario or self.admin)

    # ---- reglas para cerrar
    def test_un_dia_con_movimientos_sin_resolver_no_se_puede_cerrar(self):
        self.mov(5, estado='conciliado')
        self.mov(5, estado='sin_coincidencia')
        self.mov(5, estado='por_revisar')
        with self.assertRaises(self.motor.AccionInvalida) as ctx:
            self.cerrar(5)
        self.assertIn('1 por revisar', str(ctx.exception))
        self.assertIn('1 sin coincidencia', str(ctx.exception))
        self.assertFalse(self.Cierre.objects.exists())

    def test_cierre_guarda_la_foto_del_dia_con_el_saldo_de_la_cadena(self):
        # las filas del archivo no vienen en orden: el saldo final sale de la cadena, no de la ultima fila
        self.mov(5, 'debito', '50.00', saldo='1050.00', desc='COMPRA MAESTRO')
        self.mov(5, 'credito', '25.00', saldo='1075.00')
        self.mov(5, 'credito', '100.00', saldo='1100.00', estado='conciliado')
        ignorado = self.mov(5, 'debito', '5.00', saldo='1070.00', estado='ignorado', desc='OTRO CARGO')
        VGMovimientoBancario.objects.filter(pk=ignorado.pk).update(saldo=Decimal('1070.00'))
        # cadena: 1000 -> +100 -> 1100 -> -50 -> 1050 -> +25 -> 1075 -> -5 -> 1070
        c = self.cerrar(5, usuario=self.admin)
        self.assertEqual((c.estado, c.movimientos_total, c.conciliados, c.ignorados), ('vigente', 4, 3, 1))
        self.assertEqual((c.creditos, c.debitos), (Decimal('125.00'), Decimal('55.00')))
        self.assertEqual((c.saldo_final_banco, c.saldo_inicial_banco), (Decimal('1070.00'), Decimal('1000.00')))
        self.assertEqual((c.saltos_saldo, c.creado_por), (0, self.admin))

    def test_el_pos_pendiente_no_impide_cerrar_el_dia(self):
        self.mov(5, estado='pendiente', desc='POS MAE 88013794 001 0056 3009', monto='990.00')
        c = self.cerrar(5)
        self.assertEqual((c.pendientes_pos, c.pos_banco), (1, Decimal('990.00')))

    def test_un_dia_sin_movimientos_solo_se_cierra_con_nota_y_no_se_cierra_el_futuro_ni_dos_veces(self):
        with self.assertRaises(self.motor.AccionInvalida):
            self.cerrar(5)
        c = self.cerrar(5, nota='Feriado, el banco no tuvo movimientos')
        self.assertEqual((c.movimientos_total, c.nota), (0, 'Feriado, el banco no tuvo movimientos'))
        with self.assertRaises(self.motor.AccionInvalida):
            self.cerrar(5, nota='otra vez')
        futuro = timezone.localdate() + timedelta(days=3)
        with self.assertRaises(self.motor.AccionInvalida):
            self.motor.cerrar_dia(self.CUENTA, futuro, 'x', self.admin)

    # ---- un dia cerrado queda bloqueado
    def test_un_dia_cerrado_no_admite_cambios_ni_cruces_ni_lineas_nuevas(self):
        from varagrill.banco_excel import parsear_extracto
        m = self.mov(5, estado='sin_coincidencia')
        self.motor.ignorar_movimiento(m, 'Cargo del banco', self.admin)
        self.cerrar(5)
        for accion in (
            lambda: self.motor.ignorar_movimiento(m, 'otro motivo', self.admin),
            lambda: self.motor.reabrir_movimiento(m, self.admin),
        ):
            with self.assertRaises(self.motor.AccionInvalida):
                accion()
        self.assertEqual(self.motor.conciliar(self.CUENTA, date(2026, 10, 1), date(2026, 10, 31), self.admin), {})

        # una linea nueva de ese dia en un archivo posterior NO se importa; las de otros dias si
        archivo = parsear_extracto(_xlsx_bytes([('d', [
            ENCABEZADO_BANCO,
            ['05/10/2026 18:00:00', '777', 'COMPRA MAESTRO', 'Débito', '-10,00', '90,00', ''],
            ['06/10/2026 18:00:00', '778', 'COMPRA MAESTRO', 'Débito', '-20,00', '70,00', ''],
        ])]), 'x.xlsx')
        self.assertEqual(self.motor.movimientos_en_dias_cerrados(self.CUENTA, archivo)['cantidad'], 1)
        extracto = self.motor.importar_extracto(self.CUENTA, archivo, 'x.xlsx', self.admin)
        self.assertEqual((extracto.movimientos_nuevos, extracto.omitidos_dia_cerrado), (1, 1))
        self.assertFalse(VGMovimientoBancario.objects.filter(referencia='777').exists())

    def test_reabrir_deja_historial_y_permite_volver_a_cerrar(self):
        c1 = self.cerrar(5, nota='Sin movimientos')
        with self.assertRaises(self.motor.AccionInvalida):
            self.motor.reabrir_cierre(c1, '  ', self.admin)
        self.motor.reabrir_cierre(c1, 'Faltaba una línea del banco', self.admin)
        c1.refresh_from_db()
        self.assertEqual((c1.estado, c1.reabierto_por, c1.motivo_reapertura), ('reabierto', self.admin, 'Faltaba una línea del banco'))
        self.assertIsNotNone(c1.fecha_reapertura)
        c2 = self.cerrar(5, nota='Ahora sí')
        self.assertEqual(self.Cierre.objects.filter(fecha=date(2026, 10, 5)).count(), 2)
        self.assertEqual(self.Cierre.objects.filter(fecha=date(2026, 10, 5), estado='vigente').get(), c2)
        with self.assertRaises(self.motor.AccionInvalida):
            self.motor.reabrir_cierre(c1, 'ya estaba reabierto', self.admin)

    # ---- continuidad del saldo entre dias
    def test_si_el_saldo_no_encadena_con_el_dia_anterior_hace_falta_una_nota(self):
        self.mov(5, 'credito', '100.00', saldo='1100.00')      # dia 5: abre en 1000, cierra en 1100
        self.cerrar(5)
        self.mov(6, 'debito', '50.00', saldo='1000.00', desc='COMPRA MAESTRO')   # abre en 1050: no cuadra con 1100
        with self.assertRaises(self.motor.AccionInvalida) as ctx:
            self.cerrar(6)
        self.assertIn('no encadena', str(ctx.exception))
        c = self.cerrar(6, nota='Falta una línea de Bs 50 en el archivo del banco')
        dias, resumen = self.motor.listar_cierres(self.CUENTA, date(2026, 10, 5), date(2026, 10, 6))
        self.assertEqual([d['continuidad'] for d in dias], [None, False])
        self.assertEqual((resumen['cerrados'], resumen['discontinuidades'], resumen['completo']), (2, 1, False))
        self.assertEqual(c.saldo_inicial_banco, Decimal('1050.00'))

    def test_dias_que_encadenan_dan_continuidad_y_el_periodo_queda_completo(self):
        self.mov(5, 'credito', '100.00', saldo='1100.00')
        self.mov(6, 'debito', '50.00', saldo='1050.00', desc='COMPRA MAESTRO')
        self.cerrar(5)
        self.cerrar(6)
        dias, resumen = self.motor.listar_cierres(self.CUENTA, date(2026, 10, 5), date(2026, 10, 6))
        self.assertEqual([d['continuidad'] for d in dias], [None, True])
        self.assertTrue(resumen['completo'])
        self.assertEqual((resumen['creditos_cerrados'], resumen['debitos_cerrados']), (Decimal('100.00'), Decimal('50.00')))

    def test_listar_cierres_distingue_cerrado_pendiente_listo_y_sin_movimientos(self):
        self.mov(5)                                  # listo para cerrar
        self.mov(6, estado='sin_coincidencia')       # pendiente
        self.mov(7)                                  # se cierra
        self.cerrar(7)
        dias, resumen = self.motor.listar_cierres(self.CUENTA, date(2026, 10, 5), date(2026, 10, 8))
        self.assertEqual([d['estado'] for d in dias], ['listo', 'pendiente', 'cerrado', 'sin_movimientos'])
        self.assertEqual((resumen['cerrados'], resumen['pendientes'], resumen['listos'], resumen['sin_movimientos']), (1, 1, 1, 1))
        self.assertFalse(resumen['completo'])


class ConciliacionCierreDiarioViewsTests(TestCase):
    """API de cierres: solo administrador y contador, exige confirmar la revision y bloquea los dias cerrados."""

    BASE = '/api/admin/conciliacion-bancaria/'

    def setUp(self):
        for nombre in ('Administrador', 'Contador', 'Mesero'):
            VGRol.objects.get_or_create(nombre_role=nombre)
        crear = lambda user, rol, ced: VGUsuario.objects.create_user(
            username=user, password='claveCierre123', cedula=ced, email=f'{user}@test.test', id_role=VGRol.objects.get(nombre_role=rol),
        )
        self.contador = crear('cv_contador', 'Contador', '91000001')
        self.mesero = crear('cv_mesero', 'Mesero', '91000002')
        VGMetodoPago.objects.create(nombre='PM Cierre V', moneda='VES', cuenta_bancaria='Banco Cierre V')
        from varagrill.models import VGExtractoBancario
        extracto = VGExtractoBancario.objects.create(cuenta_bancaria='Banco Cierre V')
        self.mov = VGMovimientoBancario.objects.create(
            extracto=extracto, cuenta_bancaria='Banco Cierre V', fecha=timezone.make_aware(datetime(2026, 10, 5, 12, 0)),
            referencia='1', descripcion='COMPRA MAESTRO', tipo='debito', monto=Decimal('40.00'), saldo=Decimal('960.00'),
            clase='compra_tarjeta', huella='v1', estado='sin_coincidencia',
        )

    def post(self, ruta, cuerpo):
        return self.client.post(self.BASE + ruta, data=json.dumps(cuerpo), content_type='application/json')

    def test_solo_administrador_y_contador(self):
        url = self.BASE + 'cierres/?cuenta=Banco Cierre V&desde=2026-10-05&hasta=2026-10-05'
        self.assertEqual(self.client.get(url).status_code, 401)
        self.client.force_login(self.mesero)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.post('cierres/cerrar/', {}).status_code, 403)
        self.client.force_login(self.contador)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_cerrar_exige_confirmar_resolver_los_pendientes_y_luego_bloquea_el_dia(self):
        self.client.force_login(self.contador)
        base = {'cuenta': 'Banco Cierre V', 'fecha': '2026-10-05', 'nota': ''}
        self.assertEqual(self.post('cierres/cerrar/', base).status_code, 400)                  # falta confirmar la revision
        r = self.post('cierres/cerrar/', {**base, 'confirmo': True})
        self.assertEqual(r.status_code, 400)                                                    # queda uno sin coincidencia
        self.assertIn('sin coincidencia', r.json()['message'])

        accion = self.BASE + f'movimientos/{self.mov.id}/accion/'
        r = self.client.post(accion, data=json.dumps({'accion': 'ignorar', 'motivo': 'Cargo ya contabilizado'}), content_type='application/json')
        self.assertEqual(r.status_code, 200)
        r = self.post('cierres/cerrar/', {**base, 'confirmo': True})
        self.assertEqual(r.status_code, 201, r.content)
        dia = r.json()['dia']
        self.assertEqual((dia['estado'], dia['cierre']['movimientos_total'], dia['cierre']['saldo_final_banco']), ('cerrado', 1, '960.00'))
        self.assertEqual(dia['cierre']['cerrado_por'], 'cv_contador')

        # el movimiento ahora esta bloqueado
        r = self.client.post(accion, data=json.dumps({'accion': 'reabrir'}), content_type='application/json')
        self.assertEqual(r.status_code, 400)
        movs = self.client.get(self.BASE + 'movimientos/?cuenta=Banco Cierre V&desde=2026-10-01&hasta=2026-10-31').json()['movimientos']
        self.assertTrue(movs[0]['dia_cerrado'])

        # reabrir el cierre (con motivo) lo desbloquea
        cierre_id = dia['cierre']['id']
        self.assertEqual(self.post(f'cierres/{cierre_id}/reabrir/', {'motivo': ''}).status_code, 400)
        r = self.post(f'cierres/{cierre_id}/reabrir/', {'motivo': 'Falta una línea'})
        self.assertEqual((r.status_code, r.json()['dia']['estado']), (200, 'listo'))
        r = self.client.post(accion, data=json.dumps({'accion': 'reabrir'}), content_type='application/json')
        self.assertEqual(r.status_code, 200)

    def test_el_listado_de_cierres_y_el_pdf_incluyen_el_estado_de_cada_dia(self):
        self.client.force_login(self.contador)
        data = self.client.get(self.BASE + 'cierres/?cuenta=Banco Cierre V&desde=2026-10-05&hasta=2026-10-06').json()
        self.assertEqual([d['estado'] for d in data['dias']], ['pendiente', 'sin_movimientos'])
        self.assertEqual((data['resumen']['dias'], data['resumen']['cerrados'], data['resumen']['completo']), (2, 0, False))
        r = self.client.get(self.BASE + 'pdf/?cuenta=Banco Cierre V&desde=2026-10-05&hasta=2026-10-06&conciliados=0')
        self.assertEqual((r.status_code, r.content[:4]), (200, b'%PDF'))


class LotePosIdReporteTests(TestCase):
    """ID del reporte detallado del punto en el lote POS, y como une los creditos del banco con su lote."""

    CUENTA = 'Banco Lote'

    def setUp(self):
        from varagrill import conciliacion_bancaria as motor
        from varagrill import lotes_pos
        from varagrill.models import VGExtractoBancario
        self.motor, self.lotes_pos = motor, lotes_pos
        rol, _ = VGRol.objects.get_or_create(nombre_role='Administrador')
        self.admin = VGUsuario.objects.create_superuser(
            username='lote_admin', password='claveLote123', cedula='90000001', email='lote@test.test', id_role=rol,
        )
        self.pos = VGMetodoPago.objects.create(nombre='POS Lote', moneda='VES', cuenta_bancaria='Banco Lote', es_punto_venta=True)
        self.pos2 = VGMetodoPago.objects.create(nombre='POS Lote 2', moneda='VES', cuenta_bancaria='Banco Lote', es_punto_venta=True)
        VGMetodoPago.objects.create(nombre='PM Lote', moneda='VES', cuenta_bancaria='Banco Lote')
        self.extracto = VGExtractoBancario.objects.create(cuenta_bancaria=self.CUENTA)
        self.n = 0

    def lote(self, numero, bs, estado='cerrado', id_reporte='', metodo=None):
        return VGLotePOS.objects.create(
            numero=numero, metodo_pago=metodo or self.pos, estado=estado, fecha_operacion=date(2026, 9, 30),
            monto_bruto_sistema_bs=Decimal(bs), id_reporte_punto=id_reporte,
        )

    def credito(self, monto, desc='POS MAE 88013794 001 0061 3009', dia=6):
        self.n += 1
        return VGMovimientoBancario.objects.create(
            extracto=self.extracto, cuenta_bancaria=self.CUENTA, fecha=timezone.make_aware(datetime(2026, 10, dia, 8, 0)),
            referencia=str(self.n), descripcion=desc, tipo='credito', monto=Decimal(monto), clase='pos', huella=f'l{self.n}',
        )

    def conciliar(self):
        return self.motor.conciliar(self.CUENTA, date(2026, 10, 1), date(2026, 10, 31), self.admin)

    # ---- el campo en el lote
    def test_registrar_el_id_lo_normaliza_lo_anota_y_se_puede_corregir_o_borrar(self):
        lote = self.lote(1, '1000.00')
        lote = self.lotes_pos.registrar_id_reporte(lote, '  00 61 ', self.admin)
        self.assertEqual(lote.id_reporte_punto, '0061')
        self.assertIn('ID del reporte del punto: 0061', lote.notas)
        lote = self.lotes_pos.registrar_id_reporte(lote, '0062', self.admin)       # corregir
        self.assertEqual(lote.id_reporte_punto, '0062')
        lote = self.lotes_pos.registrar_id_reporte(lote, '', self.admin)           # borrar
        self.assertEqual(lote.id_reporte_punto, '')
        with self.assertRaises(self.lotes_pos.LoteError):
            self.lotes_pos.registrar_id_reporte(lote, 'no vale!', self.admin)

    def test_se_puede_registrar_en_un_lote_acreditado_pero_no_en_uno_anulado(self):
        acreditado = self.lote(1, '1000.00', estado='acreditado')
        self.assertEqual(self.lotes_pos.registrar_id_reporte(acreditado, '55', self.admin).id_reporte_punto, '55')
        anulado = self.lote(2, '1000.00', estado='anulado')
        with self.assertRaises(self.lotes_pos.LoteError):
            self.lotes_pos.registrar_id_reporte(anulado, '56', self.admin)

    def test_el_mismo_id_no_se_repite_en_un_metodo_pero_si_entre_metodos_del_mismo_banco(self):
        self.lote(1, '1000.00', id_reporte='0061')
        otro = self.lote(2, '500.00')
        with self.assertRaises(self.lotes_pos.LoteError) as ctx:
            self.lotes_pos.registrar_id_reporte(otro, '61', self.admin)          # '61' y '0061' son el mismo ID
        self.assertIn('#1', str(ctx.exception))
        de_otro_metodo = self.lote(3, '500.00', metodo=self.pos2)
        self.assertEqual(self.lotes_pos.registrar_id_reporte(de_otro_metodo, '0061', self.admin).id_reporte_punto, '0061')

    def test_cerrar_un_lote_puede_guardar_el_id_de_una_vez(self):
        pedido = VGPedido.objects.create(usuario=self.admin, tipo_pedido='llevar', estado='pagado', subtotal=Decimal('1'), total=Decimal('1'))
        pago = VGPago.objects.create(
            pedido=pedido, monto=Decimal('10'), metodo_pago=self.pos, estado='completado', tasa_cambio_referencia=Decimal('100'),
        )
        lote = self.lotes_pos.asignar_pago_a_lote(pago, self.admin)
        lote = self.lotes_pos.cerrar_lote(lote, self.admin, id_reporte='0061')
        self.assertEqual((lote.estado, lote.id_reporte_punto), ('cerrado', '0061'))

    def test_la_api_de_lotes_registra_y_devuelve_el_id_solo_a_cajera_y_administrador(self):
        for nombre in ('Cajera', 'Mesero'):
            VGRol.objects.get_or_create(nombre_role=nombre)
        cajera = VGUsuario.objects.create_user(
            username='lote_cajera', password='claveLote123', cedula='90000002', email='lc@test.test', id_role=VGRol.objects.get(nombre_role='Cajera'),
        )
        mesero = VGUsuario.objects.create_user(
            username='lote_mesero', password='claveLote123', cedula='90000003', email='lm@test.test', id_role=VGRol.objects.get(nombre_role='Mesero'),
        )
        lote = self.lote(1, '1000.00')
        cuerpo = json.dumps({'action': 'registrar_id_reporte', 'lote_id': lote.id, 'id_reporte_punto': '0061'})
        self.client.force_login(mesero)
        self.assertEqual(self.client.post('/api/admin/lotes-pos/', data=cuerpo, content_type='application/json').status_code, 401)
        self.client.force_login(cajera)
        r = self.client.post('/api/admin/lotes-pos/', data=cuerpo, content_type='application/json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()['lote']['id_reporte_punto'], '0061')
        listado = self.client.get('/api/admin/lotes-pos/?desde=2026-10-01&hasta=2026-10-31').json()
        self.assertEqual(listado['lotes'][0]['id_reporte_punto'], '0061')
        repetido = self.lote(2, '300.00')
        r = self.client.post('/api/admin/lotes-pos/', data=json.dumps({'action': 'registrar_id_reporte', 'lote_id': repetido.id, 'id_reporte_punto': '61'}), content_type='application/json')
        self.assertEqual(r.status_code, 400)

    # ---- conciliacion de los creditos POS por ese ID
    def test_los_creditos_con_el_id_del_lote_se_suman_y_se_concilian(self):
        lote = self.lote(1, '1000.00', id_reporte='0061')
        a = self.credito('600.00', 'POS MAE 88013794 001 0061 3009')
        b = self.credito('395.00', 'POS CRE 88013794 001 0061 3009')   # el banco lo acredito en dos partes
        self.assertEqual(self.conciliar(), {'conciliado': 2})
        for m in (a, b):
            m.refresh_from_db()
            v = m.vinculos.get()
            self.assertEqual((m.estado, v.origen_tipo, v.origen_id, v.metodo, v.estado), ('conciliado', 'lote_pos', lote.id, 'id_reporte', 'confirmado'))
            self.assertEqual((v.monto_sistema, v.diferencia), (Decimal('1000.00'), Decimal('5.00')))

    def test_el_id_con_ceros_o_sin_ceros_es_el_mismo(self):
        self.lote(1, '1000.00', id_reporte='61')
        m = self.credito('1000.00', 'POS MAE 88013794 001 0061 3009')
        self.assertEqual(self.conciliar(), {'conciliado': 1})
        m.refresh_from_db()
        self.assertEqual(m.estado, 'conciliado')

    def test_si_falta_un_credito_queda_por_revisar_con_la_diferencia_y_al_llegar_se_concilia(self):
        self.lote(1, '1000.00', id_reporte='0061')
        a = self.credito('600.00', 'POS MAE 88013794 001 0061 3009')
        self.assertEqual(self.conciliar(), {'por_revisar': 1})
        a.refresh_from_db()
        v = a.vinculos.get()
        self.assertEqual((a.estado, v.estado, v.diferencia), ('por_revisar', 'sugerido', Decimal('400.00')))
        self.assertIn('Diferencia', v.nota)
        b = self.credito('395.00', 'POS CRE 88013794 001 0061 3009', dia=7)   # llega despues
        self.assertEqual(self.conciliar(), {'conciliado': 2})
        for m in (a, b):
            m.refresh_from_db()
            self.assertEqual(m.estado, 'conciliado')

    def test_el_mismo_id_en_otra_fecha_no_se_toma_por_bueno_se_sugiere_con_aviso(self):
        # El punto repite numeros en dias distintos ("0061 0110" y "0061 0310"): el ID solo no basta.
        self.lote(1, '1000.00', id_reporte='0061')                       # lote del 30/09
        m = self.credito('1000.00', 'POS MAE 88013794 001 0061 0310')    # reporte del 03/10
        self.assertEqual(self.conciliar(), {'por_revisar': 1})
        m.refresh_from_db()
        v = m.vinculos.get()
        self.assertEqual((m.estado, v.estado, v.puntaje), ('por_revisar', 'sugerido', 40))
        self.assertIn('fecha del reporte no coincide', v.nota)

    def test_dos_reportes_con_el_mismo_id_en_fechas_distintas_van_a_su_propio_lote(self):
        primero = self.lote(1, '1000.00', id_reporte='0061')                       # 30/09
        segundo = VGLotePOS.objects.create(
            numero=2, metodo_pago=self.pos2, estado='cerrado', fecha_operacion=date(2026, 10, 3),
            monto_bruto_sistema_bs=Decimal('500.00'), id_reporte_punto='0061',
        )
        a = self.credito('1000.00', 'POS MAE 88013794 001 0061 3009')
        b = self.credito('500.00', 'POS MAE 88013794 001 0061 0310')
        self.assertEqual(self.conciliar(), {'conciliado': 2})
        self.assertEqual((a.vinculos.get().origen_id, b.vinculos.get().origen_id), (primero.id, segundo.id))

    def test_confirmar_un_credito_confirma_a_los_demas_del_mismo_reporte(self):
        self.lote(1, '1000.00', id_reporte='0061')
        a = self.credito('600.00', 'POS MAE 88013794 001 0061 3009')
        b = self.credito('200.00', 'POS CRE 88013794 001 0061 3009')
        self.conciliar()                                                 # suma 800 de 1000: por revisar los dos
        self.motor.confirmar_vinculo(a.vinculos.get(), self.admin)
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual((a.estado, b.estado), ('conciliado', 'conciliado'))

    def test_sin_lote_con_ese_id_o_con_el_lote_abierto_el_credito_sigue_pendiente(self):
        self.lote(1, '1000.00', id_reporte='0070')                        # otro ID
        self.lote(2, '1000.00', estado='abierto', id_reporte='0061')      # abierto: aun no es lo que cerro el punto
        m = self.credito('1000.00', 'POS MAE 88013794 001 0061 3009')
        self.assertEqual(self.conciliar(), {'pos': 1})
        m.refresh_from_db()
        self.assertEqual(m.estado, 'pendiente')

    def test_un_lote_de_otra_cuenta_no_se_toma(self):
        otro = VGMetodoPago.objects.create(nombre='POS Otro Banco', moneda='VES', cuenta_bancaria='Otro Banco', es_punto_venta=True)
        self.lote(1, '1000.00', id_reporte='0061', metodo=otro)
        m = self.credito('1000.00', 'POS MAE 88013794 001 0061 3009')
        self.assertEqual(self.conciliar(), {'pos': 1})
        m.refresh_from_db()
        self.assertEqual(m.estado, 'pendiente')

    def test_rechazar_la_sugerencia_no_la_repite(self):
        self.lote(1, '1000.00', id_reporte='0061')
        m = self.credito('600.00', 'POS MAE 88013794 001 0061 3009')
        self.conciliar()
        self.motor.rechazar_vinculo(m.vinculos.get(estado='sugerido'), self.admin)
        m.refresh_from_db()
        self.assertEqual(m.estado, 'pendiente')
        self.assertFalse(m.vinculos.filter(estado='sugerido').exists())
