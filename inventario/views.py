from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import DecimalField, ExpressionWrapper, F, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from gestion_comercial.models import CatalogoPrecio
from operacion.models import Accesorio, Cliente

from .forms import (
    ConsumoInventarioForm,
    AjusteExistenciaForm,
    DetalleConsumoFormSet,
    DetalleEntradaFormSet,
    EntradaInventarioForm,
    NuevoProductoInventarioForm,
    ProveedorForm,
    siguiente_codigo_interno,
)
from .models import (
    ConsumoInventario,
    EntradaInventario,
    ExistenciaInventario,
    MovimientoInventario,
    ProductoInventario,
    ReferenciaProveedor,
)
from .permisos import exigir_consulta, exigir_gestion, puede_gestionar_inventario
from .servicios import ajustar_existencia, confirmar_consumo, confirmar_entrada


@login_required
def tablero(request):
    exigir_consulta(request.user)
    buscar = request.GET.get("buscar", "").strip()
    existencias = (
        ExistenciaInventario.objects.select_related(
            "producto__accesorio",
            "ubicacion",
        )
        .filter(ubicacion__tipo="BODEGA")
        .annotate(
            valor_total=ExpressionWrapper(
                F("cantidad") * F("producto__precio_referencia"),
                output_field=DecimalField(max_digits=20, decimal_places=2),
            )
        )
        .order_by("producto__accesorio__descripcion")
    )
    if buscar:
        existencias = existencias.filter(
            Q(producto__accesorio__codigo__icontains=buscar)
            | Q(producto__accesorio__descripcion__icontains=buscar)
        )

    valor = ExpressionWrapper(
        F("cantidad") * F("producto__precio_referencia"),
        output_field=DecimalField(max_digits=20, decimal_places=2),
    )
    resumen = ExistenciaInventario.objects.filter(
        ubicacion__tipo="BODEGA",
    ).aggregate(
        unidades=Sum("cantidad"),
        valorizado=Sum(valor),
    )
    bajos = ExistenciaInventario.objects.filter(
        ubicacion__tipo="BODEGA",
        cantidad__lte=F("producto__stock_minimo"),
        producto__stock_minimo__gt=0,
    ).count()
    desde_estadisticas = timezone.now() - timedelta(days=30)
    consumos_periodo = MovimientoInventario.objects.filter(
        tipo="CONSUMO",
        creado__gte=desde_estadisticas,
    )
    productos_mas_usados = (
        consumos_periodo.values(
            "producto__accesorio__codigo",
            "producto__accesorio__descripcion",
        )
        .annotate(total=Sum("cantidad"))
        .order_by("-total")[:5]
    )
    clientes_mayor_consumo = (
        consumos_periodo.filter(cliente__isnull=False)
        .values("cliente__nombre")
        .annotate(total=Sum("cantidad"))
        .order_by("-total")[:5]
    )

    return render(
        request,
        "inventario/tablero.html",
        {
            "existencias": existencias[:300],
            "buscar": buscar,
            "total_unidades": resumen["unidades"] or Decimal("0.00"),
            "valor_inventario": resumen["valorizado"] or Decimal("0.00"),
            "productos_bajo_minimo": bajos,
            "productos_mas_usados": productos_mas_usados,
            "clientes_mayor_consumo": clientes_mayor_consumo,
            "ajustes_recientes": MovimientoInventario.objects.filter(
                tipo__in=("AJUSTE_ENTRADA", "AJUSTE_SALIDA"),
            ).select_related("producto__accesorio", "registrado_por")[:10],
            "puede_gestionar": puede_gestionar_inventario(request.user),
            "entradas_borrador": EntradaInventario.objects.filter(
                estado="BORRADOR"
            ).select_related("proveedor")[:10],
            "consumos_borrador": ConsumoInventario.objects.filter(
                estado="BORRADOR"
            ).select_related("cliente", "ubicacion_origen")[:10],
        },
    )


@login_required
def ajustar_existencia_vista(request, existencia_id):
    exigir_gestion(request.user)
    existencia = get_object_or_404(
        ExistenciaInventario.objects.select_related(
            "producto__accesorio",
            "ubicacion",
        ),
        pk=existencia_id,
    )
    if request.method == "POST":
        form = AjusteExistenciaForm(request.POST)
        if form.is_valid():
            try:
                ajustar_existencia(
                    existencia_id=existencia.pk,
                    cantidad_fisica=form.cleaned_data["cantidad_fisica"],
                    motivo=dict(AjusteExistenciaForm.MOTIVOS)[
                        form.cleaned_data["motivo"]
                    ],
                    observaciones=form.cleaned_data["observaciones"],
                    usuario=request.user,
                )
                messages.success(request, "La existencia fue ajustada con trazabilidad.")
                return redirect("inventario:tablero")
            except ValidationError as exc:
                form.add_error(None, "; ".join(exc.messages))
    else:
        form = AjusteExistenciaForm(initial={"cantidad_fisica": existencia.cantidad})
    return render(
        request,
        "inventario/ajustar_existencia.html",
        {"existencia": existencia, "form": form},
    )


@login_required
def nueva_entrada(request):
    exigir_gestion(request.user)
    if request.method == "POST":
        form = EntradaInventarioForm(request.POST)
        formset = DetalleEntradaFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                entrada = form.save(commit=False)
                entrada.creado_por = request.user
                entrada.save()
                formset.instance = entrada
                formset.save()
            messages.success(request, "Entrada guardada en borrador. Confírmela para aumentar stock.")
            return redirect("inventario:tablero")
    else:
        form = EntradaInventarioForm(initial={"fecha_factura": timezone.localdate()})
        formset = DetalleEntradaFormSet()
    return render(
        request,
        "inventario/formulario.html",
        {
            "titulo": "Nueva entrada por compra",
            "form": form,
            "formset": formset,
            "tipo_formulario": "entrada",
            "productos_disponibles": ProductoInventario.objects.filter(
                activo=True,
            ).select_related("accesorio").order_by("accesorio__descripcion"),
        },
    )


@login_required
def nuevo_proveedor(request):
    exigir_gestion(request.user)
    if request.method == "POST":
        form = ProveedorForm(request.POST)
        if form.is_valid():
            proveedor = form.save()
            messages.success(request, f"Proveedor {proveedor.nombre} creado correctamente.")
            return redirect("inventario:nueva_entrada")
    else:
        form = ProveedorForm(initial={"activo": True})
    return render(request, "inventario/proveedor_formulario.html", {"form": form})


@login_required
def nuevo_producto(request):
    exigir_gestion(request.user)
    if request.method == "POST":
        form = NuevoProductoInventarioForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    accesorio = Accesorio.objects.create(
                        codigo=form.cleaned_data["codigo"],
                        descripcion=form.cleaned_data["descripcion"].strip().upper(),
                        activo=True,
                    )
                    producto = ProductoInventario.objects.create(
                        accesorio=accesorio,
                        unidad_medida=form.cleaned_data["unidad_medida"].strip().upper(),
                        stock_minimo=form.cleaned_data["stock_minimo"],
                        precio_referencia=form.cleaned_data["precio_referencia"],
                        costo_neto_ultimo=Decimal("0.00"),
                        activo=True,
                    )
                    if form.cleaned_data.get("proveedor"):
                        ReferenciaProveedor.objects.create(
                            producto=producto,
                            proveedor=form.cleaned_data["proveedor"],
                            codigo_proveedor=form.cleaned_data["codigo_proveedor"].strip(),
                            descripcion_proveedor=(
                                form.cleaned_data.get("descripcion_proveedor") or ""
                            ).strip(),
                            activa=True,
                        )
            except IntegrityError:
                form.add_error(
                    "codigo",
                    "El código fue ocupado mientras se guardaba. Solicite uno nuevo.",
                )
            else:
                messages.success(
                    request,
                    f"Accesorio {producto} creado correctamente y disponible para la entrada.",
                )
                return redirect("inventario:nueva_entrada")
    else:
        form = NuevoProductoInventarioForm()
    return render(request, "inventario/producto_formulario.html", {"form": form})


@login_required
def verificar_codigo_producto(request):
    exigir_gestion(request.user)
    prefijo = request.GET.get("prefijo", "A").strip().upper()[:1]
    codigo = request.GET.get("codigo", "").strip().upper()
    sugerido = siguiente_codigo_interno(prefijo)
    respuesta = {"sugerido": sugerido}
    if codigo:
        accesorio = Accesorio.objects.filter(codigo__iexact=codigo).first()
        precio = CatalogoPrecio.objects.filter(codigo__iexact=codigo).first()
        if accesorio:
            respuesta.update(
                disponible=False,
                mensaje=f"{codigo} ya pertenece a {accesorio.descripcion}.",
            )
        elif precio:
            respuesta.update(
                disponible=False,
                mensaje=f"{codigo} está reservado en Gestión Comercial para {precio.descripcion}.",
            )
        else:
            respuesta.update(disponible=True, mensaje=f"{codigo} está disponible.")
    return JsonResponse(respuesta)


@login_required
def nuevo_consumo(request):
    exigir_gestion(request.user)
    if request.method == "POST":
        form = ConsumoInventarioForm(request.POST)
        formset = DetalleConsumoFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                consumo = form.save(commit=False)
                consumo.creado_por = request.user
                consumo.save()
                formset.instance = consumo
                formset.save()
            messages.success(request, "Consumo guardado en borrador. Confírmelo para descontar stock.")
            return redirect("inventario:tablero")
    else:
        form = ConsumoInventarioForm(initial={"fecha": timezone.localtime()})
        formset = DetalleConsumoFormSet()
    return render(
        request,
        "inventario/formulario.html",
        {
            "titulo": "Nuevo consumo por unidad",
            "form": form,
            "formset": formset,
            "tipo_formulario": "consumo",
            "clientes_disponibles": Cliente.objects.filter(
                activo=True,
            ).order_by("nombre"),
            "productos_disponibles": ProductoInventario.objects.filter(
                activo=True,
            ).select_related("accesorio").order_by("accesorio__descripcion"),
        },
    )


@login_required
@require_POST
def confirmar_entrada_vista(request, entrada_id):
    exigir_gestion(request.user)
    try:
        confirmar_entrada(entrada_id, request.user)
        messages.success(request, "La entrada fue confirmada y el stock aumentó.")
    except (ValidationError, EntradaInventario.DoesNotExist) as exc:
        messages.error(request, "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc))
    return redirect("inventario:tablero")


@login_required
@require_POST
def confirmar_consumo_vista(request, consumo_id):
    exigir_gestion(request.user)
    try:
        confirmar_consumo(consumo_id, request.user)
        messages.success(request, "El consumo fue confirmado y descontado del inventario.")
    except (ValidationError, ConsumoInventario.DoesNotExist) as exc:
        messages.error(request, "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc))
    return redirect("inventario:tablero")


@login_required
def exportar_consumos_excel(request):
    exigir_consulta(request.user)
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    fecha_desde = request.GET.get("fecha_desde", "").strip()
    fecha_hasta = request.GET.get("fecha_hasta", "").strip()
    movimientos = (
        MovimientoInventario.objects.filter(tipo="CONSUMO")
        .select_related("cliente", "producto__accesorio")
        .order_by("creado", "id")
    )
    if fecha_desde:
        movimientos = movimientos.filter(creado__date__gte=fecha_desde)
    if fecha_hasta:
        movimientos = movimientos.filter(creado__date__lte=fecha_hasta)

    libro = Workbook()
    hoja = libro.active
    hoja.title = "Consumos"
    encabezados = [
        "Fecha",
        "Unidad / cliente",
        "Código",
        "Descripción",
        "Cantidad",
        "Valor unitario",
        "Valor total",
    ]
    hoja.append(encabezados)
    for celda in hoja[1]:
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = PatternFill("solid", fgColor="0B5FA5")

    total_general = Decimal("0.00")
    for movimiento in movimientos.iterator():
        total = movimiento.cantidad * movimiento.precio_referencia_snapshot
        total_general += total
        hoja.append(
            [
                timezone.localtime(movimiento.creado).strftime("%Y-%m-%d %H:%M"),
                movimiento.cliente.nombre if movimiento.cliente_id else "",
                movimiento.producto.accesorio.codigo,
                movimiento.producto.accesorio.descripcion,
                float(movimiento.cantidad),
                float(movimiento.precio_referencia_snapshot),
                float(total),
            ]
        )

    hoja.append(["", "", "", "", "", "TOTAL", float(total_general)])
    hoja.cell(hoja.max_row, 6).font = Font(bold=True)
    hoja.cell(hoja.max_row, 7).font = Font(bold=True)
    for columna in (6, 7):
        for fila in range(2, hoja.max_row + 1):
            hoja.cell(fila, columna).number_format = '$#,##0.00'
    anchos = [18, 42, 16, 48, 12, 18, 18]
    for indice, ancho in enumerate(anchos, start=1):
        hoja.column_dimensions[chr(64 + indice)].width = ancho

    respuesta = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    respuesta["Content-Disposition"] = (
        f'attachment; filename="consumos_{fecha_desde or "inicio"}_{fecha_hasta or "hoy"}.xlsx"'
    )
    libro.save(respuesta)
    return respuesta
