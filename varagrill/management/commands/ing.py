"""
Sincroniza VGIngrediente con el conteo físico de "Resumen_Inventario_Pesaje-1.xlsx":
para cada fila de la ficha (nombre, unidad, TOTAL contado), si el ingrediente ya existe
en el inventario se actualiza su stock_actual al total contado (sin duplicar la fila) y
se registra el movimiento de ajuste correspondiente; si no existe, se inserta como
ingrediente nuevo con ese stock inicial y se registra su movimiento de entrada.

La columna "TOTAL" de la ficha es la que se usa como stock real — es la suma de todas
las lecturas registradas (la ficha original distingue "Lectura 1" de "TOTAL"; TOTAL es
el consolidado). Los datos de este archivo están embebidos abajo, siguiendo el mismo
patrón que seed_ingredientes_precios.py, para no depender de openpyxl/pandas (no están
entre las dependencias del proyecto).
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from varagrill.models import VGIngrediente, VGMovimientoInventario, VGRol, VGUsuario

# (nombre, unidad_medida, total_contado, nota_de_la_ficha)
# unidad_medida ya normalizada a las choices de VGIngrediente.UNIDADES ('unidades' -> 'unidad').
CONTEO_PESAJE = [
    ("Churrasco de Solomo", "kg", "17.45", ""),
    ("Entraña", "kg", "11.6", ""),
    ("Patacón para Servicio", "unidad", "308", ""),
    ("Patacón para Mostrador", "unidad", "71", ""),
    ("Yuca para Mostrador", "kg", "161.25", ""),
    ("Maíz para Sopa", "kg", "14.1", ""),
    ("Cola de Paleta (falsa punta)", "kg", "3.05", ""),
    ("Dembo", "kg", "4.55", ""),
    ("Short Steak", "kg", "4.05", ""),
    ("Pollo Entero", "kg", "220.95", 'Ficha también anota "100 Pollos"'),
    ("Papa de Servicio", "kg", "50", "Anotado como 5 cajas de 10 kg, o 4 paquetes de 2.5 kg."),
    ("Solomo (general)", "kg", "176.05", ""),
    ("Solomo Entero", "kg", "9.1", ""),
    ("Rack de Costilla de Cerdo", "kg", "47.4", ""),
    ("Toma Hen de Cerdo", "kg", "32.25", ""),
    ("Yuca para Servicio", "kg", "125.37", ""),
    ("Muchacho Cuadrado", "kg", "3.3", ""),
    ("Pollo de Res", "kg", "10", ""),
    ("Ganzo", "kg", "3.6", ""),
    ("Merma para Moler", "kg", "1.2", ""),
    ("Merma de Punta", "kg", "4.45", ""),
    ("Merma de Solomo", "kg", "1.75", ""),
    ("Pulpa de Pernil", "kg", "42.55", ""),
    ("Churrasco de Lomo de Cerdo", "kg", "111.96", ""),
    ("Churrasco de Punta", "kg", "21.3", ""),
    ("Punta Trasera", "kg", "188.7", ""),
    ("Lomito", "kg", "2.35", ""),
]

FUENTE = "Resumen_Inventario_Pesaje-1.xlsx"


class Command(BaseCommand):
    help = "Sincroniza el stock de ingredientes con el conteo físico de Resumen_Inventario_Pesaje-1.xlsx"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Muestra qué se crearía/actualizaría sin escribir nada en la base de datos.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        creados, actualizados, sin_cambios = [], [], []

        with transaction.atomic():
            operator = self._ensure_operator_user()

            for nombre, unidad, total_str, nota in CONTEO_PESAJE:
                total = Decimal(total_str)
                ingrediente = VGIngrediente.objects.filter(nombre__iexact=nombre).first()

                if ingrediente is not None:
                    stock_anterior = ingrediente.stock_actual
                    delta = total - stock_anterior
                    if delta == 0:
                        sin_cambios.append(nombre)
                        continue

                    actualizados.append(f"{nombre}: {stock_anterior} -> {total} {unidad}")
                    if dry_run:
                        continue

                    ingrediente.stock_actual = total
                    ingrediente.actualizado_por = operator
                    ingrediente.save(update_fields=["stock_actual", "actualizado_por", "fecha_actualizacion"])

                    motivo = f"Conteo físico ({FUENTE}): {stock_anterior} -> {total} {unidad}"
                    if nota:
                        motivo += f" — {nota}"
                    VGMovimientoInventario.objects.create(
                        ingrediente=ingrediente,
                        tipo_movimiento="ajuste",
                        cantidad=delta,
                        motivo=motivo,
                        creado_por=operator,
                    )
                else:
                    creados.append(f"{nombre}: {total} {unidad}")
                    if dry_run:
                        continue

                    nuevo = VGIngrediente.objects.create(
                        nombre=nombre,
                        unidad_medida=unidad,
                        stock_actual=total,
                        stock_minimo=Decimal("0"),
                        costo_unitario=Decimal("0"),
                        creado_por=operator,
                        actualizado_por=operator,
                    )
                    motivo = f"Carga inicial por conteo físico ({FUENTE}): {total} {unidad}"
                    if nota:
                        motivo += f" — {nota}"
                    VGMovimientoInventario.objects.create(
                        ingrediente=nuevo,
                        tipo_movimiento="entrada",
                        cantidad=total,
                        motivo=motivo,
                        creado_por=operator,
                    )

            if dry_run:
                # No queremos persistir nada en modo simulación, ni siquiera al operador
                # si se acabó de crear en esta misma corrida.
                transaction.set_rollback(True)

        self._report(dry_run, creados, actualizados, sin_cambios)

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

    def _report(self, dry_run, creados, actualizados, sin_cambios):
        prefix = "[DRY-RUN] " if dry_run else ""
        self.stdout.write(self.style.SUCCESS(f"{prefix}Sincronización de inventario/pesaje completada."))

        self.stdout.write(f"\nIngredientes nuevos a insertar ({len(creados)}):" if dry_run else f"\nIngredientes nuevos insertados ({len(creados)}):")
        for linea in creados:
            self.stdout.write(f"  + {linea}")

        self.stdout.write(f"\nIngredientes a actualizar ({len(actualizados)}):" if dry_run else f"\nIngredientes actualizados ({len(actualizados)}):")
        for linea in actualizados:
            self.stdout.write(f"  ~ {linea}")

        self.stdout.write(f"\nSin cambios (stock ya coincide) ({len(sin_cambios)}):")
        for nombre in sin_cambios:
            self.stdout.write(f"  = {nombre}")

        if dry_run:
            self.stdout.write(self.style.WARNING("\nModo simulación: no se escribió nada en la base de datos."))
