from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        ('vinos', '0003_stockmaterial_bodega_unique'),
    ]

    operations = [
        migrations.AddField(
            model_name='temporada',
            name='bloqueada',
            field=models.BooleanField(default=False,
                help_text='Configuración bloqueada: precios no se actualizan al cargar Excel'),
        ),
        migrations.CreateModel(
            name='PerfilUsuario',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True)),
                ('enologos', models.JSONField(default=list,
                    help_text='Lista de enólogos que puede ver. Vacío = todos.')),
                ('solo_lectura', models.BooleanField(default=False)),
                ('usuario', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='perfil_enologo',
                    to='auth.user')),
            ],
        ),
    ]
