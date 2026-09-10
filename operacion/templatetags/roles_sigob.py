from django import template

from operacion.models import Tecnico


register = template.Library()


@register.simple_tag
def rol_menu_sigob(user):
    if not user or not user.is_authenticated:
        return "ANONIMO"

    if user.is_superuser:
        return "ADMIN"

    grupos = set(user.groups.values_list("name", flat=True))
    if "GESTION_COORDINADOR" in grupos:
        return "COORDINADOR"
    if "GESTION_SUPERVISOR" in grupos:
        return "SUPERVISOR"
    if "GESTION_GERENCIA" in grupos:
        return "GERENCIA"
    if grupos & {"GESTION_FACTURACION", "GESTION_AUXILIAR"}:
        return "COMERCIAL"
    if Tecnico.objects.filter(user_id=user.pk, activo=True).exists():
        return "TECNICO"
    if user.is_staff:
        return "ADMIN"
    return "CLIENTE"
