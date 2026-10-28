"""Avisos de asignación limitados al destinatario del entorno local de prueba."""
import logging
import os

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .whatsapp_plantilla_prueba import enviar_prueba_plantilla

logger = logging.getLogger(__name__)


def _habilitado():
    return (settings.DEBUG
            and settings.DATABASES['default']['ENGINE'] == 'django.db.backends.sqlite3'
            and os.environ.get('SIGOB_WHATSAPP_PRUEBA') == '1')


def _programar(nombre, tipo, unidad, fecha):
    # Capturamos valores, no objetos que puedan cambiar antes del commit.
    datos = tuple(' '.join(str(v).split()) for v in (nombre, tipo, unidad, fecha))
    transaction.on_commit(lambda: _enviar(datos))


def _enviar(datos):
    try:
        enviar_prueba_plantilla(*datos)
        logger.info('Meta aceptó el aviso de asignación de prueba; confirme la entrega en el celular.')
    except Exception:
        # No mostramos credenciales ni datos del servicio en los logs.
        logger.warning('No se pudo confirmar el aviso WhatsApp de prueba. La asignación se conservó; revise el celular antes de repetir.')


def programar_preventivo_prueba(programacion):
    if not _habilitado() or not programacion.tecnico_id:
        return
    _programar(programacion.tecnico.nombre, 'preventivo', programacion.cliente.nombre,
               programacion.fecha_programada.strftime('%d/%m/%Y'))


def programar_correctivo_prueba(servicio):
    if not _habilitado() or servicio.tipo_servicio != 'CORRECTIVO' or not servicio.tecnico_id:
        return
    _programar(servicio.tecnico.nombre, 'correctivo', servicio.cliente.nombre,
               timezone.localdate().strftime('%d/%m/%Y'))
