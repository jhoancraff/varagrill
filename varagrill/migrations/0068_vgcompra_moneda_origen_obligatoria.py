from django.db import migrations, models


def completar_moneda_origen(apps, schema_editor):
    VGCompra = apps.get_model('varagrill', 'VGCompra')
    compras = VGCompra.objects.filter(moneda_origen='')
    compras.filter(total_bs_factura__isnull=False).update(moneda_origen='VES')
    compras.filter(total_bs_factura__isnull=True).update(moneda_origen='USD')


class Migration(migrations.Migration):

    dependencies = [
        ('varagrill', '0067_vgajusteinventario_vgdetalleajusteinventario_and_more'),
    ]

    operations = [
        migrations.RunPython(completar_moneda_origen, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='vgcompra',
            name='moneda_origen',
            field=models.CharField(
                choices=[('USD', 'Dólares'), ('VES', 'Bolívares')],
                default='USD',
                max_length=3,
            ),
        ),
    ]