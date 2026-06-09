# Simulador Estándar de Mezclas

## Arranque rápido (3 comandos)

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py cargar_demo
python manage.py runserver
```

Abre http://127.0.0.1:8000 — tendrás 5 vinos con stock, precios y ventas de ejemplo.

## Cargar tus datos reales

```bash
python manage.py importar_excel --file BASE_COSTO_ESTANDAR_2027.xlsx --anio 2026 --modo original
```

O desde la app: botón **📂 Cargar Excel** en la barra superior.

## Iniciar año nuevo (ej. 2027)

```bash
python manage.py copiar_temporada --origen 2026 --destino 2027
```

O desde la app: botón **📅 Nuevo año**.

## Vistas

| URL | Descripción |
|-----|-------------|
| `/` | Gestión completa (lista, filtros, editor con pestañas) |
| `/simulador/` | Vista simulador con sliders y datos desde BD |

## Plantillas Excel disponibles (bases a cargar)

| Plantilla | Hoja(s) requeridas |
|-----------|--------------------|
| BASE_MEZCLAS | BASE |
| STOCK | STOCK |
| NECESIDADES_PRECIOS | NECESIDADES + PRECIOS |
| VENTAS | VENTAS |
| VARIEDAD_4D | incluir columna Variedad_Principal_4D en BASE |

## PythonAnywhere

```bash
pip install -r requirements.txt --user
python manage.py migrate
python manage.py cargar_demo        # o importar_excel con tus datos
python manage.py collectstatic --noinput
```

En settings.py: `DEBUG = False`, agrega tu dominio en `ALLOWED_HOSTS`.
