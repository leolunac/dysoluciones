from collections import defaultdict
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

from .models import MovimientoInventario, ProductoInventario, UbicacionInventario
from .servicios import obtener_bodega_principal, registrar_movimiento


def obtener_ubicacion_tecnico(tecnico):
    ubicacion = UbicacionInventario.objects.filter(tecnico=tecnico).first()
    if ubicacion:
        return ubicacion
    return UbicacionInventario.objects.create(
        nombre=f"Técnico: {tecnico.nombre} ({tecnico.pk})",
        tipo="TECNICO",
        tecnico=tecnico,
        activa=True,
    )


def _producto_para_accesorio(accesorio):
    if not accesorio:
        return None
    return ProductoInventario.objects.filter(
        accesorio=accesorio,
        activo=True,
    ).first()


@transaction.atomic
def registrar_entrega_remision(remision, usuario):
    bodega = obtener_bodega_principal()
    ubicacion_tecnico = obtener_ubicacion_tecnico(remision.tecnico)
    movimientos = []
    for detalle in remision.detalles.select_related("accesorio"):
        producto = _producto_para_accesorio(detalle.accesorio)
        if not producto:
            continue
        movimiento, creado = registrar_movimiento(
            producto=producto,
            tipo="TRASLADO",
            cantidad=detalle.cantidad_entregada,
            origen=bodega,
            destino=ubicacion_tecnico,
            referencia=f"Remisión {remision.numero_remision}",
            observaciones=f"Entrega al técnico {remision.tecnico.nombre}.",
            usuario=usuario,
            clave_idempotencia=f"REMISION_ENTREGA:{detalle.pk}",
        )
        if creado:
            movimientos.append(movimiento)
    return movimientos


def validar_stock_para_usos(usos, tecnico):
    requeridos = defaultdict(lambda: Decimal("0.00"))
    productos = {}
    ubicaciones = {}
    for uso in usos:
        producto = _producto_para_accesorio(uso.get("accesorio"))
        if not producto:
            continue
        if uso.get("detalle_remision"):
            ubicacion = obtener_ubicacion_tecnico(tecnico)
        else:
            ubicacion = obtener_bodega_principal()
        clave = (producto.pk, ubicacion.pk)
        requeridos[clave] += Decimal(uso["cantidad"])
        productos[producto.pk] = producto
        ubicaciones[ubicacion.pk] = ubicacion

    errores = []
    for (producto_id, ubicacion_id), cantidad in requeridos.items():
        producto = productos[producto_id]
        ubicacion = ubicaciones[ubicacion_id]
        existencia = producto.existencias.filter(ubicacion=ubicacion).first()
        disponible = existencia.cantidad if existencia else Decimal("0.00")
        if disponible < cantidad:
            errores.append(
                f"Stock insuficiente de {producto.accesorio.codigo} - "
                f"{producto.accesorio.descripcion} en {ubicacion.nombre}. "
                f"Disponible: {disponible}; solicitado: {cantidad}."
            )
    if errores:
        raise ValidationError(errores)


@transaction.atomic
def registrar_consumo_actividad(uso, usuario):
    producto = _producto_para_accesorio(uso.accesorio)
    if not producto:
        return None, False
    if uso.detalle_remision_id:
        origen = obtener_ubicacion_tecnico(uso.actividad.tecnico)
    else:
        origen = obtener_bodega_principal()
    return registrar_movimiento(
        producto=producto,
        tipo="CONSUMO",
        cantidad=uso.cantidad,
        origen=origen,
        cliente=uso.actividad.cliente,
        referencia=uso.actividad.numero_informe or f"Actividad {uso.actividad_id}",
        observaciones=uso.observacion,
        usuario=usuario,
        clave_idempotencia=f"ACTIVIDAD_CONSUMO:{uso.pk}",
    )


@transaction.atomic
def registrar_devolucion_detalle(detalle, usuario):
    producto = _producto_para_accesorio(detalle.accesorio)
    if not producto:
        return None, False
    referencia = f"Devolución remisión {detalle.remision.numero_remision} detalle {detalle.pk}"
    ya_registrado = MovimientoInventario.objects.filter(
        tipo="DEVOLUCION",
        producto=producto,
        referencia=referencia,
    ).aggregate(total=Sum("cantidad"))["total"] or Decimal("0.00")
    pendiente = detalle.cantidad_devuelta - ya_registrado
    if pendiente < 0:
        raise ValidationError(
            "La devolución registrada en inventario supera la indicada en la remisión."
        )
    if pendiente == 0:
        return None, False
    origen = obtener_ubicacion_tecnico(detalle.remision.tecnico)
    bodega = obtener_bodega_principal()
    return registrar_movimiento(
        producto=producto,
        tipo="DEVOLUCION",
        cantidad=pendiente,
        origen=origen,
        destino=bodega,
        referencia=referencia,
        observaciones=detalle.observaciones,
        usuario=usuario,
        clave_idempotencia=(
            f"REMISION_DEVOLUCION:{detalle.pk}:{detalle.cantidad_devuelta}"
        ),
    )
