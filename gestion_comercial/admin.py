from django.contrib import admin

from .models import (
    Liquidacion,
    DetalleLiquidacion,
    CatalogoPrecio,
    TarifaOperativa,
    RevisionMaterialUtilizado,
)


class DetalleLiquidacionInline(admin.TabularInline):
    model = DetalleLiquidacion
    extra = 1

    fields = (
        "tipo",
        "descripcion",
        "cantidad",
        "valor_unitario",
        "subtotal",
        "observaciones",
    )

    readonly_fields = ("subtotal",)


@admin.register(Liquidacion)
class LiquidacionAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "cliente",
        "estado",
        "valor_sin_iva",
        "valor_total",
        "creado_por",
        "fecha_creacion",
    )

    list_filter = (
        "estado",
        "fecha_creacion",
    )

    search_fields = (
        "cliente__nombre",
        "descripcion",
        "numero_factura",
    )

    readonly_fields = (
        "fecha_creacion",
        "fecha_actualizacion",
        "fecha_revision",
        "fecha_facturacion",
    )

    inlines = [
        DetalleLiquidacionInline,
    ]


@admin.register(CatalogoPrecio)
class CatalogoPrecioAdmin(admin.ModelAdmin):

    list_display = (
        "codigo",
        "descripcion",
        "valor",
        "activo",
        "actualizado",
    )

    list_filter = (
        "activo",
    )

    search_fields = (
        "codigo",
        "descripcion",
    )


@admin.register(TarifaOperativa)
class TarifaOperativaAdmin(admin.ModelAdmin):

    list_display = (
        "nombre",
        "tipo",
        "valor",
        "activo",
    )

    list_filter = (
        "tipo",
        "activo",
    )

    search_fields = (
        "nombre",
    )


@admin.register(RevisionMaterialUtilizado)
class RevisionMaterialUtilizadoAdmin(admin.ModelAdmin):
    list_display = (
        "descripcion_snapshot",
        "cantidad_snapshot",
        "estado",
        "valor_unitario_sugerido",
        "revisado_por",
        "revisado_en",
    )
    list_filter = ("estado", "revisado_en")
    search_fields = (
        "codigo_snapshot",
        "descripcion_snapshot",
        "consumo__actividad__cliente__nombre",
        "consumo__actividad__tecnico__nombre",
    )
    readonly_fields = ("creado", "actualizado")
