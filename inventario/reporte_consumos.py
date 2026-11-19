"""Consumo final por línea y detalle separado de movimientos originales/ajustes."""
from decimal import Decimal
import re

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from .correcciones import TIPOS_CONSUMO
from .models import DetalleConsumoInventario, MovimientoInventario

CLAVE_CONSUMO = re.compile(r"CONSUMO:([1-9][0-9]{0,18}):([1-9][0-9]{0,18})\Z")
ENCABEZADOS = ["Fecha", "Unidad / cliente", "Código", "Descripción", "Cantidad", "Valor unitario", "Valor total"]


class FechasReporteConsumos(forms.Form):
    fecha_desde = forms.DateField(required=False, input_formats=["%Y-%m-%d"])
    fecha_hasta = forms.DateField(required=False, input_formats=["%Y-%m-%d"])

    def clean(self):
        datos = super().clean()
        if datos.get("fecha_desde") and datos.get("fecha_hasta") and datos["fecha_desde"] > datos["fecha_hasta"]:
            raise ValidationError("La fecha inicial no puede ser posterior a la final.")
        return datos


def _clave(movimiento):
    coincidencia = CLAVE_CONSUMO.fullmatch(movimiento.clave_idempotencia or "")
    if not coincidencia:
        return None
    ids = tuple(int(v) for v in coincidencia.groups())
    return ids if all(v <= 9223372036854775807 for v in ids) else None


def _agregar(hoja, valores):
    hoja.append(valores)
    # Nombres, códigos y motivos son texto; no se ejecutan como fórmulas Excel.
    for celda, valor in zip(hoja[hoja.max_row], valores):
        if isinstance(valor, str):
            celda.data_type = "s"


def _valores(movimiento, cantidad):
    return [
        timezone.localtime(movimiento.fecha_operacion).strftime("%Y-%m-%d %H:%M"),
        movimiento.cliente.nombre if movimiento.cliente_id else "",
        movimiento.producto.accesorio.codigo,
        movimiento.producto.accesorio.descripcion,
        float(cantidad), float(movimiento.precio_referencia_snapshot),
        float(cantidad * movimiento.precio_referencia_snapshot),
    ]


def _terminar(hoja, total, anchos):
    for celda in hoja[1]:
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = PatternFill("solid", fgColor="0B5FA5")
    _agregar(hoja, ["", "", "", "", "", "TOTAL", float(total)])
    for columna in (6, 7):
        hoja.cell(hoja.max_row, columna).font = Font(bold=True)
        for fila in range(2, hoja.max_row + 1):
            hoja.cell(fila, columna).number_format = '$#,##0.00'
    for fila in range(2, hoja.max_row):
        hoja.cell(fila, 5).number_format = '0.00'
    for indice, ancho in enumerate(anchos, start=1):
        hoja.column_dimensions[hoja.cell(1, indice).column_letter].width = ancho
    hoja.freeze_panes = "A2"
    hoja.auto_filter.ref = f"A1:{hoja.cell(1, len(anchos)).column_letter}{max(1, hoja.max_row - 1)}"


def crear_reporte_consumos(*, fecha_desde=None, fecha_hasta=None):
    consulta = MovimientoInventario.objects.filter(tipo__in=TIPOS_CONSUMO)
    if fecha_desde:
        consulta = consulta.filter(fecha_operacion__date__gte=fecha_desde)
    if fecha_hasta:
        consulta = consulta.filter(fecha_operacion__date__lte=fecha_hasta)
    movimientos = list(consulta.select_related(
        "cliente", "producto__accesorio", "registrado_por",
        "correccion_consumo__detalle__consumo",
    ).order_by("fecha_operacion", "id"))

    claves = {m.pk: _clave(m) for m in movimientos if m.tipo == "CONSUMO"}
    ids_detalle = {ids[1] for ids in claves.values() if ids}
    detalles = {d.pk: d for d in DetalleConsumoInventario.objects.filter(
        pk__in=ids_detalle, consumo__estado="CONFIRMADO",
    ).select_related("consumo")}
    finales, originales = {}, set()
    for movimiento in movimientos:
        ids = claves.get(movimiento.pk)
        detalle = detalles.get(ids[1]) if ids else None
        if detalle and (
            detalle.consumo_id == ids[0]
            and detalle.producto_id == movimiento.producto_id
            and detalle.consumo.cliente_id == movimiento.cliente_id
            and detalle.consumo.ubicacion_origen_id == movimiento.origen_id
        ):
            finales[movimiento.pk] = detalle.cantidad
            originales.add(detalle.pk)

    libro = Workbook()
    hoja = libro.active
    hoja.title = "Consumos"
    hoja.append(ENCABEZADOS)
    historial = libro.create_sheet("Movimientos")
    historial.append(ENCABEZADOS + ["Tipo", "Referencia", "Usuario", "Observaciones", "Fecha de registro"])
    total_final, total_movimientos = Decimal("0.00"), Decimal("0.00")
    for movimiento in movimientos:
        neta = -movimiento.cantidad if movimiento.tipo == "CORR_CONSUMO_ENTRADA" else movimiento.cantidad
        total_movimientos += neta * movimiento.precio_referencia_snapshot
        _agregar(historial, _valores(movimiento, neta) + [
            movimiento.get_tipo_display(), movimiento.referencia,
            movimiento.registrado_por.get_username() if movimiento.registrado_por_id else "",
            movimiento.observaciones,
            timezone.localtime(movimiento.creado).strftime("%Y-%m-%d %H:%M"),
        ])
        cambio = getattr(movimiento, "correccion_consumo", None)
        if movimiento.tipo != "CONSUMO" and cambio and cambio.detalle_id in originales:
            detalle = detalles[cambio.detalle_id]
            bodega_movimiento = movimiento.destino_id if movimiento.tipo == "CORR_CONSUMO_ENTRADA" else movimiento.origen_id
            if detalle.producto_id == movimiento.producto_id and detalle.consumo.cliente_id == movimiento.cliente_id and detalle.consumo.ubicacion_origen_id == bodega_movimiento:
                continue  # La cantidad final ya está en la fila del consumo original.
        # Los consumos de actividades y movimientos antiguos sin vínculo se conservan.
        # Un ajuste sin original verificable no se descarta silenciosamente.
        cantidad = finales.get(movimiento.pk, neta)
        total_final += cantidad * movimiento.precio_referencia_snapshot
        valores = _valores(movimiento, cantidad)
        if movimiento.tipo != "CONSUMO":
            valores[3] += " · Ajuste sin consumo original verificable"
        _agregar(hoja, valores)

    _terminar(hoja, total_final, [18, 42, 16, 48, 12, 18, 18])
    _terminar(historial, total_movimientos, [18, 42, 16, 48, 12, 18, 18, 35, 40, 22, 75, 20])
    return libro
