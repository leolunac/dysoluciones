"""Correcciones auditadas de cantidades en entradas por compra."""
from decimal import Decimal

from django import forms
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from .models import (
    CorreccionCantidadEntrada, DetalleEntradaInventario, EntradaInventario,
    MovimientoInventario, ProductoInventario,
)
from .permisos import exigir_gestion
from .servicios import registrar_movimiento


def corregir_cantidad_entrada(*, entrada_id, detalle_id, cantidad, motivo, revision, usuario):
    exigir_gestion(usuario)
    if not usuario.is_active:
        raise PermissionDenied
    cantidad = forms.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01")).clean(cantidad)
    motivo = forms.CharField(min_length=5, max_length=1000, strip=True).clean(motivo)
    revision = forms.IntegerField(min_value=0).clean(revision)

    with transaction.atomic():
        # Confirmar entrada también bloquea primero el padre y luego el producto.
        entrada = EntradaInventario.objects.select_for_update().get(pk=entrada_id)
        detalle = DetalleEntradaInventario.objects.select_for_update().get(pk=detalle_id, entrada_id=entrada.pk)
        actual = detalle.correcciones.order_by("-pk").values_list("pk", flat=True).first() or 0
        if revision != actual:
            raise ValidationError("La cantidad ya fue corregida por otra operación. Recargue y revise el historial antes de continuar.")
        if entrada.estado not in ("BORRADOR", "CONFIRMADA"):
            raise ValidationError("El estado de esta entrada no permite corregir cantidades.")
        anterior = detalle.cantidad
        if cantidad == anterior:
            raise ValidationError("La cantidad nueva debe ser diferente de la actual.")

        correccion = CorreccionCantidadEntrada.objects.create(
            detalle=detalle, cantidad_anterior=anterior, cantidad_nueva=cantidad,
            estado_entrada=entrada.estado, motivo=motivo, registrado_por=usuario,
        )
        if entrada.estado == "CONFIRMADA":
            producto = ProductoInventario.objects.select_for_update().get(pk=detalle.producto_id)
            original = MovimientoInventario.objects.filter(
                clave_idempotencia=f"ENTRADA:{entrada.pk}:{detalle.pk}",
                tipo="ENTRADA_COMPRA", producto_id=producto.pk,
            ).first()
            if original is None or not original.destino_id or original.origen_id:
                raise ValidationError("No se encontró un movimiento de compra válido para esta línea. Revise la entrada antes de corregirla.")
            diferencia = cantidad - anterior
            datos = dict(
                producto=producto, cantidad=abs(diferencia), usuario=usuario,
                referencia=f"Corrección #{correccion.pk} · Entrada #{entrada.pk}",
                observaciones=f"Factura {entrada.numero_factura}. Cantidad {anterior} → {cantidad}. Motivo: {motivo}",
                clave_idempotencia=f"CORRECCION_ENTRADA:{correccion.pk}",
                precio_referencia=original.precio_referencia_snapshot,
                costo_neto=original.costo_neto_snapshot,
                fecha_operacion=original.fecha_operacion,
            )
            if diferencia > 0:
                datos.update(tipo="CORR_ENTRADA_INGRESO", destino=original.destino)
            else:
                datos.update(tipo="CORR_ENTRADA_RETIRO", origen=original.destino)
            movimiento, _ = registrar_movimiento(**datos)
            correccion.movimiento = movimiento
            correccion.save(update_fields=["movimiento"])

        detalle.cantidad = cantidad
        detalle.save(update_fields=["cantidad"])
        return correccion
