from django.urls import path

from . import views


app_name = "gestion_humana"

urlpatterns = [
    path("", views.panel, name="panel"),
    path("empleados/nuevo/", views.crear_empleado, name="crear"),
    path("empleados/<int:empleado_id>/", views.detalle_empleado, name="detalle"),
    path("empleados/<int:empleado_id>/editar/", views.editar_empleado, name="editar"),
    path(
        "empleados/<int:empleado_id>/agregar/<str:tipo>/",
        views.agregar_registro,
        name="agregar_registro",
    ),
    path(
        "archivos/<str:tipo>/<int:registro_id>/",
        views.descargar_archivo,
        name="descargar_archivo",
    ),
]
