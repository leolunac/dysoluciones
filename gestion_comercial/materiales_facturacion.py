from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from operacion.models import AccesorioActividad

from .models import CatalogoPrecio, RevisionMaterialUtilizado


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
