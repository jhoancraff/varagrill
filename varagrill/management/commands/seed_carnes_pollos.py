from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from varagrill.models import (
    VGCategoriaProducto,
    VGCompra,
    VGDetalleCompra,
    VGIngrediente,
    VGMovimientoInventario,
    VGProducto,
    VGRecetaProducto,
    VGRol,
    VGUsuario,
)


class Command(BaseCommand):
    help = "Carga categorias, ingredientes y productos de Carnes/Pollos/Cortes crudos/Guarniciones para armar platos"

    def handle(self, *args, **options):
        with transaction.atomic():
            operator = self._ensure_operator_user()
            ingredients = self._seed_ingredients(operator)
            products = self._seed_products(operator, ingredients)

        self.stdout.write(self.style.SUCCESS("Datos de carnes, pollos y guarniciones insertados correctamente."))
        self.stdout.write(f"Ingredientes: {len(ingredients)} | Productos: {len(products)}")
        self.stdout.write(
            "Recuerda ajustar los precios de venta (precio por kilogramo en los productos por peso) "
            "desde Panel administrativo > Productos, ya que fluctuan segun el mercado."
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

    def _seed_ingredients(self, operator):
        purchase_batches = [
            {
                "provider": "Carnicera Central, C.A.",
                "items": [
                    ("Punta de res", "kg", "40.00", "8.00", "5.20"),
                    ("Solomo de res", "kg", "30.00", "6.00", "6.80"),
                    ("Pollo entero", "unidad", "25.00", "5.00", "3.50"),
                    ("Guasacaca", "kg", "8.00", "2.00", "2.10"),
                ],
            },
            {
                "provider": "Agromercado Andino",
                "items": [
                    ("Yuca", "kg", "20.00", "4.00", "0.60"),
                    ("Ensalada mixta (porcion)", "unidad", "40.00", "8.00", "0.50"),
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

                VGDetalleCompra.objects.update_or_create(
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
                    motivo=f"Carga carnes/pollos demo - {batch['provider']}",
                    defaults={"creado_por": operator},
                )
                ingredients[name] = ingredient

            total = sum((detalle.subtotal for detalle in purchase.detalles.all()), Decimal("0"))
            purchase.total = total
            purchase.actualizado_por = operator
            purchase.save(update_fields=["total", "actualizado_por"])

        return ingredients

    def _seed_products(self, operator, ingredients):
        categories = {
            "Carnes": "Cortes de carne a la parrilla, vendidos por peso (precio por kilogramo).",
            "Pollos": "Presentaciones de pollo por unidad.",
            "Cortes crudos": "Cortes de carne crudos para llevar, vendidos por peso.",
            "Guarniciones": "Acompanantes para armar el plato junto a la proteina.",
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

        # "recipe" quantities para productos venta_por_peso=True estan expresadas
        # por 1 KILOGRAMO vendido; para productos por unidad, por 1 unidad vendida.
        product_data = [
            {
                "name": "Punta a la parrilla",
                "category": "Carnes",
                "price": "9.50",
                "cost": "5.20",
                "time": 12,
                "venta_por_peso": True,
                "description": "Punta trasera de res a la parrilla, precio por kilogramo.",
                "recipe": [("Punta de res", "1.000")],
            },
            {
                "name": "Solomo a la parrilla",
                "category": "Carnes",
                "price": "11.00",
                "cost": "6.80",
                "time": 12,
                "venta_por_peso": True,
                "description": "Solomo de res a la parrilla, precio por kilogramo.",
                "recipe": [("Solomo de res", "1.000")],
            },
            {
                "name": "Pollo entero a la parrilla",
                "category": "Pollos",
                "price": "12.00",
                "cost": "3.50",
                "time": 25,
                "venta_por_peso": False,
                "description": "Pollo entero asado a la parrilla.",
                "recipe": [("Pollo entero", "1.000")],
            },
            {
                "name": "Medio pollo con guasacaca",
                "category": "Pollos",
                "price": "7.00",
                "cost": "2.10",
                "time": 20,
                "venta_por_peso": False,
                "description": "Medio pollo a la parrilla con guasacaca casera.",
                "recipe": [("Pollo entero", "0.500"), ("Guasacaca", "0.150")],
            },
            {
                "name": "Punta cruda (para llevar)",
                "category": "Cortes crudos",
                "price": "6.50",
                "cost": "5.20",
                "time": 0,
                "venta_por_peso": True,
                "description": "Corte de punta de res crudo para llevar, precio por kilogramo.",
                "recipe": [("Punta de res", "1.000")],
            },
            {
                "name": "Solomo crudo (para llevar)",
                "category": "Cortes crudos",
                "price": "7.80",
                "cost": "6.80",
                "time": 0,
                "venta_por_peso": True,
                "description": "Corte de solomo de res crudo para llevar, precio por kilogramo.",
                "recipe": [("Solomo de res", "1.000")],
            },
            {
                "name": "Yuca sancochada",
                "category": "Guarniciones",
                "price": "3.00",
                "cost": "0.60",
                "time": 8,
                "venta_por_peso": True,
                "description": "Yuca sancochada como guarnicion, precio por kilogramo.",
                "recipe": [("Yuca", "1.000")],
            },
            {
                "name": "Ensalada mixta",
                "category": "Guarniciones",
                "price": "1.50",
                "cost": "0.50",
                "time": 3,
                "venta_por_peso": False,
                "description": "Porcion de ensalada mixta como guarnicion.",
                "recipe": [("Ensalada mixta (porcion)", "1.000")],
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
                    "venta_por_peso": item["venta_por_peso"],
                    "tiempo_preparacion_min": item["time"],
                    "creado_por": operator,
                    "actualizado_por": operator,
                },
            )
            VGRecetaProducto.objects.filter(producto=product).delete()
            for ingredient_name, quantity in item["recipe"]:
                VGRecetaProducto.objects.create(
                    producto=product,
                    ingrediente=ingredients[ingredient_name],
                    cantidad_requerida=Decimal(quantity),
                )
            products[item["name"]] = product

        return products