from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from operacion.models import AccesorioActividad

from .models import (
    CatalogoPrecio,
    DetalleLiquidacion,
    Liquidacion,
    RevisionMaterialUtilizado,
)


GRUPO_AUXILIAR = "GESTION_AUXILIAR"
GRUPO_COORDINADOR = "GESTION_COORDINADOR"
GRUPO_FACTURACION = "GESTION_FACTURACION"
GRUPO_GERENCIA = "GESTION_GERENCIA"
GRUPO_SUPERVISOR = "GESTION_SUPERVISOR"


def _pertenece(user, *grupos):
    return (
        user.is_superuser
        or user.groups.filter(name__in=grupos).exists()
    )


def _exigir_consulta(user):
    if not _pertenece(
        user,
        GRUPO_AUXILIAR,
        GRUPO_COORDINADOR,
        GRUPO_FACTURACION,
        GRUPO_GERENCIA,
        GRUPO_SUPERVISOR,
    ):
        raise PermissionDenied


def _exigir_clasificacion(user):
    if not _pertenece(user, GRUPO_FACTURACION):
        raise PermissionDenied


def _exigir_elaboracion(user):
    if not _pertenece(user, GRUPO_AUXILIAR):
        raise PermissionDenied


@login_required
def lista_materiales_utilizados(request):
    _exigir_consulta(request.user)

    consumos = (
        AccesorioActividad.objects
        .select_related(
            "accesorio",
            "actividad__cliente",
            "actividad__tecnico",
            "actividad__remision",
            "revision_facturacion__catalogo_precio",
            "revision_facturacion__detalle_liquidacion__liquidacion",
            "revision_facturacion__revisado_por",
        )
        .order_by("-actividad__fecha", "-id")
    )

    estado = request.GET.get("estado", "PENDIENTE").strip()
    buscar = request.GET.get("buscar", "").strip()
    fecha_desde = request.GET.get("fecha_desde", "").strip()
    fecha_hasta = request.GET.get("fecha_hasta", "").strip()

    estados_validos = {valor for valor, _ in RevisionMaterialUtilizado.ESTADOS}
    if estado == "PENDIENTE":
        consumos = consumos.filter(
            Q(revision_facturacion__isnull=True)
            | Q(revision_facturacion__estado="PENDIENTE")
        )
    elif estado in estados_validos:
        consumos = consumos.filter(revision_facturacion__estado=estado)
    elif estado:
        estado = "PENDIENTE"
        consumos = consumos.filter(
            Q(revision_facturacion__isnull=True)
            | Q(revision_facturacion__estado="PENDIENTE")
        )

    if buscar:
        consumos = consumos.filter(
            Q(accesorio__codigo__icontains=buscar)
            | Q(accesorio__descripcion__icontains=buscar)
            | Q(descripcion_otro__icontains=buscar)
            | Q(actividad__cliente__nombre__icontains=buscar)
            | Q(actividad__tecnico__nombre__icontains=buscar)
            | Q(actividad__remision__numero_remision__icontains=buscar)
        )

    if fecha_desde:
        consumos = consumos.filter(actividad__fecha__gte=fecha_desde)
    if fecha_hasta:
        consumos = consumos.filter(actividad__fecha__lte=fecha_hasta)

    pagina = Paginator(consumos, 50).get_page(request.GET.get("pagina"))

    codigos = {
        consumo.accesorio.codigo
        for consumo in pagina.object_list
        if consumo.accesorio_id
    }
    precios = {
        precio.codigo: precio
        for precio in CatalogoPrecio.objects.filter(
            codigo__in=codigos,
            activo=True,
        )
    }

    for consumo in pagina.object_list:
        try:
            revision = consumo.revision_facturacion
        except RevisionMaterialUtilizado.DoesNotExist:
            revision = None

        consumo.revision_actual = revision
        consumo.precio_actual = (
            precios.get(consumo.accesorio.codigo)
            if consumo.accesorio_id
            else None
        )
        consumo.descripcion_facturacion = (
            consumo.accesorio.descripcion
            if consumo.accesorio_id
            else consumo.descripcion_otro
        )
        consumo.codigo_facturacion = (
            consumo.accesorio.codigo
            if consumo.accesorio_id
            else "OTRO"
        )

    return render(
        request,
        "gestion_comercial/materiales_utilizados/lista.html",
        {
            "pagina": pagina,
            "estados": RevisionMaterialUtilizado.ESTADOS,
            "filtro_estado": estado,
            "buscar": buscar,
            "fecha_desde": fecha_desde,
            "fecha_hasta": fecha_hasta,
            "puede_clasificar": _pertenece(
                request.user,
                GRUPO_FACTURACION,
            ),
        },
    )


@login_required
@require_POST
def clasificar_material_utilizado(request, consumo_id):
    _exigir_clasificacion(request.user)

    consumo = get_object_or_404(
        AccesorioActividad.objects.select_related(
            "accesorio",
            "actividad__cliente",
        ),
        pk=consumo_id,
    )

    estado = request.POST.get("estado", "").strip()
    estados_validos = {valor for valor, _ in RevisionMaterialUtilizado.ESTADOS}
    if estado not in estados_validos:
        messages.error(request, "La clasificación seleccionada no es válida.")
        return redirect("gestion_comercial:lista_materiales_utilizados")

    revision_existente = RevisionMaterialUtilizado.objects.filter(
        consumo=consumo,
    ).first()
    if (
        revision_existente
        and revision_existente.detalle_liquidacion_id
    ):
        messages.error(
            request,
            "El material ya pertenece a una liquidación y no puede reclasificarse.",
        )
        return redirect("gestion_comercial:lista_materiales_utilizados")

    catalogo = None
    if consumo.accesorio_id:
        catalogo = CatalogoPrecio.objects.filter(
            codigo=consumo.accesorio.codigo,
            activo=True,
        ).first()

    if estado == "FACTURAR" and catalogo is None:
        messages.error(
            request,
            "No se puede enviar a facturación porque el accesorio no tiene un precio activo.",
        )
        return redirect("gestion_comercial:lista_materiales_utilizados")

    descripcion = (
        consumo.accesorio.descripcion
        if consumo.accesorio_id
        else consumo.descripcion_otro or "Accesorio no catalogado"
    )
    codigo = consumo.accesorio.codigo if consumo.accesorio_id else ""

    RevisionMaterialUtilizado.objects.update_or_create(
        consumo=consumo,
        defaults={
            "estado": estado,
            "catalogo_precio": catalogo,
            "codigo_snapshot": codigo,
            "descripcion_snapshot": descripcion,
            "cantidad_snapshot": consumo.cantidad,
            "valor_unitario_sugerido": catalogo.valor if catalogo else None,
            "observaciones": request.POST.get("observaciones", "").strip(),
            "revisado_por": request.user,
            "revisado_en": timezone.now(),
        },
    )

    messages.success(request, "El material fue clasificado correctamente.")
    return redirect("gestion_comercial:lista_materiales_utilizados")


@login_required
@require_POST
def agregar_materiales_liquidacion(request, liquidacion_id):
    _exigir_elaboracion(request.user)

    liquidacion = get_object_or_404(
        Liquidacion.objects.select_related("cliente"),
        pk=liquidacion_id,
    )
    if (
        not request.user.is_superuser
        and liquidacion.creado_por_id != request.user.id
    ):
        raise PermissionDenied
    if liquidacion.estado not in {"BORRADOR", "DEVUELTA"}:
        raise PermissionDenied

    ids_texto = request.POST.getlist("materiales")
    try:
        ids = {int(valor) for valor in ids_texto}
    except (TypeError, ValueError):
        ids = set()
    if not ids:
        messages.error(request, "Seleccione al menos un material para agregar.")
        return redirect(
            "gestion_comercial:editar_liquidacion",
            liquidacion_id=liquidacion.pk,
        )

    with transaction.atomic():
        revisiones = list(
            RevisionMaterialUtilizado.objects
            .select_for_update()
            .filter(
                pk__in=ids,
                estado="FACTURAR",
                detalle_liquidacion__isnull=True,
                consumo__actividad__cliente_id=liquidacion.cliente_id,
                catalogo_precio__isnull=False,
                valor_unitario_sugerido__isnull=False,
            )
            .select_related(
                "catalogo_precio",
            )
        )
        if len(revisiones) != len(ids):
            messages.error(
                request,
                "Uno de los materiales ya fue liquidado o no pertenece a esta unidad.",
            )
            return redirect(
                "gestion_comercial:editar_liquidacion",
                liquidacion_id=liquidacion.pk,
            )

        for revision in revisiones:
            actividad = revision.consumo.actividad
            referencias = []
            if actividad.numero_informe:
                referencias.append(actividad.numero_informe)
            if actividad.remision_id:
                referencias.append(
                    f"Remisión {actividad.remision.numero_remision}"
                )
            detalle = DetalleLiquidacion.objects.create(
                liquidacion=liquidacion,
                catalogo=revision.catalogo_precio,
                tipo="MATERIAL",
                descripcion=revision.descripcion_snapshot,
                cantidad=revision.cantidad_snapshot,
                valor_unitario=revision.valor_unitario_sugerido,
                observaciones=" · ".join(referencias),
            )
            revision.detalle_liquidacion = detalle
            revision.save(
                update_fields=["detalle_liquidacion", "actualizado"]
            )

    liquidacion.recalcular_totales()
    messages.success(
        request,
        f"Se agregaron {len(revisiones)} materiales a la liquidación.",
    )
    return redirect(
        "gestion_comercial:editar_liquidacion",
        liquidacion_id=liquidacion.pk,
    )
