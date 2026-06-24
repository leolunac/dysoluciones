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
    TanqueUnidad,
    DistribucionUnidad,
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
    list_filter = ("estado", "prioridad", "es_nocturna", "aprobada_por_gerencia")
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
    search_fields = ("cliente__nombre", "marca", "modelo", "serie")
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
    search_fields = ("cliente__nombre", "ubicacion", "material")
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
    list_display = ("equipo", "estado", "valor", "fecha_envio", "creado_en")
    list_filter = ("estado",)
    search_fields = ("equipo__cliente__nombre",)
    ordering = ("-creado_en",)


# =========================
# USUARIO CLIENTE
# =========================

@admin.register(UsuarioCliente)
class UsuarioClienteAdmin(admin.ModelAdmin):
    list_display = ("user", "cliente")