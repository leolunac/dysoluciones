from django.core.exceptions import PermissionDenied


GRUPOS_GESTION_HUMANA = {
    "GESTION_ADMINISTRATIVA",
    "GESTION_GERENCIA",
    "GESTION_HUMANA",
}


def puede_gestionar_empleados(user):
    if not user or not user.is_authenticated or not user.is_active:
        return False
    return user.is_superuser or user.groups.filter(
        name__in=GRUPOS_GESTION_HUMANA,
    ).exists()


def exigir_gestion_humana(user):
    if not puede_gestionar_empleados(user):
        raise PermissionDenied(
            "No está autorizado para consultar información de empleados."
        )
