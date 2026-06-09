from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='Temporada',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('anio', models.IntegerField(unique=True)),
                ('descripcion', models.CharField(blank=True, max_length=100)),
                ('activa', models.BooleanField(default=False)),
                ('fecha_carga', models.DateTimeField(auto_now_add=True)),
            ],
            options={'ordering': ['-anio']},
        ),
        migrations.CreateModel(
            name='Vino',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('codigo', models.IntegerField(unique=True)),
                ('descripcion', models.CharField(max_length=200)),
                ('calidad', models.CharField(blank=True, max_length=10)),
                ('color', models.CharField(blank=True, max_length=5)),
                ('enologo', models.CharField(blank=True, max_length=50)),
                ('variedad_principal_4d', models.CharField(blank=True, max_length=80)),
                ('estado', models.CharField(choices=[('vigente', 'Vigente'), ('descontinuado', 'Descontinuado')], default='vigente', max_length=20)),
                ('estado_mezcla', models.CharField(choices=[('vigente', 'Vigente'), ('no vigente', 'No Vigente'), ('descontinuado', 'Descontinuado')], default='vigente', max_length=20)),
                ('revision', models.CharField(choices=[('pendiente', 'Pendiente'), ('revisado', 'Revisado'), ('validado', 'Validado')], default='pendiente', max_length=20)),
                ('notas_revision', models.TextField(blank=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'ordering': ['codigo']},
        ),
        migrations.CreateModel(
            name='Material',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('codigo', models.IntegerField(unique=True)),
                ('descripcion', models.CharField(max_length=200)),
                ('variedad', models.CharField(blank=True, max_length=80)),
                ('calidad', models.CharField(blank=True, max_length=10)),
                ('valle', models.CharField(blank=True, max_length=80)),
                ('color', models.CharField(blank=True, max_length=5)),
            ],
            options={'ordering': ['codigo']},
        ),
        migrations.CreateModel(
            name='CorteStock',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('anio', models.IntegerField()),
                ('mes', models.IntegerField()),
                ('descripcion', models.CharField(blank=True, max_length=80)),
                ('fecha_carga', models.DateTimeField(auto_now_add=True)),
                ('es_vigente', models.BooleanField(default=False)),
                ('temporada', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='cortes_stock', to='vinos.temporada')),
            ],
            options={'ordering': ['-anio', '-mes']},
        ),
        migrations.AlterUniqueTogether(
            name='cortestock',
            unique_together={('temporada', 'anio', 'mes')},
        ),
        migrations.CreateModel(
            name='StockMaterial',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('litros_totales', models.FloatField(default=0)),
                ('precio_litro', models.FloatField(default=0)),
                ('aptitud_vinos', models.JSONField(default=list)),
                ('bodega', models.CharField(blank=True, max_length=100)),
                ('corte', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='vinos.cortestock')),
                ('material', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='stocks', to='vinos.material')),
                ('temporada', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='stocks', to='vinos.temporada')),
            ],
        ),
        migrations.AlterUniqueTogether(
            name='stockmaterial',
            unique_together={('corte', 'material')},
        ),
        migrations.CreateModel(
            name='PrecioMaterial',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('anio', models.IntegerField()),
                ('mes', models.IntegerField()),
                ('precio_litro', models.FloatField()),
                ('cantidad_litros', models.FloatField(default=0)),
                ('costo_total', models.FloatField(default=0)),
                ('fecha_carga', models.DateTimeField(auto_now_add=True)),
                ('material', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='precios', to='vinos.material')),
                ('temporada', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='precios', to='vinos.temporada')),
            ],
            options={'ordering': ['-anio', '-mes']},
        ),
        migrations.AlterUniqueTogether(
            name='preciomaterial',
            unique_together={('material', 'temporada', 'anio', 'mes')},
        ),
        migrations.CreateModel(
            name='Necesidad',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('litros', models.FloatField(default=0)),
                ('temporada', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='necesidades', to='vinos.temporada')),
                ('vino', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='necesidades', to='vinos.vino')),
            ],
        ),
        migrations.AlterUniqueTogether(
            name='necesidad',
            unique_together={('vino', 'temporada')},
        ),
        migrations.CreateModel(
            name='Configuracion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('participacion', models.FloatField(default=0)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('material', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='configuraciones', to='vinos.material')),
                ('temporada', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='configuraciones', to='vinos.temporada')),
                ('vino', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='configuraciones', to='vinos.vino')),
            ],
            options={'ordering': ['vino__codigo', '-participacion']},
        ),
        migrations.AlterUniqueTogether(
            name='configuracion',
            unique_together={('vino', 'temporada', 'material')},
        ),
        migrations.CreateModel(
            name='VentasVino',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('anio', models.IntegerField()),
                ('litros', models.FloatField(default=0)),
                ('cajas', models.FloatField(default=0)),
                ('notas', models.CharField(blank=True, max_length=200)),
                ('vino', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ventas', to='vinos.vino')),
            ],
            options={'ordering': ['vino__codigo', 'anio']},
        ),
        migrations.AlterUniqueTogether(
            name='ventasvino',
            unique_together={('vino', 'anio')},
        ),
    ]
