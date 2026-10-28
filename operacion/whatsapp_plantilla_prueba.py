"""Envío manual de una plantilla, limitado al entorno local de pruebas."""
import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings


class ErrorPruebaWhatsApp(Exception):
    pass


def construir_payload(nombre, tipo, unidad, fecha, destino):
    valores = [nombre, tipo, unidad, fecha]
    if any(not isinstance(v, str) or not v.strip() or len(v) > 200 or any(c in v for c in '\r\n\t') for v in valores):
        raise ErrorPruebaWhatsApp('Los cuatro datos deben ser textos no vacíos, de hasta 200 caracteres y sin saltos de línea.')
    if not re.fullmatch(r'[1-9][0-9]{7,14}', destino):
        raise ErrorPruebaWhatsApp('Revise el celular de prueba: código de país y número, sin el signo +.')
    return {
        'messaging_product': 'whatsapp',
        'to': destino,
        'type': 'template',
        'template': {
            'name': 'asignacion_mantenimiento',
            'language': {'code': 'es'},
            'components': [{'type': 'body', 'parameters': [
                {'type': 'text', 'text': valor.strip()} for valor in valores
            ]}],
        },
    }


def enviar_prueba_plantilla(nombre, tipo, unidad, fecha):
    if (not settings.DEBUG
            or settings.DATABASES['default']['ENGINE'] != 'django.db.backends.sqlite3'
            or os.environ.get('SIGOB_WHATSAPP_PRUEBA') != '1'):
        raise ErrorPruebaWhatsApp('Envío bloqueado: use la configuración SQLite local y habilite expresamente la prueba.')
    token = os.environ.get('SIGOB_WHATSAPP_TOKEN', '')
    telefono_id = os.environ.get('SIGOB_WHATSAPP_TELEFONO_ID', '')
    destino = os.environ.get('SIGOB_WHATSAPP_DESTINO_PRUEBA', '')
    version = os.environ.get('SIGOB_WHATSAPP_API_VERSION', 'v25.0')
    if not token or not telefono_id.isdecimal() or not re.fullmatch(r'v[0-9]{1,3}\.[0-9]{1,2}', version):
        raise ErrorPruebaWhatsApp('Falta el token o la configuración del número de prueba.')
    payload = construir_payload(nombre, tipo, unidad, fecha, destino)
    solicitud = Request(
        f'https://graph.facebook.com/{version}/{telefono_id}/messages',
        data=json.dumps(payload).encode('utf-8'),
        headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urlopen(solicitud, timeout=15) as respuesta:
            resultado = json.loads(respuesta.read())
    except HTTPError as error:
        codigo = None
        try:
            detalle = json.loads(error.read()).get('error', {})
            codigo = detalle.get('code')
        except (ValueError, AttributeError, OSError):
            pass
        seguro = f'; código Meta {codigo}' if isinstance(codigo, int) else ''
        raise ErrorPruebaWhatsApp(f'Meta rechazó la solicitud: HTTP {error.code}{seguro}. No se reintentó el envío.') from None
    except (URLError, OSError, ValueError):
        raise ErrorPruebaWhatsApp('No se pudo confirmar la respuesta. Revise el celular antes de repetir para evitar duplicados.') from None
    if not isinstance(resultado, dict) or not resultado.get('messages'):
        raise ErrorPruebaWhatsApp('La respuesta no confirma la aceptación. Revise el celular antes de repetir.')
    return 'Meta aceptó la solicitud. Confirme la llegada del mensaje en su celular.'
