from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from varagrill.models import (
    VGCategoriaProducto,
    VGCompra,
    VGDetalleCompra,
    VGDetallePedido,
    VGIngrediente,
    VGMovimientoInventario,
    VGPreparacion,
    VGProducto,
    VGRecetaPreparacion,
    VGRecetaProducto,
    VGRol,
    VGUsuario,
)


class Command(BaseCommand):
    help = "Carga ingredientes, compras iniciales, preparaciones y productos demo para Varagrill"

    def handle(self, *args, **options):
        with transaction.atomic():
            operator = self._ensure_operator_user()
            ingredients = self._seed_ingredients(operator)
            preparations = self._seed_preparations(operator, ingredients)
            products = self._seed_products(operator, ingredients, preparations)

        self.stdout.write(self.style.SUCCESS("Datos de restaurante insertados correctamente."))
        self.stdout.write(
            f"Ingredientes: {len(ingredients)} | Preparaciones: {len(preparations)} | Productos: {len(products)}"
        )

    def _ensure_operator_user(self):
        role, _ = VGRol.objects.get_or_create(
            nombre_role="Administrador",
            defaults={"descripcion": "Usuario operador para cargas iniciales"},
        )
        user, created = VGUsuario.objects.get_or_create(
            username="operador_inventario",
            defaults={
                "cedula": "V30000001",
                "email": "inventario@varagrill.local",
                "first_name": "Operador",
                "last_name": "Inventario",
                "id_role": role,
                "is_staff": True,
            },
        )
        if created:
            user.set_password("Varagrill123!")
            user.save(update_fields=["password"])
        elif user.id_role_id != role.id:
            user.id_role = role
            user.save(update_fields=["id_role"])
        return user

    def _seed_ingredients(self, operator):
        purchase_batches = [
            {
                "provider": "Distribuidora La Montaña, C.A.",
                "items": [
                    ("Harina de maiz precocida", "kg", "45.00", "10.00", "1.48"),
                    ("Queso llanero", "kg", "18.00", "4.00", "6.35"),
                    ("Carne molida de res", "kg", "30.00", "8.00", "7.90"),
                    ("Pollo desmechado", "kg", "22.00", "6.00", "6.80"),
                    ("Caraotas negras", "kg", "16.00", "5.00", "1.95"),
                    ("Arroz blanco", "kg", "35.00", "8.00", "1.40"),
                    ("Aceite vegetal", "l", "20.00", "5.00", "2.75"),
                    ("Sal", "kg", "8.00", "1.00", "0.72"),
                    ("Azucar", "kg", "10.00", "2.00", "1.10"),
                    ("Papelon", "kg", "8.00", "2.00", "1.65"),
                ],
            },
            {
                "provider": "Agroinsumos del Centro", 
                "items": [
                    ("Cebolla", "kg", "25.00", "6.00", "1.25"),
                    ("Pimenton rojo", "kg", "14.00", "3.00", "2.15"),
                    ("Tomate", "kg", "28.00", "5.00", "1.85"),
                    ("Ajo", "kg", "6.00", "1.00", "3.10"),
                    ("Cilantro", "kg", "4.00", "0.50", "2.80"),
                    ("Lechuga", "kg", "10.00", "2.00", "1.75"),
                    ("Aguacate", "kg", "12.00", "2.00", "3.90"),
                    ("Limon", "kg", "9.00", "1.50", "1.55"),
                    ("Platano maduro", "kg", "20.00", "5.00", "1.20"),
                    ("Yuca", "kg", "18.00", "4.00", "1.30"),
                ],
            },
            {
                "provider": "Frigorifico Los Andes", 
                "items": [
                    ("Carne para mechar", "kg", "18.00", "5.00", "8.45"),
                    ("Pechuga de pollo", "kg", "20.00", "5.00", "6.95"),
                    ("Costilla de cerdo", "kg", "16.00", "4.00", "7.25"),
                    ("Tocineta", "kg", "9.00", "2.00", "8.10"),
                    ("Jamon ahumado", "kg", "7.00", "2.00", "7.80"),
                    ("Queso mozzarella", "kg", "12.00", "3.00", "6.90"),
                    ("Mantequilla", "kg", "6.00", "1.00", "5.40"),
                ],
            },
            {
                "provider": "Bebidas y Licores El Sabor", 
                "items": [
                    ("Malta", "l", "24.00", "6.00", "1.10"),
                    ("Papelon liquido", "l", "10.00", "2.00", "1.95"),
                    ("Mayonesa", "kg", "12.00", "3.00", "3.35"),
                    ("Salsa de tomate", "kg", "10.00", "2.00", "2.90"),
                    ("Mostaza", "kg", "8.00", "2.00", "2.55"),
                    ("Vinagre", "l", "6.00", "1.00", "1.45"),
                    ("Leche liquida", "l", "18.00", "4.00", "1.85"),
                    ("Huevos", "unidad", "180.00", "30.00", "0.16"),
                ],
            },
        ]

        ingredients = {}
        for batch in purchase_batches:
            purchase = VGCompra.objects.create(
                proveedor_nombre=batch["provider"],
                estado="recibido",
                creado_por=operator,
                actualizado_por=operator,
            )
            total = Decimal("0")
            for name, unit, quantity, minimum, cost in batch["items"]:
                ingredient, _ = VGIngrediente.objects.update_or_create(
                    nombre=name,
                    defaults={
                        "unidad_medida": unit,
                        "stock_minimo": Decimal(minimum),
                        "costo_unitario": Decimal(cost),
                        "ultimo_proveedor": batch["provider"],
                        "creado_por": operator,
                        "actualizado_por": operator,
                    },
                )
                ingredient.stock_actual = Decimal(quantity)
                ingredient.costo_unitario = Decimal(cost)
                ingredient.ultimo_proveedor = batch["provider"]
                ingredient.actualizado_por = operator
                ingredient.save(update_fields=["stock_actual", "costo_unitario", "ultimo_proveedor", "actualizado_por"])

                detail = VGDetalleCompra.objects.create(
                    compra=purchase,
                    ingrediente=ingredient,
                    cantidad=Decimal(quantity),
                    costo_unitario=Decimal(cost),
                )
                total += detail.subtotal
                VGMovimientoInventario.objects.create(
                    ingrediente=ingredient,
                    tipo_movimiento="entrada",
                    cantidad=Decimal(quantity),
                    motivo=f"Compra inicial de proveedor {batch['provider']}",
                    id_referencia=purchase.id,
                    creado_por=operator,
                )
                ingredients[name] = ingredient

            purchase.total = total
            purchase.save(update_fields=["total"])

        return ingredients

    def _seed_preparations(self, operator, ingredients):
        preparation_data = [
            {
                "name": "Sofrito criollo",
                "yield_qty": "2.500",
                "yield_unit": "kg",
                "components": [
                    ("ingrediente", "Cebolla", "0.900"),
                    ("ingrediente", "Pimenton rojo", "0.500"),
                    ("ingrediente", "Tomate", "0.700"),
                    ("ingrediente", "Ajo", "0.120"),
                    ("ingrediente", "Aceite vegetal", "0.180"),
                    ("ingrediente", "Sal", "0.030"),
                    ("ingrediente", "Cilantro", "0.070"),
                ],
            },
            {
                "name": "Caraotas guisadas",
                "yield_qty": "4.000",
                "yield_unit": "kg",
                "components": [
                    ("ingrediente", "Caraotas negras", "1.500"),
                    ("sub", "Sofrito criollo", "0.750"),
                    ("ingrediente", "Sal", "0.040"),
                    ("ingrediente", "Aceite vegetal", "0.100"),
                ],
            },
            {
                "name": "Pollo guisado",
                "yield_qty": "3.000",
                "yield_unit": "kg",
                "components": [
                    ("ingrediente", "Pechuga de pollo", "2.200"),
                    ("sub", "Sofrito criollo", "0.500"),
                    ("ingrediente", "Sal", "0.025"),
                    ("ingrediente", "Aceite vegetal", "0.090"),
                ],
            },
            {
                "name": "Carne mechada",
                "yield_qty": "3.000",
                "yield_unit": "kg",
                "components": [
                    ("ingrediente", "Carne para mechar", "2.300"),
                    ("sub", "Sofrito criollo", "0.550"),
                    ("ingrediente", "Sal", "0.025"),
                    ("ingrediente", "Aceite vegetal", "0.090"),
                ],
            },
            {
                "name": "Guasacaca de la casa",
                "yield_qty": "1.800",
                "yield_unit": "kg",
                "components": [
                    ("ingrediente", "Aguacate", "0.900"),
                    ("ingrediente", "Cebolla", "0.180"),
                    ("ingrediente", "Cilantro", "0.080"),
                    ("ingrediente", "Limon", "0.160"),
                    ("ingrediente", "Vinagre", "0.120"),
                    ("ingrediente", "Aceite vegetal", "0.120"),
                    ("ingrediente", "Sal", "0.020"),
                ],
            },
            {
                "name": "Salsa rosada",
                "yield_qty": "1.500",
                "yield_unit": "kg",
                "components": [
                    ("ingrediente", "Mayonesa", "0.800"),
                    ("ingrediente", "Salsa de tomate", "0.500"),
                    ("ingrediente", "Mostaza", "0.150"),
                    ("ingrediente", "Azucar", "0.050"),
                ],
            },
            {
                "name": "Queso rallado sazonado",
                "yield_qty": "1.200",
                "yield_unit": "kg",
                "components": [
                    ("ingrediente", "Queso llanero", "1.000"),
                    ("ingrediente", "Sal", "0.010"),
                    ("ingrediente", "Cilantro", "0.020"),
                ],
            },
            {
                "name": "Arroz blanco base",
                "yield_qty": "5.000",
                "yield_unit": "kg",
                "components": [
                    ("ingrediente", "Arroz blanco", "2.100"),
                    ("ingrediente", "Aceite vegetal", "0.120"),
                    ("ingrediente", "Sal", "0.040"),
                ],
            },
            {
                "name": "Platano frito dulce",
                "yield_qty": "2.500",
                "yield_unit": "kg",
                "components": [
                    ("ingrediente", "Platano maduro", "2.200"),
                    ("ingrediente", "Aceite vegetal", "0.150"),
                    ("ingrediente", "Papelon", "0.080"),
                ],
            },
            {
                "name": "Yuca sancochada",
                "yield_qty": "3.000",
                "yield_unit": "kg",
                "components": [
                    ("ingrediente", "Yuca", "2.400"),
                    ("ingrediente", "Sal", "0.030"),
                ],
            },
            {
                "name": "Perico criollo",
                "yield_qty": "2.000",
                "yield_unit": "kg",
                "components": [
                    ("ingrediente", "Huevos", "18.000"),
                    ("sub", "Sofrito criollo", "0.350"),
                    ("ingrediente", "Mantequilla", "0.120"),
                    ("ingrediente", "Sal", "0.020"),
                ],
            },
            {
                "name": "Salsa BBQ criolla",
                "yield_qty": "1.800",
                "yield_unit": "kg",
                "components": [
                    ("ingrediente", "Salsa de tomate", "0.700"),
                    ("ingrediente", "Papelon liquido", "0.450"),
                    ("ingrediente", "Mostaza", "0.120"),
                    ("ingrediente", "Vinagre", "0.090"),
                    ("ingrediente", "Ajo", "0.060"),
                ],
            },
        ]

        preparations = {}
        for item in preparation_data:
            preparation, _ = VGPreparacion.objects.update_or_create(
                nombre=item["name"],
                defaults={
                    "rendimiento_cantidad": Decimal(item["yield_qty"]),
                    "rendimiento_unidad": item["yield_unit"],
                    "creado_por": operator,
                    "actualizado_por": operator,
                },
            )
            VGRecetaPreparacion.objects.filter(preparacion=preparation).delete()
            preparations[item["name"]] = preparation

        for item in preparation_data:
            preparation = preparations[item["name"]]
            for component_type, component_name, quantity in item["components"]:
                payload = {
                    "preparacion": preparation,
                    "cantidad_requerida": Decimal(quantity),
                }
                if component_type == "ingrediente":
                    payload["ingrediente"] = ingredients[component_name]
                else:
                    payload["sub_preparacion"] = preparations[component_name]
                VGRecetaPreparacion.objects.create(**payload)

        return preparations

    def _seed_products(self, operator, ingredients, preparations):
        categories = {
            "Arepas": "Arepas rellenas y tradicionales",
            "Cachapas": "Cachapas artesanales con rellenos",
            "Platos": "Platos fuertes y combos criollos",
            "Desayunos": "Opciones para desayuno venezolano",
        }
        category_objects = {}
        for name, description in categories.items():
            category_objects[name], _ = VGCategoriaProducto.objects.update_or_create(
                nombre=name,
                defaults={
                    "descripcion": description,
                    "creado_por": operator,
                    "actualizado_por": operator,
                },
            )

        product_data = [
            {
                "name": "Arepa reina pepiada",
                "category": "Arepas",
                "price": "6.50",
                "cost": "2.25",
                "time": 9,
                "description": "Arepa asada con pollo guisado, guasacaca y queso rallado.",
                "recipe": [("ingrediente", "Harina de maiz precocida", "0.180"), ("sub", "Pollo guisado", "0.160"), ("sub", "Guasacaca de la casa", "0.050"), ("sub", "Queso rallado sazonado", "0.030")],
            },
            {
                "name": "Arepa pelua",
                "category": "Arepas",
                "price": "6.80",
                "cost": "2.45",
                "time": 10,
                "description": "Arepa rellena de carne mechada y queso mozzarella.",
                "recipe": [("ingrediente", "Harina de maiz precocida", "0.180"), ("sub", "Carne mechada", "0.170"), ("ingrediente", "Queso mozzarella", "0.050")],
            },
            {
                "name": "Arepa domino",
                "category": "Arepas",
                "price": "5.90",
                "cost": "1.95",
                "time": 8,
                "description": "Arepa con caraotas guisadas y queso rallado.",
                "recipe": [("ingrediente", "Harina de maiz precocida", "0.180"), ("sub", "Caraotas guisadas", "0.160"), ("sub", "Queso rallado sazonado", "0.040")],
            },
            {
                "name": "Cachapa con queso de mano",
                "category": "Cachapas",
                "price": "7.20",
                "cost": "2.80",
                "time": 12,
                "description": "Cachapa dorada con abundante queso fresco.",
                "recipe": [("ingrediente", "Harina de maiz precocida", "0.220"), ("ingrediente", "Queso llanero", "0.120"), ("ingrediente", "Mantequilla", "0.020")],
            },
            {
                "name": "Cachapa con pernil BBQ",
                "category": "Cachapas",
                "price": "8.90",
                "cost": "3.70",
                "time": 14,
                "description": "Cachapa rellena con costilla de cerdo y salsa BBQ criolla.",
                "recipe": [("ingrediente", "Harina de maiz precocida", "0.220"), ("ingrediente", "Costilla de cerdo", "0.180"), ("sub", "Salsa BBQ criolla", "0.050"), ("ingrediente", "Queso mozzarella", "0.060")],
            },
            {
                "name": "Pabellon criollo",
                "category": "Platos",
                "price": "11.50",
                "cost": "4.95",
                "time": 18,
                "description": "Carne mechada con arroz, caraotas y plátano maduro.",
                "recipe": [("sub", "Carne mechada", "0.180"), ("sub", "Arroz blanco base", "0.220"), ("sub", "Caraotas guisadas", "0.180"), ("sub", "Platano frito dulce", "0.120")],
            },
            {
                "name": "Bowl criollo de pollo",
                "category": "Platos",
                "price": "9.75",
                "cost": "4.10",
                "time": 13,
                "description": "Pollo guisado con arroz blanco, aguacate y salsa rosada.",
                "recipe": [("sub", "Pollo guisado", "0.190"), ("sub", "Arroz blanco base", "0.220"), ("ingrediente", "Aguacate", "0.060"), ("sub", "Salsa rosada", "0.035")],
            },
            {
                "name": "Yuca con salsa rosada y tocineta",
                "category": "Platos",
                "price": "7.40",
                "cost": "2.95",
                "time": 11,
                "description": "Yuca suave con topping de tocineta crujiente y salsa rosada.",
                "recipe": [("sub", "Yuca sancochada", "0.240"), ("ingrediente", "Tocineta", "0.050"), ("sub", "Salsa rosada", "0.040")],
            },
            {
                "name": "Arepa desayuno perico",
                "category": "Desayunos",
                "price": "6.10",
                "cost": "2.10",
                "time": 9,
                "description": "Arepa caliente con perico criollo y queso rallado.",
                "recipe": [("ingrediente", "Harina de maiz precocida", "0.180"), ("sub", "Perico criollo", "0.140"), ("sub", "Queso rallado sazonado", "0.030")],
            },
            {
                "name": "Arepa sifrina",
                "category": "Arepas",
                "price": "7.80",
                "cost": "3.05",
                "time": 11,
                "description": "Pollo guisado con queso mozzarella y salsa rosada.",
                "recipe": [("ingrediente", "Harina de maiz precocida", "0.180"), ("sub", "Pollo guisado", "0.160"), ("ingrediente", "Queso mozzarella", "0.060"), ("sub", "Salsa rosada", "0.030")],
            },
        ]

        products = {}
        for item in product_data:
            product, _ = VGProducto.objects.update_or_create(
                nombre=item["name"],
                defaults={
                    "descripcion": item["description"],
                    "categoria": category_objects[item["category"]],
                    "precio_venta": Decimal(item["price"]),
                    "costo_estimado": Decimal(item["cost"]),
                    "disponible": True,
                    "tiempo_preparacion_min": item["time"],
                    "creado_por": operator,
                    "actualizado_por": operator,
                },
            )
            VGRecetaProducto.objects.filter(producto=product).delete()
            for component_type, component_name, quantity in item["recipe"]:
                payload = {
                    "producto": product,
                    "cantidad_requerida": Decimal(quantity),
                }
                if component_type == "ingrediente":
                    payload["ingrediente"] = ingredients[component_name]
                else:
                    payload["preparacion"] = preparations[component_name]
                VGRecetaProducto.objects.create(**payload)
            products[item["name"]] = product

        return products
