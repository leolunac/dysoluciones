from django.urls import path

from . import views


app_name = "gestion_comercial"


urlpatterns = [

    path(
        "",
        views.panel_gestion_comercial,
        name="panel",
    ),

    path(
        "nueva/",
        views.nueva_liquidacion,
        name="nueva_liquidacion",
    ),

    path(
        "<int:liquidacion_id>/editar/",
        views.editar_liquidacion,
        name="editar_liquidacion",
    ),
    path(
        "<int:liquidacion_id>/crear-accesorio/",
        views.crear_accesorio,
        name="crear_accesorio",
    ),

    path(
        "<int:liquidacion_id>/enviar-revision/",
        views.enviar_revision,
        name="enviar_revision",
),
    path(
        "detalle/<int:detalle_id>/eliminar/",
        views.eliminar_detalle,
        name="eliminar_detalle",
),
    path(
    "detalle/<int:detalle_id>/editar/",
    views.editar_detalle,
    name="editar_detalle",
),
path(
    "<int:liquidacion_id>/aprobar/",
    views.aprobar_liquidacion,
    name="aprobar_liquidacion",
),

path(
    "<int:liquidacion_id>/devolver/",
    views.devolver_liquidacion,
    name="devolver_liquidacion",
),
path(
    "<int:liquidacion_id>/enviar-facturacion/",
    views.enviar_facturacion,
    name="enviar_facturacion",
),
path(
    "<int:liquidacion_id>/marcar-facturada/",
    views.marcar_facturada,
    name="marcar_facturada",
),
path(
    "consolidado-facturacion/",
    views.consolidado_facturacion,
    name="consolidado_facturacion",
),
path(
    "consolidado-facturacion/exportar-excel/",
    views.exportar_facturacion_excel,
    name="exportar_facturacion_excel",
),
]