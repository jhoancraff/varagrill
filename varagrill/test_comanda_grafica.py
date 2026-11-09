from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from varagrill.comanda_grafica import dibujar_comanda
from varagrill.impresion_termica import (
    BUZZER_ALT,
    CASH_DRAWER_KICK,
    CUT,
    _bloques_comanda,
    _build_ticket_bytes,
    _build_ticket_secundario_bytes,
    _collect_print_items,
    _datos_comanda,
    imprimir_comandas_pedido,
)
from varagrill.models import (
    VGCategoriaProducto, VGDetallePedido, VGDetallePedidoOpcion, VGMesa, VGPedido, VGProducto, VGRol, VGUsuario,
)

RASTER = b'\x1dv0'


class ComandaBase(TestCase):
    def setUp(self):
        rol, _ = VGRol.objects.get_or_create(nombre_role='Mesero')
        self.mesero = VGUsuario.objects.create_user(
            username='carlos', password='claveMesero123', cedula='97000001', email='carlos@varagrill.test', id_role=rol,
        )
        self.cocina = VGCategoriaProducto.objects.create(nombre='Cocina CG', ip_impresora='192.168.9.10', puerto_impresora=9100)
        self.parrilla = VGCategoriaProducto.objects.create(
            nombre='Parrilla CG', ip_impresora='192.168.9.11', puerto_impresora=9100,
            ip_impresora_secundaria='192.168.9.12', puerto_impresora_secundaria=9100,
        )
        self.yuca = VGProducto.objects.create(nombre='Yuca al vapor', categoria=self.cocina, precio_venta='3.00', disponible=True)
        self.tequenos = VGProducto.objects.create(nombre='Tequeños', categoria=self.cocina, precio_venta='5.00', disponible=True)
        self.punta = VGProducto.objects.create(
            nombre='Punta trasera', categoria=self.parrilla, precio_venta='6.50', disponible=True, venta_por_peso=True,
        )

    def pedido(self, tipo='local', mesa=7, notas=''):
        mesa_obj = VGMesa.objects.get_or_create(numero=mesa)[0] if mesa else None
        return VGPedido.objects.create(
            usuario=self.mesero, mesa=mesa_obj, tipo_pedido=tipo, estado='pendiente', subtotal='10', total='10', notas=notas,
        )

    def detalle(self, pedido, producto, cantidad=1, **extra):
        return VGDetallePedido.objects.create(
            pedido=pedido, producto=producto, cantidad=cantidad, precio_unitario=producto.precio_venta, estado='pendiente', **extra,
        )

    def items(self, pedido):
        detalles = list(
            pedido.detalles.select_related('producto__categoria')
            .prefetch_related('adicionales__preparacion', 'opciones__preparacion', 'opciones__producto__categoria')
        )
        return _collect_print_items(detalles), detalles


class DatosDeLaComandaTests(ComandaBase):
    def test_una_mesa_local_trae_titulo_de_mesa_y_sin_barra_de_tipo(self):
        pedido = self.pedido()
        datos = _datos_comanda(pedido, 'COCINA CG', [])
        self.assertEqual(datos['titulo'], 'MESA 7')
        self.assertEqual(datos['tipo'], '')
        self.assertEqual(datos['mesero'], 'carlos')
        self.assertEqual(datos['cliente'], 'Consumidor Final')
        self.assertEqual(datos['pedido'], pedido.id)

    def test_un_delivery_sin_mesa_muestra_el_tipo_y_el_cliente_en_grande(self):
        from varagrill.models import VGCliente
        pedido = self.pedido(tipo='delivery', mesa=None)
        pedido.cliente = VGCliente.objects.create(tipo_documento='V', numero_documento='111', nombre='Luis Gómez')
        pedido.save()
        datos = _datos_comanda(pedido, 'BARRA', [])
        self.assertEqual(datos['titulo'], 'DELIVERY')
        self.assertEqual(datos['cliente_grande'], 'Luis Gómez')
        self.assertEqual(datos['cliente'], '')

    def test_para_llevar_sin_mesa_y_local_sin_mesa(self):
        self.assertEqual(_datos_comanda(self.pedido(tipo='llevar', mesa=None), 'X', [])['titulo'], 'PARA LLEVAR')
        self.assertEqual(_datos_comanda(self.pedido(tipo='local', mesa=None), 'X', [])['titulo'], 'SIN MESA')

    def test_una_mesa_de_llevar_lleva_la_barra_de_tipo(self):
        self.assertEqual(_datos_comanda(self.pedido(tipo='llevar'), 'X', [])['tipo'], 'PARA LLEVAR')

    def test_delivery_y_para_llevar_siempre_quedan_escritos_en_la_comanda(self):
        # Con mesa (barra de tipo) o sin mesa (titulo grande): la comanda nunca omite el tipo de pedido.
        for tipo, rotulo in (('delivery', 'DELIVERY'), ('llevar', 'PARA LLEVAR')):
            for mesa in (7, None):
                datos = _datos_comanda(self.pedido(tipo=tipo, mesa=mesa), 'X', [])
                self.assertIn(rotulo, (datos['titulo'], datos.get('tipo')), (tipo, mesa))

    def test_la_nota_del_pedido_viaja_en_los_datos(self):
        self.assertEqual(_datos_comanda(self.pedido(notas='Entregar frío'), 'X', [])['nota_pedido'], 'Entregar frío')


class BloquesDeLaComandaTests(ComandaBase):
    def test_lo_repetido_se_consolida_en_una_sola_linea_con_su_cantidad(self):
        pedido = self.pedido()
        for _ in range(4):
            self.detalle(pedido, self.yuca)
        items, _ = self.items(pedido)
        bloques = _bloques_comanda(items)
        self.assertEqual(len(bloques), 1)
        self.assertEqual([(l['cantidad'], l['nombre']) for l in bloques[0]['lineas']], [('4x', 'Yuca al vapor')])

    def test_un_producto_por_peso_muestra_los_gramos(self):
        pedido = self.pedido()
        self.detalle(pedido, self.punta, peso_gramos='350')
        items, _ = self.items(pedido)
        linea = _bloques_comanda(items)[0]['lineas'][0]
        self.assertEqual((linea['cantidad'], linea['nombre']), ('350 g', 'Punta trasera'))

    def test_la_nota_del_item_y_las_opciones_curadas_van_en_su_linea(self):
        from varagrill.models import VGPreparacion
        pedido = self.pedido()
        detalle = self.detalle(pedido, self.yuca, notas='sin sal')
        preparacion = VGPreparacion.objects.create(nombre='Salsa rosada', rendimiento_cantidad='1000', rendimiento_unidad='g')
        VGDetallePedidoOpcion.objects.create(detalle_pedido=detalle, grupo_nombre='Aderezo', preparacion=preparacion, precio_unitario=0)
        items, _ = self.items(pedido)
        linea = _bloques_comanda(items)[0]['lineas'][0]
        self.assertEqual(linea['nota'], 'sin sal')
        self.assertEqual(linea['opciones'], ['Aderezo: Salsa rosada'])

    def test_un_plato_armado_con_varias_lineas_lleva_su_barra(self):
        pedido = self.pedido()
        self.detalle(pedido, self.yuca, grupo_armado=2)
        self.detalle(pedido, self.tequenos, grupo_armado=2)
        items, _ = self.items(pedido)
        bloques = _bloques_comanda(items)
        self.assertEqual(bloques[0]['plato'], 'PLATO 2 - COCINA CG')
        self.assertEqual(len(bloques[0]['lineas']), 2)

    def test_un_acompanante_de_grupo_dinamico_sale_en_la_comanda_de_su_categoria(self):
        pedido = self.pedido()
        detalle = self.detalle(pedido, self.punta, peso_gramos='350', grupo_armado=1)
        VGDetallePedidoOpcion.objects.create(detalle_pedido=detalle, grupo_nombre='Guarnición', producto=self.yuca, precio_unitario=0)
        items, _ = self.items(pedido)
        cocina = [i for i in items if i['categoria'].id == self.cocina.id]
        lineas = _bloques_comanda(cocina)[0]['lineas']
        self.assertEqual([(l['cantidad'], l['nombre']) for l in lineas], [('1x', 'Yuca al vapor')])


class DibujoDeLaComandaTests(TestCase):
    DATOS = {
        'estacion': 'COCINA', 'titulo': 'MESA 7', 'tipo': '', 'pedido': 482, 'hora': '06/11 14:32',
        'cliente': 'Ana Pérez', 'mesero': 'carlos', 'nota_pedido': 'Entregar frío, para llevar',
        'bloques': [
            {'plato': 'PLATO 1 - ENTRADA', 'lineas': [{'cantidad': '2x', 'nombre': 'Tequeños', 'nota': 'SIN PICANTE', 'opciones': [], 'adicionales': []}]},
            {'plato': None, 'lineas': [{'cantidad': '350 g', 'nombre': 'Punta trasera', 'nota': '', 'opciones': ['Término: medio'], 'adicionales': ['1x Queso extra']}]},
        ],
    }

    def test_la_imagen_tiene_el_ancho_pedido_y_el_rotulo_negro_arriba(self):
        for ancho in (576, 384):
            imagen = dibujar_comanda(self.DATOS, ancho=ancho)
            self.assertEqual(imagen.width, ancho)
            self.assertGreater(imagen.height, 300)
            # La barra negra de la estación: un punto dentro de ella, arriba y a la izquierda del texto.
            self.assertEqual(imagen.getpixel((ancho // 2 - ancho // 3, 40)), 0, ancho)

    def test_textos_largos_y_caracteres_especiales_no_rompen(self):
        datos = dict(self.DATOS, estacion='ESPECIALIDAD DE LA CASA / GUARNICIONES / ENTRADAS')
        datos['bloques'] = [{'plato': None, 'lineas': [
            {'cantidad': f'{n}x', 'nombre': 'Hamburguesa doble con queso, tocineta y salsa de la casa ñandú ' * 2, 'nota': 'sin cebolla ni picante ' * 6,
             'opciones': ['Término: tres cuartos'], 'adicionales': ['2x Tocineta extra']} for n in range(1, 25)
        ]}]
        imagen = dibujar_comanda(datos)
        self.assertEqual(imagen.width, 576)
        self.assertGreater(imagen.height, 3000)

    def test_el_delivery_con_cliente_grande_y_barra_de_tipo_se_dibuja(self):
        datos = dict(self.DATOS, titulo='DELIVERY', cliente_grande='Luis Gómez', cliente='', tipo='')
        self.assertEqual(dibujar_comanda(datos).width, 576)


class ComandaEnBytesTests(ComandaBase):
    def armar(self):
        pedido = self.pedido()
        self.detalle(pedido, self.tequenos, notas='sin picante')
        items, detalles = self.items(pedido)
        return pedido, items, detalles

    def test_la_comanda_sale_como_imagen_con_el_pitido_antes_y_el_corte_al_final(self):
        pedido, items, _ = self.armar()
        ticket = _build_ticket_bytes(pedido, [self.cocina], items)
        self.assertIn(RASTER, ticket)
        self.assertTrue(ticket.endswith(CUT))
        self.assertLess(ticket.index(CASH_DRAWER_KICK), ticket.index(RASTER))
        self.assertLess(ticket.index(BUZZER_ALT), ticket.index(RASTER))

    def test_la_secundaria_tambien_sale_como_imagen(self):
        pedido = self.pedido()
        detalle = self.detalle(pedido, self.punta, peso_gramos='350', grupo_armado=2)
        ticket = _build_ticket_secundario_bytes(pedido, self.parrilla, [detalle])
        self.assertIn(RASTER, ticket)
        self.assertTrue(ticket.endswith(CUT))

    @override_settings(COMANDA_GRAFICA=False)
    def test_apagada_por_configuracion_sale_el_texto_de_siempre(self):
        pedido, items, _ = self.armar()
        ticket = _build_ticket_bytes(pedido, [self.cocina], items)
        self.assertNotIn(RASTER, ticket)
        for texto in (b'VARAGRILL', b'COCINA CG', b'Mesero: carlos', 'Tequeños'.encode('cp1252'), b'* sin picante'):
            self.assertIn(texto, ticket)

    def test_si_falla_el_dibujo_sale_el_texto_y_nunca_se_pierde_la_comanda(self):
        pedido, items, detalles = self.armar()
        with patch('varagrill.comanda_grafica.dibujar_comanda', side_effect=OSError('sin fuentes')):
            ticket = _build_ticket_bytes(pedido, [self.cocina], items)
            secundario = _build_ticket_secundario_bytes(pedido, self.cocina, detalles)
        self.assertNotIn(RASTER, ticket)
        self.assertIn(b'Mesero: carlos', ticket)
        self.assertNotIn(RASTER, secundario)
        self.assertIn(b'Mesero: carlos', secundario)

    @override_settings(COMANDA_ANCHO_PUNTOS=384)
    def test_el_ancho_del_papel_es_configurable(self):
        pedido, items, _ = self.armar()
        ticket = _build_ticket_bytes(pedido, [self.cocina], items)
        # GS v 0 m xL xH yL yH: ancho en bytes = 384 / 8 = 48
        posicion = ticket.index(RASTER) + len(RASTER) + 1
        self.assertEqual(int.from_bytes(ticket[posicion:posicion + 2], 'little'), 48)

    def test_imprimir_comandas_manda_la_imagen_a_la_impresora_primaria_y_a_la_secundaria(self):
        pedido = self.pedido()
        self.detalle(pedido, self.tequenos)
        self.detalle(pedido, self.punta, peso_gramos='350')
        enviados = {}

        def conectar(direccion, timeout=None):
            conexion = MagicMock()
            conexion.__enter__.return_value = conexion
            conexion.sendall.side_effect = lambda datos, host=direccion[0]: enviados.__setitem__(host, datos)
            return conexion

        with patch('varagrill.impresion_termica.socket.create_connection', side_effect=conectar), \
                patch('varagrill.impresion_termica.time.sleep'):
            resultados = imprimir_comandas_pedido(pedido)
        self.assertTrue(all(r['ok'] for r in resultados))
        self.assertEqual(sorted(enviados), ['192.168.9.10', '192.168.9.11', '192.168.9.12'])
        for host, datos in enviados.items():
            self.assertIn(RASTER, datos, host)
