from decimal import Decimal

from django.conf import settings
from django.db import models

from operacion.models import Cliente


# =========================================================
# LIQUIDACIÓN COMERCIAL
# =========================================================

class Liquidacion(models.Model):

    ESTADOS = [
        ("BORRADOR", "Borrador"),
        ("REVISION", "Pendiente de revisión"),
        ("DEVUELTA", "Devuelta para corrección"),
        ("APROBADA", "Aprobada"),
        ("LISTA_FACTURAR", "Lista para facturar"),
        ("FACTURADA", "Facturada"),
        ("ANULADA", "Anulada"),
    ]

    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.PROTECT,
        related_name="liquidaciones_comerciales",
    )

    descripcion = models.TextField(
        verbose_name="Descripción / concepto",
    )

    estado = models.CharField(
        max_length=20,
        choices=ESTADOS,
        default="BORRADOR",
        db_index=True,
    )

    # =========================
    # VALORES
    # =========================

    subtotal_materiales = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
    )

    mano_obra = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
    )

    horas_adicionales = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
    )

    transporte = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
    )

    otros_costos = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
    )

    valor_sin_iva = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
    )

    valor_iva = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
    )

    valor_total = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
    )

    # =========================
    # CONTROL Y APROBACIÓN
    # =========================

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="liquidaciones_creadas",
    )

    revisado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="liquidaciones_revisadas",
    )

    observaciones_revision = models.TextField(
        blank=True,
    )

    fecha_creacion = models.DateTimeField(
        auto_now_add=True,
    )

    fecha_actualizacion = models.DateTimeField(
        auto_now=True,
    )

    fecha_revision = models.DateTimeField(
        null=True,
        blank=True,
    )

    fecha_facturacion = models.DateTimeField(
        null=True,
        blank=True,
    )

    numero_factura = models.CharField(
        max_length=50,
        blank=True,
        help_text="Número de factura generado posteriormente en SIIGO.",
    )

    class Meta:
        ordering = ["-fecha_creacion"]
        verbose_name = "Liquidación comercial"
        verbose_name_plural = "Liquidaciones comerciales"

    # =====================================================
    # RECÁLCULO AUTOMÁTICO
    # =====================================================

    def recalcular_totales(self):

        detalles = self.detalles.all()

        materiales = sum(
            (
                d.subtotal
                for d in detalles
                if d.tipo == "MATERIAL"
            ),
            Decimal("0.00"),
        )

        mano_obra = sum(
            (
                d.subtotal
                for d in detalles
                if d.tipo == "MANO_OBRA"
            ),
            Decimal("0.00"),
        )

        horas = sum(
            (
                d.subtotal
                for d in detalles
                if d.tipo == "HORA_ADICIONAL"
            ),
            Decimal("0.00"),
        )

        transporte = sum(
            (
                d.subtotal
                for d in detalles
                if d.tipo == "TRANSPORTE"
            ),
            Decimal("0.00"),
        )

        otros = sum(
            (
                d.subtotal
                for d in detalles
                if d.tipo in ["AUXILIO", "OTRO"]
            ),
            Decimal("0.00"),
        )

        valor_sin_iva = (
            materiales
            + mano_obra
            + horas
            + transporte
            + otros
        )

        valor_iva = (
            valor_sin_iva
            * Decimal("0.19")
        )

        valor_total = (
            valor_sin_iva
            + valor_iva
        )

        self.subtotal_materiales = materiales
        self.mano_obra = mano_obra
        self.horas_adicionales = horas
        self.transporte = transporte
        self.otros_costos = otros

        self.valor_sin_iva = valor_sin_iva
        self.valor_iva = valor_iva
        self.valor_total = valor_total

        self.save(
            update_fields=[
                "subtotal_materiales",
                "mano_obra",
                "horas_adicionales",
                "transporte",
                "otros_costos",
                "valor_sin_iva",
                "valor_iva",
                "valor_total",
                "fecha_actualizacion",
            ]
        )

    def __str__(self):
        return (
            f"Liquidación #{self.pk} - "
            f"{self.cliente}"
        )


# =========================================================
# DETALLE DE LA LIQUIDACIÓN
# =========================================================

class DetalleLiquidacion(models.Model):

    TIPO = [
        ("MATERIAL", "Material / accesorio"),
        ("MANO_OBRA", "Mano de obra"),
        ("HORA_ADICIONAL", "Hora adicional"),
        ("TRANSPORTE", "Transporte"),
        ("AUXILIO", "Auxilio"),
        ("OTRO", "Otro costo"),
    ]

    liquidacion = models.ForeignKey(
        Liquidacion,
        on_delete=models.CASCADE,
        related_name="detalles",
    )
    catalogo = models.ForeignKey(
    "CatalogoPrecio",
    on_delete=models.PROTECT,
    null=True,
    blank=True,
    related_name="detalles_liquidacion",
    verbose_name="Accesorio del catálogo",
    )
    tipo = models.CharField(
        max_length=20,
        choices=TIPO,
    )

    descripcion = models.CharField(
        max_length=250,
    )

    cantidad = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=1,
    )

    valor_unitario = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
    )

    subtotal = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
    )

    observaciones = models.TextField(
        blank=True,
    )

    creado = models.DateTimeField(
        auto_now_add=True,
    )

    def save(self, *args, **kwargs):

        self.subtotal = (
            self.cantidad
            * self.valor_unitario
        )

        super().save(*args, **kwargs)

        self.liquidacion.recalcular_totales()

    def delete(self, *args, **kwargs):

        liquidacion = self.liquidacion

        super().delete(*args, **kwargs)

        liquidacion.recalcular_totales()

    def __str__(self):
        return (
            f"{self.get_tipo_display()} - "
            f"{self.descripcion}"
        )


# =========================================================
# CATÁLOGO DE PRECIOS
# =========================================================

class CatalogoPrecio(models.Model):

    codigo = models.CharField(
    max_length=50,
    unique=True,
    )

    descripcion = models.CharField(
        max_length=250,
        unique=True,
    )

    valor = models.DecimalField(
        max_digits=14,
        decimal_places=2,
    )

    activo = models.BooleanField(
        default=True,
    )

    actualizado = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["descripcion"]
        verbose_name = "Precio"
        verbose_name_plural = "Catálogo de precios"

    def __str__(self):
        return self.descripcion


# =========================================================
# TARIFAS OPERATIVAS
# =========================================================

class TarifaOperativa(models.Model):

    TIPO = [
        ("HORA_NORMAL", "Hora normal"),
        ("HORA_NOCTURNA", "Hora nocturna"),
        ("SABADO", "Sábado"),
        ("DOMINGO_FESTIVO", "Domingo / Festivo"),
        ("AUXILIO", "Auxilio"),
        ("TRANSPORTE", "Transporte"),
        ("OTRO", "Otro"),
    ]

    tipo = models.CharField(
        max_length=30,
        choices=TIPO,
    )

    nombre = models.CharField(
        max_length=150,
    )

    valor = models.DecimalField(
        max_digits=14,
        decimal_places=2,
    )

    activo = models.BooleanField(
        default=True,
    )

    observaciones = models.TextField(
        blank=True,
    )

    class Meta:
        ordering = ["tipo", "nombre"]
        verbose_name = "Tarifa operativa"
        verbose_name_plural = "Tarifas operativas"

    def __str__(self):
        return (
            f"{self.nombre} - "
            f"${self.valor}"
        )