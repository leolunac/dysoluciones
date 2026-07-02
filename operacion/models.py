from django.db import models
from django.utils import timezone
from datetime import time
from decimal import Decimal


# =========================
# CLIENTE
# =========================

class Cliente(models.Model):

    TIPO_CONTRATO = [
        ('7X24', 'Contrato 7x24'),
        ('PREVENTIVO', 'Contrato Preventivo'),
        ('SIN_CONTRATO', 'Sin Contrato'),
    ]

    FRECUENCIA_LAVADO = [
        (4, 'Cada 4 meses'),
        (6, 'Cada 6 meses'),
    ]

    nombre = models.CharField(max_length=200)
    direccion = models.CharField(max_length=250)
    telefono_porteria = models.CharField(max_length=50)
    administrador = models.CharField(max_length=200)
    email = models.EmailField()
    tipo_contrato = models.CharField(max_length=20, choices=TIPO_CONTRATO)
    frecuencia_lavado = models.IntegerField(choices=FRECUENCIA_LAVADO)
    fecha_ultimo_lavado = models.DateField(null=True, blank=True)
    activo = models.BooleanField(default=True)

    def __str__(self):
        return self.nombre


# =========================
# TECNICO
# =========================

class Tecnico(models.Model):

    nombre = models.CharField(max_length=200)
    telefono = models.CharField(max_length=50)
    especialidad = models.CharField(max_length=200)
    valor_hora_diurna = models.DecimalField(max_digits=10, decimal_places=2)
    valor_hora_nocturna = models.DecimalField(max_digits=10, decimal_places=2)
    activo = models.BooleanField(default=True)

    def __str__(self):
        return self.nombre


# =========================
# EMERGENCIA
# =========================

class Emergencia(models.Model):


    ESTADO = [
        ('PENDIENTE', 'Pendiente'),
        ('EN_PROCESO', 'En Proceso'),
        ('ATENDIDA', 'Atendida'),
        ('CERRADA', 'Cerrada'),
    ]

    PRIORIDAD = [
        ('ALTA', 'Alta'),
        ('MEDIA', 'Media'),
        ('NORMAL', 'Normal'),
    ]

    TIPO_SERVICIO = [
        ("EMERGENCIA", "Emergencia"),
        ("CORRECTIVO", "Correctivo"),
        ("GARANTIA", "Garantía"),
        ("REVISION", "Revisión"),
    ]

    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE)
    tecnico = models.ForeignKey(Tecnico, on_delete=models.SET_NULL, null=True, blank=True)

    tipo_servicio = models.CharField(
        max_length=20,
        choices=TIPO_SERVICIO,
        default="CORRECTIVO"
    )

    persona_llama = models.CharField(max_length=150, null=True, blank=True)
    telefono_llama = models.CharField(max_length=50, null=True, blank=True)
    recibido_por = models.CharField(
        max_length=150,
        null=True,
        blank=True,
        help_text="Coordinador o técnico de turno que recibió la llamada"
    )

    fecha_llamada = models.DateTimeField(default=timezone.now)
    fecha_atencion = models.DateTimeField(null=True, blank=True)

    descripcion_falla = models.TextField()
    solucion_aplicada = models.TextField(null=True, blank=True)

    horas_trabajadas = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    es_nocturna = models.BooleanField(default=False)
    valor_total = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    prioridad = models.CharField(max_length=10, choices=PRIORIDAD, default='NORMAL')
    estado = models.CharField(max_length=20, choices=ESTADO, default='PENDIENTE')

    aprobada_por_gerencia = models.BooleanField(default=False)
    observaciones_internas = models.TextField(null=True, blank=True)

    def save(self, *args, **kwargs):

        hoy = timezone.now().date()

        if not self.tecnico:
            rotacion = RotacionTecnico.objects.filter(
                fecha_inicio_semana__lte=hoy,
                fecha_fin_semana__gte=hoy,
                activo=True
            ).first()

            if rotacion:
                self.tecnico = rotacion.tecnico

        hora = self.fecha_llamada.time()
        if hora >= time(21, 0) or hora <= time(6, 0):
            self.es_nocturna = True
        else:
            self.es_nocturna = False

        if self.cliente.tipo_contrato == '7X24':
            self.prioridad = 'ALTA'
        elif self.cliente.tipo_contrato == 'PREVENTIVO':
            self.prioridad = 'MEDIA'
        else:
            self.prioridad = 'NORMAL'

        if self.horas_trabajadas and self.tecnico:
            if self.es_nocturna:
                tarifa = self.tecnico.valor_hora_nocturna
            else:
                tarifa = self.tecnico.valor_hora_diurna

            self.valor_total = Decimal(self.horas_trabajadas) * Decimal(tarifa)

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.cliente.nombre} - {self.estado}"

# =========================
# ROTACION
# =========================

class RotacionTecnico(models.Model):

    tecnico = models.ForeignKey(Tecnico, on_delete=models.CASCADE)

    fecha_inicio_semana = models.DateField()
    fecha_fin_semana = models.DateField()

    es_fin_de_semana = models.BooleanField(default=False)
    activo = models.BooleanField(default=True)

    def __str__(self):
        tipo = "Fin de Semana" if self.es_fin_de_semana else "Semana"
        return f"{self.tecnico.nombre} - {tipo}"
    
from django.core.exceptions import ValidationError
from dateutil.relativedelta import relativedelta  # pip install python-dateutil


class LavadoTanque(models.Model):
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE)
    fecha_programada = models.DateField()

    ejecutado = models.BooleanField(default=False)
    fecha_ejecucion = models.DateField(null=True, blank=True)

    motivo_no_ejecucion = models.TextField(null=True, blank=True)

    # Para control interno (igual que tu idea de aprobación/publicación)
    aprobado = models.BooleanField(default=False)
    publicado_cliente = models.BooleanField(default=False)

    creado_en = models.DateTimeField(auto_now_add=True)
    def __str__(self):
        return f"{self.cliente.nombre} - {self.fecha_programada}"
# Reprogramación
    reprogramado = models.BooleanField(default=False)
    fecha_reprogramada = models.DateField(null=True, blank=True)
    motivo_reprogramacion = models.TextField(null=True, blank=True)    

    class Meta:
        unique_together = ("cliente", "fecha_programada")
        ordering = ("-fecha_programada",)

    def clean(self):
        # Si no se ejecutó y la fecha ya pasó, debería tener motivo (opcional, pero recomendado)
        if not self.ejecutado and self.fecha_programada and self.fecha_programada < timezone.now().date():
            if self.motivo_no_ejecucion is None or str(self.motivo_no_ejecucion).strip() == "":
                # No lo obligo siempre para no bloquear, pero lo puedes activar si quieres
                pass

    def __str__(self):
        estado = "Ejecutado" if self.ejecutado else "Pendiente"
        return f"{self.cliente.nombre} - {self.fecha_programada} - {estado}"   
    
class EquipoUnidad(models.Model):

    TIPO_EQUIPO = [
        ("BOMBA_IMPULSION", "Motobomba de impulsión"),
        ("BOMBA_PRESION", "Motobomba de presión"),
        ("HIDROFLOW", "Hidroflow"),
        ("TABLERO", "Tablero eléctrico"),
        ("VALVULERIA", "Válvulería"),
        ("OTRO", "Otro"),
    ]

    ESTADO = [
        ("OPERATIVO", "Operativo"),
        ("FUERA_SERVICIO", "Fuera de servicio"),
        ("EN_REPARACION", "En reparación"),
    ]

    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name="equipos")
    torre = models.CharField(max_length=100, null=True, blank=True)
    ubicacion = models.CharField(max_length=150, null=True, blank=True)

    tipo = models.CharField(max_length=30, choices=TIPO_EQUIPO)
    cantidad = models.PositiveIntegerField(default=1)

    marca = models.CharField(max_length=100, null=True, blank=True)
    modelo = models.CharField(max_length=100, null=True, blank=True)
    serie = models.CharField(max_length=100, null=True, blank=True)
    potencia = models.CharField(max_length=100, null=True, blank=True)
    voltaje = models.CharField(max_length=100, null=True, blank=True)
    control = models.CharField(max_length=100, null=True, blank=True)
    valor_comercial = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    estado = models.CharField(max_length=20, choices=ESTADO, default="OPERATIVO")
    causa_fuera_servicio = models.TextField(null=True, blank=True)
    ultima_revision = models.DateField(null=True, blank=True)
    observaciones = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"{self.cliente.nombre} - {self.get_tipo_display()}"

    

    

    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name="equipos")
    tipo = models.CharField(max_length=30, choices=TIPO_EQUIPO)
    cantidad = models.PositiveIntegerField(default=1)

    estado = models.CharField(max_length=20, choices=ESTADO, default="OPERATIVO")
    causa_fuera_servicio = models.TextField(null=True, blank=True)

    ultima_revision = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ("cliente__nombre", "tipo")

    def __str__(self):
        return f"{self.cliente.nombre} - {self.get_tipo_display()} ({self.cantidad})"
class CotizacionEquipo(models.Model):

    ESTADO = [
        ("NO_REQUIERE", "No requiere"),
        ("PENDIENTE_ENVIO", "Pendiente de envío"),
        ("ENVIADA", "Enviada"),
        ("PENDIENTE_APROBACION", "Pendiente de aprobación"),
        ("APROBADA", "Aprobada"),
        ("RECHAZADA", "Rechazada"),
    ]

    equipo = models.ForeignKey(EquipoUnidad, on_delete=models.CASCADE, related_name="cotizaciones")
    estado = models.CharField(max_length=25, choices=ESTADO, default="PENDIENTE_ENVIO")
    valor = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    fecha_envio = models.DateField(null=True, blank=True)
    observaciones = models.TextField(null=True, blank=True)

    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-creado_en",)

    def __str__(self):
        return f"Cotización - {self.equipo} - {self.estado}"    
    


from django.contrib.auth.models import User

class UsuarioCliente(models.Model):

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.user.username} - {self.cliente.nombre}"
    
class TanqueUnidad(models.Model):

    TIPO_TANQUE = [
        ("IMPULSION", "Tanque de impulsión"),
        ("TERRAZA", "Tanque de terraza"),
        ("HIDRONEUMATICO", "Tanque hidroneumático"),
        ("OTRO", "Otro"),
    ]

    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name="tanques")
    torre = models.CharField(max_length=100, null=True, blank=True)
    ubicacion = models.CharField(max_length=150, null=True, blank=True)
    tipo_tanque = models.CharField(max_length=30, choices=TIPO_TANQUE)
    cantidad = models.PositiveIntegerField(default=1)
    material = models.CharField(max_length=100, null=True, blank=True)
    capacidad = models.CharField(max_length=100, null=True, blank=True)
    observaciones = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"{self.cliente.nombre} - {self.get_tipo_tanque_display()}"


class DistribucionUnidad(models.Model):
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name="distribuciones")
    torre = models.CharField(max_length=100, null=True, blank=True)
    cantidad_pisos = models.PositiveIntegerField(null=True, blank=True)
    presion_desde = models.PositiveIntegerField(null=True, blank=True)
    presion_hasta = models.PositiveIntegerField(null=True, blank=True)
    gravedad_desde = models.PositiveIntegerField(null=True, blank=True)
    gravedad_hasta = models.PositiveIntegerField(null=True, blank=True)
    observaciones = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"{self.cliente.nombre} - {self.torre}"