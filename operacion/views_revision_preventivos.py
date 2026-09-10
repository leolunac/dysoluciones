from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.db import transaction
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from portal_cliente.models import DocumentoCliente

from .forms import (
    ProgramacionPreventivoForm,
    RevisionPreventivoForm,
    SeguimientoAnomaliaPreventivoForm,
)
from .informes_tecnicos import exigir_revisor_preventivos, puede_revisar_preventivos
from .models import (
    ActividadTecnico,
    MantenimientoPreventivo,
    ProgramacionMantenimientoPreventivo,
    SeguimientoAnomaliaPreventivo,
    Tecnico,
)
from .permisos_bitacora import es_usuario_externo


ESTADOS_CON_DETALLE = [
    "PENDIENTE_REVISION",
    "DEVUELTO",
    "PUBLICADO",
    "EJECUTADO",
]


def _programacion_con_informe(programacion_id, **filtros):
    return get_object_or_404(
        ProgramacionMantenimientoPreventivo.objects.select_related(
            "cliente",
            "sector",
            "tecnico__user",
            "actividad__preventivo__revisado_por",
            "actividad__preventivo__documento_cliente",
        ),
        pk=programacion_id,
        actividad__isnull=False,
        **filtros,
    )


@login_required
def comprobante_actividad(request, actividad_id):
    actividad = get_object_or_404(
        ActividadTecnico.objects.select_related(
            "cliente",
            "tecnico__user",
            "servicio",
            "remision",
        ).prefetch_related(
            "accesorios_utilizados__accesorio",
        ),
        pk=actividad_id,
        numero_informe__isnull=False,
        enviado_en__isnull=False,
    )

    tecnico_usuario = Tecnico.objects.filter(
        user=request.user,
        activo=True,
    ).first()

    if tecnico_usuario:
        autorizado = actividad.tecnico_id == tecnico_usuario.id
    else:
        autorizado = (
            not es_usuario_externo(request.user)
            and (
                request.user.is_staff
                or request.user.is_superuser
                or puede_revisar_preventivos(request.user)
            )
        )
    if not autorizado:
        return HttpResponseForbidden("No está autorizado para ver este comprobante.")

    return render(
        request,
        "tecnico/comprobante_envio.html",
        {"actividad": actividad, "tecnico_usuario": tecnico_usuario},
    )


@login_required
def bandeja_revision_preventivos(request):
    exigir_revisor_preventivos(request.user)
    pendientes = (
        ProgramacionMantenimientoPreventivo.objects
        .filter(estado="PENDIENTE_REVISION")
        .select_related("cliente", "sector", "tecnico", "actividad__preventivo")
        .order_by("actualizado", "fecha_programada", "pk")
    )
    devueltos = (
        ProgramacionMantenimientoPreventivo.objects
        .filter(estado="DEVUELTO")
        .select_related("cliente", "sector", "tecnico", "actividad__preventivo")
        .order_by("-actualizado")[:20]
    )
    return render(
        request,
        "preventivos/bandeja_revision.html",
        {"pendientes": pendientes, "devueltos": devueltos},
    )


@login_required
def programar_preventivo(request):
    exigir_revisor_preventivos(request.user)
    form = ProgramacionPreventivoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        programacion = form.save(commit=False)
        programacion.creado_por = request.user
        programacion.estado = "PROGRAMADO"
        programacion.full_clean()
        programacion.save()
        return redirect("bandeja_revision_preventivos")
    return render(
        request,
        "preventivos/programar.html",
        {"form": form},
    )
@login_required
def revisar_preventivo(request, programacion_id):
    exigir_revisor_preventivos(request.user)
    programacion = _programacion_con_informe(
        programacion_id,
        estado="PENDIENTE_REVISION",
    )
    preventivo = programacion.actividad.preventivo
    form = RevisionPreventivoForm(
        request.POST or None,
        preventivo=preventivo,
    )

    if request.method == "POST" and form.is_valid():
        datos = form.cleaned_data
        decision = datos["decision"]

        if decision == "DEVOLVER":
            with transaction.atomic():
                preventivo.estado_revision = "DEVUELTO"
                preventivo.observaciones_revision = datos["observaciones_revision"]
                preventivo.revisado_por = request.user
                preventivo.revisado_en = timezone.now()
                preventivo.save(update_fields=[
                    "estado_revision",
                    "observaciones_revision",
                    "revisado_por",
                    "revisado_en",
                    "actualizado",
                ])
                programacion.estado = "DEVUELTO"
                programacion.save(update_fields=["estado", "actualizado"])
            return redirect("bandeja_revision_preventivos")

        with transaction.atomic():
            estado_anterior = preventivo.estado_anomalia
            preventivo.estado_revision = "PUBLICADO"
            preventivo.observaciones_revision = datos["observaciones_revision"]
            preventivo.cliente_informado = datos["cliente_informado"]
            preventivo.medio_notificacion = datos["medio_notificacion"]
            preventivo.estado_anomalia = datos["estado_anomalia"]
            preventivo.revisado_por = request.user
            preventivo.revisado_en = timezone.now()
            if preventivo.cliente_informado and not preventivo.fecha_cliente_informado:
                preventivo.fecha_cliente_informado = timezone.now()
            preventivo.save(update_fields=[
                "estado_revision",
                "observaciones_revision",
                "cliente_informado",
                "medio_notificacion",
                "estado_anomalia",
                "revisado_por",
                "revisado_en",
                "fecha_cliente_informado",
                "actualizado",
            ])

            programacion.estado = "PUBLICADO"
            programacion.save(update_fields=["estado", "actualizado"])

            if estado_anterior != preventivo.estado_anomalia:
                SeguimientoAnomaliaPreventivo.objects.create(
                    preventivo=preventivo,
                    estado_anterior=estado_anterior,
                    estado_nuevo=preventivo.estado_anomalia,
                    observacion=datos["observaciones_revision"],
                    usuario=request.user,
                )

            # Se reutiliza el generador actual para que la vista y el archivo
            # publicado sean exactamente el mismo informe.
            from .views import preventivo_pdf

            respuesta_pdf = preventivo_pdf(request, programacion.pk)
            if respuesta_pdf.status_code != 200:
                raise Http404("No fue posible generar el informe preventivo.")

            nombre = f"{programacion.actividad.numero_informe}.pdf"
            documento = DocumentoCliente(
                cliente=programacion.cliente,
                titulo=(
                    f"Mantenimiento preventivo "
                    f"{programacion.actividad.numero_informe}"
                ),
                tipo="PREVENTIVO",
                fecha_documento=programacion.actividad.fecha,
                estado="PUBLICADO",
                observaciones=(
                    "Informe revisado y aprobado en SIGOB. "
                    f"Resultado: {preventivo.get_resultado_preventivo_display()}."
                ),
            )
            documento.archivo.save(
                nombre,
                ContentFile(respuesta_pdf.content),
                save=False,
            )
            documento.save()
            preventivo.documento_cliente = documento
            preventivo.save(update_fields=["documento_cliente", "actualizado"])

        return redirect("detalle_preventivo", programacion_id=programacion.pk)

    return render(
        request,
        "preventivos/revisar.html",
        {
            "programacion": programacion,
            "actividad": programacion.actividad,
            "preventivo": preventivo,
            "form": form,
            "mediciones": preventivo.mediciones_equipos.select_related("equipo"),
            "componentes": preventivo.componentes_revisados.all(),
            "tanques": preventivo.tanques_revisados.select_related("tanque"),
        },
    )


@login_required
def actualizar_anomalia_preventivo(request, programacion_id):
    exigir_revisor_preventivos(request.user)
    programacion = _programacion_con_informe(
        programacion_id,
        estado="PUBLICADO",
    )
    preventivo = programacion.actividad.preventivo
    if preventivo.resultado_preventivo != "CON_NOVEDAD":
        raise Http404("Este mantenimiento no tiene anomalías pendientes.")

    form = SeguimientoAnomaliaPreventivoForm(request.POST or None, initial={
        "estado_anomalia": preventivo.estado_anomalia,
    })
    if request.method == "POST" and form.is_valid():
        anterior = preventivo.estado_anomalia
        nuevo = form.cleaned_data["estado_anomalia"]
        preventivo.estado_anomalia = nuevo
        preventivo.save(update_fields=["estado_anomalia", "actualizado"])
        SeguimientoAnomaliaPreventivo.objects.create(
            preventivo=preventivo,
            estado_anterior=anterior,
            estado_nuevo=nuevo,
            observacion=form.cleaned_data["observacion"],
            usuario=request.user,
        )
        return redirect("detalle_preventivo", programacion_id=programacion.pk)

    return render(
        request,
        "preventivos/actualizar_anomalia.html",
        {"programacion": programacion, "preventivo": preventivo, "form": form},
    )


def verificar_preventivo(request, codigo):
    preventivo = get_object_or_404(
        MantenimientoPreventivo.objects.select_related(
            "actividad__cliente",
            "actividad__programacion_preventiva__sector",
        ),
        codigo_verificacion=codigo,
        estado_revision="PUBLICADO",
    )
    return render(
        request,
        "preventivos/verificar.html",
        {"preventivo": preventivo, "actividad": preventivo.actividad},
    )
