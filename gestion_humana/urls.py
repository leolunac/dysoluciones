from django.urls import path

from . import views, desprendibles


app_name = "gestion_humana"

urlpatterns = [
    path("desprendibles/", desprendibles.administrar, name="desprendibles_administrar"),
    path("desprendibles/<int:pk>/retirar/", desprendibles.retirar_desprendible, name="desprendibles_retirar"),
    path("mis-desprendibles/", desprendibles.mis_desprendibles, name="mis_desprendibles"),
    path("desprendibles/<int:pk>/descargar/", desprendibles.descargar, name="desprendibles_descargar"),
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
