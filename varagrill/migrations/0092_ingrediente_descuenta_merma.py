from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('varagrill', '0091_alerta_stock_minimo'),
    ]

    operations = [
        migrations.AddField(
            model_name='vgingrediente',
            name='descuenta_merma',
            field=models.BooleanField(
                default=False,
                help_text=(
                    'Si está activo, al vender se descuenta del inventario lo que realmente se consumió: la cantidad de la '
                    'receta (en gramos aprovechables) x contenido del envase / peso real. Ej.: 500 g de aguacate en la '
                    'receta, con envase de 1000 g y peso real de 500 g, descuentan 1000 g. Solo aplica a g/ml con peso '
                    'real menor al envase. Se activa en Costeo > Configuración de merma, cuando las recetas de este '
                    'ingrediente están escritas en gramos ya limpios (no en gramos tal como se compran).'
                ),
            ),
        ),
    ]
