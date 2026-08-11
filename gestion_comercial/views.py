from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render, get_object_or_404
from django.core.exceptions import PermissionDenied
from django.utils import timezone

from .forms import (
    LiquidacionForm,
    DetalleLiquidacionForm,
    CatalogoPrecioForm,
)

from .models import (
    Liquidacion,
    CatalogoPrecio,
    DetalleLiquidacion,
)


# =========================================================
# PERFILES / SEGURIDAD GESTIÓN COMERCIAL
# =========================================================

GRUPO_AUXILIAR = "GESTION_AUXILIAR"
GRUPO_COORDINADOR = "GESTION_COORDINADOR"
GRUPO_FACTURACION = "GESTION_FACTURACION"
GRUPO_GERENCIA = "GESTION_GERENCIA"


def _pertenece(user, *grupos):
    """Superusuario tiene acceso total; los demás según grupo."""
    return (
        user.is_superuser
        or user.groups.filter(name__in=grupos).exists()
    )


def _exigir(user, *grupos):
    if not _pertenece(user, *grupos):
        raise PermissionDenied


def _puede_elaborar(user):
    return _pertenece(user, GRUPO_AUXILIAR)


def _puede_revisar(user):
    return _pertenece(user, GRUPO_COORDINADOR)


def _puede_facturar(user):
    return _pertenece(user, GRUPO_FACTURACION)


def _puede_consultar(user):
    return _pertenece(
        user,
        GRUPO_AUXILIAR,
        GRUPO_COORDINADOR,
        GRUPO_FACTURACION,
        GRUPO_GERENCIA,
    )


@login_required
def panel_gestion_comercial(request):

    _exigir(
        request.user,
        GRUPO_AUXILIAR,
        GRUPO_COORDINADOR,
        GRUPO_FACTURACION,
        GRUPO_GERENCIA,
    )

    liquidaciones = (
        Liquidacion.objects
        .select_related(
            "cliente",
            "creado_por",
            "revisado_por",
        )
        .all()
    )

    contexto = {
        "liquidaciones": liquidaciones,
        "total": liquidaciones.count(),

        "revision": liquidaciones.filter(
            estado="REVISION",
        ).count(),

        "devueltas": liquidaciones.filter(
            estado="DEVUELTA",
        ).count(),

        "aprobadas": liquidaciones.filter(
            estado="APROBADA",
        ).count(),

        "listas_facturar": liquidaciones.filter(
            estado="LISTA_FACTURAR",
        ).count(),

        "facturadas": liquidaciones.filter(
            estado="FACTURADA",
        ).count(),

        # Permisos visuales del panel
        "puede_elaborar": _puede_elaborar(
            request.user
        ),

        "puede_revisar": _puede_revisar(
            request.user
        ),

        "puede_facturar": _puede_facturar(
            request.user
        ),

        "puede_consultar": _puede_consultar(
            request.user
        ),

        "puede_ver_consolidado": _pertenece(
            request.user,
            GRUPO_FACTURACION,
            GRUPO_GERENCIA,
        ),
    }

    return render(
        request,
        "gestion_comercial/panel.html",
        contexto,
    )


@login_required
def nueva_liquidacion(request):

    _exigir(request.user, GRUPO_AUXILIAR)

    if request.method == "POST":

        form = LiquidacionForm(request.POST)

        if form.is_valid():

            liquidacion = form.save(commit=False)

            liquidacion.creado_por = request.user
            liquidacion.estado = "BORRADOR"

            liquidacion.save()

            return redirect(
                "gestion_comercial:editar_liquidacion",
                liquidacion_id=liquidacion.id,
            )

    else:
        form = LiquidacionForm()

    return render(
        request,
        "gestion_comercial/nueva_liquidacion.html",
        {
            "form": form,
        },
    )


@login_required
def editar_liquidacion(request, liquidacion_id):

    _exigir(
        request.user,
        GRUPO_AUXILIAR,
        GRUPO_COORDINADOR,
        GRUPO_FACTURACION,
        GRUPO_GERENCIA,
    )

    liquidacion = get_object_or_404(
        Liquidacion.objects.select_related(
            "cliente",
            "creado_por",
            "revisado_por",
        ),
        id=liquidacion_id,
    )

    if request.method == "POST":

        _exigir(request.user, GRUPO_AUXILIAR)

        if (
            not request.user.is_superuser
            and liquidacion.creado_por_id != request.user.id
        ):
            raise PermissionDenied

        if liquidacion.estado not in [
            "BORRADOR",
            "DEVUELTA",
        ]:
            raise PermissionDenied

        form_detalle = DetalleLiquidacionForm(
            request.POST,
        )

        if form_detalle.is_valid():

            detalle = form_detalle.save(
                commit=False,
            )

            detalle.liquidacion = liquidacion

            if (
                detalle.tipo == "MATERIAL"
                and detalle.catalogo
            ):
                detalle.descripcion = (
                    detalle.catalogo.descripcion
                )

            if detalle.tipo != "MATERIAL":
                detalle.catalogo = None

            detalle.save()

            liquidacion.recalcular_totales()

            return redirect(
                "gestion_comercial:editar_liquidacion",
                liquidacion_id=liquidacion.id,
            )

    else:
        form_detalle = DetalleLiquidacionForm()

    detalles = (
        liquidacion.detalles
        .select_related("catalogo")
        .all()
        .order_by("id")
    )

    catalogos = (
        CatalogoPrecio.objects
        .filter(activo=True)
        .order_by("descripcion")
    )

    return render(
        request,
        "gestion_comercial/editar_liquidacion.html",
        {
            "liquidacion": liquidacion,
            "form_detalle": form_detalle,
            "detalles": detalles,
            "catalogos": catalogos,
            "form_catalogo": CatalogoPrecioForm(),
            "puede_elaborar": _puede_elaborar(request.user),
            "puede_revisar": _puede_revisar(request.user),
            "puede_facturar": _puede_facturar(request.user),
            "puede_consultar": _puede_consultar(request.user),
        },
    )


@login_required
def crear_accesorio(request, liquidacion_id):

    _exigir(request.user, GRUPO_AUXILIAR)

    liquidacion = get_object_or_404(
        Liquidacion,
        id=liquidacion_id,
    )

    if (
        not request.user.is_superuser
        and liquidacion.creado_por_id != request.user.id
    ):
        raise PermissionDenied

    if liquidacion.estado not in [
        "BORRADOR",
        "DEVUELTA",
    ]:
        raise PermissionDenied

    if request.method != "POST":
        return redirect(
            "gestion_comercial:editar_liquidacion",
            liquidacion_id=liquidacion.id,
        )

    form_catalogo = CatalogoPrecioForm(request.POST)

    if form_catalogo.is_valid():

        accesorio = form_catalogo.save(commit=False)
        accesorio.activo = True
        accesorio.save()

        return redirect(
            "gestion_comercial:editar_liquidacion",
            liquidacion_id=liquidacion.id,
        )

    form_detalle = DetalleLiquidacionForm()

    detalles = (
        liquidacion.detalles
        .select_related("catalogo")
        .all()
        .order_by("id")
    )

    catalogos = (
        CatalogoPrecio.objects
        .filter(activo=True)
        .order_by("descripcion")
    )

    return render(
        request,
        "gestion_comercial/editar_liquidacion.html",
        {
            "liquidacion": liquidacion,
            "form_detalle": form_detalle,
            "detalles": detalles,
            "catalogos": catalogos,
            "form_catalogo": form_catalogo,
            "mostrar_form_catalogo": True,
            "puede_elaborar": _puede_elaborar(request.user),
            "puede_revisar": _puede_revisar(request.user),
            "puede_facturar": _puede_facturar(request.user),
            "puede_consultar": _puede_consultar(request.user),
        },
    )


@login_required
def enviar_revision(request, liquidacion_id):

    _exigir(request.user, GRUPO_AUXILIAR)

    liquidacion = get_object_or_404(
        Liquidacion,
        id=liquidacion_id,
    )

    if (
        not request.user.is_superuser
        and liquidacion.creado_por_id != request.user.id
    ):
        raise PermissionDenied

    if liquidacion.estado not in [
        "BORRADOR",
        "DEVUELTA",
    ]:
        raise PermissionDenied

    if request.method == "POST":

        if not liquidacion.detalles.exists():
            return redirect(
                "gestion_comercial:editar_liquidacion",
                liquidacion_id=liquidacion.id,
            )

        liquidacion.estado = "REVISION"

        liquidacion.save(
            update_fields=[
                "estado",
                "fecha_actualizacion",
            ]
        )

    return redirect(
        "gestion_comercial:panel",
    )


@login_required
def eliminar_detalle(request, detalle_id):

    _exigir(request.user, GRUPO_AUXILIAR)

    detalle = get_object_or_404(
        DetalleLiquidacion,
        id=detalle_id,
    )

    liquidacion = detalle.liquidacion

    if (
        not request.user.is_superuser
        and liquidacion.creado_por_id != request.user.id
    ):
        raise PermissionDenied

    if liquidacion.estado not in [
        "BORRADOR",
        "DEVUELTA",
    ]:
        return redirect(
            "gestion_comercial:editar_liquidacion",
            liquidacion_id=liquidacion.id,
        )

    if request.method == "POST":
        detalle.delete()

    return redirect(
        "gestion_comercial:editar_liquidacion",
        liquidacion_id=liquidacion.id,
    )


@login_required
def editar_detalle(request, detalle_id):

    _exigir(request.user, GRUPO_AUXILIAR)

    detalle = get_object_or_404(
        DetalleLiquidacion,
        id=detalle_id,
    )

    liquidacion = detalle.liquidacion

    if (
        not request.user.is_superuser
        and liquidacion.creado_por_id != request.user.id
    ):
        raise PermissionDenied

    if liquidacion.estado not in [
        "BORRADOR",
        "DEVUELTA",
    ]:
        return redirect(
            "gestion_comercial:editar_liquidacion",
            liquidacion_id=liquidacion.id,
        )

    if request.method == "POST":

        form = DetalleLiquidacionForm(
            request.POST,
            instance=detalle,
        )

        if form.is_valid():

            detalle_editado = form.save(
                commit=False
            )

            if (
                detalle_editado.tipo == "MATERIAL"
                and detalle_editado.catalogo
            ):
                detalle_editado.descripcion = (
                    detalle_editado.catalogo.descripcion
                )

            if detalle_editado.tipo != "MATERIAL":
                detalle_editado.catalogo = None

            detalle_editado.save()

            liquidacion.recalcular_totales()

            return redirect(
                "gestion_comercial:editar_liquidacion",
                liquidacion_id=liquidacion.id,
            )

    else:
        form = DetalleLiquidacionForm(
            instance=detalle,
        )

    catalogos = (
        CatalogoPrecio.objects
        .filter(activo=True)
        .order_by("descripcion")
    )

    return render(
        request,
        "gestion_comercial/editar_detalle.html",
        {
            "liquidacion": liquidacion,
            "detalle": detalle,
            "form": form,
            "catalogos": catalogos,
        },
    )


@login_required
def aprobar_liquidacion(request, liquidacion_id):

    _exigir(request.user, GRUPO_COORDINADOR)

    liquidacion = get_object_or_404(
        Liquidacion,
        id=liquidacion_id,
    )

    if (
        not request.user.is_superuser
        and liquidacion.creado_por_id == request.user.id
    ):
        raise PermissionDenied

    if liquidacion.estado != "REVISION":
        return redirect(
            "gestion_comercial:editar_liquidacion",
            liquidacion_id=liquidacion.id,
        )

    if request.method == "POST":

        liquidacion.estado = "APROBADA"
        liquidacion.revisado_por = request.user
        liquidacion.fecha_revision = timezone.now()

        liquidacion.save(
            update_fields=[
                "estado",
                "revisado_por",
                "fecha_revision",
                "fecha_actualizacion",
            ]
        )

    return redirect(
        "gestion_comercial:editar_liquidacion",
        liquidacion_id=liquidacion.id,
    )


@login_required
def devolver_liquidacion(request, liquidacion_id):

    _exigir(request.user, GRUPO_COORDINADOR)

    liquidacion = get_object_or_404(
        Liquidacion,
        id=liquidacion_id,
    )

    if (
        not request.user.is_superuser
        and liquidacion.creado_por_id == request.user.id
    ):
        raise PermissionDenied

    if liquidacion.estado != "REVISION":
        return redirect(
            "gestion_comercial:editar_liquidacion",
            liquidacion_id=liquidacion.id,
        )

    if request.method == "POST":

        observacion = request.POST.get(
            "observaciones_revision",
            ""
        ).strip()

        if not observacion:
            return redirect(
                "gestion_comercial:editar_liquidacion",
                liquidacion_id=liquidacion.id,
            )

        liquidacion.estado = "DEVUELTA"
        liquidacion.revisado_por = request.user
        liquidacion.fecha_revision = timezone.now()
        liquidacion.observaciones_revision = observacion

        liquidacion.save(
            update_fields=[
                "estado",
                "revisado_por",
                "fecha_revision",
                "observaciones_revision",
                "fecha_actualizacion",
            ]
        )

    return redirect(
        "gestion_comercial:editar_liquidacion",
        liquidacion_id=liquidacion.id,
    )
@login_required
def enviar_facturacion(request, liquidacion_id):

    _exigir(request.user, GRUPO_COORDINADOR)

    liquidacion = get_object_or_404(
        Liquidacion,
        id=liquidacion_id,
    )

    # Solo una liquidación APROBADA puede
    # enviarse al área de facturación.
    if liquidacion.estado != "APROBADA":
        return redirect(
            "gestion_comercial:editar_liquidacion",
            liquidacion_id=liquidacion.id,
        )

    if request.method == "POST":

        liquidacion.estado = "LISTA_FACTURAR"

        liquidacion.save(
            update_fields=[
                "estado",
                "fecha_actualizacion",
            ]
        )

    return redirect(
        "gestion_comercial:editar_liquidacion",
        liquidacion_id=liquidacion.id,
    )
@login_required
def marcar_facturada(request, liquidacion_id):

    _exigir(request.user, GRUPO_FACTURACION)

    liquidacion = get_object_or_404(
        Liquidacion,
        id=liquidacion_id,
    )

    if liquidacion.estado != "LISTA_FACTURAR":
        return redirect(
            "gestion_comercial:editar_liquidacion",
            liquidacion_id=liquidacion.id,
        )

    if request.method == "POST":

        numero_factura = request.POST.get(
            "numero_factura",
            ""
        ).strip()

        if not numero_factura:
            return redirect(
                "gestion_comercial:editar_liquidacion",
                liquidacion_id=liquidacion.id,
            )

        liquidacion.numero_factura = numero_factura
        liquidacion.fecha_facturacion = timezone.now()
        liquidacion.estado = "FACTURADA"

        liquidacion.save(
            update_fields=[
                "numero_factura",
                "fecha_facturacion",
                "estado",
                "fecha_actualizacion",
            ]
        )

    return redirect(
        "gestion_comercial:editar_liquidacion",
        liquidacion_id=liquidacion.id,
    )
@login_required
def consolidado_facturacion(request):

    _exigir(
        request.user,
        GRUPO_FACTURACION,
        GRUPO_GERENCIA,
    )

    from django.db.models import Sum
    from operacion.models import Cliente

    facturadas = (
        Liquidacion.objects
        .filter(estado="FACTURADA")
        .select_related(
            "cliente",
            "creado_por",
        )
    )

    fecha_desde = request.GET.get("fecha_desde", "").strip()
    fecha_hasta = request.GET.get("fecha_hasta", "").strip()
    cliente_id = request.GET.get("cliente", "").strip()

    if fecha_desde:
        facturadas = facturadas.filter(
            fecha_facturacion__date__gte=fecha_desde
        )

    if fecha_hasta:
        facturadas = facturadas.filter(
            fecha_facturacion__date__lte=fecha_hasta
        )

    if cliente_id:
        facturadas = facturadas.filter(
            cliente_id=cliente_id
        )

    facturadas = facturadas.order_by(
        "-fecha_facturacion"
    )

    totales = facturadas.aggregate(
        total_sin_iva=Sum("valor_sin_iva"),
        total_iva=Sum("valor_iva"),
        total_facturado=Sum("valor_total"),
    )

    clientes = (
        Cliente.objects
        .filter(activo=True)
        .order_by("nombre")
    )

    contexto = {
        "facturadas": facturadas,
        "cantidad_facturas": facturadas.count(),
        "total_sin_iva": totales["total_sin_iva"] or 0,
        "total_iva": totales["total_iva"] or 0,
        "total_facturado": totales["total_facturado"] or 0,
        "clientes": clientes,
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta,
        "cliente_seleccionado": cliente_id,
    }

    return render(
        request,
        "gestion_comercial/consolidado_facturacion.html",
        contexto,
    )

@login_required
def exportar_facturacion_excel(request):

    _exigir(
        request.user,
        GRUPO_FACTURACION,
        GRUPO_GERENCIA,
    )

    from io import BytesIO
    from django.http import HttpResponse
    from django.db.models import Sum
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment
    from openpyxl.utils import get_column_letter

    facturadas = (
        Liquidacion.objects
        .filter(estado="FACTURADA")
        .select_related("cliente")
    )

    fecha_desde = request.GET.get("fecha_desde", "").strip()
    fecha_hasta = request.GET.get("fecha_hasta", "").strip()
    cliente_id = request.GET.get("cliente", "").strip()

    if fecha_desde:
        facturadas = facturadas.filter(
            fecha_facturacion__date__gte=fecha_desde
        )

    if fecha_hasta:
        facturadas = facturadas.filter(
            fecha_facturacion__date__lte=fecha_hasta
        )

    if cliente_id:
        facturadas = facturadas.filter(
            cliente_id=cliente_id
        )

    facturadas = facturadas.order_by("-fecha_facturacion")

    totales = facturadas.aggregate(
        total_sin_iva=Sum("valor_sin_iva"),
        total_iva=Sum("valor_iva"),
        total_facturado=Sum("valor_total"),
    )

    wb = Workbook()
    ws = wb.active
    ws.title = "Facturación"

    ws.merge_cells("A1:G1")
    ws["A1"] = "SIGOB - Consolidado de Facturación"
    ws["A1"].font = Font(bold=True, size=16)
    ws["A1"].alignment = Alignment(horizontal="center")

    filtros = []
    if fecha_desde:
        filtros.append(f"Desde: {fecha_desde}")
    if fecha_hasta:
        filtros.append(f"Hasta: {fecha_hasta}")
    if cliente_id:
        primera = facturadas.first()
        if primera:
            filtros.append(f"Unidad: {primera.cliente.nombre}")

    ws.merge_cells("A2:G2")
    ws["A2"] = " | ".join(filtros) if filtros else "Todas las facturas"
    ws["A2"].alignment = Alignment(horizontal="center")

    encabezados = [
        "Factura",
        "Fecha",
        "Unidad",
        "Trabajo / concepto",
        "Valor sin IVA",
        "IVA",
        "Total",
    ]

    for columna, encabezado in enumerate(encabezados, start=1):
        celda = ws.cell(row=4, column=columna, value=encabezado)
        celda.font = Font(bold=True)
        celda.alignment = Alignment(horizontal="center")

    fila = 5

    for liquidacion in facturadas:
        ws.cell(fila, 1, liquidacion.numero_factura or "")
        ws.cell(
            fila,
            2,
            liquidacion.fecha_facturacion.replace(tzinfo=None)
            if liquidacion.fecha_facturacion else None,
        )
        ws.cell(fila, 3, liquidacion.cliente.nombre)
        ws.cell(fila, 4, liquidacion.descripcion or "")
        ws.cell(fila, 5, float(liquidacion.valor_sin_iva or 0))
        ws.cell(fila, 6, float(liquidacion.valor_iva or 0))
        ws.cell(fila, 7, float(liquidacion.valor_total or 0))
        fila += 1

    ws.cell(fila, 4, "TOTALES")
    ws.cell(fila, 4).font = Font(bold=True)
    ws.cell(fila, 5, float(totales["total_sin_iva"] or 0))
    ws.cell(fila, 6, float(totales["total_iva"] or 0))
    ws.cell(fila, 7, float(totales["total_facturado"] or 0))

    for col in range(5, 8):
        for row in range(5, fila + 1):
            ws.cell(row, col).number_format = '$#,##0'

    for row in range(5, fila):
        ws.cell(row, 2).number_format = "dd/mm/yyyy hh:mm"

    anchos = {
        1: 18,
        2: 20,
        3: 35,
        4: 45,
        5: 18,
        6: 18,
        7: 18,
    }

    for columna, ancho in anchos.items():
        ws.column_dimensions[get_column_letter(columna)].width = ancho

    ws.freeze_panes = "A5"
    ws.auto_filter.ref = f"A4:G{max(fila - 1, 4)}"

    archivo = BytesIO()
    wb.save(archivo)
    archivo.seek(0)

    response = HttpResponse(
        archivo.getvalue(),
        content_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
    )
    response["Content-Disposition"] = (
        'attachment; filename="consolidado_facturacion.xlsx"'
    )

    return response