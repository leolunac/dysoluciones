from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from operacion.models import Accesorio, Cliente, Tecnico


class ProductoInventario(models.Model):
    accesorio = models.OneToOneField(
        Accesorio,
        on_delete=models.PROTECT,
        related_name="producto_inventario",
    )
    unidad_medida = models.CharField(max_length=30, default="UNID")
    stock_minimo = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    precio_referencia = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Valor unitario antes del descuento del proveedor.",
    )
    costo_neto_ultimo = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Costo real pagado después del descuento.",
    )
    activo = models.BooleanField(default=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["accesorio__descripcion"]
        verbose_name = "Producto de inventario"
        verbose_name_plural = "Productos de inventario"

    def __str__(self):
        return f"{self.accesorio.codigo} - {self.accesorio.descripcion}"


class Proveedor(models.Model):
    nombre = models.CharField(max_length=200, unique=True)
    nit = models.CharField(max_length=30, blank=True, db_index=True)
    telefono = models.CharField(max_length=50, blank=True)
    correo = models.EmailField(blank=True)
    direccion = models.CharField(max_length=250, blank=True)
    activo = models.BooleanField(default=True)
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class ReferenciaProveedor(models.Model):
    producto = models.ForeignKey(
        ProductoInventario,
        on_delete=models.PROTECT,
        related_name="referencias_proveedor",
    )
    proveedor = models.ForeignKey(
        Proveedor,
        on_delete=models.PROTECT,
        related_name="referencias_productos",
    )
    codigo_proveedor = models.CharField(max_length=80)
    descripcion_proveedor = models.CharField(max_length=250, blank=True)
    activa = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["proveedor", "codigo_proveedor"],
                name="inventario_ref_proveedor_codigo_unico",
            )
        ]
        ordering = ["proveedor__nombre", "codigo_proveedor"]

    def __str__(self):
        return f"{self.proveedor} - {self.codigo_proveedor}"


class UbicacionInventario(models.Model):
    TIPOS = [
        ("BODEGA", "Bodega"),
        ("TECNICO", "En poder de técnico"),
    ]

    nombre = models.CharField(max_length=150, unique=True)
    tipo = models.CharField(max_length=20, choices=TIPOS, db_index=True)
    tecnico = models.OneToOneField(
        Tecnico,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ubicacion_inventario",
    )
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ["tipo", "nombre"]

    def clean(self):
        if self.tipo == "TECNICO" and not self.tecnico_id:
            raise ValidationError({"tecnico": "Seleccione el técnico de esta ubicación."})
        if self.tipo == "BODEGA" and self.tecnico_id:
            raise ValidationError({"tecnico": "Una bodega no debe tener técnico."})

    def __str__(self):
        return self.nombre


class ExistenciaInventario(models.Model):
    producto = models.ForeignKey(
        ProductoInventario,
        on_delete=models.PROTECT,
        related_name="existencias",
    )
    ubicacion = models.ForeignKey(
        UbicacionInventario,
        on_delete=models.PROTECT,
        related_name="existencias",
    )
    cantidad = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["producto", "ubicacion"],
                name="inventario_existencia_producto_ubicacion_unica",
            ),
            models.CheckConstraint(
                condition=models.Q(cantidad__gte=0),
                name="inventario_existencia_no_negativa",
            ),
        ]
        ordering = ["producto__accesorio__descripcion"]

    def __str__(self):
        return f"{self.producto} - {self.ubicacion}: {self.cantidad}"


class MovimientoInventario(models.Model):
    TIPOS = [
        ("SALDO_INICIAL", "Saldo inicial"),
        ("ENTRADA_COMPRA", "Entrada por compra"),
        ("TRASLADO", "Traslado"),
        ("CONSUMO", "Consumo en cliente"),
        ("DEVOLUCION", "Devolución"),
        ("AJUSTE_ENTRADA", "Ajuste de entrada"),
        ("AJUSTE_SALIDA", "Ajuste de salida"),
    ]

    producto = models.ForeignKey(
        ProductoInventario,
        on_delete=models.PROTECT,
        related_name="movimientos",
    )
    tipo = models.CharField(max_length=25, choices=TIPOS, db_index=True)
    cantidad = models.DecimalField(max_digits=14, decimal_places=2)
    origen = models.ForeignKey(
        UbicacionInventario,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="movimientos_salida",
    )
    destino = models.ForeignKey(
        UbicacionInventario,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="movimientos_entrada",
    )
    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="movimientos_inventario",
    )
    precio_referencia_snapshot = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    costo_neto_snapshot = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    referencia = models.CharField(max_length=150, blank=True)
    clave_idempotencia = models.CharField(
        max_length=180,
        unique=True,
        null=True,
        blank=True,
    )
    observaciones = models.TextField(blank=True)
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movimientos_inventario_registrados",
    )
    creado = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-creado", "-id"]

    def clean(self):
        if self.cantidad < 0 or (
            self.cantidad == 0 and self.tipo != "SALDO_INICIAL"
        ):
            raise ValidationError({"cantidad": "La cantidad debe ser mayor que cero."})
        if not self.origen_id and not self.destino_id:
            raise ValidationError("El movimiento debe tener origen o destino.")
        if self.origen_id and self.origen_id == self.destino_id:
            raise ValidationError("El origen y el destino deben ser diferentes.")

    @property
    def valor_referencia(self):
        return self.cantidad * self.precio_referencia_snapshot

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.producto} x {self.cantidad}"


class EntradaInventario(models.Model):
    ESTADOS = [("BORRADOR", "Borrador"), ("CONFIRMADA", "Confirmada")]

    proveedor = models.ForeignKey(
        Proveedor,
        on_delete=models.PROTECT,
        related_name="entradas",
    )
    numero_factura = models.CharField(max_length=80)
    fecha_factura = models.DateField()
    estado = models.CharField(max_length=15, choices=ESTADOS, default="BORRADOR")
    observaciones = models.TextField(blank=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="entradas_inventario_creadas",
    )
    confirmado_en = models.DateTimeField(null=True, blank=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["proveedor", "numero_factura"],
                name="inventario_factura_unica_por_proveedor",
            )
        ]
        ordering = ["-fecha_factura", "-id"]

    def __str__(self):
        return f"{self.proveedor} - Factura {self.numero_factura}"


class DetalleEntradaInventario(models.Model):
    entrada = models.ForeignKey(
        EntradaInventario,
        on_delete=models.CASCADE,
        related_name="detalles",
    )
    producto = models.ForeignKey(
        ProductoInventario,
        on_delete=models.PROTECT,
        related_name="detalles_entrada",
    )
    referencia_proveedor = models.ForeignKey(
        ReferenciaProveedor,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="detalles_entrada",
    )
    cantidad = models.DecimalField(max_digits=14, decimal_places=2)
    precio_unitario_lista = models.DecimalField(max_digits=14, decimal_places=2)
    porcentaje_descuento = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    class Meta:
        ordering = ["id"]

    def clean(self):
        if self.cantidad <= 0:
            raise ValidationError({"cantidad": "La cantidad debe ser mayor que cero."})
        if not Decimal("0.00") <= self.porcentaje_descuento < Decimal("100.00"):
            raise ValidationError({"porcentaje_descuento": "El descuento debe estar entre 0 y 99,99 %."})
        if self.referencia_proveedor_id and (
            self.referencia_proveedor.proveedor_id != self.entrada.proveedor_id
            or self.referencia_proveedor.producto_id != self.producto_id
        ):
            raise ValidationError("La referencia no corresponde al proveedor y producto seleccionados.")

    @property
    def costo_unitario_neto(self):
        factor = Decimal("1.00") - self.porcentaje_descuento / Decimal("100.00")
        return (self.precio_unitario_lista * factor).quantize(Decimal("0.01"))

    @property
    def total_lista(self):
        return self.cantidad * self.precio_unitario_lista

    @property
    def total_neto(self):
        return self.cantidad * self.costo_unitario_neto


class ConsumoInventario(models.Model):
    ESTADOS = [("BORRADOR", "Borrador"), ("CONFIRMADO", "Confirmado")]

    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.PROTECT,
        related_name="consumos_inventario",
    )
    ubicacion_origen = models.ForeignKey(
        UbicacionInventario,
        on_delete=models.PROTECT,
        related_name="consumos",
    )
    fecha = models.DateTimeField(default=timezone.now, db_index=True)
    estado = models.CharField(max_length=15, choices=ESTADOS, default="BORRADOR")
    observaciones = models.TextField(blank=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="consumos_inventario_creados",
    )
    confirmado_en = models.DateTimeField(null=True, blank=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha", "-id"]

    def __str__(self):
        return f"Consumo {self.pk or 'nuevo'} - {self.cliente}"


class DetalleConsumoInventario(models.Model):
    consumo = models.ForeignKey(
        ConsumoInventario,
        on_delete=models.CASCADE,
        related_name="detalles",
    )
    producto = models.ForeignKey(
        ProductoInventario,
        on_delete=models.PROTECT,
        related_name="detalles_consumo",
    )
    cantidad = models.DecimalField(max_digits=14, decimal_places=2)
    precio_referencia_snapshot = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    class Meta:
        ordering = ["id"]

    def clean(self):
        if self.cantidad <= 0:
            raise ValidationError({"cantidad": "La cantidad debe ser mayor que cero."})

    @property
    def total(self):
        return self.cantidad * self.precio_referencia_snapshot
