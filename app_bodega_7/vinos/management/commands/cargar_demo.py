"""python manage.py cargar_demo  — carga datos de ejemplo (idempotente, se puede correr N veces)"""
from django.core.management.base import BaseCommand
from vinos.models import (Temporada, Vino, Material, CorteStock,
                           StockMaterial, PrecioMaterial, Necesidad,
                           Configuracion, VentasVino)


class Command(BaseCommand):
    help = 'Carga datos de ejemplo (idempotente)'

    def handle(self, *args, **options):
        self.stdout.write('Cargando datos de ejemplo...')

        # Temporadas
        t26, _ = Temporada.objects.get_or_create(anio=2026,
                   defaults={'descripcion': 'Estándar 2026', 'activa': True})
        t25, _ = Temporada.objects.get_or_create(anio=2025,
                   defaults={'descripcion': 'Referencia 2025'})

        # Vinos — update_or_create = idempotente
        v1, _ = Vino.objects.update_or_create(codigo=1130, defaults={
            'descripcion': 'MEZCLA BLANCO GE SEMI DULCE', 'calidad': 'GE',
            'color': 'B', 'enologo': 'MWEINLAUB', 'variedad_principal_4d': 'Mezcla',
            'estado_mezcla': 'vigente'})
        v2, _ = Vino.objects.update_or_create(codigo=1100, defaults={
            'descripcion': 'CHARDONNAY PR CHILE CDD RVA.', 'calidad': 'PR',
            'color': 'B', 'enologo': 'JSOLARI', 'variedad_principal_4d': 'Chardonnay',
            'estado_mezcla': 'vigente'})
        v3, _ = Vino.objects.update_or_create(codigo=2115, defaults={
            'descripcion': 'CARMENERE PR', 'calidad': 'PR',
            'color': 'T', 'enologo': 'AFUENTES', 'variedad_principal_4d': 'Carménère',
            'estado_mezcla': 'vigente'})
        v4, _ = Vino.objects.update_or_create(codigo=1099, defaults={
            'descripcion': 'CHARDONNAY UP AMELIA', 'calidad': 'UP',
            'color': 'B', 'enologo': 'MPAPA', 'variedad_principal_4d': 'Chardonnay',
            'estado_mezcla': 'vigente'})
        v5, _ = Vino.objects.update_or_create(codigo=2180, defaults={
            'descripcion': 'CARMENERE VA', 'calidad': 'VA',
            'color': 'T', 'enologo': 'MPAPA', 'variedad_principal_4d': 'Carménère',
            'estado_mezcla': 'no vigente'})

        # Materiales
        mats_data = [
            (160910, 'CYT VINO PEDRO JIMENEZ GE LIMARI',      'Pedro Jiménez',    'GE', 'Limarí',    'B'),
            (266300, 'CYT VINO TINTO DECOLORADO GE S/D.O.',   'Tinto Decolorado', 'GE', 'Central',   'T'),
            (266000, 'CYT VINO BLANCO VINIFERO GE S/D.O.',    'Blanco Vinífero',  'GE', 'Central',   'B'),
            (101850, 'CYT VINO CHARDONNAY PR CASABLANCA',      'Chardonnay',       'PR', 'Casablanca','B'),
            (101750, 'CYT VINO CHARDONNAY PR LIMARI',          'Chardonnay',       'PR', 'Limarí',    'B'),
            (200100, 'CYT VINO CARMENERE PR MAULE',            'Carménère',        'PR', 'Maule',     'T'),
            (160960, 'CYT VINO PEDRO JIMENEZ GE CHOAPA',       'Pedro Jiménez',    'GE', 'Choapa',    'B'),
            (140910, 'CYT VINO MOSCATEL ALEJANDRIA GE LIMARI', 'Moscatel',         'GE', 'Limarí',    'B'),
        ]
        mats = {}
        for cod, desc, var, cal, val, col in mats_data:
            m, _ = Material.objects.update_or_create(codigo=cod, defaults={
                'descripcion': desc, 'variedad': var, 'calidad': cal,
                'valle': val, 'color': col})
            mats[cod] = m

        # Corte stock — delete items and recreate (clean)
        CorteStock.objects.filter(temporada=t26, es_vigente=True).update(es_vigente=False)
        corte, _ = CorteStock.objects.get_or_create(
            temporada=t26, anio=2026, mes=10,
            defaults={'descripcion': 'Oct 2026', 'es_vigente': True})
        corte.es_vigente = True
        corte.save()
        StockMaterial.objects.filter(corte=corte).delete()  # clean before recreate

        # Multi-bodega: same material can appear in multiple bodegas
        stock_data = [
            # 160910 en DOS bodegas (5.200.000 + 3.834.241 = 9.034.241 L total)
            (160910, 5200000, 293.28, [1130],       'Bodega Norte'),
            (160910, 3834241, 293.28, [1130],       'Bodega Sur'),
            # 266300 en una sola bodega
            (266300, 3139622, 303.18, [1130],       'Bodega Sur'),
            (266000,  898926, 440.71, [1130],       'Bodega Central'),
            # 101850 en DOS bodegas (1.200.000 + 900.000 = 2.100.000 L total)
            (101850, 1200000, 938.91, [1100],       'Crianza A'),
            (101850,  900000, 938.91, [1100],       'Crianza B'),
            (101750, 1800000, 605.66, [1100, 1099], 'Crianza B'),
            (200100,  950000, 710.00, [2115, 2180], 'Guarda 1'),
            (160960,  543367, 458.07, [1130],       'Bodega Norte'),
            (140910,  478432, 243.74, [1130],       'Bodega Central'),
        ]
        for cod, litros, precio, apt, bodega in stock_data:
            StockMaterial.objects.create(
                corte=corte, temporada=t26, material=mats[cod],
                litros_totales=litros, precio_litro=precio,
                aptitud_vinos=apt, bodega=bodega)

        # Necesidades — update_or_create
        for vino, litros in [(v1,4119647),(v2,84962),(v3,320000),(v4,45000),(v5,0)]:
            Necesidad.objects.update_or_create(
                vino=vino, temporada=t26, defaults={'litros': litros})

        # Configuraciones 2026 — delete all then recreate (avoid duplicates)
        Configuracion.objects.filter(temporada=t26).delete()
        configs_26 = [
            (v1, 160910, 0.491033), (v1, 266300, 0.266000), (v1, 266000, 0.119000),
            (v1, 160960, 0.074000), (v1, 140910, 0.030000), (v1, 266300, 0.020000),
            (v2, 101850, 0.650000), (v2, 101750, 0.350000),
            (v3, 200100, 1.000000),
            (v4, 101750, 0.800000), (v4, 101850, 0.200000),
            (v5, 200100, 1.000000),
        ]
        # Deduplicate: keep last pct per (vino, material)
        seen = {}
        for vino, mat_cod, pct in configs_26:
            seen[(vino.id, mat_cod)] = (vino, mat_cod, pct)
        Configuracion.objects.bulk_create([
            Configuracion(vino=vino, temporada=t26, material=mats[mat_cod], participacion=pct)
            for (vino, mat_cod, pct) in seen.values()
        ])

        # Configuraciones 2025 (referencia)
        Configuracion.objects.filter(temporada=t25).delete()
        configs_25 = [
            (v1, 160910, 0.491033), (v1, 266300, 0.300000), (v1, 266000, 0.100000),
            (v1, 160960, 0.074000), (v1, 140910, 0.035000),
            (v2, 101850, 0.700000), (v2, 101750, 0.300000),
            (v3, 200100, 1.000000),
            (v4, 101750, 0.750000), (v4, 101850, 0.250000),
        ]
        Configuracion.objects.bulk_create([
            Configuracion(vino=vino, temporada=t25, material=mats[mat_cod], participacion=pct)
            for vino, mat_cod, pct in configs_25
        ])

        # Precios
        for cod, pp, cant in [
            (160910,293.28,9034241),(266300,303.18,3139622),(266000,440.71,898926),
            (101850,938.91,2100000),(101750,605.66,1800000),(200100,710.00,950000),
            (160960,458.07,543367), (140910,243.74,478432)]:
            PrecioMaterial.objects.update_or_create(
                material=mats[cod], temporada=t26, anio=2026, mes=10,
                defaults={'precio_litro': pp, 'cantidad_litros': cant})

        # Ventas históricas
        for vino, anio, litros, cajas in [
            (v1,2023,3200000,266667),(v1,2024,3450000,287500),(v1,2025,3600000,300000),
            (v2,2023,68000,5667),(v2,2024,75000,6250),(v2,2025,82000,6833),
            (v3,2023,260000,21667),(v3,2024,290000,24167),(v3,2025,315000,26250),
            (v4,2023,38000,3167),(v4,2024,40000,3333),(v4,2025,43000,3583)]:
            VentasVino.objects.update_or_create(
                vino=vino, anio=anio, defaults={'litros': litros, 'cajas': cajas})

        self.stdout.write(self.style.SUCCESS(
            '\n✓ Datos de ejemplo cargados (idempotente):\n'
            '  5 vinos | 8 materiales | Stock Oct 2026\n'
            '  Configs 2026 + referencia 2025 | Precios | Ventas 2023-2025\n\n'
            'Abre http://127.0.0.1:8000'
        ))
