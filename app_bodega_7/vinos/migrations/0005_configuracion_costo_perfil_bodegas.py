from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('vinos', '0004_bloqueada_perfilusuario'),
    ]

    operations = [
        migrations.AddField(
            model_name='configuracion',
            name='costo_litro_guardado',
            field=models.FloatField(default=0,
                help_text='Precio $/L al momento de guardar esta configuración'),
        ),
        migrations.AddField(
            model_name='perfilusuario',
            name='bodegas',
            field=models.JSONField(default=list,
                help_text='Lista de bodegas que puede ver. Vacío = todas.'),
        ),
    ]
