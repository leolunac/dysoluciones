"""Asignaciones vigentes para el portal y la autorización de unidades."""
from django.db.models import Q
from django.utils import timezone

from .models import AdministracionUnidad


def asignaciones_administracion_vigentes(administracion):
    """Incluye ambos extremos del período y admite asignaciones sin fecha final."""
    hoy = timezone.localdate()
    return AdministracionUnidad.objects.filter(
        administracion=administracion,
        activo=True,
        cliente__activo=True,
        fecha_inicio__lte=hoy,
    ).filter(
        Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=hoy)
    )
