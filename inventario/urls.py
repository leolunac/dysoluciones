from django.urls import path

from . import views


app_name = "inventario"

urlpatterns = [
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
    path("reportes/consumos.xlsx", views.exportar_consumos_excel, name="exportar_consumos"),
]
