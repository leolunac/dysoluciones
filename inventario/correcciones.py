"""Correcciones auditadas de cantidades, sin alterar movimientos originales."""
from decimal import Decimal
from django import forms
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from .models import ConsumoInventario, CorreccionCantidadConsumo, DetalleConsumoInventario, ProductoInventario
from .permisos import exigir_gestion
from .servicios import registrar_movimiento

TIPOS_CONSUMO = ("CONSUMO", "CORR_CONSUMO_ENTRADA", "CORR_CONSUMO_SALIDA")


def corregir_cantidad(*, consumo_id, detalle_id, cantidad, motivo, revision, usuario):
    exigir_gestion(usuario)
    if not usuario.is_active:
        raise PermissionDenied
    cantidad = forms.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01")).clean(cantidad)
    motivo = forms.CharField(min_length=5, max_length=1000, strip=True).clean(motivo)
    revision = forms.IntegerField(min_value=0).clean(revision)
    with transaction.atomic():
        # Mismo orden de bloqueo que confirmar_consumo: padre, detalle, producto.
        consumo = ConsumoInventario.objects.select_for_update().get(pk=consumo_id)
        detalle = DetalleConsumoInventario.objects.select_for_update().get(pk=detalle_id, consumo_id=consumo.pk)
        actual = detalle.correcciones.order_by("-pk").values_list("pk", flat=True).first() or 0
        if revision != actual:
            raise ValidationError("La cantidad ya fue corregida por otra operación. Recargue y revise el historial antes de continuar.")
        if consumo.estado not in ("BORRADOR", "CONFIRMADO"):
            raise ValidationError("El estado de este consumo no permite corregir cantidades.")
        anterior = detalle.cantidad
        if cantidad == anterior:
            raise ValidationError("La cantidad nueva debe ser diferente de la actual.")
        correccion = CorreccionCantidadConsumo.objects.create(
            detalle=detalle, cantidad_anterior=anterior, cantidad_nueva=cantidad,
            estado_consumo=consumo.estado, motivo=motivo, registrado_por=usuario,
        )
        if consumo.estado == "CONFIRMADO":
            producto = ProductoInventario.objects.select_for_update().get(pk=detalle.producto_id)
            diferencia = cantidad - anterior
            # Usar la fecha y el precio del consumo para corregir también su periodo.
            datos = dict(producto=producto, cantidad=abs(diferencia), cliente=consumo.cliente,
                         usuario=usuario, referencia=f"Corrección #{correccion.pk} · Consumo #{consumo.pk}",
                         observaciones=f"Cantidad {anterior} → {cantidad}. Motivo: {motivo}",
                         clave_idempotencia=f"CORRECCION_CONSUMO:{correccion.pk}",
                         precio_referencia=detalle.precio_referencia_snapshot,
                         fecha_operacion=consumo.fecha)
            if diferencia > 0:
                datos.update(tipo="CORR_CONSUMO_SALIDA", origen=consumo.ubicacion_origen)
            else:
                datos.update(tipo="CORR_CONSUMO_ENTRADA", destino=consumo.ubicacion_origen)
            movimiento, _ = registrar_movimiento(**datos)
            correccion.movimiento = movimiento
            correccion.save(update_fields=["movimiento"])
        detalle.cantidad = cantidad
        detalle.save(update_fields=["cantidad"])
        return correccion
