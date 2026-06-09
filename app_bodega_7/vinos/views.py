import json
import csv
import tempfile
import os
from datetime import datetime

from django.db import models
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

from .models import (Temporada, Vino, Material, CorteStock, StockMaterial,
                     StockDetalle, PrecioMaterial, Necesidad, Configuracion, VentasVino)


# ── HELPERS ───────────────────────────────────────────────────────────

def get_vigente_stock(temporada_id):
    c = CorteStock.objects.filter(temporada_id=temporada_id, es_vigente=True).first()
    if not c:
        c = CorteStock.objects.filter(temporada_id=temporada_id).order_by('-anio', '-mes').first()
    return c


def build_stock_map(temporada_id=None, corte_id=None):
    """material_codigo -> {litros, precio, aptitud, bodega}
    Si se pasa corte_id, usa ese corte directamente.
    Si no, usa el corte vigente de la temporada (o el más reciente global).
    """
    if corte_id:
        corte = CorteStock.objects.filter(id=corte_id).first()
    elif temporada_id:
        corte = get_vigente_stock(temporada_id)
    else:
        corte = None

    # Fallback: corte más reciente de cualquier temporada
    if not corte:
        corte = CorteStock.objects.order_by('-anio', '-mes').first()
    if not corte:
        return {}

    # Aggregate multiple bodega rows per material
    from collections import defaultdict
    agg = defaultdict(lambda: {'litros': 0, 'precio': 0, 'aptitud': [], 'bodegas': []})
    for s in StockMaterial.objects.filter(corte=corte).select_related('material'):
        mc = s.material.codigo
        agg[mc]['litros'] += s.litros_totales
        if s.precio_litro:
            agg[mc]['precio'] = s.precio_litro
        for v in (s.aptitud_vinos or []):
            if v not in agg[mc]['aptitud']:
                agg[mc]['aptitud'].append(v)
        if s.bodega and s.bodega not in agg[mc]['bodegas']:
            agg[mc]['bodegas'].append(s.bodega)

    result = {}
    for mc, a in agg.items():
        bods = a['bodegas']
        result[mc] = {
            'litros': a['litros'],
            'precio': a['precio'],
            'aptitud': a['aptitud'],
            'bodega': ', '.join(bods) if len(bods) > 1 else (bods[0] if bods else ''),
            'bodegas': bods,
        }
    return result


def build_precio_map(temporada_id=None, anio=None, mes=None):
    """material_codigo -> precio más reciente (SIEMPRE GLOBAL).
    Stock y precios son independientes de la temporada de configuración.
    Si se pasa anio/mes, filtra hasta ese período (para ver precios históricos).
    """
    qs = PrecioMaterial.objects.order_by('material_id', '-anio', '-mes').select_related('material')
    if anio and mes:
        # Precio más reciente hasta ese período
        qs = qs.filter(
            models.Q(anio__lt=int(anio)) |
            models.Q(anio=int(anio), mes__lte=int(mes))
        )
    # NO filter by temporada_id — precios son globales
    result = {}
    for pm in qs:
        if pm.material.codigo not in result:
            result[pm.material.codigo] = pm.precio_litro
    return result


def build_nec_acum(temporada_id):
    """material_codigo -> litros necesarios acumulados (todos los vinos de la temporada)"""
    acum = {}
    nec_q = {n.vino.codigo: n.litros
              for n in Necesidad.objects.filter(temporada_id=temporada_id).select_related('vino')}
    for c in Configuracion.objects.filter(temporada_id=temporada_id).select_related('vino', 'material'):
        mc = c.material.codigo
        acum[mc] = acum.get(mc, 0) + nec_q.get(c.vino.codigo, 0) * c.participacion
    return acum


def get_precio(material_codigo, p_map, s_map):
    return p_map.get(material_codigo) or s_map.get(material_codigo, {}).get('precio', 0)



# ── API: CORTE MÁS RECIENTE (cross-temporada) ─────────────────────────
def api_corte_reciente(request):
    """Devuelve el corte de stock más reciente disponible, sin importar temporada."""
    corte = CorteStock.objects.order_by('-anio', '-mes').first()
    if not corte:
        return JsonResponse(None, safe=False)
    return JsonResponse({
        'id': corte.id,
        'descripcion': corte.descripcion,
        'anio': corte.anio,
        'mes': corte.mes,
        'temporada_id': corte.temporada_id,
        'temporada_anio': corte.temporada.anio,
        'n_materiales': corte.items.count(),
    })


# ── API: TODOS LOS CORTES (para selector) ─────────────────────────────
def api_todos_cortes(request):
    """Lista todos los cortes disponibles de todas las temporadas."""
    qs = CorteStock.objects.select_related('temporada').order_by('-anio', '-mes')
    return JsonResponse([{
        'id': c.id,
        'descripcion': f"{c.descripcion} (T{c.temporada.anio})",
        'anio': c.anio,
        'mes': c.mes,
        'es_vigente': c.es_vigente,
        'temporada_id': c.temporada_id,
        'temporada_anio': c.temporada.anio,
        'n_materiales': c.items.count(),
    } for c in qs], safe=False)


# ── PÁGINAS ───────────────────────────────────────────────────────────

@login_required
def index(request):
    import json as _json
    temporadas = list(Temporada.objects.all())
    # Attach bloqueada info for template
    # (already in model)

    # Active temporada
    temp = Temporada.objects.filter(activa=True).first() or (temporadas[0] if temporadas else None)
    temp_id = temp.id if temp else None

    wines_out = []
    stock_out = []

    if temp_id:
        s_map = build_stock_map()   # global: latest corte
        p_map = build_precio_map()  # global: latest prices
        nec_acum = build_nec_acum(temp_id)
        nec_q = {n.vino.codigo: n.litros
                 for n in Necesidad.objects.filter(temporada_id=temp_id).select_related('vino')}

        for vino in Vino.objects.prefetch_related('ventas').all():
            configs = list(Configuracion.objects
                           .filter(vino=vino, temporada_id=temp_id)
                           .select_related('material'))
            componentes = []
            for c in configs:
                mc = c.material.codigo
                st = s_map.get(mc, {})
                precio = get_precio(mc, p_map, s_map)
                componentes.append({
                    'material': mc,
                    'descripcion': c.material.descripcion,
                    'variedad': c.material.variedad or '',
                    'calidad': c.material.calidad or '',
                    'valle': c.material.valle or '',
                    'color': c.material.color or '',
                    'pct_2024': 0,
                    'pct_2026': c.participacion,
                    'pct_2027': c.participacion,
                    'costo_litro': round(precio, 2),
                    'stock': int(st.get('litros', 0)),
                    'stock_litros': int(st.get('litros', 0)),
                    'bodega': st.get('bodega', ''),
                    'aptitud': vino.codigo in st.get('aptitud', []),
                    'aptitud_vinos': st.get('aptitud', []),
                    'nec_acumulada_global': round(nec_acum.get(mc, 0)),
                })
            ventas_hist = {v.anio: v.litros for v in vino.ventas.order_by('anio')}
            wines_out.append({
                'codigo': vino.codigo,
                'descripcion': vino.descripcion,
                'calidad': vino.calidad,
                'color': vino.color,
                'enologo': vino.enologo,
                'variedad_principal_4d': vino.variedad_principal_4d or '',
                'estado': vino.estado,
                'estado_mezcla': vino.estado_mezcla,
                'revision': vino.revision,
                'notas': vino.notas_revision,
                'necesidad': nec_q.get(vino.codigo, 0),
                'ventas_año_actual': ventas_hist.get(datetime.now().year, 0),
                'ventas_historico': ventas_hist,
                'componentes': componentes,
            })

        corte = get_vigente_stock(temp_id)
        if corte:
            for s in StockMaterial.objects.filter(corte=corte).select_related('material'):
                stock_out.append({
                    'material': s.material.codigo,
                    'descripcion': s.material.descripcion,
                    'variedad': s.material.variedad or '',
                    'calidad': s.material.calidad or '',
                    'valle': s.material.valle or '',
                    'color': s.material.color or '',
                    'stock': int(s.litros_totales),
                    'precio': round(s.precio_litro, 2),
                    'bodega': s.bodega or '',
                    'aptitud_vinos': s.aptitud_vinos or [],
                })

    return render(request, 'vinos/index.html', {
        'temporadas': temporadas,
        'temp_activa_id': temp_id,
        'wines_json': _json.dumps(wines_out, ensure_ascii=False),
        'stock_json': _json.dumps(stock_out, ensure_ascii=False),
    })


def simulador(request):
    """Misma vista que index."""
    return index(request)


def api_temporadas(request):
    data = []
    for t in Temporada.objects.all():
        corte = get_vigente_stock(t.id)
        data.append({'id': t.id, 'anio': t.anio, 'activa': t.activa,
                     'corte_vigente': str(corte) if corte else None})
    return JsonResponse(data, safe=False)


# ── API: FILTROS ──────────────────────────────────────────────────────

def api_filtros(request):
    return JsonResponse({
        'enologos': sorted(set(Vino.objects.exclude(enologo='').values_list('enologo', flat=True))),
        'calidades': sorted(set(Vino.objects.exclude(calidad='').values_list('calidad', flat=True))),
        'variedades_4d': sorted(set(Vino.objects.exclude(variedad_principal_4d='')
                                    .values_list('variedad_principal_4d', flat=True))),
        'bodegas': sorted(set(StockMaterial.objects.exclude(bodega='')
                              .values_list('bodega', flat=True))),
    })


# ── API: LISTA VINOS ──────────────────────────────────────────────────

def api_vinos(request):
    temporada_id = request.GET.get('temporada')
    filtros = {
        'estado': request.GET.get('estado', 'todos'),
        'revision': request.GET.get('revision', 'todos'),
        'enologo': request.GET.get('enologo', 'todos'),
        'calidad': request.GET.get('calidad', 'todos'),
        'variedad': request.GET.get('variedad', 'todos'),
        'estado_mezcla': request.GET.get('estado_mezcla', 'todos'),
    }

    qs = Vino.objects.all()
    # Superuser sees everything; other users filtered by perfil
    if request.user.is_authenticated and not request.user.is_superuser:
        try:
            perfil = request.user.perfil_enologo
            if perfil.enologos:
                qs = qs.filter(enologo__in=perfil.enologos)
        except Exception:
            pass  # no profile = see all
    if filtros['estado'] != 'todos':
        qs = qs.filter(estado=filtros['estado'])
    if filtros['revision'] != 'todos':
        qs = qs.filter(revision=filtros['revision'])
    if filtros['enologo'] != 'todos':
        qs = qs.filter(enologo=filtros['enologo'])
    if filtros['calidad'] != 'todos':
        qs = qs.filter(calidad=filtros['calidad'])
    if filtros['variedad'] != 'todos':
        qs = qs.filter(variedad_principal_4d=filtros['variedad'])
    if filtros['estado_mezcla'] != 'todos':
        qs = qs.filter(estado_mezcla=filtros['estado_mezcla'])

    nec_map = {}
    if temporada_id:
        for n in Necesidad.objects.filter(temporada_id=temporada_id):
            nec_map[n.vino_id] = n.litros

    return JsonResponse([{
        'id': v.id, 'codigo': v.codigo, 'descripcion': v.descripcion,
        'calidad': v.calidad, 'color': v.color, 'enologo': v.enologo,
        'variedad_principal_4d': v.variedad_principal_4d,
        'estado': v.estado, 'estado_mezcla': v.estado_mezcla,
        'revision': v.revision, 'notas': v.notas_revision,
        'necesidad': nec_map.get(v.id, 0),
    } for v in qs], safe=False)


# ── API: DETALLE VINO ─────────────────────────────────────────────────

def api_vino_detalle(request, codigo):
    vino = get_object_or_404(Vino, codigo=codigo)
    temporada_id = request.GET.get('temporada')
    ref_temporada_id = request.GET.get('ref_temporada')

    corte_id = request.GET.get('corte_id')
    anio_precio = request.GET.get('anio_precio')
    mes_precio  = request.GET.get('mes_precio')

    # Stock: usa corte_id si viene, si no el más reciente global (ignora temporada)
    s_map = build_stock_map(temporada_id=None, corte_id=corte_id)
    # Precios: siempre globales (más recientes disponibles), opcionalmente filtrado por período
    p_map = build_precio_map(anio=anio_precio, mes=mes_precio)
    nec_acum = build_nec_acum(temporada_id) if temporada_id else {}

    nec_vino = 0
    if temporada_id:
        n = vino.necesidades.filter(temporada_id=temporada_id).first()
        nec_vino = n.litros if n else 0

    configs_ref = {}
    if ref_temporada_id:
        for c in Configuracion.objects.filter(
                vino=vino, temporada_id=ref_temporada_id).select_related('material'):
            mc = c.material.codigo
            # Use saved price for ref year if available
            precio_ref = c.costo_litro_guardado if c.costo_litro_guardado > 0                          else get_precio(mc, p_map, s_map)
            configs_ref[mc] = {
                'participacion': c.participacion,
                'precio': precio_ref,
            }

    componentes = []
    if temporada_id:
        for c in (Configuracion.objects
                  .filter(vino=vino, temporada_id=temporada_id)
                  .select_related('material')):
            mc = c.material.codigo
            st = s_map.get(mc, {})
            # Use saved price for bloqueada temporadas, current price otherwise
            try:
                t_obj = Temporada.objects.get(pk=temporada_id)
                use_saved = t_obj.bloqueada and c.costo_litro_guardado > 0
            except Exception:
                use_saved = False
            precio = c.costo_litro_guardado if use_saved else get_precio(mc, p_map, s_map)
            componentes.append({
                'material_codigo': mc,
                'descripcion': c.material.descripcion,
                'variedad': c.material.variedad or '',
                'calidad': c.material.calidad or '',
                'valle': c.material.valle or '',
                'color': c.material.color or '',
                'participacion': c.participacion,
                'participacion_ref': configs_ref.get(mc, 0),
                'costo_litro': round(precio, 2),
                'stock_litros': st.get('litros', 0),
                'bodega': st.get('bodega', ''),
                'aptitud': vino.codigo in st.get('aptitud', []),
                'nec_acumulada_global': round(nec_acum.get(mc, 0)),
            })

    ventas_hist = {v.anio: {'litros': v.litros, 'cajas': v.cajas}
                   for v in vino.ventas.order_by('anio')}

    # Build ref componentes (all components from ref year, even if not in new config)
    componentes_ref = []
    if ref_temporada_id:
        for c in (Configuracion.objects
                  .filter(vino=vino, temporada_id=ref_temporada_id)
                  .select_related('material')):
            mc = c.material.codigo
            st = s_map.get(mc, {})
            ref_data = configs_ref.get(mc, {})
            precio_comp_ref = ref_data.get('precio', get_precio(mc, p_map, s_map))                               if isinstance(ref_data, dict) else get_precio(mc, p_map, s_map)
            componentes_ref.append({
                'material_codigo': mc,
                'descripcion': c.material.descripcion,
                'variedad': c.material.variedad or '',
                'participacion': c.participacion,
                'costo_litro': round(precio_comp_ref, 2),
                'stock_litros': st.get('litros', 0),
            })

    return JsonResponse({
        'vino': {
            'id': vino.id, 'codigo': vino.codigo, 'descripcion': vino.descripcion,
            'calidad': vino.calidad, 'color': vino.color, 'enologo': vino.enologo,
            'variedad_principal_4d': vino.variedad_principal_4d,
            'estado': vino.estado, 'estado_mezcla': vino.estado_mezcla,
            'revision': vino.revision, 'notas': vino.notas_revision,
            'necesidad': nec_vino,
        },
        'componentes': componentes,
        'ventas_historico': ventas_hist,
        'componentes_ref': componentes_ref,
        'temporadas': list(Temporada.objects.values('id', 'anio', 'activa')),
    })


# ── API: GUARDAR CONFIG ───────────────────────────────────────────────

@csrf_exempt
@require_http_methods(['POST'])
def api_guardar_config(request, codigo):
    vino = get_object_or_404(Vino, codigo=codigo)
    data = json.loads(request.body)
    temporada = get_object_or_404(Temporada, id=data.get('temporada_id'))
    Configuracion.objects.filter(vino=vino, temporada=temporada).delete()
    for comp in data.get('componentes', []):
        pct = float(comp.get('participacion', 0))
        if pct <= 0:
            continue
        try:
            mat = Material.objects.get(codigo=comp.get('material_codigo'))
            Configuracion.objects.create(vino=vino, temporada=temporada,
                                         material=mat, participacion=pct)
        except Material.DoesNotExist:
            pass
    return JsonResponse({'ok': True})


# ── API: ESTADO VINO ──────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(['PATCH'])
def api_vino_estado(request, codigo):
    vino = get_object_or_404(Vino, codigo=codigo)
    data = json.loads(request.body)
    if 'revision' in data:
        vino.revision = data['revision']
    if 'estado' in data:
        vino.estado = data['estado']
    if 'estado_mezcla' in data:
        vino.estado_mezcla = data['estado_mezcla']
    if 'notas' in data:
        vino.notas_revision = data['notas']
    vino.save()
    return JsonResponse({'ok': True, 'revision': vino.revision,
                         'estado_mezcla': vino.estado_mezcla})


# ── API: STOCK ────────────────────────────────────────────────────────

def api_stock(request):
    temporada_id = request.GET.get('temporada')
    vino_codigo  = request.GET.get('vino', '')
    corte_id     = request.GET.get('corte_id') or request.GET.get('corte')

    if corte_id:
        items = StockMaterial.objects.filter(corte_id=corte_id)
    elif temporada_id:
        corte = get_vigente_stock(temporada_id)
        if not corte:
            corte = CorteStock.objects.order_by('-anio', '-mes').first()
        items = StockMaterial.objects.filter(corte=corte) if corte else StockMaterial.objects.none()
    else:
        corte = CorteStock.objects.order_by('-anio', '-mes').first()
        items = StockMaterial.objects.filter(corte=corte) if corte else StockMaterial.objects.none()

    items = items.select_related('material')

    try:
        vino_codigo_int = int(vino_codigo) if vino_codigo else None
    except (ValueError, TypeError):
        vino_codigo_int = None

    from collections import defaultdict
    agg = defaultdict(lambda: {
        'litros_total': 0,
        'litros_por_bodega': {},   # bodega -> litros
        'precio': 0, 'bodegas': [], 'aptitud': [],
        'mat': None, 'is_apt': False
    })

    for s in items:
        mc = s.material.codigo
        a  = agg[mc]
        a['litros_total'] += s.litros_totales
        bod = s.bodega or ''
        a['litros_por_bodega'][bod] = a['litros_por_bodega'].get(bod, 0) + s.litros_totales
        if s.precio_litro:
            a['precio'] = s.precio_litro
        if bod and bod not in a['bodegas']:
            a['bodegas'].append(bod)
        for v in (s.aptitud_vinos or []):
            if v not in a['aptitud']:
                a['aptitud'].append(v)
        a['mat'] = s.material
        if vino_codigo_int and vino_codigo_int in (s.aptitud_vinos or []):
            a['is_apt'] = True

    data = []
    for mc, a in agg.items():
        mat = a['mat']
        if not mat:
            continue
        bods = sorted(a['bodegas'])
        bodega_display = ', '.join(bods) if len(bods) > 1 else (bods[0] if bods else '')
        # Calculate necesidad acumulada for this material
        # = sum of (necesidad_vino * participacion) across all configs in temporada
        nec_acum = 0.0
        if temporada_id:
            from django.db.models import F
            configs_mat = (Configuracion.objects
                .filter(material__codigo=mc, temporada_id=temporada_id)
                .select_related('vino'))
            for cfg in configs_mat:
                nec_vino = getattr(
                    Necesidad.objects.filter(vino=cfg.vino, temporada_id=temporada_id).first(),
                    'litros', 0) or 0
                nec_acum += abs(nec_vino) * cfg.participacion

        data.append({
            'material_codigo':   mc,
            'descripcion':       mat.descripcion,
            'variedad':          mat.variedad or '',
            'calidad':           mat.calidad or '',
            'valle':             mat.valle or '',
            'color':             mat.color or '',
            'stock_litros':      a['litros_total'],
            'litros_por_bodega': a['litros_por_bodega'],
            'precio_litro':      a['precio'],
            'bodega':            bodega_display,
            'bodegas':           bods,
            'aptitud_vinos':     a['aptitud'],
            'is_apt':            a['is_apt'],
            'nec_acumulada':     round(nec_acum),
            'cobertura_pct':     round(a['litros_total'] / nec_acum * 100) if nec_acum > 0 else None,
        })

    data.sort(key=lambda x: (0 if x['is_apt'] else 1, -x['stock_litros']))
    return JsonResponse(data, safe=False)


def api_stock_detalle(request, material_codigo):
    """Detalle de líneas individuales (cubas/cosechas) de un material — todas las bodegas."""
    corte_id     = request.GET.get('corte_id')
    temporada_id = request.GET.get('temporada')

    if corte_id:
        sms = StockMaterial.objects.filter(
            corte_id=corte_id, material__codigo=material_codigo
        ).prefetch_related('detalles')
    else:
        corte = get_vigente_stock(temporada_id) if temporada_id else None
        if not corte:
            corte = CorteStock.objects.order_by('-anio', '-mes').first()
        sms = StockMaterial.objects.filter(
            corte=corte, material__codigo=material_codigo
        ).prefetch_related('detalles') if corte else StockMaterial.objects.none()

    if not sms.exists():
        return JsonResponse({'total_litros': 0, 'precio_litro': 0, 'detalles': []})

    from django.db.models import Sum
    # Aggregate detalles across ALL bodega rows of this material
    det_qs = StockDetalle.objects.filter(stock__in=sms)
    detalles = list(
        det_qs.values('cosecha', 'bodega')
               .annotate(litros=Sum('litros'))
               .order_by('-cosecha', 'bodega')
    )

    first = sms.first()
    total = sum(s.litros_totales for s in sms)
    precio = next((s.precio_litro for s in sms if s.precio_litro), 0)
    bodegas = sorted({s.bodega for s in sms if s.bodega})

    return JsonResponse({
        'material_codigo': material_codigo,
        'descripcion': first.material.descripcion,
        'total_litros': total,
        'precio_litro': precio,
        'bodegas': bodegas,
        'n_lineas': len(detalles),
        'detalles': detalles,
    })


def api_cortes_stock(request):
    temporada_id = request.GET.get('temporada')
    qs = CorteStock.objects.all()
    if temporada_id:
        qs = qs.filter(temporada_id=temporada_id)
    return JsonResponse([{
        'id': c.id, 'descripcion': c.descripcion,
        'anio': c.anio, 'mes': c.mes,
        'es_vigente': c.es_vigente,
        'temporada_id': c.temporada_id,
        'n_materiales': c.items.count(),
    } for c in qs], safe=False)


@csrf_exempt
@require_http_methods(['POST'])
def api_set_corte_vigente(request, corte_id):
    corte = get_object_or_404(CorteStock, id=corte_id)
    CorteStock.objects.filter(temporada=corte.temporada, es_vigente=True).update(es_vigente=False)
    corte.es_vigente = True
    corte.save()
    return JsonResponse({'ok': True, 'corte': corte.descripcion})


# ── API: PRECIOS ──────────────────────────────────────────────────────

def api_precios_resumen(request):
    temporada_id = request.GET.get('temporada')
    q = request.GET.get('q', '').lower()
    if not temporada_id:
        return JsonResponse([], safe=False)
    visto = set()
    data = []
    for pm in (PrecioMaterial.objects
               .filter(temporada_id=temporada_id)
               .select_related('material')
               .order_by('material__codigo', '-anio', '-mes')):
        mc = pm.material.codigo
        if mc in visto:
            continue
        visto.add(mc)
        if q and q not in str(mc) and q not in pm.material.descripcion.lower():
            continue
        n_hist = PrecioMaterial.objects.filter(material=pm.material,
                                               temporada_id=temporada_id).count()
        data.append({
            'material_codigo': mc,
            'descripcion': pm.material.descripcion,
            'variedad': pm.material.variedad or '',
            'valle': pm.material.valle or '',
            'precio_litro': pm.precio_litro,
            'periodo': f"{pm.mes:02d}/{pm.anio}",
            'n_historico': n_hist,
        })
    return JsonResponse(data, safe=False)


def api_precios_evolutivo(request):
    material_codigo = request.GET.get('material')
    temporada_id = request.GET.get('temporada')
    if not material_codigo:
        return JsonResponse([], safe=False)
    qs = (PrecioMaterial.objects
          .filter(material__codigo=material_codigo)
          .select_related('material', 'temporada')
          .order_by('anio', 'mes'))
    if temporada_id:
        qs = qs.filter(temporada_id=temporada_id)
    return JsonResponse([{
        'anio': p.anio, 'mes': p.mes,
        'periodo': f"{p.mes:02d}/{p.anio}",
        'precio_litro': p.precio_litro,
        'cantidad_litros': p.cantidad_litros,
        'temporada': p.temporada.anio,
    } for p in qs], safe=False)


# ── API: VENTAS ───────────────────────────────────────────────────────

def api_ventas_resumen(request):
    data = []
    for v in VentasVino.objects.select_related('vino').order_by('vino__codigo', 'anio'):
        data.append({
            'codigo': v.vino.codigo,
            'descripcion': v.vino.descripcion,
            'calidad': v.vino.calidad,
            'variedad': v.vino.variedad_principal_4d,
            'anio': v.anio,
            'litros': v.litros,
            'cajas': v.cajas,
        })
    return JsonResponse(data, safe=False)


# ── API: RESUMEN GLOBAL ───────────────────────────────────────────────

def api_resumen_global(request):
    temporada_id = request.GET.get('temporada')
    ref_temporada_id = request.GET.get('ref_temporada')
    if not temporada_id:
        return JsonResponse([], safe=False)

    p_map = build_precio_map()   # global: latest prices
    s_map = build_stock_map()    # global: latest corte
    nec_acum = build_nec_acum(temporada_id)

    configs_nueva = {}
    for c in (Configuracion.objects.filter(temporada_id=temporada_id)
              .select_related('vino', 'material')):
        configs_nueva.setdefault(c.vino.codigo, []).append(c)

    configs_ref = {}
    if ref_temporada_id:
        for c in (Configuracion.objects.filter(temporada_id=ref_temporada_id)
                  .select_related('vino', 'material')):
            configs_ref.setdefault(c.vino.codigo, []).append(c)

    necesidades = {n.vino.codigo: n.litros
                   for n in Necesidad.objects.filter(temporada_id=temporada_id)
                   .select_related('vino')}
    anio_actual = datetime.now().year
    ventas = {v.vino.codigo: v.litros
              for v in VentasVino.objects.filter(anio=anio_actual).select_related('vino')}

    data = []
    for vino in Vino.objects.all():
        cod = vino.codigo
        comps_n = configs_nueva.get(cod, [])
        comps_r = configs_ref.get(cod, [])
        nec = necesidades.get(cod, 0)

        costo_nueva = sum(c.participacion * get_precio(c.material.codigo, p_map, s_map)
                          for c in comps_n)
        costo_ref = sum(c.participacion * get_precio(c.material.codigo, p_map, s_map)
                        for c in comps_r)
        delta = costo_nueva - costo_ref

        nOkI = nWI = nBI = nOkG = nWG = nBG = 0
        for c in comps_n:
            if not c.participacion:
                continue
            nec_ind = nec * c.participacion
            nec_glob = nec_acum.get(c.material.codigo, nec_ind)
            stk = s_map.get(c.material.codigo, {}).get('litros', 0)
            ci = stk / nec_ind if nec_ind > 0 else 1
            cg = stk / nec_glob if nec_glob > 0 else 1
            if ci >= 1: nOkI += 1
            elif ci >= .7: nWI += 1
            else: nBI += 1
            if cg >= 1: nOkG += 1
            elif cg >= .7: nWG += 1
            else: nBG += 1

        data.append({
            'codigo': cod,
            'descripcion': vino.descripcion,
            'calidad': vino.calidad,
            'color': vino.color,
            'enologo': vino.enologo,
            'variedad_principal_4d': vino.variedad_principal_4d or '',
            'estado': vino.estado,
            'estado_mezcla': vino.estado_mezcla,
            'revision': vino.revision,
            'necesidad': nec,
            'costo_ref': round(costo_ref, 2),
            'costo_nueva': round(costo_nueva, 2),
            'delta': round(delta, 2),
            'delta_pct': round(delta / costo_ref * 100, 1) if costo_ref else 0,
            'cob_ind': [nOkI, nWI, nBI],
            'cob_glob': [nOkG, nWG, nBG],
            'ventas_actual': ventas.get(cod, 0),
        })
    return JsonResponse(data, safe=False)


# ── API: RESUMEN POR VARIEDAD ─────────────────────────────────────────

def api_resumen_variedad(request):
    temporada_id = request.GET.get('temporada')
    if not temporada_id:
        return JsonResponse({'vino': [], 'componente': []}, safe=False)

    p_map = build_precio_map()   # global: latest prices
    s_map = build_stock_map()    # global: latest corte
    nec_acum = build_nec_acum(temporada_id)
    necesidades = {n.vino.codigo: n.litros
                   for n in Necesidad.objects.filter(temporada_id=temporada_id).select_related('vino')}
    anio_actual = datetime.now().year
    ventas = {v.vino.codigo: v.litros
              for v in VentasVino.objects.filter(anio=anio_actual).select_related('vino')}

    # A: por variedad del VINO (4D)
    by_vino = {}
    for vino in Vino.objects.all():
        v4d = vino.variedad_principal_4d or 'Sin variedad'
        if v4d not in by_vino:
            by_vino[v4d] = {'vinos': 0, 'necesidad': 0, 'costo_sum': 0, 'ventas': 0}
        nec = necesidades.get(vino.codigo, 0)
        costo = sum(c.participacion * get_precio(c.material.codigo, p_map, s_map)
                    for c in Configuracion.objects.filter(vino=vino, temporada_id=temporada_id)
                    .select_related('material'))
        by_vino[v4d]['vinos'] += 1
        by_vino[v4d]['necesidad'] += nec
        by_vino[v4d]['costo_sum'] += costo * nec
        by_vino[v4d]['ventas'] += ventas.get(vino.codigo, 0)

    vino_res = [{
        'variedad': v,
        'vinos': d['vinos'],
        'necesidad': round(d['necesidad']),
        'costo_pond': round(d['costo_sum'] / d['necesidad'], 2) if d['necesidad'] else 0,
        'ventas': round(d['ventas']),
    } for v, d in sorted(by_vino.items(), key=lambda x: -x[1]['necesidad'])]

    # B: por variedad del COMPONENTE
    by_comp = {}
    for mc, nec_g in nec_acum.items():
        try:
            mat = Material.objects.get(codigo=mc)
        except Material.DoesNotExist:
            continue
        v = mat.variedad or 'Sin variedad'
        precio = get_precio(mc, p_map, s_map)
        stk = s_map.get(mc, {}).get('litros', 0)
        if v not in by_comp:
            by_comp[v] = {'nec': 0, 'costo_sum': 0, 'stk': 0}
        by_comp[v]['nec'] += nec_g
        by_comp[v]['costo_sum'] += nec_g * precio
        by_comp[v]['stk'] += stk

    comp_res = [{
        'variedad': v,
        'necesidad': round(d['nec']),
        'costo_pond': round(d['costo_sum'] / d['nec'], 2) if d['nec'] else 0,
        'stock': round(d['stk']),
        'cobertura': round(d['stk'] / d['nec'] * 100, 1) if d['nec'] else 0,
    } for v, d in sorted(by_comp.items(), key=lambda x: -x[1]['nec'])]

    return JsonResponse({'vino': vino_res, 'componente': comp_res})


# ── API: COPIAR TEMPORADA ─────────────────────────────────────────────

@csrf_exempt
@require_http_methods(['POST'])
def api_copiar_temporada(request):
    data = json.loads(request.body)
    anio_origen = data.get('origen')
    anio_destino = data.get('destino')
    forzar = data.get('forzar', False)
    solo_vigentes = data.get('solo_vigentes', False)

    if not anio_origen or not anio_destino or anio_origen == anio_destino:
        return JsonResponse({'error': 'Origen y destino distintos requeridos'}, status=400)

    try:
        temp_origen = Temporada.objects.get(anio=anio_origen)
    except Temporada.DoesNotExist:
        return JsonResponse({'error': f'No existe la temporada {anio_origen}'}, status=404)

    temp_destino, created = Temporada.objects.get_or_create(
        anio=anio_destino,
        defaults={'descripcion': f'Copiado desde {anio_origen}'}
    )

    qs = Configuracion.objects.filter(temporada=temp_origen).select_related('vino', 'material')
    if solo_vigentes:
        qs = qs.filter(vino__estado='vigente', vino__estado_mezcla='vigente')

    por_vino = {}
    for c in qs:
        por_vino.setdefault(c.vino.codigo, []).append(c)

    con_destino = set(
        Configuracion.objects.filter(temporada=temp_destino)
        .values_list('vino__codigo', flat=True).distinct()
    )

    copiados = saltados = total = 0
    for cod, configs in por_vino.items():
        if cod in con_destino and not forzar:
            saltados += 1
            continue
        if forzar and cod in con_destino:
            Configuracion.objects.filter(vino__codigo=cod, temporada=temp_destino).delete()
        Configuracion.objects.bulk_create([
            Configuracion(vino=c.vino, temporada=temp_destino,
                          material=c.material, participacion=c.participacion)
            for c in configs
        ], ignore_conflicts=True)
        copiados += 1
        total += len(configs)

    Vino.objects.all().update(revision='pendiente')
    return JsonResponse({
        'ok': True,
        'temporada_destino_id': temp_destino.id,
        'anio_destino': anio_destino,
        'creada': created,
        'vinos_copiados': copiados,
        'componentes': total,
        'saltados': saltados,
    })


# ── API: UPLOAD EXCEL ─────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(['POST'])
def api_upload_excel(request):
    uploaded = request.FILES.get('file')
    anio = request.POST.get('anio')
    mes_raw = request.POST.get('mes', '')
    mes = int(mes_raw) if mes_raw.isdigit() else datetime.now().month
    modo = request.POST.get('modo', 'auto')
    solo = request.POST.get('solo', '')

    if not uploaded or not anio:
        return JsonResponse({'error': 'Faltan parámetros (file, anio)'}, status=400)
    try:
        anio = int(anio)
    except ValueError:
        return JsonResponse({'error': 'Año inválido'}, status=400)

    suffix = '.xlsx' if uploaded.name.lower().endswith('.xlsx') else '.xls'
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        for chunk in uploaded.chunks():
            tmp.write(chunk)
        tmp_path = tmp.name

    try:
        import pandas as pd
        from vinos.management.commands.importar_excel import Command as ImportCmd

        xl = pd.ExcelFile(tmp_path)
        sheets_upper = {s.upper(): s for s in xl.sheet_names}

        if modo == 'auto':
            modo = 'original' if any(
                k in sheets_upper for k in ['STOCK OCT', 'TD$CON COMPRA UVA']
            ) else 'plantilla'

        temporada, _ = Temporada.objects.get_or_create(anio=anio)

        import io
        cmd = ImportCmd()
        cmd.stdout = io.StringIO()
        cmd.style = type('S', (), {'SUCCESS': lambda s, x: x})()

        if solo == 'stock':
            cmd._import_stock(xl, sheets_upper, temporada, anio, mes, modo)
        elif solo == 'precios':
            cmd._import_precios(xl, sheets_upper, temporada, anio, mes, modo)
        elif solo == 'ventas':
            cmd._import_ventas(xl, sheets_upper)
        else:
            cmd._import_configs(xl, sheets_upper, temporada, anio, modo)
            cmd._import_stock(xl, sheets_upper, temporada, anio, mes, modo)
            cmd._import_precios(xl, sheets_upper, temporada, anio, mes, modo)
            cmd._import_necesidades(xl, sheets_upper, temporada, modo)
            cmd._import_ventas(xl, sheets_upper)

        corte = get_vigente_stock(temporada.id)
        return JsonResponse({
            'ok': True, 'anio': anio, 'mes': mes, 'modo': modo,
            'temporada_id': temporada.id,
            'vinos': Vino.objects.count(),
            'configs': Configuracion.objects.filter(temporada=temporada).count(),
            'stock': StockMaterial.objects.filter(temporada=temporada).count(),
            'corte_vigente': str(corte) if corte else None,
            'necesidades': Necesidad.objects.filter(temporada=temporada).count(),
            'precios': PrecioMaterial.objects.filter(temporada=temporada,
                                                     anio=anio, mes=mes).count(),
            'ventas': VentasVino.objects.count(),
        })

    except Exception as e:
        import traceback
        return JsonResponse({'error': str(e), 'trace': traceback.format_exc()}, status=500)
    finally:
        os.unlink(tmp_path)


# ── API: EXPORTAR CSV ─────────────────────────────────────────────────

def api_exportar(request):
    temporada_id = request.GET.get('temporada')
    if not temporada_id:
        return HttpResponse('temporada requerida', status=400)

    p_map = build_precio_map()   # global: latest prices
    s_map = build_stock_map()    # global: latest corte
    nec_acum = build_nec_acum(temporada_id)
    necesidades = {n.vino.codigo: n.litros
                   for n in Necesidad.objects.filter(temporada_id=temporada_id)
                   .select_related('vino')}

    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = f'attachment; filename="estandar_{temporada_id}.csv"'
    writer = csv.writer(response, delimiter=';')
    writer.writerow([
        'Codigo_Vino', 'Descripcion', 'Calidad', 'Color', 'Enologo',
        'Variedad_4D', 'Estado_Mezcla', 'Revision', 'Necesidad_L',
        'Material', 'Descripcion_Material', 'Variedad_Comp', 'Valle',
        'Participacion_pct', 'Costo_Litro', 'Contribucion_Litro',
        'NecInd_L', 'NecGlob_L', 'Stock_L', 'CobInd_pct', 'CobGlob_pct',
    ])

    for c in (Configuracion.objects
              .filter(temporada_id=temporada_id)
              .select_related('vino', 'material')
              .order_by('vino__codigo', '-participacion')):
        v = c.vino
        mat = c.material
        nec = necesidades.get(v.codigo, 0)
        nec_ind = nec * c.participacion
        nec_glob = nec_acum.get(mat.codigo, nec_ind)
        precio = get_precio(mat.codigo, p_map, s_map)
        stk = s_map.get(mat.codigo, {}).get('litros', 0)
        cob_ind = stk / nec_ind * 100 if nec_ind > 0 else 0
        cob_glob = stk / nec_glob * 100 if nec_glob > 0 else 0
        writer.writerow([
            v.codigo, v.descripcion, v.calidad, v.color, v.enologo,
            v.variedad_principal_4d, v.estado_mezcla, v.revision, round(nec),
            mat.codigo, mat.descripcion, mat.variedad, mat.valle,
            round(c.participacion * 100, 4), round(precio, 2),
            round(c.participacion * precio, 4),
            round(nec_ind), round(nec_glob), round(stk),
            round(cob_ind, 1), round(cob_glob, 1),
        ])
    return response

def api_bloquear_temporada(request):
    """Bloquea/desbloquea una temporada para proteger el estándar de cambios de precio."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'No autenticado'}, status=403)
    import json
    data = json.loads(request.body)
    temporada_id = data.get('temporada_id')
    bloqueada = data.get('bloqueada', True)
    try:
        t = Temporada.objects.get(pk=temporada_id)
        t.bloqueada = bloqueada
        t.save()
        return JsonResponse({'ok': True, 'bloqueada': t.bloqueada, 'anio': t.anio})
    except Temporada.DoesNotExist:
        return JsonResponse({'error': 'Temporada no encontrada'}, status=404)

# ── USER MANAGEMENT ───────────────────────────────────────────────────

@login_required
def vista_usuarios(request):
    """Página de gestión de usuarios (solo superusuarios)."""
    if not request.user.is_superuser:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Solo superusuarios pueden gestionar usuarios.")
    from django.contrib.auth.models import User
    from .models import PerfilUsuario
    from django.contrib import messages as dj_messages

    # Build user list with perfil
    usuarios = []
    for u in User.objects.all().order_by('username'):
        try:
            perfil = u.perfil_enologo
        except Exception:
            perfil = PerfilUsuario.objects.create(usuario=u)
        u.perfil = perfil
        usuarios.append(u)

    return render(request, 'vinos/usuarios.html', {'usuarios': usuarios})


@login_required
def crear_usuario(request):
    if not request.user.is_superuser:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    if request.method != 'POST':
        from django.shortcuts import redirect
        return redirect('usuarios')
    from django.contrib.auth.models import User
    from django.contrib import messages as dj_messages
    from .models import PerfilUsuario

    username  = request.POST.get('username', '').strip()
    password  = request.POST.get('password', '')
    nombre    = request.POST.get('nombre', '')
    enologos_str = request.POST.get('enologos', '').strip()
    bodegas_str  = request.POST.get('bodegas', '').strip()
    solo_lect    = request.POST.get('solo_lectura', '0') == '1'

    if User.objects.filter(username=username).exists():
        dj_messages.error(request, f'El usuario "{username}" ya existe.')
        from django.shortcuts import redirect
        return redirect('usuarios')

    enologos = [e.strip() for e in enologos_str.split(',') if e.strip()]
    bodegas  = [b.strip() for b in bodegas_str.split(',')  if b.strip()]

    u = User.objects.create_user(username=username, password=password)
    if nombre:
        parts = nombre.split(' ', 1)
        u.first_name = parts[0]
        u.last_name  = parts[1] if len(parts) > 1 else ''
        u.save()
    PerfilUsuario.objects.create(usuario=u, enologos=enologos,
                                 bodegas=bodegas, solo_lectura=solo_lect)
    dj_messages.success(request, f'Usuario "{username}" creado correctamente.')
    from django.shortcuts import redirect
    return redirect('usuarios')


@login_required
def editar_usuario(request, user_id):
    if not request.user.is_superuser:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    from django.contrib.auth.models import User
    from django.contrib import messages as dj_messages
    from .models import PerfilUsuario
    from django.shortcuts import redirect, get_object_or_404

    u = get_object_or_404(User, pk=user_id)
    if request.method == 'POST':
        password     = request.POST.get('password', '')
        enologos_str = request.POST.get('enologos', '').strip()
        bodegas_str  = request.POST.get('bodegas',  '').strip()
        solo_lect    = request.POST.get('solo_lectura', '0') == '1'

        if password:
            u.set_password(password)
            u.save()

        enologos = [e.strip() for e in enologos_str.split(',') if e.strip()]
        bodegas  = [b.strip() for b in bodegas_str.split(',')  if b.strip()]

        perfil, _ = PerfilUsuario.objects.get_or_create(usuario=u)
        perfil.enologos    = enologos
        perfil.bodegas     = bodegas
        perfil.solo_lectura = solo_lect
        perfil.save()
        dj_messages.success(request, f'Usuario "{u.username}" actualizado.')
    return redirect('usuarios')


@login_required
def eliminar_usuario(request, user_id):
    if not request.user.is_superuser:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    from django.contrib.auth.models import User
    from django.contrib import messages as dj_messages
    from django.shortcuts import redirect, get_object_or_404

    u = get_object_or_404(User, pk=user_id)
    if request.method == 'POST' and not u.is_superuser:
        username = u.username
        u.delete()
        dj_messages.success(request, f'Usuario "{username}" eliminado.')
    return redirect('usuarios')

def api_temporada_estado(request):
    """Retorna el estado (bloqueada, anio) de una temporada."""
    tid = request.GET.get('id')
    if not tid:
        return JsonResponse({'error': 'id requerido'}, status=400)
    try:
        t = Temporada.objects.get(pk=tid)
        return JsonResponse({'id': t.id, 'anio': t.anio, 'bloqueada': t.bloqueada, 'activa': t.activa})
    except Temporada.DoesNotExist:
        return JsonResponse({'error': 'No encontrada'}, status=404)

def api_precio_vigente(request):
    """Retorna el período del precio más reciente cargado."""
    from .models import PrecioMaterial
    ultimo = PrecioMaterial.objects.order_by('-anio', '-mes').first()
    if not ultimo:
        return JsonResponse({'label': None})
    meses = ['','Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']
    mes_str = meses[ultimo.mes] if 1 <= ultimo.mes <= 12 else str(ultimo.mes)
    return JsonResponse({
        'anio': ultimo.anio,
        'mes':  ultimo.mes,
        'label': f"{mes_str} {ultimo.anio}",
    })
