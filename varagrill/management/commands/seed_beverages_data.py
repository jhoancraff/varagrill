from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from varagrill.models import (
    VGCategoriaProducto,
    VGCompra,
    VGDetalleCompra,
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
    help = "Carga categorias, recetas y productos de jugos/licores para pedidos"

    def handle(self, *args, **options):
        with transaction.atomic():
            operator = self._ensure_operator_user()
            ingredients = self._seed_beverage_ingredients(operator)
            preparations = self._seed_beverage_preparations(operator, ingredients)
            products = self._seed_beverage_products(operator, ingredients, preparations)

        self.stdout.write(self.style.SUCCESS("Datos de jugos y licores insertados correctamente."))
        self.stdout.write(
            f"Ingredientes bebida: {len(ingredients)} | Preparaciones bebida: {len(preparations)} | Productos bebida: {len(products)}"
        )

    def _ensure_operator_user(self):
        role, _ = VGRol.objects.get_or_create(
            nombre_role="Administrador",
            defaults={"descripcion": "Usuario operador para cargas iniciales"},
        )
        user, _ = VGUsuario.objects.get_or_create(
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
        if user.id_role_id != role.id:
            user.id_role = role
            user.save(update_fields=["id_role"])
        return user

    def _seed_beverage_ingredients(self, operator):
        purchase_batches = [
            {
                "provider": "Fruticentro Andino, C.A.",
                "items": [
                    ("Pulpa de parchita", "l", "12.00", "3.00", "2.95"),
                    ("Pulpa de guanabana", "l", "10.00", "2.50", "3.20"),
                    ("Naranja", "kg", "18.00", "4.00", "1.85"),
                    ("Pina", "kg", "16.00", "3.00", "2.10"),
                    ("Hierbabuena", "kg", "2.00", "0.40", "5.20"),
                    ("Azucar", "kg", "14.00", "2.00", "1.15"),
                    ("Limon", "kg", "12.00", "2.00", "1.65"),
                    ("Hielo", "kg", "35.00", "8.00", "0.45"),
                ],
            },
            {
                "provider": "Licoreria El Barril", 
                "items": [
                    ("Ron anejo", "l", "15.00", "3.00", "7.25"),
                    ("Vodka", "l", "10.00", "2.00", "8.40"),
                    ("Ginebra", "l", "8.00", "2.00", "9.10"),
                    ("Triple sec", "l", "6.00", "1.00", "10.20"),
                    ("Agua con gas", "l", "18.00", "4.00", "1.30"),
                    ("Refresco cola", "l", "22.00", "5.00", "1.55"),
                    ("Soda limon", "l", "14.00", "3.00", "1.60"),
                ],
            },
        ]

        ingredients = {}
        for batch in purchase_batches:
            purchase = VGCompra.objects.filter(
                proveedor_nombre=batch["provider"],
                estado="recibido",
            ).order_by("id").first()

            if purchase is None:
                purchase = VGCompra.objects.create(
                    proveedor_nombre=batch["provider"],
                    estado="recibido",
                    creado_por=operator,
                    actualizado_por=operator,
                )

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
                ingredient.ultimo_proveedor = batch["provider"]
                ingredient.costo_unitario = Decimal(cost)
                ingredient.actualizado_por = operator
                ingredient.save(update_fields=["stock_actual", "ultimo_proveedor", "costo_unitario", "actualizado_por"])

                detail, _ = VGDetalleCompra.objects.update_or_create(
                    compra=purchase,
                    ingrediente=ingredient,
                    defaults={
                        "cantidad": Decimal(quantity),
                        "costo_unitario": Decimal(cost),
                    },
                )

                VGMovimientoInventario.objects.get_or_create(
                    ingrediente=ingredient,
                    tipo_movimiento="entrada",
                    cantidad=Decimal(quantity),
                    id_referencia=purchase.id,
                    motivo=f"Carga bebidas demo - {batch['provider']}",
                    defaults={"creado_por": operator},
                )
                ingredients[name] = ingredient

            total = sum((detalle.subtotal for detalle in purchase.detalles.all()), Decimal("0"))
            purchase.total = total
            purchase.actualizado_por = operator
            purchase.save(update_fields=["total", "actualizado_por"])

        return ingredients

    def _seed_beverage_preparations(self, operator, ingredients):
        preparation_data = [
            {
                "name": "Jarabe simple",
                "yield_qty": "1.800",
                "yield_unit": "l",
                "components": [
                    ("ingrediente", "Azucar", "0.900"),
                    ("ingrediente", "Agua con gas", "0.900"),
                ],
            },
            {
                "name": "Base mojito",
                "yield_qty": "1.200",
                "yield_unit": "l",
                "components": [
                    ("ingrediente", "Limon", "0.250"),
                    ("ingrediente", "Hierbabuena", "0.080"),
                    ("sub", "Jarabe simple", "0.280"),
                    ("ingrediente", "Hielo", "0.450"),
                ],
            },
            {
                "name": "Base sangria tropical",
                "yield_qty": "2.000",
                "yield_unit": "l",
                "components": [
                    ("ingrediente", "Pulpa de parchita", "0.600"),
                    ("ingrediente", "Pulpa de guanabana", "0.450"),
                    ("ingrediente", "Pina", "0.500"),
                    ("sub", "Jarabe simple", "0.200"),
                ],
            },
            {
                "name": "Base jugo citrico",
                "yield_qty": "2.400",
                "yield_unit": "l",
                "components": [
                    ("ingrediente", "Naranja", "1.300"),
                    ("ingrediente", "Limon", "0.200"),
                    ("ingrediente", "Azucar", "0.100"),
                    ("ingrediente", "Hielo", "0.400"),
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

    def _seed_beverage_products(self, operator, ingredients, preparations):
        categories = {
            "Jugos": "Jugos naturales y mezclas frescas",
            "Licores": "Tragos, cocteles y combinaciones",
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

        beverage_products = [
            {
                "name": "Jugo de naranja natural",
                "category": "Jugos",
                "price": "3.80",
                "cost": "1.45",
                "time": 4,
                "description": "Jugo fresco de naranja con hielo.",
                "recipe": [
                    ("sub", "Base jugo citrico", "0.240"),
                ],
            },
            {
                "name": "Jugo de parchita",
                "category": "Jugos",
                "price": "4.20",
                "cost": "1.75",
                "time": 4,
                "description": "Parchita natural con toque de azucar y hielo.",
                "recipe": [
                    ("ingrediente", "Pulpa de parchita", "0.220"),
                    ("sub", "Jarabe simple", "0.030"),
                    ("ingrediente", "Hielo", "0.120"),
                ],
            },
            {
                "name": "Jugo de guanabana",
                "category": "Jugos",
                "price": "4.40",
                "cost": "1.90",
                "time": 4,
                "description": "Jugo cremoso de guanabana servido frio.",
                "recipe": [
                    ("ingrediente", "Pulpa de guanabana", "0.240"),
                    ("sub", "Jarabe simple", "0.025"),
                    ("ingrediente", "Hielo", "0.120"),
                ],
            },
            {
                "name": "Jugo tropical mixto",
                "category": "Jugos",
                "price": "4.90",
                "cost": "2.10",
                "time": 5,
                "description": "Mezcla de pina, parchita y citricos.",
                "recipe": [
                    ("sub", "Base jugo citrico", "0.120"),
                    ("ingrediente", "Pulpa de parchita", "0.130"),
                    ("ingrediente", "Pina", "0.090"),
                    ("ingrediente", "Hielo", "0.100"),
                ],
            },
            {
                "name": "Cuba libre",
                "category": "Licores",
                "price": "7.20",
                "cost": "2.95",
                "time": 3,
                "description": "Ron anejo con refresco cola y limon.",
                "recipe": [
                    ("ingrediente", "Ron anejo", "0.090"),
                    ("ingrediente", "Refresco cola", "0.180"),
                    ("ingrediente", "Limon", "0.030"),
                    ("ingrediente", "Hielo", "0.100"),
                ],
            },
            {
                "name": "Mojito clasico",
                "category": "Licores",
                "price": "8.10",
                "cost": "3.30",
                "time": 5,
                "description": "Ron anejo, base de mojito y soda limon.",
                "recipe": [
                    ("ingrediente", "Ron anejo", "0.080"),
                    ("sub", "Base mojito", "0.130"),
                    ("ingrediente", "Soda limon", "0.120"),
                ],
            },
            {
                "name": "Gin tonic citrico",
                "category": "Licores",
                "price": "8.50",
                "cost": "3.60",
                "time": 4,
                "description": "Ginebra con agua con gas y toque de limon.",
                "recipe": [
                    ("ingrediente", "Ginebra", "0.080"),
                    ("ingrediente", "Agua con gas", "0.180"),
                    ("ingrediente", "Limon", "0.030"),
                    ("ingrediente", "Hielo", "0.100"),
                ],
            },
            {
                "name": "Vodka tropical",
                "category": "Licores",
                "price": "8.80",
                "cost": "3.75",
                "time": 5,
                "description": "Vodka con pina y parchita, servido en frio.",
                "recipe": [
                    ("ingrediente", "Vodka", "0.085"),
                    ("ingrediente", "Pulpa de parchita", "0.120"),
                    ("ingrediente", "Pina", "0.100"),
                    ("ingrediente", "Hielo", "0.110"),
                ],
            },
            {
                "name": "Sangria tropical",
                "category": "Licores",
                "price": "9.20",
                "cost": "4.05",
                "time": 6,
                "description": "Combinacion de base tropical, ron y triple sec.",
                "recipe": [
                    ("sub", "Base sangria tropical", "0.180"),
                    ("ingrediente", "Ron anejo", "0.060"),
                    ("ingrediente", "Triple sec", "0.030"),
                    ("ingrediente", "Hielo", "0.120"),
                ],
            },
        ]

        products = {}
        for item in beverage_products:
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
