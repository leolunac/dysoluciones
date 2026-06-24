from django.contrib import admin
from .models import Cliente, Tecnico, Emergencia, RotacionTecnico, LavadoTanque, EquipoUnidad, CotizacionEquipo, UsuarioCliente


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
@admin.register(EquipoUnidad)
class EquipoUnidadAdmin(admin.ModelAdmin):
    list_display = ("cliente", "tipo", "cantidad", "estado", "ultima_revision")
    list_filter = ("tipo", "estado")
    search_fields = ("cliente__nombre",)
    ordering = ("cliente__nombre", "tipo")


@admin.register(CotizacionEquipo)
class CotizacionEquipoAdmin(admin.ModelAdmin):
    list_display = ("equipo", "estado", "valor", "fecha_envio", "creado_en")
    list_filter = ("estado",)
    search_fields = ("equipo__cliente__nombre",)
    ordering = ("-creado_en",)
 

@admin.register(UsuarioCliente)
class UsuarioClienteAdmin(admin.ModelAdmin):
    list_display = ("user", "cliente")   