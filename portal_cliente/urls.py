from django.urls import path

from . import views


urlpatterns = [
    path("", views.inicio_portal, name="portal_inicio"),

    path(
        "documentos/",
        views.lista_documentos,
        name="lista_documentos",
    ),

    path(
        "mis-documentos/",
        views.mis_documentos,
        name="mis_documentos",
    ),
    path(
    "mis-documentos/<int:cliente_id>/",
        views.mis_documentos,
        name="mis_documentos_unidad",
    ),

    path(
        "documentos/nuevo/",
        views.nuevo_documento,
        name="nuevo_documento",
    ),

    path(
        "documentos/<int:documento_id>/editar/",
        views.editar_documento,
        name="editar_documento",
    ),
]
