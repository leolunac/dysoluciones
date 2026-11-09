from django import template
from operacion.reporte_administraciones_panel import puede_ver_reporte_interno

register = template.Library()


@register.simple_tag
def acceso_reporte_administraciones(user):
    return puede_ver_reporte_interno(user)
