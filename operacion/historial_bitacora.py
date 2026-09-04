"""Registro de cambios realizados desde los formularios y el administrador."""
from datetime import datetime, timezone as datetime_timezone
from django.utils import timezone
from .models import SeguimientoBitacora

CAMPOS = {
    "titulo": "Título", "tipo": "Tipo", "descripcion": "Descripción",
    "accion_pendiente": "Acción pendiente", "cliente": "Unidad / cliente",
    "tecnico": "Técnico relacionado", "servicio": "Caso relacionado",
    "actividad": "Actividad relacionada", "responsable": "Responsable",
    "prioridad": "Prioridad", "estado": "Estado", "fecha_compromiso": "Compromiso",
    "fecha_cierre": "Fecha de cierre",
}


def capturar_campos(registro):
    datos = {}
    for nombre, etiqueta in CAMPOS.items():
        campo = registro._meta.get_field(nombre)
        valor = getattr(registro, campo.attname)
        if valor is None or valor == "":
            clave, texto = "", "Sin dato"
        elif isinstance(valor, datetime):
            clave = (valor.astimezone(datetime_timezone.utc) if timezone.is_aware(valor) else valor).isoformat()
            local = timezone.localtime(valor) if timezone.is_aware(valor) else valor
            texto = local.strftime("%d/%m/%Y %H:%M")
        elif campo.is_relation:
            clave, texto = str(valor), str(getattr(registro, nombre))
        else:
            clave = str(valor)
            texto = str(getattr(registro, f"get_{nombre}_display")()) if campo.choices else clave
        datos[nombre] = {"valor": clave, "texto": texto, "campo": etiqueta}
    return datos


def cambios_entre(antes, despues):
    return [
        {"campo": antes[n]["campo"], "anterior": antes[n]["texto"], "nuevo": despues[n]["texto"],
         "anterior_id": antes[n]["valor"], "nuevo_id": despues[n]["valor"]}
        for n in CAMPOS if antes[n]["valor"] != despues[n]["valor"]
    ]


def nombre_autor(user):
    return str(user.get_username())[:254]


def registrar_edicion(anteriores, registro, user):
    cambios = cambios_entre(anteriores, capturar_campos(registro))
    if cambios:
        return SeguimientoBitacora.objects.create(
            bitacora=registro, autor=user, autor_nombre=nombre_autor(user),
            tipo="EDICION", cambios=cambios,
        )
