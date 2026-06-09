from django.urls import path
from . import views

urlpatterns = [
    # páginas
    path('', views.index, name='index'),
    path('simulador/', views.simulador, name='simulador'),
    # vinos
    path('api/vinos/', views.api_vinos),
    path('api/vinos/<int:codigo>/', views.api_vino_detalle),
    path('api/vinos/<int:codigo>/guardar/', views.api_guardar_config),
    path('api/vinos/<int:codigo>/estado/', views.api_vino_estado),
    path('api/filtros/', views.api_filtros),
    # stock
    path('api/stock/', views.api_stock),
    path('api/stock/<int:material_codigo>/detalle/', views.api_stock_detalle),
    path('api/stock/cortes/', views.api_cortes_stock),
    path('api/stock/cortes/todos/', views.api_todos_cortes),
    path('api/stock/corte-reciente/', views.api_corte_reciente),
    path('api/stock/cortes/<int:corte_id>/vigente/', views.api_set_corte_vigente),
    # precios
    path('api/precios/', views.api_precios_resumen),
    path('api/precios/evolutivo/', views.api_precios_evolutivo),
    # ventas y resúmenes
    path('api/ventas/', views.api_ventas_resumen),
    path('api/resumen/', views.api_resumen_global),
    path('api/resumen/variedad/', views.api_resumen_variedad),
    path('api/temporadas/', views.api_temporadas),
    # acciones
    path('api/copiar-temporada/', views.api_copiar_temporada),
    path('api/upload-excel/', views.api_upload_excel),
    path('api/exportar/', views.api_exportar),
]
