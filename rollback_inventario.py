from decimal import Decimal
from datetime import datetime
from django.utils import timezone
from varagrill.models import VGMovimientoInventario

start = timezone.make_aware(datetime(2026, 9, 2, 0, 0, 0), timezone.get_current_timezone())
end = timezone.make_aware(datetime(2026, 9, 21, 11, 30, 0), timezone.get_current_timezone())

count = 0
for mov in VGMovimientoInventario.objects.filter(
    fecha_movimiento__gte=start,
    fecha_movimiento__lt=end
).order_by('fecha_movimiento'):
    ing = mov.ingrediente
    cantidad = Decimal(str(mov.cantidad))

    if mov.tipo_movimiento == 'entrada':
        ing.stock_actual = Decimal(str(ing.stock_actual)) - cantidad
    elif mov.tipo_movimiento == 'salida':
        ing.stock_actual = Decimal(str(ing.stock_actual)) + cantidad
    elif mov.tipo_movimiento == 'ajuste':
        ing.stock_actual = Decimal(str(ing.stock_actual)) - cantidad

    ing.save(update_fields=['stock_actual'])

    VGMovimientoInventario.objects.create(
        ingrediente=ing,
        tipo_movimiento='ajuste',
        cantidad=cantidad,
        motivo=f'ROLLBACK inventario por corrección del rango 2026-09-02 a 2026-09-21 11:30. Original #{mov.id}',
        id_referencia=mov.id,
        creado_por=mov.creado_por,
    )
    count += 1

print(f"Rollback aplicado a {count} movimientos.")
