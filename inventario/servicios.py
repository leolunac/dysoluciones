from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import (
    EntradaInventario,
    ExistenciaInventario,
    MovimientoInventario,
    ProductoInventario,
    UbicacionInventario,
)


def obtener_bodega_principal():
    bodega, _ = UbicacionInventario.objects.get_or_create(
        nombre="Bodega principal",
        defaults={"tipo": "BODEGA", "activa": True},
    )
    return bodega


def _existencia_bloqueada(producto, ubicacion):
    existencia, _ = ExistenciaInventario.objects.select_for_update().get_or_create(
        producto=producto,
        ubicacion=ubicacion,
        defaults={"cantidad": Decimal("0.00")},
    )
    return existencia


def registrar_movimiento(
    *,
    producto,
    tipo,
    cantidad,
    origen=None,
    destino=None,
    cliente=None,
    referencia="",
    observaciones="",
    usuario=None,
    clave_idempotencia=None,
    precio_referencia=None,
    costo_neto=None,
):
    cantidad = Decimal(cantidad)
    if cantidad <= 0:
        raise ValidationError("La cantidad debe ser mayor que cero.")
    if not origen and not destino:
        raise ValidationError("El movimiento debe tener origen o destino.")
    if origen and destino and origen.pk == destino.pk:
        raise ValidationError("El origen y el destino deben ser diferentes.")

    with transaction.atomic():
        if clave_idempotencia:
            existente = MovimientoInventario.objects.filter(
                clave_idempotencia=clave_idempotencia,
            ).first()
            if existente:
                return existente, False

        if origen:
            saldo_origen = _existencia_bloqueada(producto, origen)
            if saldo_origen.cantidad < cantidad:
                raise ValidationError(
                    f"Stock insuficiente de {producto}. "
                    f"Disponible: {saldo_origen.cantidad}."
                )
            saldo_origen.cantidad -= cantidad
            saldo_origen.save(update_fields=["cantidad", "actualizado"])

        if destino:
            saldo_destino = _existencia_bloqueada(producto, destino)
            saldo_destino.cantidad += cantidad
            saldo_destino.save(update_fields=["cantidad", "actualizado"])

        movimiento = MovimientoInventario.objects.create(
            producto=producto,
            tipo=tipo,
            cantidad=cantidad,
            origen=origen,
            destino=destino,
            cliente=cliente,
            precio_referencia_snapshot=(
                producto.precio_referencia
                if precio_referencia is None
                else precio_referencia
            ),
            costo_neto_snapshot=(
                producto.costo_neto_ultimo if costo_neto is None else costo_neto
            ),
            referencia=referencia,
            observaciones=observaciones,
            registrado_por=usuario,
            clave_idempotencia=clave_idempotencia,
        )
        return movimiento, True


def fijar_saldo_inicial(
    *, producto, cantidad, precio_referencia, unidad_medida, usuario=None, origen=""
):
    clave = f"SALDO_INICIAL:{origen}:{producto.accesorio.codigo}"
    with transaction.atomic():
        existente = MovimientoInventario.objects.filter(
            clave_idempotencia=clave,
        ).first()
        if existente:
            return existente, False

        bodega = obtener_bodega_principal()
        saldo = _existencia_bloqueada(producto, bodega)
        if saldo.cantidad != Decimal("0.00"):
            raise ValidationError(
                f"{producto} ya tiene saldo {saldo.cantidad}; no se reemplazó."
            )

        producto.unidad_medida = unidad_medida or "UNID"
        producto.precio_referencia = Decimal(precio_referencia)
        producto.save(
            update_fields=["unidad_medida", "precio_referencia", "actualizado"]
        )

        cantidad = Decimal(cantidad)
        if cantidad == 0:
            movimiento = MovimientoInventario.objects.create(
                producto=producto,
                tipo="SALDO_INICIAL",
                cantidad=Decimal("0.00"),
                destino=bodega,
                precio_referencia_snapshot=producto.precio_referencia,
                referencia="Saldo cero conciliado",
                observaciones=(
                    "Registro técnico de apertura con saldo cero; "
                    "no modifica existencias."
                ),
                registrado_por=usuario,
                clave_idempotencia=clave,
            )
            # El movimiento de apertura en cero no debe alterar el saldo.
            return movimiento, True

        return registrar_movimiento(
            producto=producto,
            tipo="SALDO_INICIAL",
            cantidad=cantidad,
            destino=bodega,
            referencia="Saldo inicial conciliado",
            observaciones="Importado desde el aplicativo anterior.",
            usuario=usuario,
            clave_idempotencia=clave,
            precio_referencia=producto.precio_referencia,
        )


def confirmar_entrada(entrada_id, usuario):
    with transaction.atomic():
        entrada = (
            EntradaInventario.objects.select_for_update()
            .prefetch_related("detalles__producto")
            .get(pk=entrada_id)
        )
        if entrada.estado == "CONFIRMADA":
            return entrada
        if not entrada.detalles.exists():
            raise ValidationError("La entrada no contiene productos.")

        bodega = obtener_bodega_principal()
        for detalle in entrada.detalles.all():
            detalle.full_clean()
            producto = ProductoInventario.objects.select_for_update().get(
                pk=detalle.producto_id,
            )
            producto.precio_referencia = detalle.precio_unitario_lista
            producto.costo_neto_ultimo = detalle.costo_unitario_neto
            producto.save(
                update_fields=[
                    "precio_referencia",
                    "costo_neto_ultimo",
                    "actualizado",
                ]
            )
            registrar_movimiento(
                producto=producto,
                tipo="ENTRADA_COMPRA",
                cantidad=detalle.cantidad,
                destino=bodega,
                referencia=f"Factura {entrada.numero_factura}",
                observaciones=f"Proveedor: {entrada.proveedor.nombre}",
                usuario=usuario,
                clave_idempotencia=f"ENTRADA:{entrada.pk}:{detalle.pk}",
                precio_referencia=detalle.precio_unitario_lista,
                costo_neto=detalle.costo_unitario_neto,
            )

        entrada.estado = "CONFIRMADA"
        entrada.confirmado_en = timezone.now()
        entrada.save(update_fields=["estado", "confirmado_en"])
        return entrada


def confirmar_consumo(consumo_id, usuario):
    from .models import ConsumoInventario

    with transaction.atomic():
        consumo = (
            ConsumoInventario.objects.select_for_update()
            .select_related("cliente", "ubicacion_origen")
            .prefetch_related("detalles__producto")
            .get(pk=consumo_id)
        )
        if consumo.estado == "CONFIRMADO":
            return consumo
        if not consumo.detalles.exists():
            raise ValidationError("El consumo no contiene productos.")

        for detalle in consumo.detalles.all():
            detalle.full_clean()
            producto = ProductoInventario.objects.select_for_update().get(
                pk=detalle.producto_id,
            )
            detalle.precio_referencia_snapshot = producto.precio_referencia
            detalle.save(update_fields=["precio_referencia_snapshot"])
            registrar_movimiento(
                producto=producto,
                tipo="CONSUMO",
                cantidad=detalle.cantidad,
                origen=consumo.ubicacion_origen,
                cliente=consumo.cliente,
                referencia=f"Consumo #{consumo.pk}",
                observaciones=consumo.observaciones,
                usuario=usuario,
                clave_idempotencia=f"CONSUMO:{consumo.pk}:{detalle.pk}",
                precio_referencia=detalle.precio_referencia_snapshot,
            )

        consumo.estado = "CONFIRMADO"
        consumo.confirmado_en = timezone.now()
        consumo.save(update_fields=["estado", "confirmado_en"])
        return consumo


def trasladar_producto(
    *, producto, cantidad, origen, destino, usuario, referencia="", observaciones=""
):
    return registrar_movimiento(
        producto=producto,
        tipo="TRASLADO",
        cantidad=cantidad,
        origen=origen,
        destino=destino,
        referencia=referencia,
        observaciones=observaciones,
        usuario=usuario,
    )


def ajustar_existencia(*, existencia_id, cantidad_fisica, motivo, observaciones, usuario):
    cantidad_fisica = Decimal(cantidad_fisica)
    if cantidad_fisica < 0:
        raise ValidationError("La existencia física no puede ser negativa.")

    with transaction.atomic():
        existencia = (
            ExistenciaInventario.objects.select_for_update()
            .select_related("producto__accesorio", "ubicacion")
            .get(pk=existencia_id)
        )
        cantidad_anterior = existencia.cantidad
        diferencia = cantidad_fisica - cantidad_anterior
        if diferencia == 0:
            raise ValidationError("La cantidad física es igual a la registrada; no hay ajuste.")

        detalle = (
            f"Motivo: {motivo}. Saldo anterior: {cantidad_anterior}. "
            f"Saldo físico: {cantidad_fisica}. {observaciones}"
        )
        if diferencia > 0:
            movimiento, _ = registrar_movimiento(
                producto=existencia.producto,
                tipo="AJUSTE_ENTRADA",
                cantidad=diferencia,
                destino=existencia.ubicacion,
                referencia="Ajuste por conteo físico",
                observaciones=detalle,
                usuario=usuario,
            )
        else:
            movimiento, _ = registrar_movimiento(
                producto=existencia.producto,
                tipo="AJUSTE_SALIDA",
                cantidad=abs(diferencia),
                origen=existencia.ubicacion,
                referencia="Ajuste por conteo físico",
                observaciones=detalle,
                usuario=usuario,
            )
        return movimiento
