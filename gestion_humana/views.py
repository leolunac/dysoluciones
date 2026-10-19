from datetime import timedelta
from pathlib import Path

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from operacion.models import Tecnico

from .forms import (
    AfiliacionSeguridadSocialForm,
    CertificacionEmpleadoForm,
    ContratoLaboralForm,
    DocumentoEmpleadoForm,
    EmpleadoForm,
)
from .models import (
    AfiliacionSeguridadSocial,
    CertificacionEmpleado,
    ContratoLaboral,
    DocumentoEmpleado,
    Empleado,
    HistorialEmpleado,
)
from .permisos import exigir_gestion_humana


def _auditar(empleado, usuario, accion, detalle=""):
    HistorialEmpleado.objects.create(
        empleado=empleado,
        usuario=usuario,
        accion=accion,
        detalle=detalle,
    )


def _alertas_vencimiento():
    hoy = timezone.localdate()
    limite = hoy + timedelta(days=30)
    return {
        "contratos": ContratoLaboral.objects.filter(
            fecha_fin__range=(hoy, limite), empleado__estado="ACTIVO", activo=True
        ).select_related("empleado"),
        "certificaciones": CertificacionEmpleado.objects.filter(
            fecha_vencimiento__range=(hoy, limite), empleado__estado="ACTIVO"
        ).select_related("empleado"),
        "documentos": DocumentoEmpleado.objects.filter(
            fecha_vencimiento__range=(hoy, limite), empleado__estado="ACTIVO"
        ).select_related("empleado"),
        "vencidos": (
            ContratoLaboral.objects.filter(
                fecha_fin__lt=hoy, empleado__estado="ACTIVO", activo=True
            ).count()
            + CertificacionEmpleado.objects.filter(
                fecha_vencimiento__lt=hoy, empleado__estado="ACTIVO"
            ).count()
            + DocumentoEmpleado.objects.filter(
                fecha_vencimiento__lt=hoy, empleado__estado="ACTIVO"
            ).count()
        ),
    }


@login_required
def panel(request):
    exigir_gestion_humana(request.user)
    busqueda = request.GET.get("q", "").strip()
    estado = request.GET.get("estado", "ACTIVO").strip()
    tipo_empleado = request.GET.get("tipo_empleado", "").strip()
    empleados = Empleado.objects.select_related("tecnico").all()
    if busqueda:
        empleados = empleados.filter(
            Q(nombres__icontains=busqueda)
            | Q(apellidos__icontains=busqueda)
            | Q(numero_documento__icontains=busqueda)
            | Q(cargo__icontains=busqueda)
        )
    if estado:
        empleados = empleados.filter(estado=estado)
    if tipo_empleado:
        empleados = empleados.filter(tipo_empleado=tipo_empleado)
    alertas = _alertas_vencimiento()
    return render(
        request,
        "gestion_humana/panel.html",
        {
            "empleados": empleados,
            "busqueda": busqueda,
            "filtro_estado": estado,
            "filtro_tipo_empleado": tipo_empleado,
            "total_activos": Empleado.objects.filter(estado="ACTIVO").count(),
            "total_tecnicos": Empleado.objects.filter(
                estado="ACTIVO", tipo_empleado="TECNICO"
            ).count(),
            "total_administrativos": Empleado.objects.filter(
                estado="ACTIVO", tipo_empleado="ADMINISTRATIVO"
            ).count(),
            "tecnicos_sin_ficha": Tecnico.objects.filter(
                activo=True, ficha_empleado__isnull=True
            ).order_by("nombre"),
            "alertas": alertas,
            "total_proximos": sum(
                conjunto.count()
                for clave, conjunto in alertas.items()
                if clave != "vencidos"
            ),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def crear_empleado(request):
    exigir_gestion_humana(request.user)
    inicial = None
    if request.method == "GET":
        tecnico_id = request.GET.get("tecnico", "").strip()
        tecnico = None
        if tecnico_id:
            tecnico = Tecnico.objects.filter(
                pk=tecnico_id,
                activo=True,
                ficha_empleado__isnull=True,
            ).first()
        if tecnico:
            inicial = {
                "tipo_empleado": "TECNICO",
                "tecnico": tecnico,
                "telefono": tecnico.telefono,
                "cargo": "Técnico",
                "area": "Operaciones",
            }
    form = EmpleadoForm(request.POST or None, request.FILES or None, initial=inicial)
    if request.method == "POST" and form.is_valid():
        empleado = form.save(commit=False)
        empleado.creado_por = request.user
        empleado.actualizado_por = request.user
        empleado.save()
        _auditar(empleado, request.user, "Creación", "Se creó la ficha del empleado.")
        messages.success(request, "Empleado registrado correctamente.")
        return redirect("gestion_humana:detalle", empleado.pk)
    return render(request, "gestion_humana/formulario_empleado.html", {"form": form})


@login_required
@require_http_methods(["GET", "POST"])
def editar_empleado(request, empleado_id):
    exigir_gestion_humana(request.user)
    empleado = get_object_or_404(Empleado, pk=empleado_id)
    form = EmpleadoForm(request.POST or None, request.FILES or None, instance=empleado)
    if request.method == "POST" and form.is_valid():
        empleado = form.save(commit=False)
        empleado.actualizado_por = request.user
        empleado.save()
        _auditar(empleado, request.user, "Actualización", "Se actualizó la ficha general.")
        messages.success(request, "Información actualizada correctamente.")
        return redirect("gestion_humana:detalle", empleado.pk)
    return render(
        request,
        "gestion_humana/formulario_empleado.html",
        {"form": form, "empleado": empleado},
    )


@login_required
def detalle_empleado(request, empleado_id):
    exigir_gestion_humana(request.user)
    empleado = get_object_or_404(Empleado.objects.select_related("tecnico"), pk=empleado_id)
    return render(
        request,
        "gestion_humana/detalle_empleado.html",
        {
            "empleado": empleado,
            "form_contrato": ContratoLaboralForm(prefix="contrato"),
            "form_afiliacion": AfiliacionSeguridadSocialForm(prefix="afiliacion"),
            "form_certificacion": CertificacionEmpleadoForm(prefix="certificacion"),
            "form_documento": DocumentoEmpleadoForm(prefix="documento"),
        },
    )


FORMULARIOS_REGISTRO = {
    "contrato": (ContratoLaboralForm, "Contrato agregado", "contratos"),
    "afiliacion": (AfiliacionSeguridadSocialForm, "Afiliación agregada", "afiliaciones"),
    "certificacion": (CertificacionEmpleadoForm, "Certificación agregada", "certificaciones"),
    "documento": (DocumentoEmpleadoForm, "Documento agregado", "documentos"),
}


@login_required
@require_POST
def agregar_registro(request, empleado_id, tipo):
    exigir_gestion_humana(request.user)
    empleado = get_object_or_404(Empleado, pk=empleado_id)
    configuracion = FORMULARIOS_REGISTRO.get(tipo)
    if not configuracion:
        raise Http404
    clase_form, accion, _ = configuracion
    form = clase_form(request.POST, request.FILES, prefix=tipo)
    if form.is_valid():
        with transaction.atomic():
            registro = form.save(commit=False)
            registro.empleado = empleado
            registro.creado_por = request.user
            if tipo == "contrato" and registro.activo:
                ContratoLaboral.objects.filter(empleado=empleado, activo=True).update(activo=False)
            registro.save()
        _auditar(empleado, request.user, accion, str(registro))
        messages.success(request, f"{accion} correctamente.")
    else:
        messages.error(request, "Revise la información; el registro no fue guardado.")
    return redirect("gestion_humana:detalle", empleado.pk)


@login_required
@require_GET
def descargar_archivo(request, tipo, registro_id):
    exigir_gestion_humana(request.user)
    configuracion = {
        "foto": (Empleado, "foto"),
        "contrato": (ContratoLaboral, "documento"),
        "afiliacion": (AfiliacionSeguridadSocial, "soporte"),
        "certificacion": (CertificacionEmpleado, "soporte"),
        "documento": (DocumentoEmpleado, "archivo"),
    }.get(tipo)
    if not configuracion:
        raise Http404
    modelo, campo = configuracion
    registro = get_object_or_404(modelo, pk=registro_id)
    archivo = getattr(registro, campo)
    if not archivo:
        raise Http404
    try:
        return FileResponse(
            archivo.open("rb"),
            as_attachment=tipo != "foto",
            filename=Path(archivo.name).name,
        )
    except FileNotFoundError as exc:
        raise Http404 from exc
