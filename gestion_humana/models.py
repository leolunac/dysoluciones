import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from .storage import almacenamiento_privado


EXTENSIONES_DOCUMENTOS = ["pdf", "jpg", "jpeg", "png", "doc", "docx"]


def validar_tamano_archivo(archivo):
    if archivo and archivo.size > 10 * 1024 * 1024:
        raise ValidationError("El archivo no puede superar 10 MB.")


def ruta_privada(instancia, nombre):
    extension = Path(nombre).suffix.lower()
    return f"gestion_humana/{instancia._meta.model_name}/{uuid.uuid4().hex}{extension}"


class Empleado(models.Model):
    TIPOS_DOCUMENTO = [
        ("CC", "Cédula de ciudadanía"),
        ("CE", "Cédula de extranjería"),
        ("PA", "Pasaporte"),
        ("PPT", "Permiso por protección temporal"),
    ]
    ESTADOS = [
        ("ACTIVO", "Activo"),
        ("INACTIVO", "Inactivo"),
        ("RETIRADO", "Retirado"),
    ]

    tecnico = models.OneToOneField(
        "operacion.Tecnico",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ficha_empleado",
    )
    tipo_documento = models.CharField(max_length=5, choices=TIPOS_DOCUMENTO, default="CC")
    numero_documento = models.CharField(max_length=30, unique=True, db_index=True)
    nombres = models.CharField(max_length=120)
    apellidos = models.CharField(max_length=120)
    fecha_nacimiento = models.DateField(null=True, blank=True)
    telefono = models.CharField(max_length=40, blank=True)
    correo_personal = models.EmailField(blank=True)
    correo_corporativo = models.EmailField(blank=True)
    direccion = models.CharField(max_length=250, blank=True)
    contacto_emergencia = models.CharField(max_length=180, blank=True)
    telefono_emergencia = models.CharField(max_length=40, blank=True)
    cargo = models.CharField(max_length=120)
    area = models.CharField(max_length=120, blank=True)
    fecha_ingreso = models.DateField()
    fecha_retiro = models.DateField(null=True, blank=True)
    estado = models.CharField(max_length=10, choices=ESTADOS, default="ACTIVO", db_index=True)
    foto = models.ImageField(
        storage=almacenamiento_privado,
        upload_to=ruta_privada,
        null=True,
        blank=True,
        validators=[
            FileExtensionValidator(["jpg", "jpeg", "png"]),
            validar_tamano_archivo,
        ],
    )
    observaciones = models.TextField(blank=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="empleados_creados",
    )
    actualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="empleados_actualizados",
    )
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["apellidos", "nombres", "pk"]
        verbose_name = "Empleado"
        verbose_name_plural = "Empleados"

    @property
    def nombre_completo(self):
        return f"{self.nombres} {self.apellidos}".strip()

    def clean(self):
        super().clean()
        self.numero_documento = self.numero_documento.strip()
        if self.fecha_retiro and self.fecha_retiro < self.fecha_ingreso:
            raise ValidationError({"fecha_retiro": "No puede ser anterior al ingreso."})

    def __str__(self):
        return f"{self.nombre_completo} - {self.numero_documento}"


class ContratoLaboral(models.Model):
    TIPOS = [
        ("INDEFINIDO", "Término indefinido"),
        ("FIJO", "Término fijo"),
        ("OBRA", "Obra o labor"),
        ("APRENDIZAJE", "Aprendizaje"),
        ("SERVICIOS", "Prestación de servicios"),
        ("OTRO", "Otro"),
    ]

    empleado = models.ForeignKey(Empleado, on_delete=models.CASCADE, related_name="contratos")
    tipo = models.CharField(max_length=20, choices=TIPOS)
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField(null=True, blank=True, db_index=True)
    cargo = models.CharField(max_length=120)
    salario = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    documento = models.FileField(
        storage=almacenamiento_privado,
        upload_to=ruta_privada,
        null=True,
        blank=True,
        validators=[FileExtensionValidator(EXTENSIONES_DOCUMENTOS), validar_tamano_archivo],
    )
    observaciones = models.TextField(blank=True)
    activo = models.BooleanField(
        default=True,
        help_text="Marque únicamente el contrato que actualmente rige la vinculación.",
    )
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha_inicio", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["empleado"],
                condition=models.Q(activo=True),
                name="contrato_laboral_activo_unico",
            )
        ]

    def clean(self):
        super().clean()
        if self.fecha_fin and self.fecha_fin < self.fecha_inicio:
            raise ValidationError({"fecha_fin": "No puede ser anterior al inicio."})

    @property
    def vigente(self):
        hoy = timezone.localdate()
        return self.fecha_inicio <= hoy and (not self.fecha_fin or self.fecha_fin >= hoy)

    def __str__(self):
        return f"{self.empleado} - {self.get_tipo_display()}"


class AfiliacionSeguridadSocial(models.Model):
    TIPOS = [
        ("EPS", "EPS"),
        ("PENSION", "Fondo de pensiones"),
        ("ARL", "ARL"),
        ("CAJA", "Caja de compensación"),
    ]

    empleado = models.ForeignKey(Empleado, on_delete=models.CASCADE, related_name="afiliaciones")
    tipo = models.CharField(max_length=10, choices=TIPOS)
    entidad = models.CharField(max_length=160)
    fecha_inicio = models.DateField(null=True, blank=True)
    fecha_fin = models.DateField(null=True, blank=True)
    nivel_riesgo = models.CharField(max_length=30, blank=True, help_text="Solo cuando corresponda.")
    soporte = models.FileField(
        storage=almacenamiento_privado,
        upload_to=ruta_privada,
        null=True,
        blank=True,
        validators=[FileExtensionValidator(EXTENSIONES_DOCUMENTOS), validar_tamano_archivo],
    )
    observaciones = models.TextField(blank=True)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["tipo", "-fecha_inicio", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["empleado", "tipo"],
                condition=models.Q(fecha_fin__isnull=True),
                name="afiliacion_actual_unica_por_tipo",
            )
        ]

    def clean(self):
        super().clean()
        if self.fecha_inicio and self.fecha_fin and self.fecha_fin < self.fecha_inicio:
            raise ValidationError({"fecha_fin": "No puede ser anterior al inicio."})

    def __str__(self):
        return f"{self.empleado} - {self.get_tipo_display()}: {self.entidad}"


class CertificacionEmpleado(models.Model):
    TIPOS = [
        ("ALTURAS", "Trabajo en alturas"),
        ("CONFINADOS", "Espacios confinados"),
        ("SST", "Seguridad y salud en el trabajo"),
        ("OTRO", "Otro"),
    ]

    empleado = models.ForeignKey(Empleado, on_delete=models.CASCADE, related_name="certificaciones")
    tipo = models.CharField(max_length=20, choices=TIPOS)
    nombre = models.CharField(max_length=180)
    entidad_emisora = models.CharField(max_length=180, blank=True)
    fecha_expedicion = models.DateField(null=True, blank=True)
    fecha_vencimiento = models.DateField(null=True, blank=True, db_index=True)
    soporte = models.FileField(
        storage=almacenamiento_privado,
        upload_to=ruta_privada,
        null=True,
        blank=True,
        validators=[FileExtensionValidator(EXTENSIONES_DOCUMENTOS), validar_tamano_archivo],
    )
    observaciones = models.TextField(blank=True)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["fecha_vencimiento", "tipo", "pk"]

    def clean(self):
        super().clean()
        if (
            self.fecha_expedicion
            and self.fecha_vencimiento
            and self.fecha_vencimiento < self.fecha_expedicion
        ):
            raise ValidationError({"fecha_vencimiento": "No puede ser anterior a la expedición."})

    def __str__(self):
        return f"{self.empleado} - {self.nombre}"


class DocumentoEmpleado(models.Model):
    TIPOS = [
        ("IDENTIDAD", "Documento de identidad"),
        ("HOJA_VIDA", "Hoja de vida"),
        ("EXAMEN_MEDICO", "Examen médico ocupacional"),
        ("LICENCIA", "Licencia o matrícula"),
        ("AUTORIZACION", "Autorización"),
        ("OTRO", "Otro"),
    ]

    empleado = models.ForeignKey(Empleado, on_delete=models.CASCADE, related_name="documentos")
    tipo = models.CharField(max_length=20, choices=TIPOS)
    nombre = models.CharField(max_length=180)
    fecha_documento = models.DateField(null=True, blank=True)
    fecha_vencimiento = models.DateField(null=True, blank=True, db_index=True)
    archivo = models.FileField(
        storage=almacenamiento_privado,
        upload_to=ruta_privada,
        validators=[FileExtensionValidator(EXTENSIONES_DOCUMENTOS), validar_tamano_archivo],
    )
    observaciones = models.TextField(blank=True)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["tipo", "-fecha_documento", "-pk"]

    def clean(self):
        super().clean()
        if (
            self.fecha_documento
            and self.fecha_vencimiento
            and self.fecha_vencimiento < self.fecha_documento
        ):
            raise ValidationError({"fecha_vencimiento": "No puede ser anterior a la fecha del documento."})

    def __str__(self):
        return f"{self.empleado} - {self.nombre}"


class HistorialEmpleado(models.Model):
    empleado = models.ForeignKey(Empleado, on_delete=models.CASCADE, related_name="historial")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    accion = models.CharField(max_length=80)
    detalle = models.TextField(blank=True)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha", "-pk"]

    def __str__(self):
        return f"{self.empleado} - {self.accion}"
