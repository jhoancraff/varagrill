from django.db import migrations


def seed_roles(apps, schema_editor):
    VGRol = apps.get_model('varagrill', 'VGRol')
    VGUsuario = apps.get_model('varagrill', 'VGUsuario')

    default_roles = [
        ('Administrador', 'Acceso completo al panel administrativo y gestión de usuarios.'),
        ('Analista', 'Acceso operativo a los módulos analíticos del sistema.'),
        ('Mesero', 'Registro y seguimiento de pedidos en sala.'),
        ('Cocinero', 'Gestión del flujo de pedidos en cocina.'),
    ]

    roles = {}
    for name, description in default_roles:
        role, _ = VGRol.objects.get_or_create(
            nombre_role=name,
            defaults={'descripcion': description},
        )
        roles[name] = role

    admin_role = roles['Administrador']
    VGUsuario.objects.filter(id_role__isnull=True, is_staff=True).update(id_role=admin_role)
    VGUsuario.objects.filter(id_role__isnull=True, is_superuser=True).update(id_role=admin_role, is_staff=True)


def unseed_roles(apps, schema_editor):
    VGRol = apps.get_model('varagrill', 'VGRol')
    VGRol.objects.filter(nombre_role__in=['Administrador', 'Analista', 'Mesero', 'Cocinero']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('varagrill', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_roles, unseed_roles),
    ]