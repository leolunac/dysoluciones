from django.contrib import admin
from .models import Cliente, Tecnico, Emergencia
from .models import RotacionTecnico



@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'tipo_contrato', 'activo')


@admin.register(Tecnico)
class TecnicoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'activo')


@admin.register(Emergencia)
class EmergenciaAdmin(admin.ModelAdmin):
    list_display = ('cliente', 'prioridad', 'estado', 'tecnico', 'fecha_llamada')
    list_filter = ('prioridad', 'estado')

@admin.register(RotacionTecnico)
class RotacionTecnicoAdmin(admin.ModelAdmin):
    list_display = ('tecnico', 'fecha_inicio_semana', 'fecha_fin_semana', 'es_fin_de_semana', 'activo')
    list_filter = ('es_fin_de_semana', 'activo')