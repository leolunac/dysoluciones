from django.contrib import admin

from .models import (
    Cliente,
    Tecnico,
    Emergencia,
    RotacionTecnico,
    LavadoTanque,
    EquipoUnidad,
    CotizacionEquipo,
    UsuarioCliente,
    ClienteAsignado,
    TanqueUnidad,
    DistribucionUnidad,
    EventoServicio,
    BitacoraOperativa,
)


# =========================
# INLINES DEL CLIENTE
# =========================

class EquipoUnidadInline(admin.TabularInline):
    model = EquipoUnidad
    extra = 1
    fields = (
        "tipo",
        "cantidad",
        "torre",
        "ubicacion",
        "marca",
        "modelo",
        "potencia",
        "voltaje",
        "estado",
    )


class TanqueUnidadInline(admin.TabularInline):
    model = TanqueUnidad
    extra = 1
    fields = (
        "tipo_tanque",
        "cantidad",
        "torre",
        "ubicacion",
        "material",
        "capacidad",
        "observaciones",
    )


class DistribucionUnidadInline(admin.TabularInline):
    model = DistribucionUnidad
    extra = 1
    fields = (
        "torre",
        "cantidad_pisos",
        "presion_desde",
        "presion_hasta",
        "gravedad_desde",
        "gravedad_hasta",
        "observaciones",
    )


# =========================
# CLIENTE
# =========================

@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = (
        "nombre",
        "direccion",
        "tipo_contrato",
        "frecuencia_lavado",
        "fecha_ultimo_lavado",
        "activo",
    )

    search_fields = ("nombre", "direccion")
    list_filter = ("tipo_contrato", "frecuencia_lavado", "activo")
    ordering = ("nombre",)

    inlines = [
        EquipoUnidadInline,
        TanqueUnidadInline,
        DistribucionUnidadInline,
    ]


# =========================
# TECNICO
# =========================

@admin.register(Tecnico)
class TecnicoAdmin(admin.ModelAdmin):
    list_display = (
        "nombre",
        "especialidad",
        "valor_hora_diurna",
        "valor_hora_nocturna",
        "activo",
    )
    search_fields = ("nombre", "especialidad")
    list_filter = ("activo",)


# =========================
# EMERGENCIAS
# =========================

@admin.register(Emergencia)
class EmergenciaAdmin(admin.ModelAdmin):
    list_display = (
        "cliente",
        "tecnico",
        "prioridad",
        "estado",
        "es_nocturna",
        "horas_trabajadas",
        "valor_total",
        "aprobada_por_gerencia",
        "fecha_llamada",
    )
    search_fields = ("cliente__nombre", "descripcion_falla")
    list_filter = (
        "estado",
        "prioridad",
        "es_nocturna",
        "aprobada_por_gerencia",
    )
    ordering = ("-fecha_llamada",)


# =========================
# ROTACION
# =========================

@admin.register(RotacionTecnico)
class RotacionAdmin(admin.ModelAdmin):
    list_display = (
        "tecnico",
        "fecha_inicio_semana",
        "fecha_fin_semana",
        "es_fin_de_semana",
        "activo",
    )
    list_filter = ("es_fin_de_semana", "activo")


# =========================
# LAVADOS
# =========================

@admin.register(LavadoTanque)
class LavadoTanqueAdmin(admin.ModelAdmin):
    list_display = (
        "cliente",
        "fecha_programada",
        "ejecutado",
        "fecha_ejecucion",
        "aprobado",
        "publicado_cliente",
    )
    list_filter = ("ejecutado", "aprobado", "publicado_cliente")
    search_fields = ("cliente__nombre",)
    ordering = ("-fecha_programada",)


# =========================
# EQUIPOS
# =========================

@admin.register(EquipoUnidad)
class EquipoUnidadAdmin(admin.ModelAdmin):
    list_display = (
        "cliente",
        "tipo",
        "cantidad",
        "marca",
        "modelo",
        "potencia",
        "voltaje",
        "estado",
        "ultima_revision",
    )

    list_filter = ("tipo", "estado")
    search_fields = (
        "cliente__nombre",
        "marca",
        "modelo",
        "serie",
    )
    ordering = ("cliente__nombre", "tipo")

    fields = (
        "cliente",
        "tipo",
        "cantidad",
        "torre",
        "ubicacion",
        "marca",
        "modelo",
        "serie",
        "potencia",
        "voltaje",
        "control",
        "valor_comercial",
        "estado",
        "causa_fuera_servicio",
        "ultima_revision",
        "observaciones",
    )


# =========================
# TANQUES
# =========================

@admin.register(TanqueUnidad)
class TanqueUnidadAdmin(admin.ModelAdmin):
    list_display = (
        "cliente",
        "tipo_tanque",
        "cantidad",
        "torre",
        "ubicacion",
        "material",
        "capacidad",
    )
    list_filter = ("tipo_tanque",)
    search_fields = (
        "cliente__nombre",
        "ubicacion",
        "material",
    )
    ordering = ("cliente__nombre", "tipo_tanque")


# =========================
# DISTRIBUCION
# =========================

@admin.register(DistribucionUnidad)
class DistribucionUnidadAdmin(admin.ModelAdmin):
    list_display = (
        "cliente",
        "torre",
        "cantidad_pisos",
        "presion_desde",
        "presion_hasta",
        "gravedad_desde",
        "gravedad_hasta",
    )
    search_fields = ("cliente__nombre", "torre")
    ordering = ("cliente__nombre", "torre")


# =========================
# COTIZACIONES
# =========================

@admin.register(CotizacionEquipo)
class CotizacionEquipoAdmin(admin.ModelAdmin):
    list_display = (
        "equipo",
        "estado",
        "valor",
        "fecha_envio",
        "creado_en",
    )
    list_filter = ("estado",)
    search_fields = ("equipo__cliente__nombre",)
    ordering = ("-creado_en",)


# =========================
# USUARIO CLIENTE
# =========================

@admin.register(UsuarioCliente)
class UsuarioClienteAdmin(admin.ModelAdmin):
    list_display = ("user", "cliente")
    search_fields = (
        "user__username",
        "user__first_name",
        "user__last_name",
        "cliente__nombre",
    )


# =========================
# CLIENTES ASIGNADOS
# =========================

@admin.register(ClienteAsignado)
class ClienteAsignadoAdmin(admin.ModelAdmin):
    list_display = (
        "usuario_cliente",
        "cliente",
        "principal",
        "activo",
    )

    list_filter = (
        "principal",
        "activo",
    )

    search_fields = (
        "usuario_cliente__user__username",
        "usuario_cliente__user__first_name",
        "usuario_cliente__user__last_name",
        "cliente__nombre",
    )

    raw_id_fields = (
        "usuario_cliente",
        "cliente",
    )

    ordering = (
        "-principal",
        "cliente__nombre",
    )


# =========================
# EVENTOS DE SERVICIO
# =========================

@admin.register(EventoServicio)
class EventoServicioAdmin(admin.ModelAdmin):
    list_display = (
        "servicio",
        "fecha",
        "titulo",
        "usuario",
    )

    search_fields = (
        "titulo",
        "servicio__numero_caso",
        "usuario",
    )

    list_filter = (
        "fecha",
    )
# =========================
# BITÁCORA OPERATIVA
# =========================

@admin.register(BitacoraOperativa)
class BitacoraOperativaAdmin(admin.ModelAdmin):
    list_display = (
        "titulo",
        "tipo",
        "cliente",
        "tecnico",
        "responsable",
        "prioridad",
        "estado",
        "fecha_compromiso",
        "creado",
    )

    list_filter = (
        "tipo",
        "prioridad",
        "estado",
        "visible_cliente",
        "fecha_compromiso",
    )

    search_fields = (
        "titulo",
        "descripcion",
        "accion_pendiente",
        "cliente__nombre",
        "tecnico__nombre",
        "responsable__username",
    )

    autocomplete_fields = (
        "cliente",
        "tecnico",
        "servicio",
        "responsable",
    )

    readonly_fields = (
        "creado",
        "actualizado",
        "fecha_cierre",
    )

    ordering = (
        "estado",
        "-prioridad",
        "fecha_compromiso",
    )

    fieldsets = (
        (
            "Información principal",
            {
                "fields": (
                    "titulo",
                    "tipo",
                    "descripcion",
                    "accion_pendiente",
                )
            },
        ),
        (
            "Relaciones",
            {
                "fields": (
                    "cliente",
                    "tecnico",
                    "servicio",
                    "responsable",
                )
            },
        ),
        (
            "Seguimiento",
            {
                "fields": (
                    "prioridad",
                    "estado",
                    "fecha_compromiso",
                    "fecha_cierre",
                    "visible_cliente",
                )
            },
        ),
        (
            "Auditoría",
            {
                "fields": (
                    "creado_por",
                    "creado",
                    "actualizado",
                )
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        if not obj.creado_por_id:
            obj.creado_por = request.user

        super().save_model(request, obj, form, change)