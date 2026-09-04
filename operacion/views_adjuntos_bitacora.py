"""Carga y descarga autenticadas de soportes privados de la bitácora."""
import logging
from uuid import uuid4
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError, transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods
from .adjuntos_bitacora import AdjuntoBitacoraForm, almacenamiento_privado, guardar_archivo_privado, ruta_para_lectura
from .historial_bitacora import nombre_autor
from .models import AdjuntoBitacora, BitacoraOperativa, SeguimientoBitacora
from .permisos_bitacora import acceso_bitacora, registros_visibles

logger = logging.getLogger(__name__)
SALT = 'operacion.adjunto_bitacora.v1'


def nueva_solicitud(user, registro):
    return signing.dumps({'usuario': user.pk, 'bitacora': registro.pk, 'solicitud': str(uuid4())}, salt=SALT)


@transaction.non_atomic_requests
@login_required
@require_http_methods(['GET', 'POST'])
@acceso_bitacora(escritura=True)
def adjuntar_bitacora(request, bitacora_id):
    registro = get_object_or_404(registros_visibles(request.user), pk=bitacora_id)
    status = 200
    duplicado = None
    form = AdjuntoBitacoraForm(initial={'solicitud': nueva_solicitud(request.user, registro)})
    if request.method == 'POST':
        form = AdjuntoBitacoraForm(request.POST, request.FILES)
        try:
            datos = signing.loads(request.POST.get('solicitud', ''), salt=SALT, max_age=3600)
        except signing.BadSignature:
            # Renovar el formulario sin aceptar ni guardar la solicitud anterior.
            data = request.POST.copy()
            data['solicitud'] = nueva_solicitud(request.user, registro)
            form = AdjuntoBitacoraForm(data)
            form.is_valid()
            form.add_error(None, 'La solicitud venció o no es válida. Seleccione nuevamente el archivo y confirme.')
            status = 400
        else:
            if datos['usuario'] != request.user.pk or datos['bitacora'] != registro.pk:
                raise PermissionDenied('La solicitud no corresponde a este usuario y esta novedad.')
            if form.is_valid():
                if len(request.FILES.getlist('archivo')) != 1:
                    form.add_error('archivo', 'Adjunte un archivo por vez.')
                    status = 400
                else:
                    archivo = form.cleaned_data['archivo']
                    almacen = almacenamiento_privado()
                    guardado = None
                    try:
                        with transaction.atomic():
                            registro = get_object_or_404(BitacoraOperativa.objects.select_for_update(), pk=registro.pk)
                            if SeguimientoBitacora.objects.filter(bitacora=registro, solicitud=datos['solicitud']).exists():
                                return redirect('historial_bitacora', bitacora_id=registro.pk)
                            duplicado = AdjuntoBitacora.objects.filter(
                                seguimiento__bitacora=registro, sha256=archivo['sha256'],
                            ).first()
                            if duplicado is None:
                                entrada = SeguimientoBitacora.objects.create(
                                    bitacora=registro, autor=request.user, autor_nombre=nombre_autor(request.user),
                                    tipo='ADJUNTO', solicitud=datos['solicitud'],
                                    comentario=form.cleaned_data['descripcion'] or 'Se adjuntó un archivo.',
                                )
                                adjunto = AdjuntoBitacora(
                                    seguimiento=entrada, nombre_original=archivo['nombre'],
                                    tamano=archivo['tamano'], tipo_mime=archivo['mime'], sha256=archivo['sha256'],
                                )
                                guardado = guardar_archivo_privado(almacen, adjunto.pk, archivo)
                                adjunto.ruta_privada = guardado
                                adjunto.save()
                                registro.visible_cliente = False
                                registro.save(update_fields=['actualizado', 'visible_cliente'])
                        if duplicado is None:
                            return redirect('historial_bitacora', bitacora_id=registro.pk)
                    except Exception as exc:
                        if guardado:
                            try:
                                almacen.delete(guardado)
                            except OSError:
                                logger.exception('No se pudo limpiar un archivo privado tras un fallo de registro.')
                        if not isinstance(exc, (OSError, DatabaseError)):
                            raise
                        logger.exception('No se pudo registrar el adjunto de bitácora.')
                        form.add_error(None, 'No se pudo guardar el adjunto. Seleccione el archivo e inténtelo nuevamente.')
                        status = 503
            else:
                status = 400
    return render(request, 'bitacora/adjuntar.html', {
        'registro': registro, 'form_adjunto': form, 'duplicado': duplicado,
    }, status=status)


@login_required
@require_GET
@acceso_bitacora()
def descargar_adjunto_bitacora(request, adjunto_id):
    adjunto = get_object_or_404(
        AdjuntoBitacora.objects.filter(
            seguimiento__bitacora_id__in=registros_visibles(request.user).values('pk'),
        ), pk=adjunto_id,
    )
    almacen = almacenamiento_privado()
    try:
        ruta = ruta_para_lectura(almacen, adjunto.ruta_privada)
        archivo = ruta.open('rb')
    except (FileNotFoundError, IsADirectoryError):
        raise Http404('El archivo no está disponible.')
    response = FileResponse(archivo, as_attachment=True, filename=adjunto.nombre_original, content_type='application/octet-stream')
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    response['Content-Security-Policy'] = "sandbox; default-src 'none'"
    response['Referrer-Policy'] = 'no-referrer'
    return response
