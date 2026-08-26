from django.db import migrations


def seed_rol_contador(apps, schema_editor):
    VGRol = apps.get_model('varagrill', 'VGRol')
    VGRol.objects.get_or_create(
        nombre_role='Contador',
        defaults={'descripcion': 'Acceso completo a Contabilidad y al Panel Analista.'},
    )


def unseed_rol_contador(apps, schema_editor):
    VGRol = apps.get_model('varagrill', 'VGRol')
    VGRol.objects.filter(nombre_role='Contador').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('varagrill', '0023_seed_categorias_gasto'),
    ]

    operations = [
        migrations.RunPython(seed_rol_contador, unseed_rol_contador),
    ]
