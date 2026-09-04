"""Política de la bitácora interna; independiente de permisos de otros módulos."""
from functools import wraps

from django.core.exceptions import PermissionDenied
from django.db.models import Q

from .models import (
    ActividadTecnico, BitacoraOperativa, Tecnico,
    UsuarioAdministracion, UsuarioCliente,
)


def es_usuario_externo(user):
    return (
        UsuarioCliente.objects.filter(user_id=user.pk).exists()
        or UsuarioAdministracion.objects.filter(user_id=user.pk).exists()
    )


def rol_bitacora(user):
    if not user.is_authenticated or not user.is_active:
        return None
    # Un perfil de cliente/administración nunca recibe acceso interno,
    # incluso si por error tiene grupos internos o es superusuario.
    if es_usuario_externo(user):
        return None
    if user.is_superuser:
        return "editor"
    grupos = set(user.groups.values_list("name", flat=True))
    # Gerencia permanece en consulta incluso con un segundo grupo editor.
    if "GESTION_GERENCIA" in grupos:
        return "consulta"
    if grupos & {"GESTION_COORDINADOR", "GESTION_SUPERVISOR"}:
        return "editor"
    if Tecnico.objects.filter(user_id=user.pk, activo=True).exists():
        return "tecnico"
    return None


def puede_gestionar_bitacora(user):
    return rol_bitacora(user) == "editor"


def acceso_bitacora(*, escritura=False):
    def decorar(view):
        @wraps(view)
        def protegida(request, *args, **kwargs):
            rol = rol_bitacora(request.user)
            if rol is None or (escritura and rol != "editor"):
                raise PermissionDenied("No tiene permiso para esta acción en la bitácora interna.")
            return view(request, *args, **kwargs)
        return protegida
    return decorar


def registros_visibles(user):
    registros = BitacoraOperativa.objects.all()
    rol = rol_bitacora(user)
    if rol in {"editor", "consulta"}:
        return registros
    if rol == "tecnico":
        # tecnico es una relación descriptiva autocompletada, no asignación.
        return registros.filter(responsable_id=user.pk)
    return registros.none()


def actividades_visibles(user):
    actividades = ActividadTecnico.objects.all()
    rol = rol_bitacora(user)
    if rol in {"editor", "consulta"}:
        return actividades
    if rol == "tecnico":
        return actividades.filter(
            pk__in=registros_visibles(user).values("actividad_id")
        )
    return actividades.none()


def responsables_permitidos(queryset):
    return queryset.filter(is_active=True).filter(
        Q(is_superuser=True)
        | Q(groups__name__in=["GESTION_COORDINADOR", "GESTION_SUPERVISOR"])
        | Q(perfil_tecnico__activo=True)
    ).exclude(
        pk__in=UsuarioCliente.objects.values("user_id")
    ).exclude(
        pk__in=UsuarioAdministracion.objects.values("user_id")
    ).exclude(groups__name="GESTION_GERENCIA").distinct()
