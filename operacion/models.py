from django.db import models
from django.utils import timezone
from datetime import time
from decimal import Decimal
from django.conf import settings

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
    user = models.OneToOneField(
    settings.AUTH_USER_MODEL,
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name="perfil_tecnico",
    verbose_name="Usuario de acceso",
)

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


# =========================
# EMERGENCIA / SERVICIO 7X24
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

    RESULTADO_SERVICIO = [
        ("OPERATIVO", "Operativo"),
        ("OPERATIVO_PROVISIONAL", "Operativo provisional"),
        ("PENDIENTE_REPUESTO", "Pendiente repuesto"),
        ("REQUIERE_COTIZACION", "Requiere cotización"),
        ("REQUIERE_REGRESO", "Requiere regreso"),
        ("NO_SOLUCIONADO", "No solucionado"),
    ]

    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE)
    tecnico = models.ForeignKey(
        Tecnico,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    numero_caso = models.CharField(
        max_length=30,
        unique=True,
        null=True,
        blank=True
    )

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
    diagnostico = models.TextField(null=True, blank=True)
    solucion_aplicada = models.TextField(null=True, blank=True)
    materiales_usados = models.TextField(null=True, blank=True)

    horas_trabajadas = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True
    )

    es_nocturna = models.BooleanField(default=False)
    valor_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True
    )

    prioridad = models.CharField(
        max_length=10,
        choices=PRIORIDAD,
        default='NORMAL'
    )

    estado = models.CharField(
        max_length=20,
        choices=ESTADO,
        default='PENDIENTE'
    )

    resultado_servicio = models.CharField(
        max_length=30,
        choices=RESULTADO_SERVICIO,
        null=True,
        blank=True
    )

    requiere_regreso = models.BooleanField(default=False)
    requiere_cotizacion = models.BooleanField(default=False)
    cliente_conforme = models.BooleanField(null=True, blank=True)

    observacion_cierre = models.TextField(null=True, blank=True)

    aprobada_por_gerencia = models.BooleanField(default=False)
    observaciones_internas = models.TextField(null=True, blank=True)

    def save(self, *args, **kwargs):

        hoy = timezone.now().date()

        if not self.numero_caso:
            anio = timezone.now().year

            ultimo = Emergencia.objects.filter(
                numero_caso__startswith=f"EM-{anio}-"
            ).order_by("id").last()

            if ultimo and ultimo.numero_caso:
                try:
                    consecutivo = int(ultimo.numero_caso.split("-")[-1]) + 1
                except:
                    consecutivo = 1
            else:
                consecutivo = 1

            self.numero_caso = f"EM-{anio}-{consecutivo:06d}"

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
        return f"{self.numero_caso or 'Sin caso'} - {self.cliente.nombre}"
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

    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.CASCADE,
        related_name="equipos"
    )

    torre = models.CharField(
        max_length=100,
        null=True,
        blank=True
    )

    ubicacion = models.CharField(
        max_length=150,
        null=True,
        blank=True
    )

    tipo = models.CharField(
        max_length=30,
        choices=TIPO_EQUIPO
    )

    cantidad = models.PositiveIntegerField(default=1)

    codigo_activo = models.CharField(
        max_length=50,
        unique=True,
        null=True,
        blank=True
    )

    nombre_equipo = models.CharField(
        max_length=150,
        null=True,
        blank=True,
        help_text="Ejemplo: Bomba de presión No. 2"
    )

    marca = models.CharField(
        max_length=100,
        null=True,
        blank=True
    )

    modelo = models.CharField(
        max_length=100,
        null=True,
        blank=True
    )

    serie = models.CharField(
        max_length=100,
        null=True,
        blank=True
    )

    potencia = models.CharField(
        max_length=100,
        null=True,
        blank=True
    )

    voltaje = models.CharField(
        max_length=100,
        null=True,
        blank=True
    )

    control = models.CharField(
        max_length=100,
        null=True,
        blank=True
    )

    valor_comercial = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True
    )

    fecha_instalacion = models.DateField(
        null=True,
        blank=True
    )

    anio_fabricacion = models.PositiveIntegerField(
        null=True,
        blank=True
    )

    placa_identificada = models.BooleanField(
        default=False
    )

    informacion_validada = models.BooleanField(
        default=False
    )

    fecha_levantamiento = models.DateField(
        null=True,
        blank=True
    )

    estado = models.CharField(
        max_length=20,
        choices=ESTADO,
        default="OPERATIVO"
    )

    causa_fuera_servicio = models.TextField(
        null=True,
        blank=True
    )

    ultima_revision = models.DateField(
        null=True,
        blank=True
    )

    observaciones = models.TextField(
        null=True,
        blank=True
    )

    class Meta:
        ordering = ("cliente__nombre", "tipo")

    def __str__(self):
        nombre = self.nombre_equipo or self.get_tipo_display()
        return f"{self.cliente.nombre} - {nombre}"


class CotizacionEquipo(models.Model):

    ESTADO = [
        ("NO_REQUIERE", "No requiere"),
        ("PENDIENTE_ENVIO", "Pendiente de envío"),
        ("ENVIADA", "Enviada"),
        ("PENDIENTE_APROBACION", "Pendiente de aprobación"),
        ("APROBADA", "Aprobada"),
        ("RECHAZADA", "Rechazada"),
    ]

    equipo = models.ForeignKey(
        EquipoUnidad,
        on_delete=models.CASCADE,
        related_name="cotizaciones"
    )

    estado = models.CharField(
        max_length=25,
        choices=ESTADO,
        default="PENDIENTE_ENVIO"
    )

    valor = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True
    )

    fecha_envio = models.DateField(
        null=True,
        blank=True
    )

    observaciones = models.TextField(
        null=True,
        blank=True
    )

    creado_en = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ("-creado_en",)

    def __str__(self):
        return f"Cotización - {self.equipo} - {self.get_estado_display()}"

from django.contrib.auth.models import User

class UsuarioCliente(models.Model):

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.user.username} - {self.cliente.nombre}"
class ClienteAsignado(models.Model):
    usuario_cliente = models.ForeignKey(
        UsuarioCliente,
        on_delete=models.CASCADE,
        related_name="clientes_asignados"
    )

    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.CASCADE,
        related_name="usuarios_asignados"
    )

    principal = models.BooleanField(default=False)
    activo = models.BooleanField(default=True)

    class Meta:
        unique_together = ("usuario_cliente", "cliente")
        ordering = ["-principal", "cliente__nombre"]

    def __str__(self):
        return f"{self.usuario_cliente.user.username} - {self.cliente.nombre}"    
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
class EventoServicio(models.Model):

    servicio = models.ForeignKey(
        Emergencia,
        on_delete=models.CASCADE,
        related_name="eventos"
    )

    fecha = models.DateTimeField(auto_now_add=True)

    titulo = models.CharField(max_length=120)

    descripcion = models.TextField(blank=True)

    usuario = models.CharField(max_length=100, blank=True)

    icono = models.CharField(max_length=20, default="📌")

    class Meta:
        ordering = ["fecha"]

    def __str__(self):
        return f"{self.servicio.id} - {self.titulo}"
# =========================
# BITÁCORA OPERATIVA
# =========================

class BitacoraOperativa(models.Model):

    TIPO = [
        ("ACTIVIDAD_TECNICA", "Actividad técnica"),
        ("LLAMADA_CLIENTE", "Llamada de cliente"),
        ("REUNION", "Reunión"),
        ("REGRESO", "Regreso a unidad"),
        ("COTIZACION", "Cotización pendiente"),
        ("COMPROMISO", "Compromiso"),
        ("MATERIAL", "Material o repuesto pendiente"),
        ("ENTREGA_TURNO", "Entrega de turno"),
        ("NOTA_INTERNA", "Nota interna"),
        ("OTRO", "Otro"),
    ]

    PRIORIDAD = [
        ("BAJA", "Baja"),
        ("MEDIA", "Media"),
        ("ALTA", "Alta"),
        ("URGENTE", "Urgente"),
    ]

    ESTADO = [
        ("PENDIENTE", "Pendiente"),
        ("EN_SEGUIMIENTO", "En seguimiento"),
        ("CERRADO", "Cerrado"),
    ]

    titulo = models.CharField(
        max_length=180,
    )

    tipo = models.CharField(
        max_length=30,
        choices=TIPO,
        default="NOTA_INTERNA",
    )

    descripcion = models.TextField()

    accion_pendiente = models.TextField(
        blank=True,
        null=True,
    )

    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bitacoras",
    )
    actividad = models.ForeignKey(
        "ActividadTecnico",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bitacoras",
        verbose_name="Actividad técnica relacionada",
        help_text="Actividad realizada por el técnico relacionada con esta novedad.",
    )
    tecnico = models.ForeignKey(
        Tecnico,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bitacoras",
    )

    servicio = models.ForeignKey(
        Emergencia,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bitacoras",
    )

    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bitacoras_asignadas",
    )

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="bitacoras_creadas",
    )

    prioridad = models.CharField(
        max_length=15,
        choices=PRIORIDAD,
        default="MEDIA",
    )

    estado = models.CharField(
        max_length=20,
        choices=ESTADO,
        default="PENDIENTE",
    )

    fecha_compromiso = models.DateTimeField(
        null=True,
        blank=True,
    )

    fecha_cierre = models.DateTimeField(
        null=True,
        blank=True,
    )

    visible_cliente = models.BooleanField(
        default=False,
        help_text="Permite mostrar esta novedad en el portal del cliente.",
    )

    creado = models.DateTimeField(
        auto_now_add=True,
    )

    actualizado = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = (
            "estado",
            "-prioridad",
            "fecha_compromiso",
            "-creado",
        )
        verbose_name = "Bitácora operativa"
        verbose_name_plural = "Bitácoras operativas"

    def save(self, *args, **kwargs):
        if self.estado == "CERRADO" and self.fecha_cierre is None:
            self.fecha_cierre = timezone.now()

        if self.estado != "CERRADO":
            self.fecha_cierre = None

        super().save(*args, **kwargs)

    @property
    def vencida(self):
        return (
            self.estado != "CERRADO"
            and self.fecha_compromiso
            and self.fecha_compromiso < timezone.now()
        )

    def __str__(self):
        cliente = self.cliente.nombre if self.cliente else "Sin unidad"
        return f"{self.titulo} - {cliente}"

# =========================================================
# CATÁLOGO MAESTRO DE ACCESORIOS
# =========================================================

class Accesorio(models.Model):

    codigo = models.CharField(
        max_length=50,
        unique=True,
    )

    descripcion = models.CharField(
        max_length=250,
    )

    activo = models.BooleanField(
        default=True,
    )

    creado = models.DateTimeField(
        auto_now_add=True,
    )

    actualizado = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["descripcion"]
        verbose_name = "Accesorio"
        verbose_name_plural = "Accesorios"

    def __str__(self):
        # Al usuario solo le mostramos la descripción.
        return self.descripcion
    # =========================================================
# REMISIONES DE ACCESORIOS A TÉCNICOS
# =========================================================

class RemisionTecnico(models.Model):

    ESTADO = [
        ("PENDIENTE", "Pendiente de conciliar"),
        ("CONCILIADA", "Conciliada"),
    ]

    numero_remision = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Número de remisión física",
    )

    fecha = models.DateTimeField(
        default=timezone.now,
    )

    tecnico = models.ForeignKey(
        Tecnico,
        on_delete=models.PROTECT,
        related_name="remisiones",
    )

    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.PROTECT,
        related_name="remisiones_tecnicas",
    )

    servicio = models.ForeignKey(
        Emergencia,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="remisiones",
        help_text="Caso 7x24 relacionado, si existe.",
    )

    entregado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="remisiones_entregadas",
    )

    observaciones = models.TextField(
        blank=True,
    )

    estado = models.CharField(
        max_length=20,
        choices=ESTADO,
        default="PENDIENTE",
    )

    creado = models.DateTimeField(
        auto_now_add=True,
    )

    actualizado = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["-fecha", "-id"]
        verbose_name = "Remisión de técnico"
        verbose_name_plural = "Remisiones de técnicos"

    @property
    def esta_conciliada(self):
        detalles = self.detalles.all()

        if not detalles.exists():
            return False

        return all(detalle.esta_conciliado for detalle in detalles)

    def __str__(self):
        return (
            f"Remisión {self.numero_remision} - "
            f"{self.tecnico.nombre} - {self.cliente.nombre}"
        )


class DetalleRemision(models.Model):

    remision = models.ForeignKey(
        RemisionTecnico,
        on_delete=models.CASCADE,
        related_name="detalles",
    )

    codigo_accesorio = models.CharField(
        max_length=50,
        blank=True,
    )

    descripcion_accesorio = models.CharField(
        max_length=250,
    )

    cantidad_entregada = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
    )

    cantidad_utilizada = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
    )

    cantidad_devuelta = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
    )

    observaciones = models.TextField(
        blank=True,
    )

    @property
    def cantidad_pendiente(self):
        return (
            self.cantidad_entregada
            - self.cantidad_utilizada
            - self.cantidad_devuelta
        )

    @property
    def esta_conciliado(self):
        return self.cantidad_pendiente == Decimal("0.00")

    def __str__(self):
        return (
            f"{self.descripcion_accesorio} - "
            f"Remisión {self.remision.numero_remision}"
        )
   # =========================================================
# ACTIVIDADES / VISITAS DE TÉCNICOS
# =========================================================

class ActividadTecnico(models.Model):

    TIPO_ACTIVIDAD = [
        ("CORRECTIVO", "Correctivo"),
        ("DIAGNOSTICO", "Visita de diagnóstico"),
        ("REGRESO", "Regreso a unidad"),
        ("GARANTIA", "Garantía"),
        ("PREVENTIVO", "Mantenimiento preventivo"),
        ("INSTALACION", "Instalación"),
        ("OTRO", "Otro"),
    ]

    RESULTADO = [
        ("OPERATIVO", "Equipo operativo"),
        ("OPERATIVO_PROVISIONAL", "Operativo provisional"),
        ("PENDIENTE_REPUESTO", "Pendiente repuesto"),
        ("REQUIERE_COTIZACION", "Requiere cotización"),
        ("REQUIERE_REGRESO", "Requiere regreso"),
        ("NO_SOLUCIONADO", "No solucionado"),
    ]

    tecnico = models.ForeignKey(
        Tecnico,
        on_delete=models.PROTECT,
        related_name="actividades",
    )

    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.PROTECT,
        related_name="actividades_tecnicas",
    )

    servicio = models.ForeignKey(
        Emergencia,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="actividades_tecnicas",
    )

    remision = models.ForeignKey(
        "RemisionTecnico",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="actividades",
        help_text="Remisión de accesorios relacionada con esta actividad.",
    )

    tipo_actividad = models.CharField(
        max_length=30,
        choices=TIPO_ACTIVIDAD,
        default="CORRECTIVO",
    )

    fecha = models.DateField(
        default=timezone.localdate,
    )

    hora_llegada = models.TimeField(
        null=True,
        blank=True,
        verbose_name="Hora de llegada a la unidad",
    )

    hora_salida = models.TimeField(
        null=True,
        blank=True,
        verbose_name="Hora de salida de la unidad",
    )

    diagnostico = models.TextField(
        blank=True,
    )

    labor_realizada = models.TextField()

    resultado = models.CharField(
        max_length=30,
        choices=RESULTADO,
        null=True,
        blank=True,
    )

    requiere_regreso = models.BooleanField(
        default=False,
    )

    requiere_cotizacion = models.BooleanField(
        default=False,
    )

    observaciones = models.TextField(
        blank=True,
    )

    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="actividades_tecnicas_registradas",
    )

    creado = models.DateTimeField(
        auto_now_add=True,
    )

    actualizado = models.DateTimeField(
        auto_now=True,
    )

    @property
    def duracion_en_sitio(self):
        if not self.hora_llegada or not self.hora_salida:
            return None

        from datetime import datetime, timedelta

        llegada = datetime.combine(
            self.fecha,
            self.hora_llegada,
        )

        salida = datetime.combine(
            self.fecha,
            self.hora_salida,
        )

        # Si la atención termina después de medianoche.
        if salida < llegada:
            salida += timedelta(days=1)

        diferencia = salida - llegada
        minutos_totales = int(
            diferencia.total_seconds() // 60
        )

        horas = minutos_totales // 60
        minutos = minutos_totales % 60

        if horas and minutos:
            return f"{horas} h {minutos} min"

        if horas:
            return f"{horas} h"

        return f"{minutos} min"

    class Meta:
        ordering = [
            "-fecha",
            "-hora_llegada",
            "-id",
        ]
        verbose_name = "Actividad de técnico"
        verbose_name_plural = "Actividades de técnicos"

    def __str__(self):
        return (
            f"{self.fecha} - "
            f"{self.tecnico.nombre} - "
            f"{self.cliente.nombre}"
        )

    # =========================================================
# ACCESORIOS UTILIZADOS EN UNA ACTIVIDAD
# =========================================================

class AccesorioActividad(models.Model):

    actividad = models.ForeignKey(
        ActividadTecnico,
        on_delete=models.CASCADE,
        related_name="accesorios_utilizados",
    )

    accesorio = models.ForeignKey(
        Accesorio,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="usos_en_actividades",
    )

    es_otro = models.BooleanField(
        default=False,
    )

    descripcion_otro = models.CharField(
        max_length=250,
        blank=True,
    )

    cantidad = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=1,
    )

    observacion = models.TextField(
        blank=True,
    )

    creado = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["id"]
        verbose_name = "Accesorio utilizado"
        verbose_name_plural = "Accesorios utilizados"

    def __str__(self):

        if self.es_otro:
            descripcion = self.descripcion_otro or "Otro accesorio"
        elif self.accesorio:
            descripcion = self.accesorio.descripcion
        else:
            descripcion = "Accesorio sin identificar"

        return f"{descripcion} x {self.cantidad}"

# =========================================================
# PROGRAMACIÓN DE MANTENIMIENTOS PREVENTIVOS
# =========================================================

class ProgramacionMantenimientoPreventivo(models.Model):

    ESTADO = [
        ("PROGRAMADO", "Programado"),
        ("EN_PROCESO", "En proceso"),
        ("EJECUTADO", "Ejecutado"),
        ("REPROGRAMADO", "Reprogramado"),
        ("CANCELADO", "Cancelado"),
    ]

    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.PROTECT,
        related_name="preventivos_programados",
    )

    tecnico = models.ForeignKey(
        Tecnico,
        on_delete=models.PROTECT,
        related_name="preventivos_programados",
    )

    fecha_programada = models.DateField()

    hora_programada = models.TimeField(
        null=True,
        blank=True,
    )

    estado = models.CharField(
        max_length=20,
        choices=ESTADO,
        default="PROGRAMADO",
    )

    observaciones = models.TextField(
        blank=True,
    )

    fecha_reprogramada = models.DateField(
        null=True,
        blank=True,
    )

    motivo_reprogramacion = models.TextField(
        blank=True,
    )

    actividad = models.OneToOneField(
        ActividadTecnico,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="programacion_preventiva",
    )

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="preventivos_programados_creados",
    )

    creado = models.DateTimeField(
        auto_now_add=True,
    )

    actualizado = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = [
            "fecha_programada",
            "hora_programada",
            "id",
        ]
        verbose_name = "Programación de mantenimiento preventivo"
        verbose_name_plural = "Programaciones de mantenimientos preventivos"

    def __str__(self):
        return (
            f"{self.fecha_programada} - "
            f"{self.cliente.nombre} - "
            f"{self.tecnico.nombre}"
        )

# =========================================================
# MANTENIMIENTO PREVENTIVO
# =========================================================

class MantenimientoPreventivo(models.Model):

    actividad = models.OneToOneField(
        ActividadTecnico,
        on_delete=models.CASCADE,
        related_name="preventivo",
    )

    control_nivel = models.TextField(
        blank=True,
    )

    tablero_electrico = models.TextField(
        blank=True,
    )

    novedades = models.TextField(
        blank=True,
    )

    persona_recibe = models.CharField(
        max_length=150,
        blank=True,
    )

    cargo_recibe = models.CharField(
        max_length=120,
        blank=True,
    )

    firma_recibido = models.FileField(
        upload_to="preventivos/firmas/%Y/%m/",
        null=True,
        blank=True,
    )

    creado = models.DateTimeField(
        auto_now_add=True,
    )

    actualizado = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["-creado"]
        verbose_name = "Mantenimiento preventivo"
        verbose_name_plural = "Mantenimientos preventivos"

    def __str__(self):
        return (
            f"Preventivo - "
            f"{self.actividad.cliente.nombre} - "
            f"{self.actividad.fecha}"
        )


# =========================================================
# MEDICIONES DE EQUIPOS DURANTE PREVENTIVO
# =========================================================

class MedicionEquipoPreventivo(models.Model):

    ESTADO = [
        ("OPERATIVO", "Operativo"),
        ("CON_NOVEDAD", "Operativo con novedad"),
        ("FUERA_SERVICIO", "Fuera de servicio"),
        ("NO_REVISADO", "No revisado"),
    ]

    preventivo = models.ForeignKey(
        MantenimientoPreventivo,
        on_delete=models.CASCADE,
        related_name="mediciones_equipos",
    )

    equipo = models.ForeignKey(
        EquipoUnidad,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mediciones_preventivas",
    )

    nombre_equipo = models.CharField(
        max_length=180,
        blank=True,
        help_text="Nombre guardado como referencia histórica.",
    )

    voltaje_medido = models.CharField(
        max_length=50,
        blank=True,
    )

    corriente_medida = models.CharField(
        max_length=50,
        blank=True,
    )

    estado = models.CharField(
        max_length=25,
        choices=ESTADO,
        default="OPERATIVO",
    )

    observaciones = models.TextField(
        blank=True,
    )

    class Meta:
        ordering = ["id"]
        verbose_name = "Medición de equipo en preventivo"
        verbose_name_plural = "Mediciones de equipos en preventivos"

    def __str__(self):
        nombre = (
            self.nombre_equipo
            or (
                str(self.equipo)
                if self.equipo
                else "Equipo"
            )
        )
        return f"{nombre} - {self.preventivo.actividad.fecha}"


# =========================================================
# REVISIÓN DE COMPONENTES HIDRÁULICOS
# =========================================================

class RevisionComponentePreventivo(models.Model):

    TIPO = [
        ("VALVULA", "Válvula"),
        ("CHEQUE", "Cheque"),
        ("FLOTADOR", "Flotador mecánico"),
        ("PRESOSTATO", "Presostato"),
        ("MANOMETRO", "Manómetro"),
        ("OTRO", "Otro"),
    ]

    ESTADO = [
        ("OK", "Funciona correctamente"),
        ("CON_NOVEDAD", "Presenta novedad"),
        ("REQUIERE_CAMBIO", "Requiere cambio"),
        ("NO_APLICA", "No aplica"),
    ]

    preventivo = models.ForeignKey(
        MantenimientoPreventivo,
        on_delete=models.CASCADE,
        related_name="componentes_revisados",
    )

    tipo = models.CharField(
        max_length=30,
        choices=TIPO,
    )

    estado = models.CharField(
        max_length=30,
        choices=ESTADO,
        default="OK",
    )

    observaciones = models.TextField(
        blank=True,
    )

    class Meta:
        ordering = ["tipo", "id"]
        verbose_name = "Componente revisado en preventivo"
        verbose_name_plural = "Componentes revisados en preventivos"

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.get_estado_display()}"


# =========================================================
# REVISIÓN DE TANQUES HIDRONEUMÁTICOS
# =========================================================

class RevisionTanquePreventivo(models.Model):

    preventivo = models.ForeignKey(
        MantenimientoPreventivo,
        on_delete=models.CASCADE,
        related_name="tanques_revisados",
    )

    tanque = models.ForeignKey(
        TanqueUnidad,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="revisiones_preventivas",
    )

    descripcion_tanque = models.CharField(
        max_length=180,
        blank=True,
        help_text="Descripción guardada como referencia histórica.",
    )

    capacidad = models.CharField(
        max_length=100,
        blank=True,
    )

    precarga_aire = models.CharField(
        max_length=100,
        blank=True,
    )

    observaciones = models.TextField(
        blank=True,
    )

    class Meta:
        ordering = ["id"]
        verbose_name = "Revisión de tanque en preventivo"
        verbose_name_plural = "Revisiones de tanques en preventivos"

    def __str__(self):
        descripcion = (
            self.descripcion_tanque
            or (
                str(self.tanque)
                if self.tanque
                else "Tanque"
            )
        )
        return descripcion    