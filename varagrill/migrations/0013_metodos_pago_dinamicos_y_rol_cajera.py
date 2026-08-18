import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

# (clave vieja del CharField, nombre nuevo en VGMetodoPago, es_efectivo)
PAYMENT_METHOD_SEED = [
    ('efectivo', 'Efectivo', True),
    ('tarjeta', 'Tarjeta', False),
    ('transferencia', 'Transferencia', False),
    ('pago_movil', 'Pago móvil', False),
    ('binance', 'Binance', False),
    ('zelle', 'Zelle', False),
]


def seed_metodos_pago(apps, schema_editor):
    VGMetodoPago = apps.get_model('varagrill', 'VGMetodoPago')
    for _, nombre, es_efectivo in PAYMENT_METHOD_SEED:
        VGMetodoPago.objects.get_or_create(nombre=nombre, defaults={'es_efectivo': es_efectivo})


def backfill_vgpago_metodo_pago(apps, schema_editor):
    VGPago = apps.get_model('varagrill', 'VGPago')
    VGMetodoPago = apps.get_model('varagrill', 'VGMetodoPago')
    metodos_por_clave_vieja = {
        clave: VGMetodoPago.objects.get(nombre=nombre)
        for clave, nombre, _ in PAYMENT_METHOD_SEED
    }
    for pago in VGPago.objects.all():
        metodo = metodos_por_clave_vieja.get(pago.metodo_pago_old)
        if metodo is not None:
            pago.metodo_pago_new_id = metodo.id
            pago.save(update_fields=['metodo_pago_new'])


def seed_cajera_role(apps, schema_editor):
    VGRol = apps.get_model('varagrill', 'VGRol')
    VGRol.objects.get_or_create(
        nombre_role='Cajera',
        defaults={'descripcion': 'Acceso solo a cobros pendientes y al cuadre de caja diario.'},
    )


def unseed_cajera_role(apps, schema_editor):
    VGRol = apps.get_model('varagrill', 'VGRol')
    VGRol.objects.filter(nombre_role='Cajera').delete()


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('varagrill', '0012_alter_vgpago_metodo_pago_vgcierrecaja_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_cajera_role, unseed_cajera_role),

        migrations.CreateModel(
            name='VGMetodoPago',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fecha_creacion', models.DateTimeField(auto_now_add=True)),
                ('fecha_actualizacion', models.DateTimeField(auto_now=True)),
                ('nombre', models.CharField(max_length=50, unique=True)),
                ('es_efectivo', models.BooleanField(default=False, help_text='Si esta activo, este metodo cuenta como efectivo fisico en el cuadre de caja.')),
                ('activo', models.BooleanField(default=True)),
                ('actualizado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_actualizados', to=settings.AUTH_USER_MODEL)),
                ('creado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_creados', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Metodo de pago',
                'verbose_name_plural': 'Metodos de pago',
                'db_table': 'vg_metodos_pago',
                'ordering': ['nombre'],
            },
        ),

        migrations.RunPython(seed_metodos_pago, noop),

        migrations.RenameField(
            model_name='vgpago',
            old_name='metodo_pago',
            new_name='metodo_pago_old',
        ),
        migrations.AddField(
            model_name='vgpago',
            name='metodo_pago_new',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name='pagos', to='varagrill.vgmetodopago'),
        ),

        migrations.RunPython(backfill_vgpago_metodo_pago, noop),

        migrations.RemoveField(
            model_name='vgpago',
            name='metodo_pago_old',
        ),
        migrations.RenameField(
            model_name='vgpago',
            old_name='metodo_pago_new',
            new_name='metodo_pago',
        ),
        migrations.AlterField(
            model_name='vgpago',
            name='metodo_pago',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='pagos', to='varagrill.vgmetodopago'),
        ),
    ]
