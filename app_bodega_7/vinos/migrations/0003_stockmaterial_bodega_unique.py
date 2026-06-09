from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('vinos', '0002_stockdetalle'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='stockmaterial',
            unique_together={('corte', 'material', 'bodega')},
        ),
    ]
