"""Consulta interna de administraciones y asignaciones de unidades."""
from io import BytesIO
from urllib.parse import urlencode

from django import forms
from django.core.exceptions import PermissionDenied
from django.db.models import Prefetch, Q
from django.http import HttpResponse, HttpResponseBadRequest
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_GET

from .models import Administracion, AdministracionUnidad


class FiltrosAdministracionesForm(forms.Form):
    q = forms.CharField(
        label="Buscar administración o unidad", required=False, max_length=150,
        widget=forms.TextInput(attrs={"placeholder": "Nombre, NIT o dirección de la unidad"}),
    )
    administracion = forms.ModelChoiceField(
        label="Administración", required=False,
        queryset=Administracion.objects.order_by("nombre", "pk"),
        empty_label="Todas las administraciones",
    )
    estado = forms.ChoiceField(
        label="Asignaciones", initial="vigentes",
        choices=[("vigentes", "Vigentes hoy"), ("todas", "Todas las asignaciones e historial")],
    )


def puede_consultar_reporte(user):
    """El reporte requiere consultar tanto administraciones como sus asignaciones."""
    return user.is_active and user.is_staff and all(
        user.has_perm(f"operacion.view_{modelo}")
        or user.has_perm(f"operacion.change_{modelo}")
        for modelo in ("administracion", "administracionunidad")
    )


def estado_asignacion(asignacion, hoy):
    if not asignacion.activo:
        return "Asignación inactiva"
    if not asignacion.cliente.activo:
        return "Unidad inactiva"
    if asignacion.fecha_inicio > hoy:
        return "Inicio futuro"
    if asignacion.fecha_fin and asignacion.fecha_fin < hoy:
        return "Finalizada"
    return "Vigente"


def datos_reporte(filtros, hoy):
    asignaciones = AdministracionUnidad.objects.select_related("cliente")
    if filtros["estado"] == "vigentes":
        # Misma vigencia inclusiva y fecha local que el portal de administraciones.
        asignaciones = asignaciones.filter(
            activo=True, cliente__activo=True, fecha_inicio__lte=hoy,
        ).filter(Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=hoy))

    administraciones = Administracion.objects.order_by("nombre", "pk")
    if filtros["administracion"]:
        administraciones = administraciones.filter(pk=filtros["administracion"].pk)

    texto = filtros["q"]
    if texto:
        coincide_administracion = Q(administracion__nombre__icontains=texto) | Q(administracion__nit__icontains=texto)
        asignaciones = asignaciones.filter(
            coincide_administracion | Q(cliente__nombre__icontains=texto)
            | Q(cliente__nit__icontains=texto) | Q(cliente__direccion__icontains=texto)
        )
        administraciones = administraciones.filter(
            Q(nombre__icontains=texto) | Q(nit__icontains=texto)
            | Q(pk__in=asignaciones.values("administracion_id"))
        )

    asignaciones = asignaciones.order_by("cliente__nombre", "-fecha_inicio", "pk")
    administraciones = administraciones.prefetch_related(Prefetch(
        "unidades_asignadas", queryset=asignaciones, to_attr="asignaciones_reporte",
    ))
    grupos = []
    unidades = set()
    total_asignaciones = 0
    for administracion in administraciones:
        filas = []
        for asignacion in administracion.asignaciones_reporte:
            filas.append({"asignacion": asignacion, "estado": estado_asignacion(asignacion, hoy)})
            unidades.add(asignacion.cliente_id)
        total_asignaciones += len(filas)
        grupos.append({"administracion": administracion, "filas": filas, "total": len(filas)})
    return grupos, {
        "administraciones": len(grupos), "unidades": len(unidades),
        "asignaciones": total_asignaciones,
    }


def exportar_excel(grupos, resumen, filtros, hoy):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "Administraciones y unidades"
    ws.append(["SIGOB - Administraciones y unidades"])
    ws.append(["Fecha de consulta", hoy])
    ws["B2"].number_format = "yyyy-mm-dd"
    ws.append(["Asignaciones", dict(FiltrosAdministracionesForm.base_fields["estado"].choices)[filtros["estado"]]])
    ws.append(["Búsqueda", filtros["q"] or "Sin búsqueda",
               "Administraciones", resumen["administraciones"], "Unidades distintas", resumen["unidades"],
               "Asignaciones", resumen["asignaciones"]])
    ws.append(["Administración seleccionada", filtros["administracion"].nombre if filtros["administracion"] else "Todas"])
    ws.append([])
    ws.append([
        "Administración", "NIT administración", "Administración activa", "Unidad / cliente",
        "NIT unidad", "Dirección unidad", "Tipo de contrato", "Unidad activa",
        "Fecha inicio", "Fecha fin", "Asignación activa", "Situación de la asignación",
    ])
    for grupo in grupos:
        administracion = grupo["administracion"]
        base = [administracion.nombre, administracion.nit, "Sí" if administracion.activo else "No"]
        if not grupo["filas"]:
            ws.append(base + [None] * 8 + ["Sin asignaciones para estos filtros"])
        for fila in grupo["filas"]:
            asignacion = fila["asignacion"]
            cliente = asignacion.cliente
            ws.append(base + [
                cliente.nombre, cliente.nit or "", cliente.direccion,
                cliente.get_tipo_contrato_display(), "Sí" if cliente.activo else "No",
                asignacion.fecha_inicio, asignacion.fecha_fin,
                "Sí" if asignacion.activo else "No", fila["estado"],
            ])

    # Los textos de la base se exportan como texto literal, nunca como fórmulas.
    for fila in ws:
        for celda in fila:
            if isinstance(celda.value, str):
                celda.data_type = "s"
            celda.font = Font(name="Calibri", size=10)
            celda.alignment = Alignment(vertical="top", wrap_text=True)
            if celda.row >= 8 and celda.column in (9, 10):
                celda.number_format = "yyyy-mm-dd"
            if celda.row >= 8 and celda.row % 2 == 0:
                celda.fill = PatternFill("solid", fgColor="F1F5F9")
    for celda in ws[7]:
        celda.fill = PatternFill("solid", fgColor="075985")
        celda.font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
    ws["A1"].font = Font(name="Calibri", size=16, bold=True)
    for i, ancho in enumerate([38, 20, 18, 55, 20, 35, 23, 15, 16, 16, 18, 30], 1):
        ws.column_dimensions[get_column_letter(i)].width = ancho
    ws.freeze_panes = "D8"
    ws.auto_filter.ref = f"A7:L{ws.max_row}"
    ws.print_title_rows = "1:7"
    ws.print_options.horizontalCentered = True
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_LETTER
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    salida = BytesIO()
    wb.save(salida)
    response = HttpResponse(salida.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="administraciones_unidades_{hoy:%Y%m%d}.xlsx"'
    return response


class ReporteAdministracionesMixin:
    change_list_template = "admin/operacion/reporte_administraciones/change_list.html"

    def get_urls(self):
        nombre = f"{self.opts.app_label}_{self.opts.model_name}_reporte_unidades"
        return [path(
            "reporte-unidades/", self.admin_site.admin_view(self.reporte_unidades), name=nombre,
        )] + super().get_urls()

    def changelist_view(self, request, extra_context=None):
        contexto = dict(extra_context or {})
        if puede_consultar_reporte(request.user):
            contexto["reporte_administraciones_url"] = reverse(
                f"admin:{self.opts.app_label}_{self.opts.model_name}_reporte_unidades",
                current_app=self.admin_site.name,
            )
        return super().changelist_view(request, extra_context=contexto)

    @method_decorator(require_GET)
    def reporte_unidades(self, request):
        if not puede_consultar_reporte(request.user):
            raise PermissionDenied("No tiene permisos para consultar administraciones y sus unidades.")
        parametros = request.GET.copy()
        if "estado" not in parametros:
            parametros["estado"] = "vigentes"
        form = FiltrosAdministracionesForm(parametros)
        if not form.is_valid():
            return HttpResponseBadRequest("Filtros no válidos. Revise la administración, búsqueda y estado seleccionados.")
        formato = request.GET.get("formato", "")
        if formato not in ("", "excel"):
            return HttpResponseBadRequest("Formato de reporte no válido.")
        hoy = timezone.localdate()
        grupos, resumen = datos_reporte(form.cleaned_data, hoy)
        if formato == "excel":
            return exportar_excel(grupos, resumen, form.cleaned_data, hoy)
        filtros = form.cleaned_data
        consulta = urlencode({
            "q": filtros["q"], "estado": filtros["estado"],
            "administracion": filtros["administracion"].pk if filtros["administracion"] else "",
            "formato": "excel",
        })
        # Un lector puede consultar el reporte sin poder ver usuarios de acceso.
        opciones_regreso = self.opts if self.has_view_or_change_permission(request) else Administracion._meta
        context = {
            **self.admin_site.each_context(request),
            "title": "Administraciones y sus unidades", "opts": self.opts,
            "form": form, "grupos": grupos, "resumen": resumen, "hoy": hoy,
            "estado_filtro": filtros["estado"],
            "estado_texto": dict(form.fields["estado"].choices)[filtros["estado"]],
            "excel_url": "?" + consulta,
            "volver_label": str(opciones_regreso.verbose_name_plural).capitalize(),
            "volver_url": reverse(
                f"admin:{opciones_regreso.app_label}_{opciones_regreso.model_name}_changelist",
                current_app=self.admin_site.name,
            ),
        }
        request.current_app = self.admin_site.name
        return TemplateResponse(request, "admin/operacion/reporte_administraciones/reporte.html", context)
