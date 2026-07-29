from django.db import models
from django.utils import timezone

from operacion.models import Cliente


class DocumentoCliente(models.Model):

    TIPO_DOCUMENTO = [
        ("INFORME", "Informe Técnico"),
        ("PREVENTIVO", "Mantenimiento Preventivo"),
        ("CORRECTIVO", "Mantenimiento Correctivo"),
        ("LAVADO", "Lavado de Tanques"),
        ("CERTIFICADO", "Certificado"),
        ("COTIZACION", "Cotización"),
        ("MANUAL", "Manual"),
        ("OTRO", "Otro"),
    ]

    ESTADO = [
        ("BORRADOR", "Borrador"),
        ("REVISION", "En revisión"),
        ("PUBLICADO", "Publicado"),
    ]

    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.CASCADE,
        related_name="documentos",
    )

    titulo = models.CharField(max_length=200)

    tipo = models.CharField(
        max_length=20,
        choices=TIPO_DOCUMENTO,
        default="INFORME",
    )

    fecha_documento = models.DateField()

    archivo = models.FileField(
        upload_to="documentos_clientes/%Y/%m/",
    )

    estado = models.CharField(
        max_length=20,
        choices=ESTADO,
        default="BORRADOR",
    )

    observaciones = models.TextField(
        blank=True,
        null=True,
    )

    fecha_publicacion = models.DateTimeField(
        null=True,
        blank=True,
    )

    creado = models.DateTimeField(
        auto_now_add=True,
    )

    actualizado = models.DateTimeField(
        auto_now=True,
    )

    def save(self, *args, **kwargs):
        if self.estado == "PUBLICADO" and self.fecha_publicacion is None:
            self.fecha_publicacion = timezone.now()

        if self.estado != "PUBLICADO":
            self.fecha_publicacion = None

        super().save(*args, **kwargs)

    class Meta:
        ordering = ["-fecha_documento"]

    def __str__(self):
        return f"{self.cliente.nombre} - {self.titulo}"