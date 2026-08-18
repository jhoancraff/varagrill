from django.db import migrations, models

# Metodos que ya existian y se reciben en bolivares (el resto se queda en USD por defecto).
METODOS_EN_VES = ['Transferencia', 'Pago móvil']


def marcar_metodos_ves(apps, schema_editor):
    VGMetodoPago = apps.get_model('varagrill', 'VGMetodoPago')
    VGMetodoPago.objects.filter(nombre__in=METODOS_EN_VES).update(moneda='VES')


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('varagrill', '0013_metodos_pago_dinamicos_y_rol_cajera'),
    ]

    operations = [
        migrations.AddField(
            model_name='vgmetodopago',
            name='moneda',
            field=models.CharField(choices=[('USD', 'Dólares'), ('VES', 'Bolívares')], default='USD', max_length=3),
        ),
        migrations.RunPython(marcar_metodos_ves, noop),
    ]
