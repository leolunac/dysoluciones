from django.urls import path

from . import views


app_name = "gestion_comercial"


urlpatterns = [

    # =====================================================
    # PANEL GESTIÓN COMERCIAL
    # =====================================================

    path(
        "",
        views.panel_gestion_comercial,
        name="panel",
    ),


    # =====================================================
    # CONTRATOS / PASES
    # =====================================================

    path(
        "contratos/",
        views.lista_contratos_pases,
        name="lista_contratos_pases",
    ),

    path(
        "contratos/nuevo/",
        views.nuevo_contrato_pase,
        name="nuevo_contrato_pase",
    ),

    path(
        "contratos/<int:contrato_id>/editar/",
        views.editar_contrato_pase,
        name="editar_contrato_pase",
    ),

    path(
        "contratos/<int:contrato_id>/editar/<str:guardado>/",
        views.editar_contrato_pase,
        name="editar_contrato_pase_guardado",
    ),

    # =====================================================
    # LIQUIDACIONES
    # =====================================================

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

    # =====================================================
    # CONSOLIDADO DE FACTURACIÓN
    # =====================================================

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

    # =====================================================
    # COTIZACIONES
    # =====================================================

    path(
        "cotizaciones/",
        views.lista_cotizaciones,
        name="lista_cotizaciones",
    ),

    path(
        "cotizaciones/nueva/",
        views.nueva_cotizacion,
        name="nueva_cotizacion",
    ),

    path(
        "cotizaciones/<int:cotizacion_id>/editar/",
        views.editar_cotizacion,
        name="editar_cotizacion",
    ),

    path(
        "cotizaciones/<int:cotizacion_id>/finalizar/",
        views.finalizar_elaboracion_cotizacion,
        name="finalizar_elaboracion_cotizacion",
    ),

    path(
        "cotizaciones/<int:cotizacion_id>/pdf/",
        views.generar_pdf_cotizacion,
        name="generar_pdf_cotizacion",
    ),

    path(
        "cotizaciones/<int:cotizacion_id>/marcar-enviada/",
        views.marcar_cotizacion_enviada,
        name="marcar_cotizacion_enviada",
    ),

    path(
        "cotizaciones/<int:cotizacion_id>/aprobar/",
        views.aprobar_cotizacion,
        name="aprobar_cotizacion",
    ),

    path(
        "cotizaciones/<int:cotizacion_id>/rechazar/",
        views.rechazar_cotizacion,
        name="rechazar_cotizacion",
    ),

    path(
        "cotizaciones/detalle/<int:detalle_id>/eliminar/",
        views.eliminar_detalle_cotizacion,
        name="eliminar_detalle_cotizacion",
    ),
]
