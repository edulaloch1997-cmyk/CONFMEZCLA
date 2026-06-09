"""
python manage.py importar_excel --file archivo.xlsx --anio 2026 [--mes 10] [--modo original|plantilla]
"""
import pandas as pd
from datetime import datetime
from django.core.management.base import BaseCommand, CommandError
from vinos.models import (Temporada, Vino, Material, CorteStock,
                          StockMaterial, StockDetalle, PrecioMaterial,
                          Necesidad, Configuracion, VentasVino)


def to_float(val, default=0.0):
    try:
        v = float(val)
        return v if v == v else default
    except (TypeError, ValueError):
        return default


def to_int(val):
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return None


def find_sheet(sheets_upper, *keys):
    """Busca la primera hoja que contenga alguna de las claves."""
    for key in keys:
        for k, v in sheets_upper.items():
            if key in k:
                return v
    return None


class Command(BaseCommand):
    help = 'Importa bases desde Excel'

    def add_arguments(self, parser):
        parser.add_argument('--file', required=True)
        parser.add_argument('--anio', type=int, required=True)
        parser.add_argument('--mes', type=int, default=None)
        parser.add_argument('--modo', default='auto',
                            choices=['auto', 'plantilla', 'original'])
        parser.add_argument('--solo-stock', action='store_true')
        parser.add_argument('--solo-precios', action='store_true')

    def handle(self, *args, **options):
        path = options['file']
        anio = options['anio']
        mes = options['mes'] or datetime.now().month
        modo = options['modo']

        xl = pd.ExcelFile(path)
        sheets_upper = {s.upper(): s for s in xl.sheet_names}

        if modo == 'auto':
            modo = 'original' if any(
                k in sheets_upper for k in ['STOCK OCT', 'TD$CON COMPRA UVA']
            ) else 'plantilla'

        temporada, _ = Temporada.objects.get_or_create(anio=anio)

        if not options['solo_stock'] and not options['solo_precios']:
            self._import_configs(xl, sheets_upper, temporada, anio, modo)
            self._import_necesidades(xl, sheets_upper, temporada, modo)
            self._import_ventas(xl, sheets_upper)

        self._import_stock(xl, sheets_upper, temporada, anio, mes, modo)
        self._import_precios(xl, sheets_upper, temporada, anio, mes, modo)

        self.stdout.write(self.style.SUCCESS(
            f'✓ Importación completa — temporada {anio}, corte {mes}/{anio}'
        ))

    # ── CONFIGURACIONES ───────────────────────────────────────────────
    def _import_configs(self, xl, sheets, temporada, anio, modo):
        sheet_name = find_sheet(sheets, 'BASE')
        if not sheet_name:
            self.stdout.write('  ⚠ Sin hoja BASE')
            return

        df = xl.parse(sheet_name, header=0)
        df.columns = [str(c).strip() for c in df.columns]

        # Detectar columnas según modo
        if modo == 'original':
            col_cod   = next((c for c in df.columns if c in ('Código', 'Codigo')), None)
            col_mat   = next((c for c in df.columns if c == 'Material'), None)
            col_dv    = next((c for c in df.columns if 'Descripci' in c and 'Vino' in c), None)
            col_dm    = next((c for c in df.columns if 'breve' in c.lower()), None)
            col_p26   = next((c for c in df.columns if 'Nueva' in c or 'Part2026' in c), None)
            col_p24   = next((c for c in df.columns if 'Ultima' in c or 'Part2024' in c), None)
            col_cal   = next((c for c in df.columns if 'Calidad 4D' in c or c == 'Calidad'), None)
            col_col   = next((c for c in df.columns if 'Color 4D' in c or c == 'Color'), None)
            col_enol  = next((c for c in df.columns if 'Enologo' in c or 'Enólogo' in c), None)
            col_var4d = next((c for c in df.columns if 'Variedad 4D' in c), None)
            col_em    = next((c for c in df.columns if 'Estado' in c and 'Mezcla' not in c), None)
            col_em2   = next((c for c in df.columns if 'Estado_Mezcla' in c or 'EstadoMezcla' in c), None)
            col_var6d = next((c for c in df.columns if 'Variedad 6D' in c), None)
            col_cal6d = next((c for c in df.columns if 'Calidad 6D' in c), None)
            col_val6d = next((c for c in df.columns if 'Valle 6D' in c), None)
            col_col6d = next((c for c in df.columns if 'Color 6D' in c), None)
        else:
            col_cod   = next((c for c in df.columns if 'Codigo' in c and 'Comp' not in c and 'Material' not in c), None)
            col_mat   = next((c for c in df.columns if c == 'Material'), None)
            col_dv    = next((c for c in df.columns if 'Descripcion_Vino' in c or 'Descripcion Vino' in c), None)
            col_dm    = next((c for c in df.columns if 'DescripcionComp' in c or 'Descripcion_Comp' in c), None)
            col_p26   = next((c for c in df.columns if 'Part2026' in c), None)
            col_p24   = next((c for c in df.columns if 'Part2024' in c), None)
            col_cal   = next((c for c in df.columns if 'Calidad' in c and '6D' not in c), None)
            col_col   = next((c for c in df.columns if 'Color' in c and '6D' not in c), None)
            col_enol  = next((c for c in df.columns if 'Enologo' in c), None)
            col_var4d = next((c for c in df.columns if 'Variedad_Principal' in c or 'Variedad Principal' in c), None)
            col_em2   = next((c for c in df.columns if 'Estado_Mezcla' in c or 'EstadoMezcla' in c), None)
            col_em    = None
            col_var6d = next((c for c in df.columns if 'Variedad' in c and '6D' not in c and 'Principal' not in c), None)
            col_cal6d = col_cal
            col_val6d = next((c for c in df.columns if 'Valle' in c), None)
            col_col6d = col_col

        if not col_cod or not col_mat:
            self.stdout.write(f'  ⚠ BASE: no se encontraron columnas Codigo/Material. Columnas: {list(df.columns)}')
            return

        df[col_cod] = pd.to_numeric(df[col_cod], errors='coerce')
        df[col_mat] = pd.to_numeric(df[col_mat], errors='coerce')
        df = df.dropna(subset=[col_cod, col_mat])

        anio_ref = anio - 1
        temp_ref, _ = Temporada.objects.get_or_create(anio=anio_ref)

        for _, row in df.iterrows():
            cod_v = to_int(row[col_cod])
            cod_m = to_int(row[col_mat])
            if not cod_v or not cod_m:
                continue

            estado_raw = str(row.get(col_em2 or col_em or '__', '') or '').lower()
            em = 'no vigente' if 'no vig' in estado_raw else (
                 'descontinuado' if 'desc' in estado_raw else 'vigente')
            estado_vino = 'descontinuado' if 'desc' in str(row.get(col_em or '__', '') or '').lower() else 'vigente'

            vino, _ = Vino.objects.update_or_create(
                codigo=cod_v,
                defaults={
                    'descripcion': str(row.get(col_dv or '__', '') or ''),
                    'calidad': str(row.get(col_cal or '__', '') or ''),
                    'color': str(row.get(col_col or '__', '') or ''),
                    'enologo': str(row.get(col_enol or '__', '') or ''),
                    'variedad_principal_4d': str(row.get(col_var4d or '__', '') or ''),
                    'estado': estado_vino,
                    'estado_mezcla': em,
                }
            )

            Material.objects.update_or_create(
                codigo=cod_m,
                defaults={
                    'descripcion': str(row.get(col_dm or '__', '') or ''),
                    'variedad': str(row.get(col_var6d or '__', '') or ''),
                    'calidad': str(row.get(col_cal6d or '__', '') or ''),
                    'valle': str(row.get(col_val6d or '__', '') or ''),
                    'color': str(row.get(col_col6d or '__', '') or ''),
                }
            )

            try:
                mat = Material.objects.get(codigo=cod_m)
            except Material.DoesNotExist:
                continue

            pct26 = to_float(row.get(col_p26 or '__', 0))
            pct24 = to_float(row.get(col_p24 or '__', 0))

            if pct26 > 0:
                Configuracion.objects.update_or_create(
                    vino=vino, temporada=temporada, material=mat,
                    defaults={'participacion': pct26}
                )
            if pct24 > 0:
                Configuracion.objects.update_or_create(
                    vino=vino, temporada=temp_ref, material=mat,
                    defaults={'participacion': pct24}
                )

        self.stdout.write(f'  Configuraciones {anio}: {Configuracion.objects.filter(temporada=temporada).count()}')

    # ── STOCK ─────────────────────────────────────────────────────────
    def _import_stock(self, xl, sheets, temporada, anio, mes, modo):
        sheet_name = find_sheet(sheets, 'STOCK')
        if not sheet_name:
            self.stdout.write('  ⚠ Sin hoja STOCK')
            return

        df = xl.parse(sheet_name, header=0)
        df.columns = [str(c).strip() for c in df.columns]

        col_mat  = next((c for c in df.columns if 'Material' in c and 'Texto' not in c and 'breve' not in c.lower()), None)
        col_cant = next((c for c in df.columns if 'Cant' in c or 'Cantidad' in c or 'Litros' in c), None)
        col_apt  = next((c for c in df.columns if 'Aptitud' in c), None)
        col_desc = next((c for c in df.columns if 'Texto' in c or 'breve' in c.lower() or 'Descripci' in c), None)
        col_precio = next((c for c in df.columns if 'Precio' in c or 'PP' in c), None)
        col_var  = next((c for c in df.columns if 'Variedad' in c), None)
        col_cal  = next((c for c in df.columns if 'Calidad' in c), None)
        col_val  = next((c for c in df.columns if 'Valle' in c), None)
        col_col  = next((c for c in df.columns if 'Color' in c), None)
        col_bod  = next((c for c in df.columns if 'Bodega' in c or 'bodega' in c.lower() or 'Almac' in c), None)

        if not col_mat or not col_cant:
            self.stdout.write(f'  ⚠ STOCK: columnas no encontradas. Disponibles: {list(df.columns)}')
            return

        df[col_mat]  = pd.to_numeric(df[col_mat], errors='coerce')
        df[col_cant] = pd.to_numeric(df[col_cant], errors='coerce').fillna(0)
        if col_apt:
            df[col_apt] = pd.to_numeric(df[col_apt], errors='coerce')
        df = df[df[col_mat].notna()].copy()

        # Aggregate by material
        agg_dict = {'litros': (col_cant, 'sum')}
        for alias, src in [('desc', col_desc), ('precio', col_precio), ('variedad', col_var),
                            ('calidad', col_cal), ('valle', col_val), ('color', col_col),
                            ('bodega', col_bod)]:
            if src:
                agg_dict[alias] = (src, 'first')

        stock_agg = df.groupby(col_mat).agg(**agg_dict).reset_index()

        # Check if a material appears in multiple bodegas
        if col_bod:
            multi_bod = (df.groupby(col_mat)[col_bod]
                         .apply(lambda x: x.nunique() > 1)
                         .to_dict())
        else:
            multi_bod = {}

        apt_map = {}
        if col_apt:
            apt_map = (df.dropna(subset=[col_apt])
                       .groupby(col_mat)[col_apt]
                       .apply(lambda x: [int(v) for v in x.unique()])
                       .to_dict())

        # Crear corte
        CorteStock.objects.filter(temporada=temporada, es_vigente=True).update(es_vigente=False)
        corte, _ = CorteStock.objects.get_or_create(
            temporada=temporada, anio=anio, mes=mes,
            defaults={'es_vigente': True}
        )
        corte.es_vigente = True
        corte.save()
        StockMaterial.objects.filter(corte=corte).delete()

        # Also detect cosecha and cuba columns
        col_cosecha = next((c for c in df.columns if 'cosecha' in c.lower() or 'coseha' in c.lower() or 'año cosecha' in c.lower()), None)
        col_cuba    = next((c for c in df.columns if 'vasija' in c.lower() or 'cuba' in c.lower() or 'envase' in c.lower()), None)
        col_grado   = next((c for c in df.columns if 'grado' in c.lower() or 'alc' in c.lower()), None)

        count = 0
        for _, row in stock_agg.iterrows():
            cod_m = to_int(row[col_mat])
            if not cod_m:
                continue
            mat, _ = Material.objects.update_or_create(
                codigo=cod_m,
                defaults={
                    'descripcion': str(row.get('desc', '') or ''),
                    'variedad':    str(row.get('variedad', '') or ''),
                    'calidad':     str(row.get('calidad', '') or ''),
                    'valle':       str(row.get('valle', '') or ''),
                    'color':       str(row.get('color', '') or ''),
                }
            )
            # If this material has stock in multiple bodegas, mark as 'Varias'
            mat_cod_key = row[col_mat]
            is_multi = multi_bod.get(mat_cod_key, False)
            bodega_display = 'Varias' if is_multi else str(row.get('bodega', '') or '')

            sm = StockMaterial.objects.create(
                corte=corte, temporada=temporada, material=mat,
                litros_totales=to_float(row['litros']),
                precio_litro=to_float(row.get('precio', 0)),
                aptitud_vinos=apt_map.get(mat_cod_key, []),
                bodega=bodega_display,
            )

            # Save individual lines (detalles) for this material
            filas_mat = df[df[col_mat] == row[col_mat]]
            detalles = []
            for _, fila in filas_mat.iterrows():
                cosecha = to_int(fila[col_cosecha]) if col_cosecha else None
                cuba    = str(fila[col_cuba] or '') if col_cuba else ''
                grado   = str(fila[col_grado] or '') if col_grado else ''
                bod     = str(fila[col_bod] or '') if col_bod else ''
                litros  = to_float(fila[col_cant])
                if litros > 0:
                    detalles.append(StockDetalle(
                        stock=sm, cuba=cuba, cosecha=cosecha,
                        litros=litros, bodega=bod, grado_alc=grado,
                    ))
            if detalles:
                StockDetalle.objects.bulk_create(detalles)
            count += 1

        self.stdout.write(f'  Stock {corte}: {count} materiales (vigente)')

    # ── PRECIOS ───────────────────────────────────────────────────────
    def _import_precios(self, xl, sheets, temporada, anio, mes, modo):
        sheet_name = find_sheet(sheets, 'PRECIO', 'TD$')
        if not sheet_name:
            return

        if 'TD$' in sheet_name.upper():
            df = xl.parse(sheet_name, header=None, usecols='A:D')
            df.columns = ['material', 'cantidad', 'costo_total', 'pp']
            df = df.iloc[2:].copy()
        else:
            df = xl.parse(sheet_name, header=0)
            df.columns = [str(c).strip() for c in df.columns]
            col_m = next((c for c in df.columns if 'Material' in c), None)
            col_p = next((c for c in df.columns if 'PP' in c or 'Precio' in c or 'precio' in c.lower()), None)
            col_q = next((c for c in df.columns if 'Cantidad' in c or 'cantidad' in c.lower()), None)
            col_ct = next((c for c in df.columns if 'Costo' in c and 'total' in c.lower()), None)
            if not col_m or not col_p:
                return
            df = df.rename(columns={col_m: 'material', col_p: 'pp',
                                     col_q or '__': 'cantidad', col_ct or '__': 'costo_total'})

        df['material'] = pd.to_numeric(df['material'], errors='coerce')
        df['pp'] = pd.to_numeric(df['pp'], errors='coerce')
        df['cantidad'] = pd.to_numeric(df.get('cantidad', 0), errors='coerce').fillna(0)
        df['costo_total'] = pd.to_numeric(df.get('costo_total', 0), errors='coerce').fillna(0)
        df = df.dropna(subset=['material', 'pp'])

        count = 0
        for _, row in df.iterrows():
            cod_m = to_int(row['material'])
            pp = to_float(row['pp'])
            if not cod_m or not pp:
                continue
            mat, _ = Material.objects.get_or_create(codigo=cod_m,
                                                     defaults={'descripcion': str(cod_m)})
            PrecioMaterial.objects.update_or_create(
                material=mat, temporada=temporada, anio=anio, mes=mes,
                defaults={'precio_litro': pp,
                          'cantidad_litros': to_float(row.get('cantidad', 0)),
                          'costo_total': to_float(row.get('costo_total', 0))}
            )
            # Actualizar precio en stock vigente
            StockMaterial.objects.filter(
                material=mat, corte__es_vigente=True, temporada=temporada
            ).update(precio_litro=pp)
            count += 1

        self.stdout.write(f'  Precios {mes}/{anio}: {count} materiales')

    # ── NECESIDADES ───────────────────────────────────────────────────
    def _import_necesidades(self, xl, sheets, temporada, modo):
        sheet_name = find_sheet(sheets, 'NECESIDAD', 'PRODUCCI')
        if not sheet_name:
            return

        df = xl.parse(sheet_name, header=0, usecols='A:B')
        df.columns = ['codigo', 'necesidad']
        df['codigo']    = pd.to_numeric(df['codigo'], errors='coerce')
        df['necesidad'] = pd.to_numeric(df['necesidad'], errors='coerce')
        df = df.dropna(subset=['codigo'])

        count = 0
        for _, row in df.iterrows():
            cod = to_int(row['codigo'])
            nec = to_float(row['necesidad'])
            if not cod:
                continue
            try:
                vino = Vino.objects.get(codigo=cod)
                Necesidad.objects.update_or_create(
                    vino=vino, temporada=temporada,
                    defaults={'litros': abs(nec) if nec < 0 else 0}
                )
                count += 1
            except Vino.DoesNotExist:
                pass

        self.stdout.write(f'  Necesidades: {count} vinos')

    # ── VENTAS ────────────────────────────────────────────────────────
    def _import_ventas(self, xl, sheets):
        sheet_name = find_sheet(sheets, 'VENTA')
        if not sheet_name:
            return

        df = xl.parse(sheet_name, header=0)
        df.columns = [str(c).strip() for c in df.columns]

        col_cod  = next((c for c in df.columns if 'Codigo' in c or 'Código' in c), None)
        col_anio = next((c for c in df.columns if 'Anio' in c or 'Año' in c or 'anio' in c.lower()), None)
        col_lit  = next((c for c in df.columns if 'Litro' in c or 'litro' in c.lower()), None)
        col_caj  = next((c for c in df.columns if 'Caja' in c or 'caja' in c.lower()), None)

        if not col_cod or not col_anio or not col_lit:
            self.stdout.write(f'  ⚠ VENTAS: columnas no encontradas. Disponibles: {list(df.columns)}')
            return

        df[col_cod]  = pd.to_numeric(df[col_cod], errors='coerce')
        df[col_anio] = pd.to_numeric(df[col_anio], errors='coerce')
        df[col_lit]  = pd.to_numeric(df[col_lit], errors='coerce').fillna(0)
        df = df.dropna(subset=[col_cod, col_anio])

        count = 0
        for _, row in df.iterrows():
            cod  = to_int(row[col_cod])
            anio = to_int(row[col_anio])
            if not cod or not anio:
                continue
            try:
                vino = Vino.objects.get(codigo=cod)
                VentasVino.objects.update_or_create(
                    vino=vino, anio=anio,
                    defaults={
                        'litros': to_float(row[col_lit]),
                        'cajas': to_float(row[col_caj]) if col_caj else 0,
                    }
                )
                count += 1
            except Vino.DoesNotExist:
                pass

        self.stdout.write(f'  Ventas: {count} registros')
