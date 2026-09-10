"""Reglas compartidas para envío y revisión de informes técnicos."""

from django.core.exceptions import PermissionDenied
from django.utils import timezone

from .permisos_bitacora import es_usuario_externo


GRUPOS_REVISION_PREVENTIVOS = {
    "GESTION_COORDINADOR",
    "GESTION_SUPERVISOR",
}

GRUPOS_GESTION_REMISIONES = {
    "GESTION_COORDINADOR",
    "GESTION_SUPERVISOR",
}


def puede_revisar_preventivos(user):
    if not user.is_authenticated or not user.is_active:
        return False
    if es_usuario_externo(user):
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=GRUPOS_REVISION_PREVENTIVOS).exists()


def exigir_revisor_preventivos(user):
    if not puede_revisar_preventivos(user):
        raise PermissionDenied(
            "Solo coordinación o supervisión puede revisar estos informes."
        )


def puede_gestionar_remisiones(user):
    if not user.is_authenticated or not user.is_active:
        return False
    if es_usuario_externo(user):
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=GRUPOS_GESTION_REMISIONES).exists()


def asignar_comprobante(actividad):
    """Asigna una constancia estable usando fecha, tipo y llave primaria."""
    cambios = []
    if not actividad.enviado_en:
        actividad.enviado_en = timezone.now()
        cambios.append("enviado_en")

    if not actividad.numero_informe:
        prefijo = {
            "PREVENTIVO": "PREV",
            "LAVADO": "LAV",
        }.get(actividad.tipo_actividad, "COR")
        anio = actividad.fecha.year
        actividad.numero_informe = f"{prefijo}-{anio}-{actividad.pk:06d}"
        cambios.append("numero_informe")

    if cambios:
        cambios.append("actualizado")
        actividad.save(update_fields=cambios)
    return actividad


def errores_para_enviar_preventivo(preventivo):
    errores = []

    if not preventivo.resultado_preventivo:
        errores.append("Seleccione el resultado del mantenimiento.")

    if (
        preventivo.resultado_preventivo == "CON_NOVEDAD"
        and not preventivo.novedades.strip()
    ):
        errores.append("Describa las anomalías encontradas en Novedades.")

    tiene_detalle = any([
        preventivo.control_nivel.strip(),
        preventivo.tablero_electrico.strip(),
        preventivo.novedades.strip(),
        preventivo.mediciones_equipos.exists(),
        preventivo.componentes_revisados.exists(),
        preventivo.tanques_revisados.exists(),
    ])
    if not tiene_detalle:
        errores.append(
            "Registre por lo menos una revisión, medición o componente antes de enviar."
        )

    return errores
