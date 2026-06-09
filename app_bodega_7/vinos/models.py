from django.db import models


class Temporada(models.Model):
    anio = models.IntegerField(unique=True)
    descripcion = models.CharField(max_length=100, blank=True)
    activa = models.BooleanField(default=False)
    bloqueada = models.BooleanField(default=False, help_text='Configuración bloqueada: precios no se actualizan al cargar Excel')
    fecha_carga = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-anio']

    def __str__(self):
        return f"Estándar {self.anio}"


class Vino(models.Model):
    ESTADO_CHOICES = [('vigente', 'Vigente'), ('descontinuado', 'Descontinuado')]
    REVISION_CHOICES = [('pendiente', 'Pendiente'), ('revisado', 'Revisado'), ('validado', 'Validado')]
    MEZCLA_CHOICES = [('vigente', 'Vigente'), ('no vigente', 'No Vigente'), ('descontinuado', 'Descontinuado')]

    codigo = models.IntegerField(unique=True)
    descripcion = models.CharField(max_length=200)
    calidad = models.CharField(max_length=10, blank=True)
    color = models.CharField(max_length=5, blank=True)
    enologo = models.CharField(max_length=50, blank=True)
    variedad_principal_4d = models.CharField(max_length=80, blank=True)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='vigente')
    estado_mezcla = models.CharField(max_length=20, choices=MEZCLA_CHOICES, default='vigente')
    revision = models.CharField(max_length=20, choices=REVISION_CHOICES, default='pendiente')
    notas_revision = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['codigo']

    def __str__(self):
        return f"{self.codigo} – {self.descripcion}"


class Material(models.Model):
    codigo = models.IntegerField(unique=True)
    descripcion = models.CharField(max_length=200)
    variedad = models.CharField(max_length=80, blank=True)
    calidad = models.CharField(max_length=10, blank=True)
    valle = models.CharField(max_length=80, blank=True)
    color = models.CharField(max_length=5, blank=True)

    class Meta:
        ordering = ['codigo']

    def __str__(self):
        return f"{self.codigo} – {self.descripcion}"


class CorteStock(models.Model):
    """Snapshot mensual de stock."""
    temporada = models.ForeignKey(Temporada, on_delete=models.CASCADE, related_name='cortes_stock')
    anio = models.IntegerField()
    mes = models.IntegerField()
    descripcion = models.CharField(max_length=80, blank=True)
    fecha_carga = models.DateTimeField(auto_now_add=True)
    es_vigente = models.BooleanField(default=False)

    class Meta:
        ordering = ['-anio', '-mes']
        unique_together = ('temporada', 'anio', 'mes')

    def __str__(self):
        return self.descripcion or f"{self.mes}/{self.anio}"

    def save(self, *args, **kwargs):
        if not self.descripcion:
            meses = ['', 'Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
                     'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
            self.descripcion = f"{meses[self.mes]} {self.anio}"
        super().save(*args, **kwargs)


class StockMaterial(models.Model):
    corte = models.ForeignKey(CorteStock, on_delete=models.CASCADE, related_name='items')
    temporada = models.ForeignKey(Temporada, on_delete=models.CASCADE, related_name='stocks')
    material = models.ForeignKey(Material, on_delete=models.CASCADE, related_name='stocks')
    litros_totales = models.FloatField(default=0)
    precio_litro = models.FloatField(default=0)
    aptitud_vinos = models.JSONField(default=list)
    bodega = models.CharField(max_length=100, blank=True)

    class Meta:
        unique_together = ('corte', 'material', 'bodega')

    def __str__(self):
        return f"{self.material.codigo} – {self.litros_totales:,.0f} L"


class StockDetalle(models.Model):
    """Línea individual de stock: una cuba/vasija/partida dentro de un corte."""
    stock = models.ForeignKey(StockMaterial, on_delete=models.CASCADE, related_name='detalles')
    cuba = models.CharField(max_length=80, blank=True)     # vasija/cuba
    cosecha = models.IntegerField(null=True, blank=True)   # año cosecha
    litros = models.FloatField(default=0)
    bodega = models.CharField(max_length=100, blank=True)
    grado_alc = models.CharField(max_length=10, blank=True)

    class Meta:
        ordering = ['-cosecha', '-litros']

    def __str__(self):
        return f"{self.stock.material.codigo} cuba={self.cuba} cosecha={self.cosecha} {self.litros:,.0f}L"


class PrecioMaterial(models.Model):
    """Precio promedio ponderado mensual."""
    material = models.ForeignKey(Material, on_delete=models.CASCADE, related_name='precios')
    temporada = models.ForeignKey(Temporada, on_delete=models.CASCADE, related_name='precios')
    anio = models.IntegerField()
    mes = models.IntegerField()
    precio_litro = models.FloatField()
    cantidad_litros = models.FloatField(default=0)
    costo_total = models.FloatField(default=0)
    fecha_carga = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-anio', '-mes']
        unique_together = ('material', 'temporada', 'anio', 'mes')


class Necesidad(models.Model):
    vino = models.ForeignKey(Vino, on_delete=models.CASCADE, related_name='necesidades')
    temporada = models.ForeignKey(Temporada, on_delete=models.CASCADE, related_name='necesidades')
    litros = models.FloatField(default=0)

    class Meta:
        unique_together = ('vino', 'temporada')


class Configuracion(models.Model):
    vino = models.ForeignKey(Vino, on_delete=models.CASCADE, related_name='configuraciones')
    temporada = models.ForeignKey(Temporada, on_delete=models.CASCADE, related_name='configuraciones')
    material = models.ForeignKey(Material, on_delete=models.CASCADE, related_name='configuraciones')
    participacion = models.FloatField(default=0)
    costo_litro_guardado = models.FloatField(default=0,
        help_text='Precio $/L al momento de guardar esta configuración')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('vino', 'temporada', 'material')
        ordering = ['vino__codigo', '-participacion']


class VentasVino(models.Model):
    vino = models.ForeignKey(Vino, on_delete=models.CASCADE, related_name='ventas')
    anio = models.IntegerField()
    litros = models.FloatField(default=0)
    cajas = models.FloatField(default=0)
    notas = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['vino__codigo', 'anio']
        unique_together = ('vino', 'anio')

class PerfilUsuario(models.Model):
    """Asocia un usuario Django con enólogos y bodegas que puede ver."""
    usuario = models.OneToOneField('auth.User', on_delete=models.CASCADE,
                                   related_name='perfil_enologo')
    enologos = models.JSONField(default=list,
        help_text='Lista de enólogos que puede ver. Vacío = todos.')
    bodegas = models.JSONField(default=list,
        help_text='Lista de bodegas que puede ver. Vacío = todas.')
    solo_lectura = models.BooleanField(default=False,
        help_text='Solo puede ver, no puede guardar configuraciones')

    def puede_ver_enologo(self, enologo):
        if not self.enologos: return True
        return enologo in self.enologos

    def puede_ver_bodega(self, bodega):
        if not self.bodegas: return True
        return bodega in self.bodegas

    def __str__(self):
        return f"Perfil {self.usuario.username}"

    def puede_ver_enologo(self, enologo):
        if not self.enologos:
            return True
        return enologo in self.enologos
