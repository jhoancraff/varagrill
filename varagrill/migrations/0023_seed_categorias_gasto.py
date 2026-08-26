from django.db import migrations

CATEGORIAS_INICIALES = [
    "Alquiler",
    "Servicios",
    "Nómina",
    "Mantenimiento",
    "Insumos de aseo",
    "Otros",
]


def seed_categorias(apps, schema_editor):
    VGCategoriaGasto = apps.get_model('varagrill', 'VGCategoriaGasto')
    for nombre in CATEGORIAS_INICIALES:
        VGCategoriaGasto.objects.get_or_create(nombre=nombre)


def unseed_categorias(apps, schema_editor):
    VGCategoriaGasto = apps.get_model('varagrill', 'VGCategoriaGasto')
    VGCategoriaGasto.objects.filter(nombre__in=CATEGORIAS_INICIALES).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('varagrill', '0022_vgcategoriagasto_vggasto_vgabonogasto'),
    ]

    operations = [
        migrations.RunPython(seed_categorias, unseed_categorias),
    ]
