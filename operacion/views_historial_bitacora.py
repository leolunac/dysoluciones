"""Historial interno con revisión previa, autorización y confirmación única."""
from uuid import uuid4
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from .forms import SeguimientoBitacoraForm
from .historial_bitacora import capturar_campos, cambios_entre, nombre_autor
from .models import BitacoraOperativa, SeguimientoBitacora
from .permisos_bitacora import acceso_bitacora, puede_gestionar_bitacora, registros_visibles

SALT = "operacion.seguimiento_bitacora.v1"


def version_registro(registro):
    return registro.actualizado.isoformat()


def leer_revision(token, user, registro):
    datos = signing.loads(token, salt=SALT, max_age=3600)
    if datos["usuario"] != user.pk or datos["bitacora"] != registro.pk:
        raise PermissionDenied("Esta revisión no corresponde a su usuario o a esta novedad.")
    return datos


@login_required
@require_http_methods(["GET", "POST"])
@acceso_bitacora()
def historial_bitacora(request, bitacora_id):
    editor = puede_gestionar_bitacora(request.user)
    if request.method == "POST" and not editor:
        raise PermissionDenied("Solo coordinación y supervisión pueden registrar seguimientos.")
    registro = get_object_or_404(registros_visibles(request.user), pk=bitacora_id)
    form = SeguimientoBitacoraForm()
    revision = None
    token = ""
    error = ""
    status = 200
    if request.method == "POST":
        accion = request.POST.get("accion")
        if accion == "revisar":
            form = SeguimientoBitacoraForm(request.POST)
            if form.is_valid():
                datos = {
                    "usuario": request.user.pk, "bitacora": registro.pk,
                    "version": version_registro(registro), "solicitud": str(uuid4()),
                    "comentario": form.cleaned_data["comentario"],
                    "estado": form.cleaned_data["estado"],
                }
                token = signing.dumps(datos, salt=SALT, compress=True)
                revision = {"comentario": datos["comentario"], "estado": dict(BitacoraOperativa.ESTADO)[datos["estado"] or registro.estado]}
            else:
                status = 400
        elif accion in {"confirmar", "corregir"}:
            try:
                datos = leer_revision(request.POST.get("revision", ""), request.user, registro)
            except signing.BadSignature:
                error = "La revisión venció o no es válida. Vuelva a escribir el seguimiento y revíselo antes de confirmar."
                status = 400
            else:
                form = SeguimientoBitacoraForm(initial={"comentario": datos["comentario"], "estado": datos["estado"]})
                if accion == "confirmar":
                    with transaction.atomic():
                        # Serializa los cambios de esta novedad, incluidos envíos repetidos.
                        registro = get_object_or_404(BitacoraOperativa.objects.select_for_update(), pk=bitacora_id)
                        if SeguimientoBitacora.objects.filter(solicitud=datos["solicitud"], bitacora=registro).exists():
                            return redirect("historial_bitacora", bitacora_id=registro.pk)
                        if version_registro(registro) != datos["version"]:
                            error = "La novedad cambió mientras revisaba el seguimiento. Revise sus datos actuales y confirme nuevamente; su comentario sigue en el formulario."
                            status = 409
                        else:
                            antes = capturar_campos(registro)
                            if datos["estado"]:
                                registro.estado = datos["estado"]
                            registro.visible_cliente = False
                            registro.save(update_fields=["estado", "fecha_cierre", "actualizado", "visible_cliente"])
                            SeguimientoBitacora.objects.create(
                                bitacora=registro, autor=request.user, autor_nombre=nombre_autor(request.user),
                                comentario=datos["comentario"], solicitud=datos["solicitud"],
                                cambios=cambios_entre(antes, capturar_campos(registro)),
                            )
                            return redirect("historial_bitacora", bitacora_id=registro.pk)
        else:
            error = "Seleccione Revisar seguimiento antes de guardarlo."
            status = 400
    pagina = Paginator(registro.seguimientos.select_related("adjunto"), 25).get_page(request.GET.get("pagina"))
    return render(request, "bitacora/historial.html", {
        "registro": registro, "puede_gestionar_bitacora": editor,
        "form_seguimiento": form, "revision": revision, "token_revision": token,
        "error_historial": error, "pagina": pagina,
    }, status=status)
