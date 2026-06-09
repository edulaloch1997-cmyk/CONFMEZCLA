from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('vinos', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='StockDetalle',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('cuba', models.CharField(blank=True, max_length=80)),
                ('cosecha', models.IntegerField(blank=True, null=True)),
                ('litros', models.FloatField(default=0)),
                ('bodega', models.CharField(blank=True, max_length=100)),
                ('grado_alc', models.CharField(blank=True, max_length=10)),
                ('stock', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name='detalles', to='vinos.stockmaterial')),
            ],
            options={'ordering': ['-cosecha', '-litros']},
        ),
    ]
