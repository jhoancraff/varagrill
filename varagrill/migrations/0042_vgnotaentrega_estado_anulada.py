from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('varagrill', '0041_vgcorreccionmetodopago'),
    ]

    operations = [
        migrations.AlterField(
            model_name='vgnotaentrega',
            name='estado',
            field=models.CharField(
                choices=[
                    ('pendiente_pago', 'Pendiente de pago'),
                    ('abonada_parcial', 'Abonada parcialmente'),
                    ('pagada', 'Pagada'),
                    ('anulada', 'Anulada'),
                ],
                default='pendiente_pago',
                max_length=20,
            ),
        ),
    ]