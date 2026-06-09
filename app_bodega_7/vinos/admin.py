from django.contrib import admin
from .models import (Temporada, Vino, Material, CorteStock, StockMaterial,
                     PrecioMaterial, Necesidad, Configuracion, VentasVino)


@admin.register(Temporada)
class TemporadaAdmin(admin.ModelAdmin):
    list_display = ('anio', 'descripcion', 'activa', 'fecha_carga')
    list_editable = ('activa',)
    ordering = ('-anio',)


@admin.register(Vino)
class VinoAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'descripcion', 'calidad', 'color', 'enologo',
                    'variedad_principal_4d', 'estado_mezcla', 'revision', 'updated_at')
    list_filter = ('calidad', 'color', 'enologo', 'estado_mezcla', 'revision',
                   'variedad_principal_4d')
    search_fields = ('codigo', 'descripcion', 'enologo')
    list_editable = ('estado_mezcla', 'revision')
    ordering = ('codigo',)


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'descripcion', 'variedad', 'calidad', 'valle', 'color')
    list_filter = ('calidad', 'color', 'variedad')
    search_fields = ('codigo', 'descripcion', 'variedad', 'valle')
    ordering = ('codigo',)


@admin.register(CorteStock)
class CorteStockAdmin(admin.ModelAdmin):
    list_display = ('descripcion', 'temporada', 'anio', 'mes', 'es_vigente',
                    'fecha_carga', 'n_materiales')
    list_filter = ('temporada', 'es_vigente')
    list_editable = ('es_vigente',)
    ordering = ('-anio', '-mes')

    def n_materiales(self, obj):
        return obj.items.count()
    n_materiales.short_description = '# Materiales'


@admin.register(StockMaterial)
class StockMaterialAdmin(admin.ModelAdmin):
    list_display = ('material', 'corte', 'temporada', 'litros_totales',
                    'precio_litro', 'bodega', 'aptitud_vinos')
    list_filter = ('temporada', 'bodega', 'corte')
    search_fields = ('material__codigo', 'material__descripcion', 'bodega')
    ordering = ('material__codigo',)


@admin.register(PrecioMaterial)
class PrecioMaterialAdmin(admin.ModelAdmin):
    list_display = ('material', 'temporada', 'anio', 'mes', 'precio_litro',
                    'cantidad_litros', 'fecha_carga')
    list_filter = ('temporada', 'anio', 'mes')
    search_fields = ('material__codigo', 'material__descripcion')
    ordering = ('material__codigo', '-anio', '-mes')


@admin.register(Necesidad)
class NecesidadAdmin(admin.ModelAdmin):
    list_display = ('vino', 'temporada', 'litros')
    list_filter = ('temporada',)
    search_fields = ('vino__codigo', 'vino__descripcion')
    ordering = ('vino__codigo',)


@admin.register(Configuracion)
class ConfiguracionAdmin(admin.ModelAdmin):
    list_display = ('vino', 'temporada', 'material', 'participacion', 'updated_at')
    list_filter = ('temporada', 'vino__calidad')
    search_fields = ('vino__codigo', 'vino__descripcion', 'material__codigo')
    ordering = ('vino__codigo', '-participacion')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('vino', 'material', 'temporada')


@admin.register(VentasVino)
class VentasVinoAdmin(admin.ModelAdmin):
    list_display = ('vino', 'anio', 'litros', 'cajas', 'notas')
    list_filter = ('anio', 'vino__calidad')
    search_fields = ('vino__codigo', 'vino__descripcion')
    ordering = ('vino__codigo', 'anio')
