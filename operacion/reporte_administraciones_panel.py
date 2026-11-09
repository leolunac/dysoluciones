"""Acceso de consulta al reporte desde los paneles internos de SIGOB."""
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseBadRequest
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .models import Tecnico, UsuarioAdministracion, UsuarioCliente
from .reporte_administraciones import FiltrosAdministracionesForm, datos_reporte, exportar_excel

GRUPOS_INTERNOS = frozenset({
    "GESTION_COORDINADOR", "GESTION_SUPERVISOR", "GESTION_GERENCIA",
    "GESTION_FACTURACION", "GESTION_AUXILIAR", "GESTION_ADMINISTRATIVA",
    "GESTION_HUMANA", "GESTION_INVENTARIO",
})


def puede_ver_reporte_interno(user):
    if not user or not user.is_authenticated or not user.is_active:
        return False
    if user.is_superuser:
        return True
    # Una cuenta de portal externo nunca obtiene el listado global por ser staff.
    if (UsuarioAdministracion.objects.filter(user_id=user.pk).exists()
            or UsuarioCliente.objects.filter(user_id=user.pk).exists()):
        return False
    if user.groups.filter(name__in=GRUPOS_INTERNOS).exists():
        return True
    return user.is_staff and not Tecnico.objects.filter(user_id=user.pk).exists()


@login_required
@never_cache
@require_GET
def reporte_administraciones_panel(request):
    if not puede_ver_reporte_interno(request.user):
        raise PermissionDenied("El reporte está disponible únicamente para personal interno autorizado.")
    parametros = request.GET.copy()
    if "estado" not in parametros:
        parametros["estado"] = "vigentes"
    form = FiltrosAdministracionesForm(parametros)
    if not form.is_valid():
        return HttpResponseBadRequest("Filtros no válidos. Revise administración, búsqueda y estado.")
    formato = request.GET.get("formato", "")
    if formato not in ("", "excel"):
        return HttpResponseBadRequest("Formato de reporte no válido.")
    hoy = timezone.localdate()
    filtros = form.cleaned_data
    grupos, resumen = datos_reporte(filtros, hoy)
    if formato == "excel":
        return exportar_excel(grupos, resumen, filtros, hoy)
    consulta = urlencode({
        "q": filtros["q"], "estado": filtros["estado"],
        "administracion": filtros["administracion"].pk if filtros["administracion"] else "",
        "formato": "excel",
    })
    return TemplateResponse(request, "operacion/reporte_administraciones_panel.html", {
        "form": form, "grupos": grupos, "resumen": resumen, "hoy": hoy,
        "estado_texto": dict(form.fields["estado"].choices)[filtros["estado"]],
        "excel_url": "?" + consulta, "volver_url": reverse("home"),
    })
