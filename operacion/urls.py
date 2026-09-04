from .views_adjuntos_bitacora import adjuntar_bitacora, descargar_adjunto_bitacora
from .views_historial_bitacora import historial_bitacora
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
    accion_servicio,
    levantamiento_equipo,
    demo_sigob,
    portal_unidades,
    lista_bitacora,
    nueva_bitacora,
    editar_bitacora,
    lista_remisiones,
    nueva_remision,
    conciliar_remision,
    lista_actividades,
    nueva_actividad,
    casos_por_cliente,
    remisiones_por_cliente,
    buscar_accesorios,
    actividades_por_cliente,
    detalle_actividad,
    panel_tecnico,
    servicio_tecnico,
    iniciar_preventivo,
    formulario_preventivo,
    historial_preventivos,
    detalle_preventivo,
    preventivo_pdf,
)


urlpatterns = [

    # LOGIN
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),

    # OPERACIÓN
    path(
        "centro-operaciones/",
        centro_operaciones,
        name="centro_operaciones",
    ),

    path(
        "coordinador/",
        escritorio_coordinador,
        name="escritorio_coordinador",
    ),

    path(
        "nueva-llamada/",
        nueva_llamada,
        name="nueva_llamada",
    ),

    # HOME
    path("", home, name="home"),
    # PANEL DEL TÉCNICO
    path(
        "tecnico/",
    panel_tecnico,
        name="panel_tecnico",
    ),
    path(
        "tecnico/servicio/<int:servicio_id>/",
        servicio_tecnico,
        name="servicio_tecnico",
    ),
    path(
        "tecnico/preventivo/<int:programacion_id>/iniciar/",
        iniciar_preventivo,
        name="iniciar_preventivo",
    ),

    path(
        "tecnico/preventivo/<int:programacion_id>/",
        formulario_preventivo,
        name="formulario_preventivo",
    ),

    path(
        "tecnico/preventivos/historial/",
        historial_preventivos,
        name="historial_preventivos",
    ),

    path(
        "tecnico/preventivos/<int:programacion_id>/detalle/",
        detalle_preventivo,
        name="detalle_preventivo",
    ),
    path(
        "tecnico/preventivos/<int:programacion_id>/pdf/",
        preventivo_pdf,
        name="preventivo_pdf",
    ),
    path(
        "inventario/nuevo/",
        levantamiento_equipo,
        name="levantamiento_equipo",
    ),

    path(
        "demo/",
        demo_sigob,
        name="demo_sigob",
    ),

    path(
        "mis-unidades/",
        portal_unidades,
        name="portal_unidades",
    ),

    # =====================================================
    # BITÁCORA
    # =====================================================

    path("bitacora/<int:bitacora_id>/adjuntar/", adjuntar_bitacora, name="adjuntar_bitacora"),
    path("bitacora/adjuntos/<uuid:adjunto_id>/descargar/", descargar_adjunto_bitacora, name="descargar_adjunto_bitacora"),
    path("bitacora/<int:bitacora_id>/historial/", historial_bitacora, name="historial_bitacora"),

    path(
        "bitacora/",
        lista_bitacora,
        name="lista_bitacora",
    ),

    path(
        "bitacora/nueva/",
        nueva_bitacora,
        name="nueva_bitacora",
    ),

    path(
        "bitacora/<int:bitacora_id>/editar/",
        editar_bitacora,
        name="editar_bitacora",
    ),

    path(
        "bitacora/actividades-por-cliente/",
        actividades_por_cliente,
        name="actividades_por_cliente",
    ),

    path(
        "bitacora/actividad/<int:actividad_id>/detalle/",
        detalle_actividad,
        name="detalle_actividad",
    ),

    # =====================================================
    # ACTIVIDADES DE TÉCNICOS
    # =====================================================

    path(
        "actividades/",
        lista_actividades,
        name="lista_actividades",
    ),

    path(
        "actividades/nueva/",
        nueva_actividad,
        name="nueva_actividad",
    ),

    path(
        "actividades/casos-por-cliente/",
        casos_por_cliente,
        name="casos_por_cliente",
    ),

    path(
        "actividades/remisiones-por-cliente/",
        remisiones_por_cliente,
        name="remisiones_por_cliente",
    ),

    path(
        "actividades/buscar-accesorios/",
        buscar_accesorios,
        name="buscar_accesorios",
    ),

    # DASHBOARD GERENCIA
    path(
        "gerencia/",
        dashboard,
        name="dashboard",
    ),

    # DASHBOARD CLIENTE
    path(
        "cliente/<int:cliente_id>/",
        dashboard_cliente,
        name="dashboard_cliente",
    ),

    # HOJA DE VIDA HTML
    path(
        "hoja-vida/<int:cliente_id>/",
        hoja_vida,
        name="hoja_vida",
    ),

    # HOJA DE VIDA PDF
    path(
        "hoja-vida/<int:cliente_id>/pdf/",
        hoja_vida_pdf,
        name="hoja_vida_pdf",
    ),

    # EXPORTACIONES
    path(
        "export/csv/<int:cliente_id>/",
        export_csv,
        name="export_csv",
    ),

    path(
        "export/excel/<int:cliente_id>/",
        export_excel,
        name="export_excel",
    ),

    # PDF SIMPLE
    path(
        "reporte/pdf/<int:cliente_id>/",
        reporte_pdf,
        name="reporte_pdf",
    ),

    # SERVICIOS
    path(
        "servicio/<int:servicio_id>/gestionar/",
        gestionar_servicio,
        name="gestionar_servicio",
    ),

    path(
        "servicio/<int:servicio_id>/accion/<str:accion>/",
        accion_servicio,
        name="accion_servicio",
    ),

    # =====================================================
    # REMISIONES DE TÉCNICOS
    # =====================================================

    path(
        "remisiones/",
        lista_remisiones,
        name="lista_remisiones",
    ),

    path(
        "remisiones/nueva/",
        nueva_remision,
        name="nueva_remision",
    ),

    path(
        "remisiones/<int:remision_id>/conciliar/",
        conciliar_remision,
        name="conciliar_remision",
    ),
]