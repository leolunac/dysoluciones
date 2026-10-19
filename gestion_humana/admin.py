from django.contrib import admin

from .models import (
    AfiliacionSeguridadSocial,
    CertificacionEmpleado,
    ContratoLaboral,
    DocumentoEmpleado,
    Empleado,
    HistorialEmpleado,
)


@admin.register(Empleado)
class EmpleadoAdmin(admin.ModelAdmin):
    list_display = (
        "numero_documento",
        "nombre_completo",
        "tipo_empleado",
        "cargo",
        "estado",
        "fecha_ingreso",
    )
    list_filter = ("tipo_empleado", "estado", "area")
    search_fields = ("numero_documento", "nombres", "apellidos", "cargo")
    readonly_fields = ("creado", "actualizado")


admin.site.register(ContratoLaboral)
admin.site.register(AfiliacionSeguridadSocial)
admin.site.register(CertificacionEmpleado)
admin.site.register(DocumentoEmpleado)
admin.site.register(HistorialEmpleado)
