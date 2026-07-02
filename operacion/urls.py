from django.urls import path


from .views import (
    home,
    dashboard,
    dashboard_cliente,
    login_view,
    logout_view,
    hoja_vida,
    export_csv,
    export_excel,
    reporte_pdf,
    hoja_vida_pdf,
    centro_operaciones,
    escritorio_coordinador,
    nueva_llamada,
    gestionar_servicio,
)

urlpatterns = [

    # LOGIN
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),
    path("centro-operaciones/", centro_operaciones, name="centro_operaciones"),
    path("coordinador/", escritorio_coordinador, name="escritorio_coordinador"),
    path("nueva-llamada/", nueva_llamada, name="nueva_llamada"),
    # HOME
    path("", home, name="home"),

    # DASHBOARD GERENCIA
    path("gerencia/", dashboard, name="dashboard"),

    # DASHBOARD CLIENTE
    path(
        "cliente/<int:cliente_id>/",
        dashboard_cliente,
        name="dashboard_cliente"
    ),

    # HOJA DE VIDA HTML
    path(
        "hoja-vida/<int:cliente_id>/",
        hoja_vida,
        name="hoja_vida"
    ),

    # HOJA DE VIDA PDF
    path(
        "hoja-vida/<int:cliente_id>/pdf/",
        hoja_vida_pdf,
        name="hoja_vida_pdf"
    ),

    # EXPORTACIONES
    path(
        "export/csv/<int:cliente_id>/",
        export_csv,
        name="export_csv"
    ),

    path(
        "export/excel/<int:cliente_id>/",
        export_excel,
        name="export_excel"
    ),

    # PDF SIMPLE
    path(
        "reporte/pdf/<int:cliente_id>/",
        reporte_pdf,
        name="reporte_pdf"
    ),
path(
    "servicio/<int:servicio_id>/gestionar/",
    gestionar_servicio,
    name="gestionar_servicio"
),
]