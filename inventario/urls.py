from django.urls import path

from . import views
from . import consumos, entradas


app_name = "inventario"

urlpatterns = [
    path("entradas/", entradas.lista_entradas, name="lista_entradas"),
    path("entradas/<int:entrada_id>/", entradas.detalle_entrada, name="detalle_entrada"),
    path("entradas/<int:entrada_id>/materiales/<int:detalle_id>/corregir/", entradas.corregir_cantidad_vista, name="corregir_cantidad_entrada"),
    path("consumos/", consumos.lista_consumos, name="lista_consumos"),
    path("consumos/<int:consumo_id>/", consumos.detalle_consumo, name="detalle_consumo"),
    path("consumos/<int:consumo_id>/materiales/<int:detalle_id>/corregir/", consumos.corregir_cantidad_vista, name="corregir_cantidad_consumo"),
    path("", views.tablero, name="tablero"),
    path(
        "existencias/<int:existencia_id>/ajustar/",
        views.ajustar_existencia_vista,
        name="ajustar_existencia",
    ),
    path("entradas/nueva/", views.nueva_entrada, name="nueva_entrada"),
    path("productos/nuevo/", views.nuevo_producto, name="nuevo_producto"),
    path("productos/", views.lista_productos, name="lista_productos"),
    path(
        "productos/<int:producto_id>/editar/",
        views.editar_producto,
        name="editar_producto",
    ),
    path(
        "productos/verificar-codigo/",
        views.verificar_codigo_producto,
        name="verificar_codigo_producto",
    ),
    path("proveedores/nuevo/", views.nuevo_proveedor, name="nuevo_proveedor"),
    path(
        "entradas/<int:entrada_id>/confirmar/",
        views.confirmar_entrada_vista,
        name="confirmar_entrada",
    ),
    path("consumos/nuevo/", views.nuevo_consumo, name="nuevo_consumo"),
    path(
        "consumos/<int:consumo_id>/confirmar/",
        views.confirmar_consumo_vista,
        name="confirmar_consumo",
    ),
    path(
        "reportes/existencias.xlsx",
        views.exportar_existencias_excel,
        name="exportar_existencias",
    ),
    path("reportes/consumos.xlsx", views.exportar_consumos_excel, name="exportar_consumos"),
]
