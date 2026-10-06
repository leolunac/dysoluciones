from django.contrib import admin

from .models import (
    ConsumoInventario,
    DetalleConsumoInventario,
    DetalleEntradaInventario,
    EntradaInventario,
    ExistenciaInventario,
    MovimientoInventario,
    ProductoInventario,
    Proveedor,
    ReferenciaProveedor,
    UbicacionInventario,
)


@admin.register(ProductoInventario)
class ProductoInventarioAdmin(admin.ModelAdmin):
    list_display = (
        "accesorio",
        "unidad_medida",
        "precio_referencia",
        "costo_neto_ultimo",
        "activo",
    )
    search_fields = ("accesorio__codigo", "accesorio__descripcion")
    list_filter = ("activo", "unidad_medida")


@admin.register(Proveedor)
class ProveedorAdmin(admin.ModelAdmin):
    list_display = ("nombre", "nit", "telefono", "activo")
    search_fields = ("nombre", "nit")
    list_filter = ("activo",)


@admin.register(ReferenciaProveedor)
class ReferenciaProveedorAdmin(admin.ModelAdmin):
    list_display = ("codigo_proveedor", "proveedor", "producto", "activa")
    search_fields = (
        "codigo_proveedor",
        "descripcion_proveedor",
        "producto__accesorio__codigo",
        "producto__accesorio__descripcion",
    )
    list_filter = ("proveedor", "activa")


@admin.register(UbicacionInventario)
class UbicacionInventarioAdmin(admin.ModelAdmin):
    list_display = ("nombre", "tipo", "tecnico", "activa")
    list_filter = ("tipo", "activa")


@admin.register(ExistenciaInventario)
class ExistenciaInventarioAdmin(admin.ModelAdmin):
    list_display = ("producto", "ubicacion", "cantidad", "actualizado")
    search_fields = (
        "producto__accesorio__codigo",
        "producto__accesorio__descripcion",
        "ubicacion__nombre",
    )
    list_filter = ("ubicacion",)
    readonly_fields = ("producto", "ubicacion", "cantidad", "actualizado")


@admin.register(MovimientoInventario)
class MovimientoInventarioAdmin(admin.ModelAdmin):
    list_display = ("creado", "tipo", "producto", "cantidad", "origen", "destino")
    search_fields = (
        "producto__accesorio__codigo",
        "producto__accesorio__descripcion",
        "referencia",
        "cliente__nombre",
    )
    list_filter = ("tipo", "origen", "destino")
    readonly_fields = [field.name for field in MovimientoInventario._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class DetalleEntradaInline(admin.TabularInline):
    model = DetalleEntradaInventario
    extra = 1


@admin.register(EntradaInventario)
class EntradaInventarioAdmin(admin.ModelAdmin):
    list_display = ("numero_factura", "proveedor", "fecha_factura", "estado")
    search_fields = ("numero_factura", "proveedor__nombre")
    list_filter = ("estado", "proveedor")
    inlines = (DetalleEntradaInline,)


class DetalleConsumoInline(admin.TabularInline):
    model = DetalleConsumoInventario
    extra = 1


@admin.register(ConsumoInventario)
class ConsumoInventarioAdmin(admin.ModelAdmin):
    list_display = ("id", "fecha", "cliente", "ubicacion_origen", "estado")
    search_fields = ("cliente__nombre",)
    list_filter = ("estado", "ubicacion_origen")
    inlines = (DetalleConsumoInline,)
