from django.core.exceptions import PermissionDenied


GRUPO_INVENTARIO = "GESTION_INVENTARIO"
GRUPO_GERENCIA = "GESTION_GERENCIA"


def puede_consultar_inventario(user):
    return (
        user.is_authenticated
        and (
            user.is_superuser
            or user.groups.filter(
                name__in=[GRUPO_INVENTARIO, GRUPO_GERENCIA],
            ).exists()
        )
    )


def puede_gestionar_inventario(user):
    return (
        user.is_authenticated
        and (
            user.is_superuser
            or user.groups.filter(name=GRUPO_INVENTARIO).exists()
        )
    )


def exigir_consulta(user):
    if not puede_consultar_inventario(user):
        raise PermissionDenied


def exigir_gestion(user):
    if not puede_gestionar_inventario(user):
        raise PermissionDenied
