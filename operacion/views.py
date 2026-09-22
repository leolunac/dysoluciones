from django.db.models import DateField
from django.db.models.functions import Coalesce, TruncDate
from .sectores import filtrar_sector, sectores_en
from django.db import transaction
from .historial_bitacora import capturar_campos, registrar_edicion
import csv
import os
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

import openpyxl

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum, Q
from django.db.models.functions import TruncMonth
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from reportlab.lib.pagesizes import letter
from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.pdfgen import canvas
from django.urls import reverse

from .forms import (
    NuevaLlamadaForm,
    GestionServicioForm,
    LevantamientoEquipoForm,
    BitacoraOperativaForm,
    RemisionTecnicoForm,
    DetalleRemisionFormSet,
    DetalleConciliacionFormSet,
    ActividadTecnicoForm,
    MantenimientoPreventivoForm,
    MedicionEquipoPreventivoForm,
    RevisionComponentePreventivoForm,
    RevisionTanquePreventivoForm,
)
from .models import (
    Cliente,
    CotizacionEquipo,
    DistribucionUnidad,
    Emergencia,
    EquipoUnidad,
    TanqueUnidad,
    Tecnico,
    UsuarioCliente,
    ClienteAsignado,
    AdministracionUnidad,
    UsuarioAdministracion,
    BitacoraOperativa,
    RemisionTecnico,
    DetalleRemision,
    ActividadTecnico,
    Accesorio,
    AccesorioActividad,
    ProgramacionMantenimientoPreventivo,
    MantenimientoPreventivo,
    RevisionComponentePreventivo,
    RevisionTanquePreventivo,
    

)                    

from .permisos_bitacora import (
    acceso_bitacora, actividades_visibles, es_usuario_externo,
    puede_gestionar_bitacora, registros_visibles,
)
from .informes_tecnicos import (
    asignar_comprobante,
    errores_para_enviar_preventivo,
    puede_gestionar_remisiones,
    puede_revisar_preventivos,
)
from .lavados import registrar_ejecucion_lavado
from django.views.decorators.http import require_GET, require_http_methods

from .utils import registrar_evento
from gestion_comercial.models import Cotizacion, Liquidacion

# =========================================
# LOGIN / REDIRECCIÓN POR PERFIL
# =========================================

GRUPOS_GESTION_COMERCIAL = {
    "GESTION_AUXILIAR",
    "GESTION_COORDINADOR",
    "GESTION_FACTURACION",
    "GESTION_GERENCIA",
    
}


def es_usuario_gestion_comercial(user):
    """
    Devuelve True si el usuario pertenece a uno de los perfiles
    internos de Gestión Comercial.
    """
    if not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    return user.groups.filter(
        name__in=GRUPOS_GESTION_COMERCIAL
    ).exists()

def es_coordinador_operativo(user):
    """
    Permite acceso a la operación 7x24 al Coordinador,
    Gerencia y superusuarios.
    """
    if not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    return user.groups.filter(
        name__in=[
            "GESTION_COORDINADOR",
            "GESTION_GERENCIA",
        ]
    ).exists()
def login_view(request):

    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(
            request,
            username=username,
            password=password,
        )

        if user is not None:
            login(request, user)

            # =========================================
            # GERENCIA / SUPERUSUARIO
            # =========================================
            if (
                user.is_superuser
                or user.groups.filter(
                    name="GESTION_GERENCIA"
                ).exists()
            ):
                return redirect("/gerencia/")

            # =========================================
            # TÉCNICO
            # =========================================
            if Tecnico.objects.filter(
                user=user,
                activo=True,
            ).exists():
                return redirect("/tecnico/")
    # =========================================
# SUPERVISOR
# =========================================
    if user.groups.filter(
        name="GESTION_SUPERVISOR"
    ).exists():
        return redirect(
        "gestion_comercial:lista_cotizaciones"
    )        

            # =========================================
# COORDINADOR OPERATIVO
# =========================================
    if user.groups.filter(
    name="GESTION_COORDINADOR"
    ).exists():
        return redirect("escritorio_coordinador")

# =========================================
# FACTURACIÓN
# =========================================
    if user.groups.filter(
    name="GESTION_FACTURACION"
    ).exists():
        return redirect("gestion_comercial:panel")

# =========================================
# GESTIÓN COMERCIAL
# =========================================
    if es_usuario_gestion_comercial(user):
        return redirect("/gestion-comercial/")

# =========================================
# OTROS USUARIOS INTERNOS
# =========================================
    if user.is_staff:
        return redirect("/")

# =========================================
# USUARIOS CLIENTE
# =========================================
    return redirect("/mis-unidades/")

    return render(
            request,
            "login.html",
            {
                "error": "Usuario o contraseña incorrectos",
            },
        )

    return render(request, "login.html")
# =========================================
# LOGOUT
# =========================================
def logout_view(request):
    logout(request)
    return redirect("/accounts/login/")


# =========================================
# HOME
# =========================================


@login_required
def home(request):

    # =========================================
    # GERENCIA / SUPERUSUARIO
    # =========================================
    if (
        request.user.is_superuser
        or request.user.groups.filter(
            name="GESTION_GERENCIA"
        ).exists()
    ):
        return redirect("/gerencia/")

# =========================================
# SUPERVISOR
# =========================================
    if request.user.groups.filter(
        name="GESTION_SUPERVISOR"
    ).exists():
        return redirect(
        "gestion_comercial:lista_cotizaciones"
    )
    # =========================================
    # TÉCNICO
    # =========================================
    if Tecnico.objects.filter(
        user=request.user,
        activo=True,
    ).exists():
        return redirect("/tecnico/")

    # =========================================
    # GESTIÓN COMERCIAL
    # =========================================
    if request.user.groups.filter(
    name="GESTION_COORDINADOR"
    ).exists():
        return redirect("escritorio_coordinador")

# =========================================
# FACTURACIÓN
# =========================================
    if request.user.groups.filter(
    name="GESTION_FACTURACION"
    ).exists():
        return redirect("gestion_comercial:panel")

# =========================================
# GESTIÓN COMERCIAL
# =========================================
    if es_usuario_gestion_comercial(request.user):
        return redirect("/gestion-comercial/")

    # =========================================
    # OTROS USUARIOS INTERNOS
    # =========================================
    if request.user.is_staff:
        return render(
            request,
            "menu_principal.html",
        )

    # =========================================
    # CLIENTES
    # =========================================
    return redirect("/mis-unidades/")

# =========================================
# PANEL DEL TÉCNICO
# =========================================
@login_required
def panel_tecnico(request):

    tecnico = Tecnico.objects.filter(
        user=request.user,
        activo=True,
    ).first()

    if not tecnico:
        return HttpResponseForbidden(
            "Este usuario no tiene un perfil de técnico activo."
        )

    hoy = timezone.localdate()

    servicios = (
        Emergencia.objects
        .filter(tecnico=tecnico)
        .select_related("cliente")
        .order_by("-fecha_llamada")
    )

    servicios_activos = servicios.exclude(
        estado="CERRADA"
    )

    actividades_hoy = ActividadTecnico.objects.filter(
        tecnico=tecnico,
        fecha=hoy,
    ).count()

    pendientes = servicios.filter(
        estado="PENDIENTE"
    ).count()

    en_proceso = servicios.filter(
        estado="EN_PROCESO"
    ).count()

    atendidos = servicios.filter(
        estado="ATENDIDA"
    ).count()

    preventivos = (
    ProgramacionMantenimientoPreventivo.objects
    .filter(
        tecnico=tecnico,
        estado__in=[
            "PROGRAMADO",
            "REPROGRAMADO",
            "EN_PROCESO",
            "DEVUELTO",
        ],
    )
    .select_related("cliente", "sector")
    .order_by(
        "fecha_programada",
        "hora_programada",
    )
)

    context = {
        "tecnico": tecnico,
        "servicios": servicios[:20],
        "pendientes": pendientes,
        "en_proceso": en_proceso,
        "atendidos": atendidos,
        "actividades_hoy": actividades_hoy,
        "preventivos": preventivos,
    }

    return render(
        request,
        "tecnico/panel.html",
        context,
    )


 # =========================================
# DETALLE DE SERVICIO PARA TÉCNICO
# =========================================
@login_required
def servicio_tecnico(request, servicio_id):

    tecnico = Tecnico.objects.filter(
        user=request.user,
        activo=True,
    ).first()

    if not tecnico:
        return HttpResponseForbidden(
            "Este usuario no tiene un perfil de técnico activo."
        )

    servicio = get_object_or_404(
        Emergencia.objects.select_related(
            "cliente",
            "tecnico",
        ),
        id=servicio_id,
    )

    if servicio.tecnico_id != tecnico.id:
        return HttpResponseForbidden(
            "No está autorizado para consultar este servicio."
        )

    eventos = servicio.eventos.all().order_by("fecha")

    actividades = (
        ActividadTecnico.objects
        .filter(
            tecnico=tecnico,
            servicio=servicio,
        )
        .prefetch_related(
            "accesorios_utilizados__accesorio",
        )
        .order_by(
            "-fecha",
            "-hora_llegada",
        )
    )

    return render(
        request,
        "tecnico/servicio.html",
        {
            "tecnico": tecnico,
            "servicio": servicio,
            "eventos": eventos,
            "actividades": actividades,
        },
    ) 
# =========================================
# INICIAR MANTENIMIENTO PREVENTIVO
# =========================================
@login_required
def iniciar_preventivo(request, programacion_id):

    tecnico = Tecnico.objects.filter(
        user=request.user,
        activo=True,
    ).first()

    if not tecnico:
        return HttpResponseForbidden(
            "Este usuario no tiene un perfil de técnico activo."
        )

    programacion = get_object_or_404(
        ProgramacionMantenimientoPreventivo.objects.select_related(
            "cliente",
            "tecnico",
            "actividad",
        ),
        id=programacion_id,
        tecnico=tecnico,
    )

    if programacion.estado in [
        "CANCELADO",
        "EJECUTADO",
        "PENDIENTE_REVISION",
        "PUBLICADO",
    ]:
        return HttpResponseForbidden(
            "Este mantenimiento preventivo ya no puede iniciarse."
        )

    # Si ya existe una actividad asociada, la reutilizamos.
    if programacion.actividad:

        actividad = programacion.actividad

        if not actividad.hora_llegada:
            actividad.hora_llegada = timezone.localtime().time()
            actividad.save(update_fields=["hora_llegada", "actualizado"])

        if programacion.estado in {"PROGRAMADO", "REPROGRAMADO", "DEVUELTO"}:
            estaba_devuelto = programacion.estado == "DEVUELTO"
            programacion.estado = "EN_PROCESO"
            programacion.save(update_fields=["estado", "actualizado"])
            if estaba_devuelto and hasattr(actividad, "preventivo"):
                actividad.preventivo.estado_revision = "BORRADOR"
                actividad.preventivo.save(update_fields=["estado_revision", "actualizado"])

    else:

        actividad = ActividadTecnico.objects.create(
            tecnico=tecnico,
            cliente=programacion.cliente,
            servicio=None,
            tipo_actividad="PREVENTIVO",
            fecha=timezone.localdate(),
            hora_llegada=timezone.localtime().time(),
            labor_realizada="Mantenimiento preventivo programado.",
            registrado_por=request.user,
        )

        programacion.actividad = actividad
        programacion.estado = "EN_PROCESO"

        programacion.save(
            update_fields=[
                "actividad",
                "estado",
                "actualizado",
            ]
        )

    preventivo, created = MantenimientoPreventivo.objects.get_or_create(
        actividad=actividad,
    )

    return redirect(
        "formulario_preventivo",
        programacion_id=programacion.id,
    ) 
# =========================================
# FORMULARIO MANTENIMIENTO PREVENTIVO
# =========================================
@login_required
def formulario_preventivo(request, programacion_id):

    # =====================================================
    # VALIDAR TÉCNICO
    # =====================================================
    tecnico = Tecnico.objects.filter(
        user=request.user,
        activo=True,
    ).first()

    if not tecnico:
        return HttpResponseForbidden(
            "Este usuario no tiene un perfil de técnico activo."
        )

    # =====================================================
    # VALIDAR PROGRAMACIÓN
    # El técnico solamente puede abrir sus propios preventivos.
    # =====================================================
    programacion = get_object_or_404(
        ProgramacionMantenimientoPreventivo.objects.select_related(
            "cliente",
            "tecnico",
            "actividad",
        ),
        id=programacion_id,
        tecnico=tecnico,
    )

    # Si todavía no ha sido iniciado, lo enviamos al proceso de inicio.
    if not programacion.actividad:
        return redirect(
            "iniciar_preventivo",
            programacion_id=programacion.id,
        )

    actividad = programacion.actividad

    if programacion.estado not in {"EN_PROCESO", "DEVUELTO"}:
        return redirect(
            "detalle_preventivo",
            programacion_id=programacion.id,
        )

    # =====================================================
    # OBTENER / CREAR EXPEDIENTE PREVENTIVO
    # =====================================================
    preventivo, created = MantenimientoPreventivo.objects.get_or_create(
        actividad=actividad,
    )

    # =====================================================
    # FORMULARIOS BASE
    # =====================================================
    form_general = MantenimientoPreventivoForm(
        instance=preventivo,
    )

    form_equipo = MedicionEquipoPreventivoForm()

    form_componente = RevisionComponentePreventivoForm()

    form_tanque = RevisionTanquePreventivoForm()
    errores_envio = []

    # Solo equipos pertenecientes a esta unidad.
    form_equipo.fields["equipo"].queryset = (
        EquipoUnidad.objects
        .filter(cliente=programacion.cliente)
        .order_by("tipo", "id")
    )

    # Solo tanques pertenecientes a esta unidad.
    form_tanque.fields["tanque"].queryset = (
        TanqueUnidad.objects
        .filter(cliente=programacion.cliente)
        .order_by("tipo_tanque", "id")
    )

    # =====================================================
    # GUARDAR SECCIONES
    # =====================================================
    if request.method == "POST":

        accion = request.POST.get("accion")

        # -------------------------------------------------
        # DATOS GENERALES
        # -------------------------------------------------
        if accion == "guardar_general":

            form_general = MantenimientoPreventivoForm(
                request.POST,
                request.FILES,
                instance=preventivo,
            )

            if form_general.is_valid():

                form_general.save()

                return redirect(
                    "formulario_preventivo",
                    programacion_id=programacion.id,
                )

        # -------------------------------------------------
        # MEDICIÓN DE EQUIPO
        # -------------------------------------------------
        elif accion == "agregar_equipo":

            form_equipo = MedicionEquipoPreventivoForm(
                request.POST,
            )

            form_equipo.fields["equipo"].queryset = (
                EquipoUnidad.objects
                .filter(cliente=programacion.cliente)
                .order_by("tipo", "id")
            )

            if form_equipo.is_valid():

                medicion = form_equipo.save(
                    commit=False
                )

                medicion.preventivo = preventivo

                # Guardamos una referencia histórica del nombre.
                if (
                    medicion.equipo
                    and not medicion.nombre_equipo
                ):
                    medicion.nombre_equipo = str(
                        medicion.equipo
                    )

                medicion.save()

                return redirect(
                    "formulario_preventivo",
                    programacion_id=programacion.id,
                )

        # -------------------------------------------------
        # COMPONENTE HIDRÁULICO
        # -------------------------------------------------
        elif accion == "agregar_componente":

            form_componente = RevisionComponentePreventivoForm(
                request.POST,
            )

            if form_componente.is_valid():

                componente = form_componente.save(
                    commit=False
                )

                componente.preventivo = preventivo
                componente.save()

                return redirect(
                    "formulario_preventivo",
                    programacion_id=programacion.id,
                )

        # -------------------------------------------------
        # TANQUE HIDRONEUMÁTICO
        # -------------------------------------------------
        elif accion == "agregar_tanque":

            form_tanque = RevisionTanquePreventivoForm(
                request.POST,
            )

            form_tanque.fields["tanque"].queryset = (
                TanqueUnidad.objects
                .filter(cliente=programacion.cliente)
                .order_by("tipo_tanque", "id")
            )

            if form_tanque.is_valid():

                revision_tanque = form_tanque.save(
                    commit=False
                )

                revision_tanque.preventivo = preventivo

                # Conservamos descripción histórica.
                if (
                    revision_tanque.tanque
                    and not revision_tanque.descripcion_tanque
                ):
                    revision_tanque.descripcion_tanque = (
                        revision_tanque.tanque.get_tipo_tanque_display()
                    )

                # Si el tanque ya tiene capacidad registrada,
                # la precargamos como referencia histórica.
                if (
                    revision_tanque.tanque
                    and not revision_tanque.capacidad
                ):
                    revision_tanque.capacidad = (
                        revision_tanque.tanque.capacidad or ""
                    )

                revision_tanque.save()

                return redirect(
                    "formulario_preventivo",
                    programacion_id=programacion.id,
                )
        # -------------------------------------------------
        # FINALIZAR MANTENIMIENTO PREVENTIVO
        # -------------------------------------------------
        elif accion == "finalizar":
            errores_envio = errores_para_enviar_preventivo(preventivo)

            if not errores_envio:
                with transaction.atomic():
                    if not actividad.hora_salida:
                        actividad.hora_salida = timezone.localtime().time()

                    actividad.enviado_en = timezone.now()
                    actividad.save(update_fields=[
                        "hora_salida",
                        "enviado_en",
                        "actualizado",
                    ])
                    asignar_comprobante(actividad)

                    preventivo.estado_revision = "PENDIENTE"
                    if preventivo.resultado_preventivo == "CON_NOVEDAD":
                        if preventivo.estado_anomalia == "NO_APLICA":
                            preventivo.estado_anomalia = "PENDIENTE_RESPUESTA"
                    else:
                        preventivo.estado_anomalia = "NO_APLICA"
                    preventivo.save(update_fields=[
                        "estado_revision",
                        "estado_anomalia",
                        "actualizado",
                    ])

                    programacion.estado = "PENDIENTE_REVISION"
                    programacion.save(update_fields=["estado", "actualizado"])

                return redirect(
                    "comprobante_actividad",
                    actividad_id=actividad.id,
                )
    # =====================================================
    # REGISTROS YA GUARDADOS
    # =====================================================
    mediciones = (
        preventivo.mediciones_equipos
        .select_related("equipo")
        .all()
    )

    componentes = (
        preventivo.componentes_revisados
        .all()
    )

    tanques = (
        preventivo.tanques_revisados
        .select_related("tanque")
        .all()
    )

    # =====================================================
    # MOSTRAR FORMULARIO
    # =====================================================
    return render(
        request,
        "tecnico/preventivo.html",
        {
            "tecnico": tecnico,
            "programacion": programacion,
            "actividad": actividad,
            "preventivo": preventivo,

            "form_general": form_general,
            "form_equipo": form_equipo,
            "form_componente": form_componente,
            "form_tanque": form_tanque,

            "mediciones": mediciones,
            "componentes": componentes,
            "tanques": tanques,
            "errores_envio": errores_envio,
        },
    )  

 # =========================================================
# HISTORIAL DE MANTENIMIENTOS PREVENTIVOS
# =========================================================
@login_required
def historial_preventivos(request):

    tecnico = Tecnico.objects.filter(
        user=request.user,
        activo=True,
    ).first()

    preventivos = (
        ProgramacionMantenimientoPreventivo.objects
        .filter(estado__in=[
            "PENDIENTE_REVISION",
            "DEVUELTO",
            "PUBLICADO",
            "EJECUTADO",
        ])
        .select_related(
            "cliente",
            "tecnico",
            "actividad",
        )
        .order_by(
            "-actualizado",
            "-fecha_programada",
        )
    )

    # Si el usuario es técnico, solamente ve sus propios mantenimientos.
    if tecnico:
        preventivos = preventivos.filter(
            tecnico=tecnico,
        )

    # El personal que no sea técnico debe ser interno.
    elif not (
        request.user.is_staff
        or request.user.is_superuser
        or puede_revisar_preventivos(request.user)
    ):
        return HttpResponseForbidden(
            "No está autorizado para consultar el historial de mantenimientos."
        )

    return render(
        request,
        "tecnico/historial_preventivos.html",
        {
            "preventivos": preventivos,
            "tecnico": tecnico,
        },
    )


# =========================================================
# DETALLE DE MANTENIMIENTO PREVENTIVO EJECUTADO
# =========================================================
@login_required
def detalle_preventivo(request, programacion_id):

    tecnico = Tecnico.objects.filter(
        user=request.user,
        activo=True,
    ).first()

    programacion = get_object_or_404(
        ProgramacionMantenimientoPreventivo.objects.select_related(
            "cliente",
            "tecnico",
            "actividad",
        ),
        id=programacion_id,
        estado__in=[
            "PENDIENTE_REVISION",
            "DEVUELTO",
            "PUBLICADO",
            "EJECUTADO",
        ],
    )

    # Técnico: solo puede consultar sus propios preventivos.
    if tecnico and programacion.tecnico_id != tecnico.id:
        return HttpResponseForbidden(
            "No está autorizado para consultar este mantenimiento."
        )

    # Usuario externo que no sea técnico ni personal interno.
    if not tecnico and not (
        request.user.is_staff
        or request.user.is_superuser
        or puede_revisar_preventivos(request.user)
    ):
        return HttpResponseForbidden(
            "No está autorizado para consultar este mantenimiento."
        )

    actividad = programacion.actividad

    preventivo = None
    mediciones = []
    componentes = []
    tanques = []

    if actividad:

        preventivo = MantenimientoPreventivo.objects.filter(
            actividad=actividad,
        ).first()

        if preventivo:

            mediciones = (
                preventivo.mediciones_equipos
                .select_related("equipo")
                .all()
            )

            componentes = (
                preventivo.componentes_revisados
                .all()
            )

            tanques = (
                preventivo.tanques_revisados
                .select_related("tanque")
                .all()
            )

    return render(
        request,
        "tecnico/detalle_preventivo.html",
        {
            "programacion": programacion,
            "actividad": actividad,
            "preventivo": preventivo,
            "mediciones": mediciones,
            "componentes": componentes,
            "tanques": tanques,
            "tecnico": tecnico,
            "puede_revisar": puede_revisar_preventivos(request.user),
            "seguimientos_anomalia": (
                preventivo.seguimientos_anomalia.select_related("usuario")
                if preventivo else []
            ),
        },
    )

 # =========================================================
# PDF MANTENIMIENTO PREVENTIVO
# =========================================================
@login_required
def preventivo_pdf(request, programacion_id):

    tecnico_usuario = Tecnico.objects.filter(
        user=request.user,
        activo=True,
    ).first()

    programacion = get_object_or_404(
        ProgramacionMantenimientoPreventivo.objects.select_related(
            "cliente",
            "tecnico",
            "actividad",
        ),
        id=programacion_id,
        estado__in=[
            "PENDIENTE_REVISION",
            "DEVUELTO",
            "PUBLICADO",
            "EJECUTADO",
        ],
    )

    # =====================================================
    # SEGURIDAD
    # =====================================================
    if tecnico_usuario:

        if programacion.tecnico_id != tecnico_usuario.id:
            return HttpResponseForbidden(
                "No está autorizado para generar este informe."
            )

    elif not (
        request.user.is_staff
        or request.user.is_superuser
        or puede_revisar_preventivos(request.user)
    ):

        return HttpResponseForbidden(
            "No está autorizado para generar este informe."
        )

    actividad = programacion.actividad

    preventivo = None

    if actividad:

        preventivo = MantenimientoPreventivo.objects.filter(
            actividad=actividad,
        ).first()

    mediciones = []
    componentes = []
    tanques = []

    if preventivo:

        mediciones = (
            preventivo.mediciones_equipos
            .select_related("equipo")
            .all()
        )

        componentes = (
            preventivo.componentes_revisados
            .all()
        )

        tanques = (
            preventivo.tanques_revisados
            .select_related("tanque")
            .all()
        )

    # =====================================================
    # RESPUESTA PDF
    # =====================================================
    response = HttpResponse(
        content_type="application/pdf"
    )

    nombre_pdf = (
        actividad.numero_informe
        if actividad and actividad.numero_informe
        else f"mantenimiento_preventivo_{programacion.id}"
    )
    response["Content-Disposition"] = f'attachment; filename="{nombre_pdf}.pdf"'

    pdf = canvas.Canvas(
        response,
        pagesize=letter,
    )
    pdf.setTitle(nombre_pdf)
    pdf.setAuthor("D&S Soluciones en Bombeo S.A.S.")
    pdf.setSubject("Informe de mantenimiento preventivo generado por SIGOB 7x24")

    width, height = letter

    margen = 38
    ancho_util = width - (margen * 2)

    azul = (0.0, 0.20, 0.40)
    azul_claro = (0.92, 0.96, 0.98)
    gris = (0.35, 0.40, 0.45)
    gris_claro = (0.92, 0.93, 0.94)
    verde = (0.10, 0.45, 0.25)

    logo = os.path.join(
        settings.BASE_DIR,
        "static",
        "img",
        "logo_dys.png",
    )

    pagina_actual = 1

    # =====================================================
    # UTILIDADES
    # =====================================================

    def limpiar(valor):
        if valor is None:
            return "-"
        valor = str(valor).strip()
        return valor if valor else "-"

    def encabezado():

        # Logo
        if os.path.exists(logo):

            pdf.drawImage(
                logo,
                margen,
                height - 70,
                width=58,
                height=40,
                preserveAspectRatio=True,
                mask="auto",
            )

        # Bloque corporativo
        pdf.setFillColorRGB(*azul)

        pdf.roundRect(
            102,
            height - 70,
            width - 140,
            40,
            5,
            fill=True,
            stroke=False,
        )

        pdf.setFillColorRGB(1, 1, 1)

        pdf.setFont(
            "Helvetica-Bold",
            10.5,
        )

        pdf.drawString(
            116,
            height - 47,
            "D&S SOLUCIONES EN BOMBEO S.A.S.",
        )

        pdf.setFont(
            "Helvetica",
            7.5,
        )

        pdf.drawString(
            116,
            height - 60,
            "SIGOB 7x24 - Sistema Integral de Gestión Operativa",
        )

        # Título
        pdf.setFillColorRGB(0, 0, 0)

        pdf.setFont(
            "Helvetica-Bold",
            12.5,
        )

        pdf.drawCentredString(
            width / 2,
            height - 88,
            "INFORME DE MANTENIMIENTO PREVENTIVO",
        )

        pdf.setStrokeColorRGB(*azul)

        pdf.setLineWidth(1)

        pdf.line(
            margen,
            height - 98,
            width - margen,
            height - 98,
        )

    def pie():

        pdf.setStrokeColorRGB(
            0.80,
            0.83,
            0.86,
        )

        pdf.line(
            margen,
            42,
            width - margen,
            42,
        )

        pdf.setFillColorRGB(*gris)

        pdf.setFont(
            "Helvetica",
            7.5,
        )

        pdf.drawString(
            margen,
            29,
            "SIGOB 7x24 - Informe generado automáticamente",
        )

        pdf.drawRightString(
            width - margen,
            29,
            "D&S Soluciones en Bombeo S.A.S.",
        )

        pdf.drawCentredString(
            width / 2,
            29,
            f"Página {pagina_actual}",
        )

        pdf.setFillColorRGB(0, 0, 0)

    def nueva_pagina():

        nonlocal pagina_actual

        pie()
        pdf.showPage()
        pagina_actual += 1
        encabezado()

        return height - 112

    def asegurar_espacio(y, necesario=55):

        if y - necesario < 58:
            y = nueva_pagina()

        return y

    def seccion(titulo, y):

        y = asegurar_espacio(
            y,
            34,
        )

        pdf.setFillColorRGB(*azul)

        pdf.roundRect(
            margen,
            y - 14,
            ancho_util,
            17,
            4,
            fill=True,
            stroke=False,
        )

        pdf.setFillColorRGB(1, 1, 1)

        pdf.setFont(
            "Helvetica-Bold",
            8.5,
        )

        pdf.drawString(
            margen + 9,
            y - 8,
            titulo,
        )

        pdf.setFillColorRGB(0, 0, 0)

        return y - 20

    def dividir_texto(
        texto,
        ancho,
        tamano=8.2,
        fuente="Helvetica",
    ):
        texto = limpiar(texto)
        lineas = []

        for parrafo in texto.splitlines() or [texto]:
            palabras = parrafo.split()
            if not palabras:
                lineas.append("-")
                continue

            linea = ""
            for palabra in palabras:
                prueba = f"{linea} {palabra}".strip()
                if pdf.stringWidth(prueba, fuente, tamano) <= ancho:
                    linea = prueba
                    continue

                if linea:
                    lineas.append(linea)
                    linea = ""

                fragmento = ""
                for caracter in palabra:
                    prueba_fragmento = fragmento + caracter
                    if (
                        fragmento
                        and pdf.stringWidth(
                            prueba_fragmento,
                            fuente,
                            tamano,
                        ) > ancho
                    ):
                        lineas.append(fragmento)
                        fragmento = caracter
                    else:
                        fragmento = prueba_fragmento
                linea = fragmento

            if linea:
                lineas.append(linea)

        return lineas or ["-"]

    def envolver_texto(
        texto,
        x,
        y,
        ancho,
        tamano=7.6,
        interlineado=9.2,
        fuente="Helvetica",
    ):

        pdf.setFont(
            fuente,
            tamano,
        )

        for linea in dividir_texto(texto, ancho, tamano, fuente):
            y = asegurar_espacio(
                y,
                interlineado,
            )

            pdf.drawString(
                x,
                y,
                linea,
            )

            y -= interlineado

        return y

    def campo_caja(
        label,
        valor,
        x,
        y,
        ancho,
        alto=34,
    ):

        pdf.setStrokeColorRGB(
            0.82,
            0.85,
            0.88,
        )

        pdf.setFillColorRGB(
            0.98,
            0.99,
            1,
        )

        pdf.roundRect(
            x,
            y - alto,
            ancho,
            alto,
            4,
            fill=True,
            stroke=True,
        )

        pdf.setFillColorRGB(*gris)

        pdf.setFont(
            "Helvetica-Bold",
            6.8,
        )

        pdf.drawString(
            x + 7,
            y - 10,
            label,
        )

        pdf.setFillColorRGB(0, 0, 0)

        pdf.setFont(
            "Helvetica-Bold",
            7.8,
        )

        lineas = dividir_texto(
            valor,
            ancho - 14,
            7.8,
            "Helvetica-Bold",
        )
        posicion_y = y - 22
        for linea in lineas:
            pdf.drawString(x + 7, posicion_y, linea)
            posicion_y -= 8.5

    def fila_campos(
        campos,
        y,
        anchos,
        separacion=10,
        alto_minimo=30,
    ):
        cantidades = [
            len(dividir_texto(valor, ancho - 14, 7.8, "Helvetica-Bold"))
            for (_, valor), ancho in zip(campos, anchos)
        ]
        alto = max(alto_minimo, 18 + (max(cantidades) * 8.5))
        y = asegurar_espacio(y, alto + 4)
        posicion_x = margen

        for (label, valor), ancho in zip(campos, anchos):
            campo_caja(label, valor, posicion_x, y, ancho, alto)
            posicion_x += ancho + separacion

        return y - alto - 4

    def encabezado_tabla(
        columnas,
        x,
        y,
        anchos,
    ):

        altura = 17

        pdf.setFillColorRGB(*azul_claro)

        pdf.rect(
            x,
            y - altura,
            sum(anchos),
            altura,
            fill=True,
            stroke=False,
        )

        pdf.setFillColorRGB(*azul)

        pdf.setFont(
            "Helvetica-Bold",
            6.8,
        )

        posicion = x

        for titulo, ancho in zip(
            columnas,
            anchos,
        ):

            pdf.drawString(
                posicion + 5,
                y - 11,
                titulo,
            )

            posicion += ancho

        pdf.setFillColorRGB(0, 0, 0)

        return y - altura

    def fila_tabla(
        valores,
        x,
        y,
        anchos,
        alto=22,
    ):

        lineas_celdas = [
            dividir_texto(valor, ancho - 10, 7, "Helvetica")
            for valor, ancho in zip(valores, anchos)
        ]
        alto = max(alto, 7 + (max(len(lineas) for lineas in lineas_celdas) * 8))
        y = asegurar_espacio(y, alto + 5)

        pdf.setStrokeColorRGB(
            0.85,
            0.87,
            0.90,
        )

        posicion = x

        for lineas, ancho in zip(
            lineas_celdas,
            anchos,
        ):

            pdf.rect(
                posicion,
                y - alto,
                ancho,
                alto,
                fill=False,
                stroke=True,
            )

            pdf.setFont(
                "Helvetica",
                7,
            )

            posicion_y = y - 10
            for linea in lineas:
                pdf.drawString(posicion + 5, posicion_y, linea)
                posicion_y -= 8

            posicion += ancho

        return y - alto

    # =====================================================
    # INICIO DOCUMENTO
    # =====================================================

    encabezado()

    y = height - 108

    # =====================================================
    # 1. INFORMACIÓN GENERAL
    # =====================================================

    y = seccion(
        "1. INFORMACIÓN GENERAL",
        y,
    )

    espacio = 8
    ancho_caja = (ancho_util - espacio) / 2

    ancho_unidad = 330
    y = fila_campos(
        [
            ("UNIDAD / CLIENTE", programacion.cliente.nombre),
            (
                "SECTOR",
                programacion.sector.nombre
                if programacion.sector
                else "Sin sector / por identificar",
            ),
        ],
        y,
        [ancho_unidad, ancho_util - ancho_unidad - espacio],
        separacion=espacio,
    )

    y = fila_campos(
        [
            (
                "NÚMERO DE INFORME",
                actividad.numero_informe if actividad else "Pendiente",
            ),
            (
                "FECHA",
                programacion.fecha_programada.strftime("%d/%m/%Y"),
            ),
            ("TÉCNICO", programacion.tecnico.nombre),
        ],
        y,
        [135, 82, ancho_util - 233],
        separacion=espacio,
    )

    hora_llegada = "-"

    hora_salida = "-"

    if actividad:

        if actividad.hora_llegada:
            hora_llegada = (
                actividad.hora_llegada.strftime(
                    "%H:%M"
                )
            )

        if actividad.hora_salida:
            hora_salida = (
                actividad.hora_salida.strftime(
                    "%H:%M"
                )
            )

    y = fila_campos(
        [
            ("LLEGADA", hora_llegada),
            ("SALIDA", hora_salida),
            (
                "RESULTADO",
                preventivo.get_resultado_preventivo_display()
                if preventivo and preventivo.resultado_preventivo
                else "Sin definir",
            ),
            (
                "REVISIÓN",
                preventivo.get_estado_revision_display()
                if preventivo
                else "Pendiente",
            ),
        ],
        y,
        [58, 58, 235, ancho_util - 375],
        separacion=espacio,
    )

    if programacion.observaciones:

        pdf.setFont(
            "Helvetica-Bold",
            7.5,
        )

        pdf.setFillColorRGB(*gris)

        pdf.drawString(
            margen,
            y,
            "OBSERVACIONES DE PROGRAMACIÓN",
        )

        pdf.setFillColorRGB(0, 0, 0)

        y -= 12

        y = envolver_texto(
            programacion.observaciones,
            margen + 5,
            y,
            ancho_util - 10,
        )

        y -= 6

    # =====================================================
    # 2. REVISIÓN GENERAL
    # =====================================================

    y = seccion(
        "2. REVISIÓN GENERAL",
        y,
    )

    revision_control = (
        preventivo.control_nivel
        if preventivo
        else "-"
    )

    revision_tablero = (
        preventivo.tablero_electrico
        if preventivo
        else "-"
    )

    novedades = (
        preventivo.novedades
        if preventivo
        else "-"
    )

    # Revisión general en columnas de altura variable para conservar el texto.
    ancho_revision = (ancho_util - 16) / 3

    campos_revision = [
        ("Control de nivel", revision_control),
        ("Tablero eléctrico", revision_tablero),
        ("Novedades", novedades),
    ]

    y = fila_campos(
        campos_revision,
        y,
        [ancho_revision, ancho_revision, ancho_revision],
        separacion=8,
        alto_minimo=34,
    )
    # =====================================================
    # 3. EQUIPOS
    # =====================================================

    y = seccion(
        "3. EQUIPOS REVISADOS",
        y,
    )

    if mediciones:

        anchos = [
            170,
            70,
            75,
            100,
            ancho_util - 415,
        ]

        y = encabezado_tabla(
            [
                "Equipo",
                "Voltaje",
                "Corriente",
                "Estado",
                "Observaciones",
            ],
            margen,
            y,
            anchos,
        )

        for medicion in mediciones:

            nombre = (
                medicion.nombre_equipo
                or str(medicion.equipo)
                or "Equipo"
            )

            y = fila_tabla(
                [
                    nombre,
                    medicion.voltaje_medido,
                    medicion.corriente_medida,
                    medicion.get_estado_display(),
                    medicion.observaciones,
                ],
                margen,
                y,
                anchos,
            )

        y -= 8

    else:

        pdf.setFont(
            "Helvetica-Oblique",
            8,
        )

        pdf.setFillColorRGB(*gris)

        pdf.drawString(
            margen + 5,
            y,
            "No se registraron mediciones de equipos.",
        )

        pdf.setFillColorRGB(0, 0, 0)

        y -= 18

    # =====================================================
    # 4. COMPONENTES HIDRÁULICOS
    # =====================================================

    y = seccion(
        "4. REVISIÓN DE COMPONENTES HIDRÁULICOS",
        y,
    )

    if componentes:

        anchos = [
            150,
            150,
            ancho_util - 300,
        ]

        y = encabezado_tabla(
            [
                "Componente",
                "Estado",
                "Observaciones",
            ],
            margen,
            y,
            anchos,
        )

        for componente in componentes:

            y = fila_tabla(
                [
                    componente.get_tipo_display(),
                    componente.get_estado_display(),
                    componente.observaciones,
                ],
                margen,
                y,
                anchos,
            )

        y -= 8

    else:

        pdf.setFont(
            "Helvetica-Oblique",
            8,
        )

        pdf.setFillColorRGB(*gris)

        pdf.drawString(
            margen + 5,
            y,
            "No se registraron componentes hidráulicos.",
        )

        pdf.setFillColorRGB(0, 0, 0)

        y -= 18

    # =====================================================
    # 5. TANQUES HIDRONEUMÁTICOS
    # =====================================================

    y = seccion(
        "5. TANQUES HIDRONEUMÁTICOS",
        y,
    )

    if tanques:

        anchos = [
            175,
            105,
            105,
            ancho_util - 385,
        ]

        y = encabezado_tabla(
            [
                "Tanque",
                "Capacidad",
                "Precarga",
                "Observaciones",
            ],
            margen,
            y,
            anchos,
        )

        for tanque in tanques:

            descripcion = (
                tanque.descripcion_tanque
                or str(tanque.tanque)
                or "Tanque"
            )

            y = fila_tabla(
                [
                    descripcion,
                    tanque.capacidad,
                    tanque.precarga_aire,
                    tanque.observaciones,
                ],
                margen,
                y,
                anchos,
            )

        y -= 8

    else:

        pdf.setFont(
            "Helvetica-Oblique",
            8,
        )

        pdf.setFillColorRGB(*gris)

        pdf.drawString(
            margen + 5,
            y,
            "No se registraron revisiones de tanques.",
        )

        pdf.setFillColorRGB(0, 0, 0)

        y -= 18

    # =====================================================
    # 6. REVISIÓN, AVISO Y VERIFICACIÓN
    # =====================================================

    y = asegurar_espacio(y, 145)
    y = seccion(
        "6. REVISIÓN, AVISO Y ESTADO DE LA CORRECCIÓN",
        y,
    )

    revisor = "Pendiente"
    fecha_revision = "Pendiente"
    cliente_informado = "No registrado"
    estado_anomalia = "Sin anomalías"
    if preventivo:
        if preventivo.revisado_por:
            revisor = preventivo.revisado_por.get_full_name() or preventivo.revisado_por.username
        if preventivo.revisado_en:
            fecha_revision = timezone.localtime(preventivo.revisado_en).strftime("%d/%m/%Y %H:%M")
        if preventivo.cliente_informado:
            cliente_informado = f"Sí - {preventivo.medio_notificacion or 'medio no indicado'}"
        estado_anomalia = preventivo.get_estado_anomalia_display()

    y = fila_campos(
        [
            ("REVISADO POR", revisor),
            ("FECHA DE REVISIÓN", fecha_revision),
        ],
        y,
        [ancho_caja, ancho_caja],
    )
    y = fila_campos(
        [
            ("CLIENTE / ADMINISTRACIÓN INFORMADO", cliente_informado),
            ("ESTADO DE LA CORRECCIÓN", estado_anomalia),
        ],
        y,
        [ancho_caja, ancho_caja],
    )

    if preventivo and preventivo.observaciones_revision:
        y = asegurar_espacio(y, 35)
        pdf.setFont("Helvetica-Bold", 7.5)
        pdf.setFillColorRGB(*gris)
        pdf.drawString(margen, y - 2, "OBSERVACIONES DE REVISIÓN")
        pdf.setFillColorRGB(0, 0, 0)
        y = envolver_texto(
            preventivo.observaciones_revision,
            margen + 5,
            y - 14,
            ancho_util - 10,
        )
        y -= 5

    if preventivo and preventivo.estado_revision == "PUBLICADO":
        # El QR, su título y su explicación deben permanecer juntos.
        y = asegurar_espacio(y, 68)
        url_verificacion = request.build_absolute_uri(
            reverse("verificar_preventivo", args=[preventivo.codigo_verificacion])
        )
        codigo_qr = QrCodeWidget(url_verificacion)
        x1, y1, x2, y2 = codigo_qr.getBounds()
        lado = 46
        dibujo_qr = Drawing(
            lado,
            lado,
            transform=[lado / (x2 - x1), 0, 0, lado / (y2 - y1), 0, 0],
        )
        dibujo_qr.add(codigo_qr)
        renderPDF.draw(dibujo_qr, pdf, margen, y - lado + 4)
        pdf.setFont("Helvetica-Bold", 7.5)
        pdf.setFillColorRGB(*azul)
        pdf.drawString(margen + 58, y - 9, "VERIFICACIÓN DEL INFORME")
        pdf.setFillColorRGB(0, 0, 0)
        y_texto = envolver_texto(
            "Escanee el código QR para comprobar que este informe fue aprobado y publicado en SIGOB.",
            margen + 58,
            y - 22,
            ancho_util - 65,
            tamano=7.5,
        )
        pdf.setFillColorRGB(*gris)
        pdf.setFont("Helvetica", 6.5)
        pdf.drawString(margen + 58, y_texto - 2, str(preventivo.codigo_verificacion))
        pdf.setFillColorRGB(0, 0, 0)
        y -= 56

    # =====================================================
    # 7. RECIBIDO DEL SERVICIO
    # =====================================================

    y = seccion(
        "7. RECIBIDO DEL SERVICIO",
        y,
    )

    recibe = "-"
    cargo = "-"

    if preventivo:
        recibe = preventivo.persona_recibe or "-"
        cargo = preventivo.cargo_recibe or "-"

    # -----------------------------------------------------
    # DATOS DE QUIEN RECIBE
    # -----------------------------------------------------

    campo_caja(
        "PERSONA QUE RECIBE",
        recibe,
        margen,
        y,
        ancho_caja,
        28,
    )

    campo_caja(
        "CARGO",
        cargo,
        margen + ancho_caja + espacio,
        y,
        ancho_caja,
        28,
    )

    # Bajamos para ubicar las firmas debajo de los datos.
    y -= 34

    # =====================================================
    # FIRMA / SOPORTE Y TÉCNICO RESPONSABLE
    # =====================================================

    alto_firma = 34

    pdf.setStrokeColorRGB(
        0.75,
        0.78,
        0.82,
    )

    # -----------------------------------------------------
    # FIRMA / SOPORTE DE RECIBIDO
    # -----------------------------------------------------

    pdf.roundRect(
        margen,
        y - alto_firma,
        ancho_caja,
        alto_firma,
        4,
        fill=False,
        stroke=True,
    )

    pdf.setFont(
        "Helvetica-Bold",
        7.2,
    )

    pdf.setFillColorRGB(*gris)

    pdf.drawString(
        margen + 7,
        y - 11,
        "FIRMA / SOPORTE DE RECIBIDO",
    )

    firma_dibujada = False

    if preventivo and preventivo.firma_recibido:

        try:
            ruta_firma = preventivo.firma_recibido.path

            if os.path.exists(ruta_firma):

                pdf.drawImage(
                    ruta_firma,
                    margen + 8,
                    y - 31,
                    width=115,
                    height=18,
                    preserveAspectRatio=True,
                    mask="auto",
                )

                firma_dibujada = True

        except Exception:
            firma_dibujada = False

    if not firma_dibujada:

        pdf.setFont(
            "Helvetica",
            7.5,
        )

        pdf.setFillColorRGB(*gris)

        pdf.drawString(
            margen + 9,
            y - 25,
            "Sin firma registrada",
        )

    # -----------------------------------------------------
    # TÉCNICO RESPONSABLE
    # -----------------------------------------------------

    x_tecnico = (
        margen
        + ancho_caja
        + espacio
    )

    pdf.roundRect(
        x_tecnico,
        y - alto_firma,
        ancho_caja,
        alto_firma,
        4,
        fill=False,
        stroke=True,
    )

    pdf.setFont(
        "Helvetica-Bold",
        7.2,
    )

    pdf.setFillColorRGB(*gris)

    pdf.drawString(
        x_tecnico + 7,
        y - 11,
        "TÉCNICO RESPONSABLE",
    )

    pdf.setFont(
        "Helvetica-Bold",
        8.5,
    )

    pdf.setFillColorRGB(0, 0, 0)

    pdf.drawString(
        x_tecnico + 9,
        y - 24,
        limpiar(
            programacion.tecnico.nombre
        ),
    )

    pdf.setFont(
        "Helvetica",
        7,
    )

    pdf.setFillColorRGB(*gris)

    pdf.drawString(
        x_tecnico + 9,
        y - 32,
        "D&S Soluciones en Bombeo S.A.S.",
    )
    # =====================================================
    # CIERRE
    # =====================================================

    pie()
    pdf.save()

    return response         
# =========================================
# VALIDAR ACCESO DEL CLIENTE
# =========================================
def usuario_puede_ver_cliente(user, cliente_id):

    """
        Comprueba si el usuario tiene autorización para consultar una unidad.
        El personal interno puede consultar cualquier cliente.
    """

    if user.is_staff:
        return True

    # =========================================
    # USUARIO DE ADMINISTRACION
    # =========================================
    usuario_administracion = UsuarioAdministracion.objects.filter(
        user=user,
        activo=True,
    ).select_related(
        "administracion",
    ).first()

    if usuario_administracion:
        return AdministracionUnidad.objects.filter(
            administracion=usuario_administracion.administracion,
            cliente_id=cliente_id,
            activo=True,
            fecha_fin__isnull=True,
            cliente__activo=True,
        ).exists()

    # =========================================
    # USUARIO CLIENTE TRADICIONAL
    # =========================================
    usuario_cliente = UsuarioCliente.objects.filter(
        user=user,
    ).first()

    if not usuario_cliente:
        return False

    # Unidad principal del usuario cliente.
    if usuario_cliente.cliente_id == cliente_id:
        return True

    # Unidades adicionales activas.
    return ClienteAsignado.objects.filter(
        usuario_cliente=usuario_cliente,
        cliente_id=cliente_id,
        activo=True,
    ).exists()
def usuario_puede_gestionar_servicio(user, servicio):
    """
    Personal interno puede gestionar servicios.
    Un técnico únicamente puede gestionar servicios asignados a él.
    """

    if not user.is_authenticated:
        return False

    # Si el usuario corresponde a un técnico,
    # solamente puede consultar sus propios servicios.
    tecnico = Tecnico.objects.filter(
        user=user,
        activo=True,
    ).first()

    if tecnico:
        return servicio.tecnico_id == tecnico.id

    # Gerencia / superusuario.
    if (
        user.is_superuser
        or user.groups.filter(
            name="GESTION_GERENCIA"
        ).exists()
    ):
        return True

    # Coordinador.
    if user.groups.filter(
        name="GESTION_COORDINADOR"
    ).exists():
        return True

    # Conservamos acceso del personal interno/staff existente.
    if user.is_staff:
        return True

    return False
# =========================================
# PORTAL DE UNIDADES DEL CLIENTE
# =========================================
@login_required
@login_required
def portal_unidades(request):

    # =========================================
    # PERSONAL INTERNO
    # =========================================
    if request.user.is_staff:
        clientes = Cliente.objects.filter(
            activo=True
        ).order_by("nombre")

        return render(
            request,
            "mis_unidades.html",
            {
                "clientes": clientes,
                "usuario_cliente": None,
            }
        )

    # =========================================
    # USUARIO DE ADMINISTRACION
    # =========================================
    usuario_administracion = UsuarioAdministracion.objects.filter(
        user=request.user,
        activo=True,
    ).select_related(
        "administracion",
    ).first()

    if usuario_administracion:

        clientes_ids = list(
            AdministracionUnidad.objects.filter(
                administracion=usuario_administracion.administracion,
                activo=True,
                fecha_fin__isnull=True,
                cliente__activo=True,
            ).values_list(
                "cliente_id",
                flat=True,
            )
        )

        clientes = Cliente.objects.filter(
            id__in=clientes_ids,
            activo=True,
        ).order_by("nombre")

        total_unidades = clientes.count()

        total_correctivos = Emergencia.objects.filter(
            cliente_id__in=clientes_ids,
            tipo_servicio="CORRECTIVO",
        ).count()

        total_preventivos = ProgramacionMantenimientoPreventivo.objects.filter(
            cliente_id__in=clientes_ids,
        ).count()

        total_cotizaciones = Cotizacion.objects.filter(
            cliente_id__in=clientes_ids,
        ).count()

        # Resumen individual de cada unidad
        resumen_unidades = []

        for cliente in clientes:

            resumen_unidades.append(
                {
                    "cliente": cliente,

                    "equipos": EquipoUnidad.objects.filter(
                        cliente=cliente
                    ).count(),

                    "correctivos": Emergencia.objects.filter(
                        cliente=cliente,
                        tipo_servicio="CORRECTIVO",
                    ).count(),

                    "preventivos": ProgramacionMantenimientoPreventivo.objects.filter(
                        cliente=cliente
                    ).count(),

                    "cotizaciones": Cotizacion.objects.filter(
                        cliente=cliente
                    ).count(),
                }
            )

        return render(
            request,
            "mis_unidades.html",
            {
                "clientes": clientes,
                "resumen_unidades": resumen_unidades,
                "usuario_cliente": None,
                "usuario_administracion": usuario_administracion,
                "administracion": usuario_administracion.administracion,
                "total_unidades": total_unidades,
                "total_correctivos": total_correctivos,
                "total_preventivos": total_preventivos,
                "total_cotizaciones": total_cotizaciones,
            }
        )

    # =========================================
    # USUARIO CLIENTE TRADICIONAL
    # =========================================
    usuario_cliente = UsuarioCliente.objects.filter(
        user=request.user,
    ).first()

    if not usuario_cliente:
        return HttpResponseForbidden(
            "Este usuario no tiene unidades asignadas."
        )

    clientes_ids = set()

    if usuario_cliente.cliente_id:
        clientes_ids.add(
            usuario_cliente.cliente_id
        )

    clientes_asignados = ClienteAsignado.objects.filter(
        usuario_cliente=usuario_cliente,
        activo=True,
    ).values_list(
        "cliente_id",
        flat=True,
    )

    clientes_ids.update(
        clientes_asignados
    )

    clientes = Cliente.objects.filter(
        id__in=clientes_ids,
        activo=True,
    ).order_by("nombre")

    return render(
        request,
        "mis_unidades.html",
        {
            "clientes": clientes,
            "usuario_cliente": usuario_cliente,
        }
    )
    
    
# =========================================
# NUEVA LLAMADA
# =========================================
@login_required
def nueva_llamada(request):

    if not es_coordinador_operativo(request.user):
        return HttpResponseForbidden(
            "No está autorizado para registrar llamadas."
        )

    if request.method == "POST":
        form = NuevaLlamadaForm(request.POST)

        if form.is_valid():
            servicio = form.save()

            registrar_evento(
                servicio,
                "Llamada recibida",
                "Se registró una nueva llamada del cliente.",
                request.user.username,
                "📞",
            )

            return redirect("/centro-operaciones/")
    else:
        form = NuevaLlamadaForm()

    return render(
        request,
        "nueva_llamada.html",
        {"form": form},
    )
@login_required
def levantamiento_equipo(request):

    cliente_id = request.GET.get("cliente", "").strip()
    torre_actual = request.GET.get("torre", "").strip()
    guardado = request.GET.get("guardado") == "1"

    if request.method == "POST":
        form = LevantamientoEquipoForm(request.POST)

        if form.is_valid():
            equipo = form.save()
            accion = request.POST.get("accion", "misma_torre")

            if accion == "finalizar":
                return redirect(
                    "hoja_vida",
                    cliente_id=equipo.cliente_id,
                )

            parametros = [
                f"cliente={equipo.cliente_id}",
                "guardado=1",
            ]

            if accion == "misma_torre" and equipo.torre:
                from urllib.parse import quote_plus
                parametros.append(
                    f"torre={quote_plus(equipo.torre)}"
                )

            return redirect(
                request.path + "?" + "&".join(parametros)
            )

    else:
        inicial = {
            "ultima_revision": timezone.now().date(),
        }
        if cliente_id:
            inicial["cliente"] = cliente_id
        if torre_actual:
            inicial["torre"] = torre_actual
        form = LevantamientoEquipoForm(initial=inicial)

    cliente_seleccionado = None
    equipos_registrados = EquipoUnidad.objects.none()

    if cliente_id:
        cliente_seleccionado = Cliente.objects.filter(
            id=cliente_id
        ).first()

        if cliente_seleccionado:
            equipos_registrados = EquipoUnidad.objects.filter(
                cliente=cliente_seleccionado
            )
            if torre_actual:
                equipos_registrados = equipos_registrados.filter(
                    torre__iexact=torre_actual
                )
            equipos_registrados = equipos_registrados.order_by(
                "torre",
                "tipo",
                "id",
            )

    return render(
        request,
        "levantamiento_equipo.html",
        {
            "form": form,
            "cliente_seleccionado": cliente_seleccionado,
            "torre_actual": torre_actual,
            "equipos_registrados": equipos_registrados,
            "guardado": guardado,
        }
    )

# =========================================
# DASHBOARD GERENCIAL
# =========================================
@login_required
def demo_sigob(request):
    return render(request, "demo_sigob.html")

@login_required
def dashboard(request):

    # =========================================
    # SEGURIDAD - SOLO GERENCIA
    # =========================================
    es_gerencia = (
        request.user.is_superuser
        or request.user.groups.filter(
            name="GESTION_GERENCIA"
        ).exists()
    )

    if not es_gerencia:
        return HttpResponseForbidden(
            "No está autorizado para acceder al Panel de Gerencia."
        )

        # =====================================================
    # INDICADORES OPERATIVOS 7X24
    # =====================================================

    total_servicios = Emergencia.objects.count()

    pendientes = Emergencia.objects.filter(
        estado="PENDIENTE"
    ).count()

    atendidas = Emergencia.objects.filter(
        estado="ATENDIDA"
    ).count()

    clientes = Cliente.objects.filter(
        activo=True
    ).count()

    emergencias = Emergencia.objects.filter(
        tipo_servicio="EMERGENCIA"
    ).count()

    correctivos = Emergencia.objects.filter(
        tipo_servicio="CORRECTIVO"
    ).count()

    garantias = Emergencia.objects.filter(
        tipo_servicio="GARANTIA"
    ).count()

    revisiones = Emergencia.objects.filter(
        tipo_servicio="REVISION"
    ).count()
        # =====================================================
    # INDICADORES DE FACTURACIÓN
    # =====================================================

    hoy = timezone.localdate()

    facturadas = Liquidacion.objects.filter(
        estado="FACTURADA",
        fecha_facturacion__isnull=False,
    )

    facturado_mes = (
        facturadas.filter(
            fecha_facturacion__year=hoy.year,
            fecha_facturacion__month=hoy.month,
        ).aggregate(
            total=Sum("valor_total")
        )["total"]
        or 0
    )

    facturado_anio = (
        facturadas.filter(
            fecha_facturacion__year=hoy.year,
        ).aggregate(
            total=Sum("valor_total")
        )["total"]
        or 0
    )

    pendiente_facturar = (
        Liquidacion.objects.filter(
            estado="LISTA_FACTURAR"
        ).aggregate(
            total=Sum("valor_total")
        )["total"]
        or 0
    )

    facturas_mes = facturadas.filter(
        fecha_facturacion__year=hoy.year,
        fecha_facturacion__month=hoy.month,
    ).count()
    # =====================================================
        # =====================================================
    # GRÁFICA 1: SERVICIOS 7X24 ÚLTIMOS 12 MESES
    # =====================================================

    hoy = timezone.now().date()

    inicio = (
        hoy.replace(day=1)
        - timedelta(days=365)
    ).replace(day=1)

    qs_servicios = (
        Emergencia.objects
        .filter(
            fecha_llamada__date__gte=inicio
        )
        .annotate(
            mes=TruncMonth("fecha_llamada")
        )
        .values("mes")
        .annotate(
            total=Count("id")
        )
        .order_by("mes")
    )

    servicios_dict = {
        x["mes"].strftime("%Y-%m"): x["total"]
        for x in qs_servicios
    }

    labels_servicios = []
    data_servicios = []

    anio = hoy.year
    mes = hoy.month

    for i in range(11, -1, -1):

        m = mes - i
        y = anio

        while m <= 0:
            m += 12
            y -= 1

        key = f"{y:04d}-{m:02d}"

        labels_servicios.append(key)

        data_servicios.append(
            servicios_dict.get(key, 0)
        )
    # =====================================================
    # GRÁFICA 2: ESTADO GENERAL DE EQUIPOS
    # =====================================================
    equipos_operativos = EquipoUnidad.objects.filter(
        estado="OPERATIVO"
    ).count()

    equipos_reparacion = EquipoUnidad.objects.filter(
        estado="EN_REPARACION"
    ).count()

    equipos_fuera = EquipoUnidad.objects.filter(
        estado="FUERA_SERVICIO"
    ).count()

    labels_equipos = [
        "Operativos",
        "En reparación",
        "Fuera de servicio",
    ]

    data_equipos = [
        equipos_operativos,
        equipos_reparacion,
        equipos_fuera,
    ]

    # =====================================================
    # GRÁFICA 3: COTIZACIONES POR ESTADO
    # =====================================================
    estados_cotizaciones = [
        "BORRADOR",
        "ELABORADA",
        "ENVIADA",
        "APROBADA",
        "RECHAZADA",
        "ANULADA",
    ]

    labels_cotizaciones = [
        "Borrador",
        "Elaborada",
        "Enviada",
        "Aprobada",
        "Rechazada",
        "Anulada",
    ]

    data_cotizaciones = [
        Cotizacion.objects.filter(
            estado=estado
        ).count()
        for estado in estados_cotizaciones
    ]
        # =====================================================
    # GRÁFICA 4: FACTURACIÓN ÚLTIMOS 12 MESES
    # =====================================================

    qs_facturacion = (
        facturadas
        .filter(
            fecha_facturacion__date__gte=inicio
        )
        .annotate(
            mes=TruncMonth("fecha_facturacion")
        )
        .values("mes")
        .annotate(
            total=Sum("valor_total")
        )
        .order_by("mes")
    )

    facturacion_dict = {
        x["mes"].strftime("%Y-%m"): float(x["total"] or 0)
        for x in qs_facturacion
    }

    labels_facturacion = []
    data_facturacion = []

    for i in range(11, -1, -1):
        m = hoy.month - i
        y = hoy.year

        while m <= 0:
            m += 12
            y -= 1

        key = f"{y:04d}-{m:02d}"

        labels_facturacion.append(key)
        data_facturacion.append(
            facturacion_dict.get(key, 0)
        )
    context = {
        "total_servicios": total_servicios,
    "pendientes": pendientes,
    "atendidas": atendidas,
    "clientes": clientes,

    "emergencias": emergencias,
    "correctivos": correctivos,
    "garantias": garantias,
    "revisiones": revisiones,

    "labels_servicios": labels_servicios,
    "data_servicios": data_servicios,

    "labels_equipos": labels_equipos,
    "data_equipos": data_equipos,

    "labels_cotizaciones": labels_cotizaciones,
    "data_cotizaciones": data_cotizaciones,

    "facturado_mes": facturado_mes,
    "facturado_anio": facturado_anio,
    "pendiente_facturar": pendiente_facturar,
    "facturas_mes": facturas_mes,

    "labels_facturacion": labels_facturacion,
    "data_facturacion": data_facturacion,
    }

    return render(
        request,
        "dashboard.html",
        context,
    )

# =========================================
# CENTRO DE OPERACIONES
# =========================================
@login_required
def centro_operaciones(request):

    if not es_coordinador_operativo(request.user):
        return HttpResponseForbidden(
            "No está autorizado para acceder al centro de operaciones."
        )

    ahora = timezone.now()
    hoy = ahora.date()
    ayer = hoy - timedelta(days=1)

    inicio_noche = timezone.datetime.combine(
        ayer,
        timezone.datetime.min.time(),
    ).replace(hour=17, minute=0)

    fin_noche = timezone.datetime.combine(
        hoy,
        timezone.datetime.min.time(),
    ).replace(hour=7, minute=0)

    inicio_noche = timezone.make_aware(inicio_noche)
    fin_noche = timezone.make_aware(fin_noche)

    servicios = Emergencia.objects.select_related(
        "cliente",
        "tecnico",
    ).order_by("-fecha_llamada")

    sectores_filtro = sectores_en(servicios)
    filtro_sector = request.GET.get("sector", "").strip()
    servicios = filtrar_sector(servicios, filtro_sector).select_related("sector")

    emergencias_activas = servicios.filter(
        tipo_servicio="EMERGENCIA",
    ).exclude(
        estado="CERRADA",
    )

    correctivos_pendientes = servicios.filter(
        tipo_servicio="CORRECTIVO",
    ).exclude(
        estado="CERRADA",
    )

    tecnicos_activos = Tecnico.objects.filter(activo=True)

    tecnicos_ocupados_ids = servicios.filter(
        estado__in=["PENDIENTE", "EN_PROCESO"],
        tecnico__isnull=False,
    ).values_list(
        "tecnico_id",
        flat=True,
    ).distinct()

    tecnicos_ocupados = tecnicos_activos.filter(
        id__in=tecnicos_ocupados_ids,
    ).count()

    tecnicos_disponibles = tecnicos_activos.exclude(
        id__in=tecnicos_ocupados_ids,
    ).count()

    servicios_noche = servicios.filter(
        fecha_llamada__gte=inicio_noche,
        fecha_llamada__lte=fin_noche,
    )

    bandeja_cotizacion = servicios.filter(
        requiere_cotizacion=True,
    ).exclude(
        estado="CERRADA",
    )

    bandeja_regreso = servicios.filter(
        requiere_regreso=True,
    ).exclude(
        estado="CERRADA",
    )

    bandeja_llamar_cliente = servicios.filter(
        estado="ATENDIDA",
        cliente_conforme__isnull=True,
    )

    bandeja_no_conforme = servicios.filter(
        cliente_conforme=False,
    ).exclude(
        estado="CERRADA",
    )

    clientes_esperando = servicios.filter(
        estado__in=["PENDIENTE", "ATENDIDA"],
    ).values(
        "cliente_id",
    ).distinct().count()

    context = {
        "sectores_filtro": sectores_filtro, "filtro_sector": filtro_sector,
        # Indicadores ejecutivos
        "emergencias_activas": emergencias_activas.count(),
        "correctivos_pendientes": correctivos_pendientes.count(),
        "tecnicos_disponibles": tecnicos_disponibles,
        "tecnicos_ocupados": tecnicos_ocupados,
        "clientes_esperando": clientes_esperando,

        # Indicadores generales
        "total": servicios.count(),
        "pendientes": servicios.filter(estado="PENDIENTE").count(),
        "en_proceso": servicios.filter(estado="EN_PROCESO").count(),
        "atendidas": servicios.filter(estado="ATENDIDA").count(),
        "cerradas": servicios.filter(estado="CERRADA").count(),
        "ultimos_servicios": servicios[:20],

        # Turno nocturno
        "total_noche": servicios_noche.count(),
        "solucionados_noche": servicios_noche.filter(
            estado="ATENDIDA",
        ).count(),
        "pendientes_noche": servicios_noche.filter(
            estado="PENDIENTE",
        ).count(),
        "cerrados_noche": servicios_noche.filter(
            estado="CERRADA",
        ).count(),
        "en_proceso_noche": servicios_noche.filter(
            estado="EN_PROCESO",
        ).count(),
        "inicio_noche": inicio_noche,
        "fin_noche": fin_noche,

        # Bandejas del coordinador
        "bandeja_cotizacion": bandeja_cotizacion[:5],
        "bandeja_regreso": bandeja_regreso[:5],
        "bandeja_llamar_cliente": bandeja_llamar_cliente[:5],
        "bandeja_no_conforme": bandeja_no_conforme[:5],

        "clientes_inconformes": bandeja_no_conforme.count(),
        "pendiente_repuesto": servicios.filter(
            resultado_servicio="PENDIENTE_REPUESTO",
        ).exclude(
            estado="CERRADA",
        ).count(),
        "cotizaciones": bandeja_cotizacion.count(),
        "regresos": bandeja_regreso.count(),

        "total_bandeja": (
            bandeja_cotizacion.count()
            + bandeja_regreso.count()
            + bandeja_llamar_cliente.count()
            + bandeja_no_conforme.count()
        ),
    }

    return render(request, "centro_operaciones.html", context)


# =========================================
# ESCRITORIO DEL COORDINADOR
# =========================================
@login_required
def escritorio_coordinador(request):

    if not es_coordinador_operativo(request.user):
        return HttpResponseForbidden(
            "No está autorizado para acceder al escritorio del coordinador."
        )

    ahora = timezone.now()
    hoy = ahora.date()
    ayer = hoy - timedelta(days=1)

    inicio_noche = timezone.datetime.combine(
        ayer,
        timezone.datetime.min.time(),
    ).replace(hour=17, minute=0)

    fin_noche = timezone.datetime.combine(
        hoy,
        timezone.datetime.min.time(),
    ).replace(hour=7, minute=0)

    inicio_noche = timezone.make_aware(inicio_noche)
    fin_noche = timezone.make_aware(fin_noche)

    servicios_noche = Emergencia.objects.filter(
        fecha_llamada__gte=inicio_noche,
        fecha_llamada__lte=fin_noche,
    )

    total_noche = servicios_noche.count()
    solucionados = servicios_noche.filter(estado="ATENDIDA").count()
    pendientes = servicios_noche.filter(estado="PENDIENTE").count()
    en_proceso = servicios_noche.filter(estado="EN_PROCESO").count()
    cerrados = servicios_noche.filter(estado="CERRADA").count()

    servicios_revision = servicios_noche.order_by("-fecha_llamada")
        # =========================================
    # SERVICIOS PENDIENTES DE ASIGNACIÓN
    # =========================================
    servicios_sin_asignar = (
        Emergencia.objects
        .filter(tecnico__isnull=True)
        .exclude(estado="CERRADA")
        .order_by("-fecha_llamada")
    )

    context = {
        "total_noche": total_noche,
        "solucionados": solucionados,
        "pendientes": pendientes,
        "en_proceso": en_proceso,
        "cerrados": cerrados,
        "servicios_revision": servicios_revision,
        "inicio_noche": inicio_noche,
        "fin_noche": fin_noche,
        "servicios_sin_asignar": servicios_sin_asignar,
    }

    return render(request, "escritorio_coordinador.html", context)
# =========================================
# BITÁCORA OPERATIVA
# =========================================

@login_required
@require_GET
@acceso_bitacora()
def lista_bitacora(request):

    registros = (
        registros_visibles(request.user)
        .select_related(
            "cliente",
            "tecnico",
            "servicio",
            "actividad",
            "responsable",
            "creado_por",
        )
        .prefetch_related(
            "actividad__accesorios_utilizados__accesorio",
        )
        .all()
    )

    registros = registros.select_related("origen_keep").annotate(
        fecha_consulta=Coalesce("origen_keep__fecha_original", TruncDate("creado"), output_field=DateField())
    )
    sectores_filtro = sectores_en(registros)
    filtro_sector = request.GET.get("sector", "").strip()
    registros = filtrar_sector(registros, filtro_sector).select_related("sector")

    estado = request.GET.get("estado", "").strip()
    tipo = request.GET.get("tipo", "").strip()
    prioridad = request.GET.get("prioridad", "").strip()
    buscar = request.GET.get("buscar", "").strip()

    if estado:
        registros = registros.filter(
            estado=estado
        )

    if tipo:
        registros = registros.filter(
            tipo=tipo
        )

    if prioridad:
        registros = registros.filter(
            prioridad=prioridad
        )

    if buscar:
        registros = registros.filter(
            Q(titulo__icontains=buscar)
            | Q(descripcion__icontains=buscar)
            | Q(accion_pendiente__icontains=buscar)
            | Q(cliente__nombre__icontains=buscar)
            | Q(tecnico__nombre__icontains=buscar)
        )

    ahora = timezone.now()
    hoy = timezone.localdate()
    fecha_desde_texto = request.GET.get("fecha_desde", "").strip()
    fecha_hasta_texto = request.GET.get("fecha_hasta", "").strip()
    periodo = request.GET.get("periodo", "")
    if periodo in {"hoy", "ayer"}:
        dia = hoy if periodo == "hoy" else hoy - timedelta(days=1)
        fecha_desde_texto = fecha_hasta_texto = dia.isoformat()

    fechas = {}
    errores_fechas = []
    for nombre, texto, etiqueta in (
        ("desde", fecha_desde_texto, "Desde"),
        ("hasta", fecha_hasta_texto, "Hasta"),
    ):
        fechas[nombre] = None
        if texto:
            try:
                fecha = date.fromisoformat(texto)
                if fecha.isoformat() != texto:
                    raise ValueError
                fechas[nombre] = fecha
            except ValueError:
                errores_fechas.append(
                    f"La fecha de {etiqueta} no es válida. Use el calendario o el formato AAAA-MM-DD."
                )

    desde = fechas["desde"]
    hasta = fechas["hasta"]
    if desde and hasta and desde > hasta:
        errores_fechas.append("La fecha Desde debe ser anterior o igual a Hasta.")

    if errores_fechas:
        registros = registros.none()
    else:
        # Keep conserva la fecha del título; las notas normales usan la fecha de registro.
        if desde:
            registros = registros.filter(fecha_consulta__gte=desde)
        if hasta:
            registros = registros.filter(fecha_consulta__lte=hasta)
        if desde or hasta:
            registros = registros.order_by("-fecha_consulta", "-creado", "-pk")

    total = registros.count()

    pendientes = registros.filter(
        estado="PENDIENTE",
    ).count()

    seguimiento = registros.filter(
        estado="EN_SEGUIMIENTO",
    ).count()

    # =========================================
    # COMPROMISOS VENCIDOS
    # =========================================

    vencidas = registros.filter(
        estado__in=[
            "PENDIENTE",
            "EN_SEGUIMIENTO",
        ],
        fecha_compromiso__lt=ahora,
    ).count()

    # =========================================
    # COMPROMISOS DE HOY
    # =========================================

    compromisos_hoy = registros.filter(
        estado__in=[
            "PENDIENTE",
            "EN_SEGUIMIENTO",
        ],
        fecha_compromiso__date=hoy,
    ).count()

    # =========================================
    # PRÓXIMOS COMPROMISOS
    # =========================================

    proximos_compromisos = registros.filter(
        estado__in=[
            "PENDIENTE",
            "EN_SEGUIMIENTO",
        ],
        fecha_compromiso__date__gt=hoy,
    ).count()

    # =========================================
    # REUNIONES DE HOY
    # =========================================

    reuniones_hoy = registros.filter(
        tipo="REUNION",
        fecha_compromiso__date=hoy,
    ).exclude(
        estado="CERRADO",
    ).count()

    return render(
        request,
        "bitacora/lista.html",
        {
            "puede_gestionar_bitacora": puede_gestionar_bitacora(request.user),
            "registros": registros,
            "sectores_filtro": sectores_filtro, "filtro_sector": filtro_sector,
            "total": total,
            "pendientes": pendientes,
            "seguimiento": seguimiento,
            "vencidas": vencidas,
            "compromisos_hoy": compromisos_hoy,
            "proximos_compromisos": proximos_compromisos,
            "reuniones_hoy": reuniones_hoy,

            "estados": BitacoraOperativa.ESTADO,
            "tipos": BitacoraOperativa.TIPO,
            "prioridades": BitacoraOperativa.PRIORIDAD,

            "filtro_estado": estado,
            "filtro_tipo": tipo,
            "filtro_prioridad": prioridad,
            "buscar": buscar,
            "filtro_fecha_desde": fecha_desde_texto,
            "filtro_fecha_hasta": fecha_hasta_texto,
            "fecha_desde": desde,
            "fecha_hasta": hasta,
            "es_vista_diaria": bool(desde and hasta and desde == hasta),
            "errores_fechas": errores_fechas,
        },
        status=400 if errores_fechas else 200,
    )

@login_required
@require_http_methods(["GET", "POST"])
@acceso_bitacora(escritura=True)
def nueva_bitacora(request):

    if request.method == "POST":
        form = BitacoraOperativaForm(request.POST)

        if form.is_valid():
            registro = form.save(commit=False)
            registro.creado_por = request.user

            if not registro.responsable:
                registro.responsable = request.user

            registro.save()

            return redirect("lista_bitacora")

    else:
        form = BitacoraOperativaForm(
            initial={
                "responsable": request.user,
                "prioridad": "MEDIA",
                "estado": "PENDIENTE",
            }
        )

    return render(
        request,
        "bitacora/formulario.html",
        {
            "form": form,
            "titulo_pagina": "Nueva novedad",
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
@acceso_bitacora(escritura=True)
def editar_bitacora(request, bitacora_id):
    if request.method == "POST":
        with transaction.atomic():
            registro = get_object_or_404(BitacoraOperativa.objects.select_for_update(), pk=bitacora_id)
            anteriores = capturar_campos(registro)
            form = BitacoraOperativaForm(request.POST, instance=registro)
            if form.is_valid():
                form.save()
                registrar_edicion(anteriores, registro, request.user)
                return redirect("lista_bitacora")
    else:
        registro = get_object_or_404(BitacoraOperativa, pk=bitacora_id)
        form = BitacoraOperativaForm(instance=registro)
    return render(request, "bitacora/formulario.html", {
        "form": form, "registro": registro, "titulo_pagina": "Editar novedad",
    })

# =========================================
# REMISIONES DE TÉCNICOS
# =========================================

@login_required
def lista_remisiones(request):

    if not puede_gestionar_remisiones(request.user):
        return HttpResponseForbidden(
            "No está autorizado para administrar remisiones."
        )

    remisiones = (
        RemisionTecnico.objects
        .select_related(
            "tecnico",
            "cliente",
            "servicio",
            "entregado_por",
        )
        .prefetch_related("detalles")
        .order_by("-fecha", "-id")
    )

    buscar = request.GET.get("buscar", "").strip()
    estado = request.GET.get("estado", "").strip()

    if buscar:
        remisiones = remisiones.filter(
            Q(numero_remision__icontains=buscar)
            | Q(tecnico__nombre__icontains=buscar)
            | Q(cliente__nombre__icontains=buscar)
        )

    if estado == "PENDIENTE":
        remisiones = [
            remision
            for remision in remisiones
            if not remision.esta_conciliada
        ]

    elif estado == "CONCILIADA":
        remisiones = [
            remision
            for remision in remisiones
            if remision.esta_conciliada
        ]

    return render(
        request,
        "remisiones/lista.html",
        {
            "remisiones": remisiones,
            "buscar": buscar,
            "filtro_estado": estado,
        },
    )


@login_required
def nueva_remision(request):

    if not puede_gestionar_remisiones(request.user):
        return HttpResponseForbidden(
            "No está autorizado para registrar remisiones."
        )

    if request.method == "POST":

        form = RemisionTecnicoForm(request.POST)
        formset = DetalleRemisionFormSet(request.POST)

        if form.is_valid() and formset.is_valid():

            remision = form.save(commit=False)
            remision.entregado_por = request.user
            remision.estado = "PENDIENTE"
            remision.save()

            formset.instance = remision
            formset.save()

            return redirect("lista_remisiones")

    else:

        form = RemisionTecnicoForm(
            initial={
                "fecha": timezone.localtime(),
            }
        )

        formset = DetalleRemisionFormSet()

    return render(
        request,
        "remisiones/formulario.html",
        {
            "form": form,
            "formset": formset,
            "titulo_pagina": "Nueva remisión",
        },
    )


@login_required
def conciliar_remision(request, remision_id):

    if not puede_gestionar_remisiones(request.user):
        return HttpResponseForbidden(
            "No está autorizado para conciliar remisiones."
        )

    remision = get_object_or_404(
        RemisionTecnico,
        id=remision_id,
    )

    if request.method == "POST":

        formset = DetalleConciliacionFormSet(
            request.POST,
            instance=remision,
        )

        if formset.is_valid():

            formset.save()

            # Volvemos a leer la remisión desde la base de datos
            # para validar con los valores realmente guardados.
            remision.refresh_from_db()

            if remision.esta_conciliada:
                remision.estado = "CONCILIADA"
            else:
                remision.estado = "PENDIENTE"

            remision.save(
                update_fields=[
                    "estado",
                    "actualizado",
                ]
            )

            return redirect("lista_remisiones")

    else:

        formset = DetalleConciliacionFormSet(
            instance=remision,
        )

    return render(
        request,
        "remisiones/conciliar.html",
        {
            "remision": remision,
            "formset": formset,
        },
    )
# =========================================
# DASHBOARD CLIENTE
# =========================================
@login_required
def dashboard_cliente(request, cliente_id):
    if not usuario_puede_ver_cliente(request.user, cliente_id):
        return HttpResponseForbidden(
            "No está autorizado para consultar esta unidad."
        )

    cliente = get_object_or_404(
        Cliente,
        id=cliente_id,
        activo=True,
    )
    equipos = EquipoUnidad.objects.filter(cliente=cliente)

    total_equipos = equipos.count()
    operativos = equipos.filter(estado="OPERATIVO").count()
    fuera_servicio = equipos.exclude(estado="OPERATIVO").count()
    equipos_fuera = equipos.exclude(estado="OPERATIVO")

    operativos_count = equipos.filter(estado="OPERATIVO").count()
    reparacion_count = equipos.filter(estado="EN_REPARACION").count()
    fuera_count = equipos.filter(estado="FUERA_SERVICIO").count()

    hoy_dt = timezone.now()

    emergencias_mes = Emergencia.objects.filter(
        cliente=cliente,
        fecha_llamada__year=hoy_dt.year,
        fecha_llamada__month=hoy_dt.month,
    ).count()

    cotizaciones = CotizacionEquipo.objects.filter(
        equipo__cliente=cliente,
    ).order_by("-creado_en")[:10]
    hoy = timezone.localdate()
    hoy = timezone.now().date()
    inicio = (hoy.replace(day=1) - timedelta(days=365)).replace(day=1)

    qs = (
        Emergencia.objects
        .filter(cliente=cliente, fecha_llamada__date__gte=inicio)
        .annotate(mes=TruncMonth("fecha_llamada"))
        .values("mes")
        .annotate(total=Count("id"))
        .order_by("mes")
    )

    data_dict = {
        x["mes"].strftime("%Y-%m"): x["total"]
        for x in qs
    }

    labels = []
    values = []

    anio = hoy.year
    mes = hoy.month

    for i in range(11, -1, -1):
        m = mes - i
        y = anio

        while m <= 0:
            m += 12
            y -= 1

        key = f"{y:04d}-{m:02d}"
        labels.append(key)
        values.append(data_dict.get(key, 0))

    context = {
        "cliente": cliente,
        "total_equipos": total_equipos,
        "operativos": operativos,
        "fuera_servicio": fuera_servicio,
        "emergencias_mes": emergencias_mes,
        "equipos_fuera": equipos_fuera,
        "cotizaciones": cotizaciones,
        "labels": labels,
        "values": values,
        "labels_estado": [
            "Operativos",
            "En reparación",
            "Fuera de servicio",
        ],
        "data_estado": [
            operativos_count,
            reparacion_count,
            fuera_count,
        ],
    }

    usuario_administracion = UsuarioAdministracion.objects.filter(
        user=request.user,
        activo=True,
    ).exists()

    context["mostrar_volver_unidades"] = usuario_administracion

    return render(request, "dashboard_cliente.html", context)


# =========================================
# HOJA DE VIDA HTML
# =========================================
def _agrupar_activos_por_torre(equipos, tanques, distribuciones):
    import re

    grupos = {}

    def datos_torre(valor):
        original = str(valor or "").strip()
        if not original:
            return "sin torre", "Sin torre especificada"

        clave = " ".join(original.lower().split())
        if clave.startswith("torre") or clave.startswith("bloque"):
            nombre = original
        else:
            nombre = f"Torre {original}"
        return clave, nombre

    def obtener(valor):
        clave, nombre = datos_torre(valor)
        return grupos.setdefault(
            clave,
            {
                "clave": clave,
                "nombre": nombre,
                "equipos": [],
                "tanques": [],
                "distribuciones": [],
            },
        )

    for equipo in equipos:
        obtener(equipo.torre)["equipos"].append(equipo)
    for tanque in tanques:
        obtener(tanque.torre)["tanques"].append(tanque)
    for distribucion in distribuciones:
        obtener(distribucion.torre)["distribuciones"].append(distribucion)

    def orden(grupo):
        partes = re.split(r"(\d+)", grupo["nombre"].lower())
        return [
            (0, int(p)) if p.isdigit() else (1, p)
            for p in partes
        ]

    return sorted(grupos.values(), key=orden)


@login_required
def hoja_vida(request, cliente_id):
    cliente = get_object_or_404(Cliente, id=cliente_id)

    equipos = list(
        EquipoUnidad.objects.filter(cliente=cliente).order_by("torre", "id")
    )
    tanques = list(
        TanqueUnidad.objects.filter(cliente=cliente).order_by("torre", "id")
    )
    distribuciones = list(
        DistribucionUnidad.objects.filter(cliente=cliente).order_by("torre", "id")
    )
    grupos_torres = _agrupar_activos_por_torre(
        equipos,
        tanques,
        distribuciones,
    )

    context = {
        "cliente": cliente,
        "equipos": equipos,
        "tanques": tanques,
        "distribuciones": distribuciones,
        "grupos_torres": grupos_torres,
    }

    return render(request, "hoja_vida.html", context)


# =========================================
# HOJA DE VIDA PDF
# =========================================
@login_required
def hoja_vida_pdf(request, cliente_id):
    cliente = get_object_or_404(Cliente, id=cliente_id)

    equipos = list(
        EquipoUnidad.objects.filter(cliente=cliente).order_by("torre", "id")
    )
    tanques = list(
        TanqueUnidad.objects.filter(cliente=cliente).order_by("torre", "id")
    )
    distribuciones = list(
        DistribucionUnidad.objects.filter(cliente=cliente).order_by("torre", "id")
    )
    grupos_torres = _agrupar_activos_por_torre(
        equipos,
        tanques,
        distribuciones,
    )

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="hoja_vida_{cliente.nombre}.pdf"'
    )

    pdf = canvas.Canvas(response, pagesize=letter)
    width, height = letter

    logo = os.path.join(
        settings.BASE_DIR,
        "static",
        "img",
        "logo_dys.png",
    )

    def encabezado():
        if os.path.exists(logo):
            pdf.drawImage(
                logo,
                40,
                height - 90,
                width=80,
                height=60,
                preserveAspectRatio=True,
            )

        pdf.setFillColorRGB(0.0, 0.20, 0.40)
        pdf.rect(0, height - 120, width, 35, fill=True, stroke=False)

        pdf.setFillColorRGB(1, 1, 1)
        pdf.setFont("Helvetica-Bold", 13)
        pdf.drawString(
            140,
            height - 105,
            "D&S SOLUCIONES EN BOMBEO S.A.S.",
        )

        pdf.setFillColorRGB(0, 0, 0)
        pdf.setFont("Helvetica-Bold", 16)
        pdf.drawString(
            190,
            height - 150,
            "HOJA DE VIDA TÉCNICA",
        )

    def pie():
        pdf.setFont("Helvetica", 8)
        pdf.setFillColorRGB(0.35, 0.35, 0.35)
        pdf.drawString(
            40,
            35,
            "Sistema 7x24 - Reporte generado automáticamente",
        )
        pdf.drawRightString(
            width - 40,
            35,
            "D&S Soluciones en Bombeo S.A.S.",
        )

    def nueva_pagina():
        pie()
        pdf.showPage()
        encabezado()
        return height - 180

    def seccion(titulo, y):
        if y < 100:
            y = nueva_pagina()

        pdf.setFillColorRGB(0.0, 0.20, 0.40)
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(40, y, titulo)
        pdf.line(40, y - 4, width - 40, y - 4)
        return y - 22

    def fila_texto(label, valor, x, y):
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(x, y, label)
        pdf.setFont("Helvetica", 9)
        pdf.drawString(x + 85, y, str(valor or "-"))

    encabezado()
    y = height - 180

    y = seccion("DATOS GENERALES", y)
    fila_texto("Cliente:", cliente.nombre, 40, y)
    fila_texto(
        "Contrato:",
        cliente.get_tipo_contrato_display(),
        330,
        y,
    )
    y -= 16

    fila_texto("Dirección:", cliente.direccion, 40, y)
    y -= 16

    fila_texto(
        "Administrador:",
        cliente.administrador,
        40,
        y,
    )
    fila_texto(
        "Teléfono:",
        cliente.telefono_porteria,
        330,
        y,
    )
    y -= 28

    y = seccion("RESUMEN EJECUTIVO", y)
    fila_texto("Equipos:", len(equipos), 40, y)
    fila_texto("Tanques:", len(tanques), 200, y)
    fila_texto(
        "Distribuciones:",
        len(distribuciones),
        360,
        y,
    )
    y -= 30

    for grupo in grupos_torres:
        if y < 145:
            y = nueva_pagina()

        y = seccion(grupo["nombre"].upper(), y)
        fila_texto("Equipos:", len(grupo["equipos"]), 40, y)
        fila_texto("Tanques:", len(grupo["tanques"]), 200, y)
        fila_texto(
            "Distribuciones:",
            len(grupo["distribuciones"]),
            360,
            y,
        )
        y -= 24

        if grupo["equipos"]:
            y = seccion("EQUIPOS INSTALADOS", y)
            pdf.setFont("Helvetica-Bold", 8)
            columnas = [40, 145, 210, 275, 340, 405, 480]
            headers = [
                "Tipo", "Marca", "Modelo", "Potencia",
                "Voltaje", "Cantidad", "Estado",
            ]
            for x, header in zip(columnas, headers):
                pdf.drawString(x, y, header)
            y -= 10
            pdf.line(40, y, width - 40, y)
            y -= 12
            pdf.setFont("Helvetica", 8)

            for equipo in grupo["equipos"]:
                if y < 70:
                    y = nueva_pagina()
                pdf.drawString(40, y, str(equipo.get_tipo_display() or "-")[:22])
                pdf.drawString(145, y, str(equipo.marca or "-")[:12])
                pdf.drawString(210, y, str(equipo.modelo or "-")[:12])
                pdf.drawString(275, y, str(equipo.potencia or "-")[:12])
                pdf.drawString(340, y, str(equipo.voltaje or "-")[:10])
                pdf.drawString(405, y, str(equipo.cantidad or "-"))
                pdf.drawString(480, y, str(equipo.get_estado_display() or "-")[:18])
                y -= 14
            y -= 12

        if grupo["tanques"]:
            y = seccion("TANQUES", y)
            pdf.setFont("Helvetica-Bold", 8)
            columnas = [40, 180, 255, 330, 430]
            headers = ["Tipo", "Material", "Capacidad", "Ubicacion", "Cantidad"]
            for x, header in zip(columnas, headers):
                pdf.drawString(x, y, header)
            y -= 10
            pdf.line(40, y, width - 40, y)
            y -= 12
            pdf.setFont("Helvetica", 8)

            for tanque in grupo["tanques"]:
                if y < 70:
                    y = nueva_pagina()
                pdf.drawString(40, y, str(tanque.get_tipo_tanque_display() or "-")[:28])
                pdf.drawString(180, y, str(tanque.material or "-")[:14])
                pdf.drawString(255, y, str(tanque.capacidad or "-")[:14])
                pdf.drawString(330, y, str(tanque.ubicacion or "-")[:18])
                pdf.drawString(430, y, str(tanque.cantidad or "-"))
                y -= 14
            y -= 12

        if grupo["distribuciones"]:
            y = seccion("DISTRIBUCION", y)
            pdf.setFont("Helvetica-Bold", 8)
            columnas = [40, 110, 210, 330]
            headers = ["Pisos", "Presion", "Gravedad", "Observaciones"]
            for x, header in zip(columnas, headers):
                pdf.drawString(x, y, header)
            y -= 10
            pdf.line(40, y, width - 40, y)
            y -= 12
            pdf.setFont("Helvetica", 8)

            for distribucion in grupo["distribuciones"]:
                if y < 70:
                    y = nueva_pagina()
                pdf.drawString(40, y, str(distribucion.cantidad_pisos or "-"))
                pdf.drawString(
                    110, y,
                    f"{distribucion.presion_desde or '-'} - "
                    f"{distribucion.presion_hasta or '-'}",
                )
                pdf.drawString(
                    210, y,
                    f"{distribucion.gravedad_desde or '-'} - "
                    f"{distribucion.gravedad_hasta or '-'}",
                )
                pdf.drawString(
                    330, y,
                    str(distribucion.observaciones or "-")[:38],
                )
                y -= 14
            y -= 12

        y -= 8

    pie()
    pdf.save()

    return response


# =========================================
# GESTIONAR SERVICIO
# =========================================
# =========================================
# GESTIONAR SERVICIO
# =========================================
@login_required
def gestionar_servicio(request, servicio_id):

    servicio = get_object_or_404(
        Emergencia,
        id=servicio_id,
    )

    # Seguridad:
    # el técnico solo puede consultar servicios asignados a él.
    if not usuario_puede_gestionar_servicio(
        request.user,
        servicio,
    ):
        return HttpResponseForbidden(
            "No está autorizado para consultar este servicio."
        )

    eventos = servicio.eventos.all()

    if request.method == "POST":

        form = GestionServicioForm(
            request.POST,
            instance=servicio,
            puede_cambiar_sector=es_coordinador_operativo(request.user),
        )

        if form.is_valid():

            sector_anterior = servicio.sector_id
            # ModelForm ya contiene los valores validados; recuperar el anterior de la BD.
            sector_anterior = Emergencia.objects.get(pk=servicio.pk).sector_id
            servicio = form.save()
            if sector_anterior != servicio.sector_id:
                from .models import SectorCliente
                anterior = SectorCliente.objects.filter(pk=sector_anterior).first()
                registrar_evento(servicio, "Sector actualizado",
                    f"Antes: {anterior or 'Sin sector / por identificar'}. Después: {servicio.sector or 'Sin sector / por identificar'}.",
                    request.user.username, "")

            registrar_evento(
                servicio,
                "Seguimiento actualizado",
                "Se actualizó la información del expediente del servicio.",
                request.user.username,
                "📝",
            )

            # Si quien actualiza es técnico,
            # vuelve a su Panel Técnico.
            if Tecnico.objects.filter(
                user=request.user,
                activo=True,
            ).exists():
                return redirect("panel_tecnico")

            # Personal interno vuelve al Centro de Operaciones.
            return redirect("/centro-operaciones/")

    else:
        form = GestionServicioForm(
            instance=servicio,
            puede_cambiar_sector=es_coordinador_operativo(request.user),
        )

    return render(
        request,
        "gestionar_servicio.html",
        {
            "servicio": servicio,
            "form": form,
            "eventos": eventos,
        },
    )


# =========================================
# ACCIONES DEL SERVICIO
# =========================================
@login_required
def accion_servicio(request, servicio_id, accion):

    servicio = get_object_or_404(
        Emergencia,
        id=servicio_id,
    )

    # Seguridad:
    # el técnico solo puede actuar sobre servicios asignados a él.
    if not usuario_puede_gestionar_servicio(
        request.user,
        servicio,
    ):
        return HttpResponseForbidden(
            "No está autorizado para realizar acciones sobre este servicio."
        )

    acciones = {
        "salida": (
            "🚗",
            "Técnico salió",
            "El técnico salió hacia el sitio.",
        ),
        "llegada": (
            "📍",
            "Llegó al sitio",
            "El técnico llegó al sitio.",
        ),
        "reparando": (
            "🔧",
            "Reparación iniciada",
            "El técnico inició la reparación.",
        ),
        "terminado": (
            "✅",
            "Servicio finalizado",
            "El técnico informó que terminó la reparación.",
        ),
    }
        # Evitar registrar dos veces la misma acción
    titulos_accion = {
        "salida": "Técnico salió",
        "llegada": "Llegó al sitio",
        "reparando": "Reparación iniciada",
        "terminado": "Servicio finalizado",
    }

    titulo_esperado = titulos_accion.get(accion)

    if titulo_esperado and servicio.eventos.filter(
        titulo=titulo_esperado
    ).exists():
        return redirect(
            "servicio_tecnico",
            servicio_id=servicio.id,
        )
        # =========================================
    # EVITAR ACCIONES DUPLICADAS
    # =========================================
    titulos_accion = {
        "salida": "Técnico salió",
        "llegada": "Llegó al sitio",
        "reparando": "Reparación iniciada",
        "terminado": "Servicio finalizado",
    }

    titulo_esperado = titulos_accion.get(accion)

    if titulo_esperado and servicio.eventos.filter(
        titulo=titulo_esperado
    ).exists():
        return redirect(
            "servicio_tecnico",
            servicio_id=servicio.id,
        )
        # =========================================
    # NO PERMITIR TERMINAR SIN ACTIVIDAD TÉCNICA
    # =========================================
    if accion == "terminado":
        tiene_actividad = ActividadTecnico.objects.filter(
            servicio=servicio,
            tecnico=servicio.tecnico,
        ).exists()

        if not tiene_actividad:
            return HttpResponseForbidden(
                "Debe registrar al menos una actividad técnica antes de terminar la atención."
            )
    if accion in acciones:

        icono, titulo, descripcion = acciones[accion]

        registrar_evento(
            servicio,
            titulo,
            descripcion,
            request.user.username,
            icono,
        )

        if accion in [
            "salida",
            "llegada",
            "reparando",
        ]:
            servicio.estado = "EN_PROCESO"

        if accion == "terminado":
            servicio.estado = "ATENDIDA"

        servicio.save()

    
    return redirect(
        "servicio_tecnico",
    servicio_id=servicio.id,
    )
# =========================================
# EXPORTAR CSV
# =========================================
@login_required
def export_csv(request, cliente_id):
    cliente = get_object_or_404(Cliente, id=cliente_id)
    equipos = EquipoUnidad.objects.filter(cliente=cliente)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        'attachment; filename="equipos.csv"'
    )

    writer = csv.writer(response)
    writer.writerow(["Tipo", "Cantidad", "Estado"])

    for equipo in equipos:
        writer.writerow(
            [
                equipo.get_tipo_display(),
                equipo.cantidad,
                equipo.get_estado_display(),
            ]
        )

    return response


# =========================================
# EXPORTAR EXCEL
# =========================================
@login_required
def export_excel(request, cliente_id):
    cliente = get_object_or_404(Cliente, id=cliente_id)
    equipos = EquipoUnidad.objects.filter(cliente=cliente)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Equipos"

    ws.append(["Tipo", "Cantidad", "Estado"])

    for equipo in equipos:
        ws.append(
            [
                equipo.get_tipo_display(),
                equipo.cantidad,
                equipo.get_estado_display(),
            ]
        )

    response = HttpResponse(
        content_type="application/ms-excel",
    )
    response["Content-Disposition"] = (
        'attachment; filename="equipos.xlsx"'
    )

    wb.save(response)
    return response


# =========================================
# PDF SIMPLE
# =========================================
@login_required
def reporte_pdf(request, cliente_id):
    cliente = get_object_or_404(Cliente, id=cliente_id)
    equipos = EquipoUnidad.objects.filter(cliente=cliente)

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="reporte_{cliente.nombre}.pdf"'
    )

    pdf = canvas.Canvas(response, pagesize=letter)
    y = 750

    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(200, y, "INFORME TÉCNICO")

    y -= 40

    pdf.setFont("Helvetica", 11)
    pdf.drawString(
        50,
        y,
        f"Cliente: {cliente.nombre}",
    )

    y -= 20
    pdf.drawString(
        50,
        y,
        f"Dirección: {cliente.direccion}",
    )

    y -= 30

    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(50, y, "Equipo")
    pdf.drawString(200, y, "Cantidad")
    pdf.drawString(300, y, "Estado")

    y -= 15

    pdf.setFont("Helvetica", 10)

    for equipo in equipos:
        pdf.drawString(
            50,
            y,
            equipo.get_tipo_display(),
        )
        pdf.drawString(
            200,
            y,
            str(equipo.cantidad),
        )
        pdf.drawString(
            300,
            y,
            equipo.get_estado_display(),
        )
        y -= 15

        if y < 100:
            pdf.showPage()
            pdf.setFont("Helvetica", 10)
            y = 750

    y -= 40
    pdf.setFont("Helvetica", 9)
    pdf.drawString(
        50,
        y,
        "Sistema D&S - Reporte generado automáticamente",
    )

    pdf.save()
    return response



# =========================================================
# ACTIVIDADES DE TÉCNICOS
# =========================================================
@login_required
@require_GET
def casos_por_cliente(request):
    if not request.user.is_active or es_usuario_externo(request.user):
        return HttpResponseForbidden("Consulta disponible solo para personal interno.")
    interno = (
        request.user.is_superuser
        or request.user.groups.filter(name__in=[
            "GESTION_COORDINADOR", "GESTION_SUPERVISOR", "GESTION_GERENCIA",
            "GESTION_AUXILIAR", "GESTION_FACTURACION",
        ]).exists()
    )
    tecnico = Tecnico.objects.filter(user=request.user, activo=True).first()
    if not interno and tecnico is None:
        return HttpResponseForbidden("No está autorizado para consultar casos.")
    cliente_id = request.GET.get("cliente_id")
    if cliente_id and not cliente_id.isdecimal():
        return JsonResponse({"error": "Unidad inválida"}, status=400)

    if not cliente_id:
        return JsonResponse({"casos": []})

    casos = (
        Emergencia.objects
        .filter(
            cliente_id=cliente_id,
            numero_caso__isnull=False,
        )
        .exclude(numero_caso="")
        .order_by("-fecha_llamada")
    )

    if not interno:
        casos = casos.filter(tecnico=tecnico)

    datos = []

    for caso in casos:
        datos.append({
            "id": caso.id,
            "texto": (
                f"{caso.numero_caso} - "
                f"{caso.get_tipo_servicio_display()} - "
                f"{caso.get_estado_display()}"
            ),
        })

    return JsonResponse({"casos": datos})


@login_required
@require_GET
def datos_caso_remision(request):
    if not puede_gestionar_remisiones(request.user):
        return HttpResponseForbidden(
            "No está autorizado para consultar datos de remisiones."
        )

    servicio_id = request.GET.get("servicio_id", "").strip()
    if not servicio_id.isdecimal():
        return JsonResponse({"error": "Caso inválido."}, status=400)

    servicio = get_object_or_404(
        Emergencia.objects.select_related("cliente", "tecnico"),
        pk=servicio_id,
    )

    return JsonResponse({
        "caso": {
            "id": servicio.id,
            "numero": servicio.numero_caso,
            "cliente_id": servicio.cliente_id,
            "cliente": servicio.cliente.nombre,
            "tecnico_id": servicio.tecnico_id,
            "tecnico": servicio.tecnico.nombre if servicio.tecnico_id else "",
        }
    })


@login_required
@require_GET
def remisiones_por_cliente(request):
    if not request.user.is_active or es_usuario_externo(request.user):
        return HttpResponseForbidden(
            "Consulta disponible solo para personal interno."
        )

    cliente_id = request.GET.get("cliente_id")
    servicio_id = request.GET.get("servicio_id")

    if any(
        valor and not valor.isdecimal()
        for valor in (cliente_id, servicio_id)
    ):
        return JsonResponse({"error": "Identificador inválido"}, status=400)

    if not cliente_id:
        return JsonResponse({"remisiones": []})

    tecnico = Tecnico.objects.filter(
        user=request.user,
        activo=True,
    ).first()

    gestor = (
        request.user.is_superuser
        or puede_gestionar_remisiones(request.user)
    )
    interno = gestor or (request.user.is_staff and tecnico is None)

    if not interno and tecnico is None:
        return HttpResponseForbidden(
            "No está autorizado para consultar remisiones."
        )

    remisiones = RemisionTecnico.objects.select_related(
        "tecnico",
    ).filter(
        cliente_id=cliente_id,
        estado="PENDIENTE",
    )

    if tecnico is not None and not gestor:
        remisiones = remisiones.filter(tecnico=tecnico)

    # Si además se seleccionó un caso 7x24,
    # mostramos las remisiones relacionadas con ese caso.
    if servicio_id:
        remisiones = remisiones.filter(
            servicio_id=servicio_id
        )

    remisiones = remisiones.order_by("-fecha", "-id")

    datos = []

    for remision in remisiones:
        datos.append({
            "id": remision.id,
            "texto": (
                f"{remision.numero_remision} - "
                f"{remision.tecnico.nombre} - "
                f"{remision.get_estado_display()}"
            ),
        })

    return JsonResponse({"remisiones": datos})


@login_required
@require_GET
def accesorios_remision(request, remision_id):
    if not request.user.is_active or es_usuario_externo(request.user):
        return HttpResponseForbidden(
            "Consulta disponible solo para personal interno."
        )

    remision = get_object_or_404(
        RemisionTecnico.objects.select_related(
            "tecnico",
        ).prefetch_related(
            "detalles__accesorio",
        ),
        pk=remision_id,
    )

    tecnico = Tecnico.objects.filter(
        user=request.user,
        activo=True,
    ).first()

    gestor = (
        request.user.is_superuser
        or puede_gestionar_remisiones(request.user)
    )
    autorizado = (
        gestor
        or (tecnico is not None and remision.tecnico_id == tecnico.id)
        or (request.user.is_staff and tecnico is None)
    )

    if not autorizado:
        return HttpResponseForbidden(
            "No está autorizado para consultar esta remisión."
        )

    detalles = []

    for detalle in remision.detalles.all():
        disponible = detalle.cantidad_pendiente
        detalles.append({
            "id": detalle.id,
            "accesorio_id": detalle.accesorio_id,
            "codigo": detalle.codigo_accesorio,
            "descripcion": detalle.descripcion_accesorio,
            "entregada": str(detalle.cantidad_entregada),
            "utilizada": str(detalle.cantidad_utilizada),
            "devuelta": str(detalle.cantidad_devuelta),
            "disponible": str(max(disponible, Decimal("0.00"))),
            "catalogado": bool(detalle.accesorio_id),
        })

    return JsonResponse({
        "remision": {
            "id": remision.id,
            "numero": remision.numero_remision,
            "estado": remision.estado,
        },
        "detalles": detalles,
    })

@login_required
@require_GET
def buscar_accesorios(request):
    if not request.user.is_active or es_usuario_externo(request.user):
        return HttpResponseForbidden(
            "Consulta disponible solo para personal interno."
        )

    tecnico = Tecnico.objects.filter(
        user=request.user,
        activo=True,
    ).exists()
    if not (
        tecnico
        or request.user.is_staff
        or request.user.is_superuser
        or puede_gestionar_remisiones(request.user)
    ):
        return HttpResponseForbidden(
            "No está autorizado para consultar accesorios."
        )

    texto = request.GET.get("q", "").strip()

    if len(texto) < 2:
        return JsonResponse({"resultados": []})

    accesorios = (
        Accesorio.objects
        .filter(
            Q(descripcion__icontains=texto)
            | Q(codigo__icontains=texto),
            activo=True,
        )
        .order_by("descripcion")[:20]
    )

    resultados = [
        {
            "id": accesorio.id,
            "codigo": accesorio.codigo,
            "descripcion": accesorio.descripcion,
        }
        for accesorio in accesorios
    ]

    return JsonResponse({
        "resultados": resultados,
    })
@login_required
@require_GET
@acceso_bitacora()
def actividades_por_cliente(request):
    cliente_id = request.GET.get("cliente_id")
    servicio_id = request.GET.get("servicio_id")

    if any(valor and not valor.isdecimal() for valor in (cliente_id, servicio_id)):
        return JsonResponse({"error": "Identificador inválido"}, status=400)

    if not cliente_id:
        return JsonResponse({"actividades": []})

    actividades = (
        actividades_visibles(request.user)
        .filter(cliente_id=cliente_id)
        .select_related(
            "tecnico",
            "cliente",
            "servicio",
        )
        .order_by(
            "-fecha",
            "-hora_llegada",
            "-id",
        )
    )

    if servicio_id:
        actividades = actividades.filter(
            servicio_id=servicio_id
        )

    datos = []

    for actividad in actividades:
        datos.append({
            "id": actividad.id,
            "texto": (
                f"{actividad.fecha.strftime('%d/%m/%Y')} - "
                f"{actividad.tecnico.nombre} - "
                f"{actividad.get_tipo_actividad_display()}"
            ),
        })

    return JsonResponse({
        "actividades": datos,
    })


@login_required
@require_GET
@acceso_bitacora()
def detalle_actividad(request, actividad_id):

    actividad = get_object_or_404(
        actividades_visibles(request.user)
        .select_related(
            "tecnico",
            "cliente",
            "servicio",
        )
        .prefetch_related(
            "accesorios_utilizados__accesorio",
        ),
        id=actividad_id,
    )

    accesorios = []

    for uso in actividad.accesorios_utilizados.all():

        if uso.es_otro:
            descripcion = uso.descripcion_otro
        elif uso.accesorio:
            descripcion = uso.accesorio.descripcion
        else:
            descripcion = "Accesorio sin identificar"

        accesorios.append({
            "descripcion": descripcion,
            "cantidad": str(uso.cantidad),
            "observacion": uso.observacion or "",
            "es_otro": uso.es_otro,
        })

    return JsonResponse({
        "actividad": {
            "id": actividad.id,
            "tecnico_id": actividad.tecnico_id,
            "tecnico": actividad.tecnico.nombre,
            "cliente": actividad.cliente.nombre,
            "fecha": actividad.fecha.strftime("%d/%m/%Y"),

            "hora_llegada": (
                actividad.hora_llegada.strftime("%H:%M")
                if actividad.hora_llegada
                else ""
            ),

            "hora_salida": (
                actividad.hora_salida.strftime("%H:%M")
                if actividad.hora_salida
                else ""
            ),

            "permanencia": actividad.duracion_en_sitio or "",
            "diagnostico": actividad.diagnostico or "",
            "labor_realizada": actividad.labor_realizada or "",

            "resultado": (
                actividad.get_resultado_display()
                if actividad.resultado
                else ""
            ),

            "accesorios": accesorios,
        }
    })



@login_required

def lista_actividades(request):

    autorizado = (
        request.user.is_superuser
        or request.user.is_staff
        or (
            not es_usuario_externo(request.user)
            and request.user.groups.filter(name__in=[
                "GESTION_COORDINADOR",
                "GESTION_SUPERVISOR",
                "GESTION_GERENCIA",
                "GESTION_AUXILIAR",
                "GESTION_FACTURACION",
            ]).exists()
        )
    )
    if not autorizado or es_usuario_externo(request.user):
        return HttpResponseForbidden(
            "No está autorizado para consultar los informes técnicos."
        )

    actividades = (
        ActividadTecnico.objects
        .select_related(
            "tecnico",
            "cliente",
            "servicio",
            "remision",
            "registrado_por",
        )
        .prefetch_related(
            "remision__detalles",
            "accesorios_utilizados__accesorio",
)
        .all()
    )

    # ==============================
    # FILTROS
    # ==============================

    fecha = request.GET.get("fecha", "").strip()
    tecnico_id = request.GET.get("tecnico", "").strip()
    cliente_id = request.GET.get("cliente", "").strip()
    tipo = request.GET.get("tipo", "").strip()

    if fecha:
        actividades = actividades.filter(
            fecha=fecha
        )

    if tecnico_id:
        actividades = actividades.filter(
            tecnico_id=tecnico_id
        )

    if cliente_id:
        actividades = actividades.filter(
            cliente_id=cliente_id
        )

    if tipo:
        actividades = actividades.filter(
            tipo_actividad=tipo
        )

    tecnicos = Tecnico.objects.filter(
        activo=True
    ).order_by("nombre")

    clientes = Cliente.objects.filter(
        activo=True
    ).order_by("nombre")

    return render(
        request,
        "actividades/lista.html",
        {
            "actividades": actividades,

            # Opciones para los filtros
            "tecnicos": tecnicos,
            "clientes": clientes,
            "tipos_actividad": ActividadTecnico.TIPO_ACTIVIDAD,

            # Valores seleccionados
            "filtro_fecha": fecha,
            "filtro_tecnico": tecnico_id,
            "filtro_cliente": cliente_id,
            "filtro_tipo": tipo,
        },
    )


def _validar_remision_actividad(form):
    remision = form.cleaned_data.get("remision")
    if not remision:
        return None

    tecnico = form.cleaned_data.get("tecnico")
    cliente = form.cleaned_data.get("cliente")
    servicio = form.cleaned_data.get("servicio")

    if remision.estado == "CONCILIADA":
        form.add_error(
            "remision",
            "La remisión ya está conciliada y no admite nuevos consumos.",
        )
    elif tecnico and remision.tecnico_id != tecnico.id:
        form.add_error(
            "remision",
            "La remisión no pertenece al técnico seleccionado.",
        )
    elif cliente and remision.cliente_id != cliente.id:
        form.add_error(
            "remision",
            "La remisión no pertenece a la unidad seleccionada.",
        )
    elif remision.servicio_id and (
        not servicio or remision.servicio_id != servicio.id
    ):
        form.add_error(
            "remision",
            "La remisión pertenece a otro caso 7x24.",
        )

    return remision


def _usos_accesorios_solicitados(request, form):
    accesorios_ids = request.POST.getlist("accesorio_id[]")
    detalles_ids = request.POST.getlist("detalle_remision_id[]")
    cantidades = request.POST.getlist("cantidad[]")
    es_otro_lista = request.POST.getlist("es_otro[]")
    descripciones_otro = request.POST.getlist("descripcion_otro[]")
    observaciones = request.POST.getlist("observacion[]")

    total_filas = max(
        len(accesorios_ids),
        len(detalles_ids),
        len(cantidades),
        len(es_otro_lista),
        len(descripciones_otro),
        len(observaciones),
        0,
    )

    remision = form.cleaned_data.get("remision")
    usos = []

    for i in range(total_filas):
        accesorio_id = accesorios_ids[i].strip() if i < len(accesorios_ids) else ""
        detalle_id = detalles_ids[i].strip() if i < len(detalles_ids) else ""
        cantidad_texto = cantidades[i].strip() if i < len(cantidades) else ""
        es_otro = (
            i < len(es_otro_lista)
            and es_otro_lista[i] == "1"
        )
        descripcion_otro = (
            descripciones_otro[i].strip()
            if i < len(descripciones_otro)
            else ""
        )
        observacion = (
            observaciones[i].strip()
            if i < len(observaciones)
            else ""
        )

        if not accesorio_id and not detalle_id and not descripcion_otro:
            continue

        try:
            cantidad = Decimal(cantidad_texto or "1")
        except (InvalidOperation, ValueError):
            cantidad = Decimal("0")

        if cantidad <= 0:
            form.add_error(
                None,
                "La cantidad de cada accesorio debe ser mayor que cero.",
            )
            return []

        detalle = None
        accesorio = None

        if detalle_id:
            if not detalle_id.isdecimal() or not remision:
                form.add_error(None, "El accesorio de la remisión no es válido.")
                return []

            detalle = (
                DetalleRemision.objects
                .select_related("accesorio")
                .filter(pk=detalle_id, remision=remision)
                .first()
            )
            if not detalle or not detalle.accesorio_id:
                form.add_error(
                    None,
                    "El accesorio no está relacionado correctamente con la remisión.",
                )
                return []
            accesorio = detalle.accesorio
            es_otro = False
            descripcion_otro = ""

        elif es_otro:
            if not descripcion_otro:
                form.add_error(None, "Describa el accesorio no catalogado.")
                return []

        else:
            if not accesorio_id.isdecimal():
                form.add_error(None, "Seleccione un accesorio válido del catálogo.")
                return []

            accesorio = Accesorio.objects.filter(
                pk=accesorio_id,
                activo=True,
            ).first()
            if not accesorio:
                form.add_error(None, "El accesorio seleccionado no está disponible.")
                return []

            if remision:
                coincidencias = list(
                    remision.detalles.select_related("accesorio").filter(
                        accesorio=accesorio,
                    )[:2]
                )
                if len(coincidencias) == 1:
                    detalle = coincidencias[0]

        usos.append({
            "accesorio": accesorio,
            "detalle_remision": detalle,
            "es_otro": es_otro,
            "descripcion_otro": descripcion_otro,
            "cantidad": cantidad,
            "observacion": observacion,
        })

    cantidades_por_detalle = {}
    detalles = {}

    for uso in usos:
        detalle = uso["detalle_remision"]
        if not detalle:
            continue
        detalles[detalle.pk] = detalle
        cantidades_por_detalle[detalle.pk] = (
            cantidades_por_detalle.get(detalle.pk, Decimal("0.00"))
            + uso["cantidad"]
        )

    for detalle_id, cantidad in cantidades_por_detalle.items():
        detalle = detalles[detalle_id]
        if cantidad > detalle.cantidad_pendiente:
            form.add_error(
                None,
                (
                    f"La cantidad utilizada de {detalle.descripcion_accesorio} "
                    "supera lo disponible en la remisión."
                ),
            )
            return []

    return usos

@login_required
@transaction.atomic
def nueva_actividad(request):

    # Técnico asociado al usuario conectado, si existe.
    tecnico_usuario = Tecnico.objects.filter(
        user=request.user,
        activo=True,
    ).first()

    if not tecnico_usuario and (
        es_usuario_externo(request.user)
        or not (request.user.is_staff or request.user.is_superuser)
    ):
        return HttpResponseForbidden(
            "No está autorizado para registrar actividades técnicas."
        )

    # Servicio que viene desde el Panel Técnico.
    servicio_id = (
        request.GET.get("servicio")
        or request.POST.get("servicio")
    )

    servicio_forzado = None

    # =====================================================
    # SEGURIDAD PARA USUARIO TÉCNICO
    # =====================================================
    if tecnico_usuario and servicio_id:

        servicio_forzado = get_object_or_404(
            Emergencia,
            id=servicio_id,
            tecnico=tecnico_usuario,
        )

    # =====================================================
    # POST - GUARDAR ACTIVIDAD
    # =====================================================
    if request.method == "POST":

        datos_post = request.POST.copy()

        # Si es técnico, estos valores NO los decide el formulario.
        # Los impone SIGOB desde el servidor.
        if tecnico_usuario:

            if not servicio_forzado:
                return HttpResponseForbidden(
                    "No está autorizado para registrar esta actividad."
                )

            datos_post["tecnico"] = str(tecnico_usuario.id)
            datos_post["cliente"] = str(servicio_forzado.cliente_id)
            datos_post["servicio"] = str(servicio_forzado.id)

        form = ActividadTecnicoForm(
            datos_post,
            exigir_envio=bool(tecnico_usuario),
        )

        if tecnico_usuario and servicio_forzado:
            form.fields["remision"].queryset = RemisionTecnico.objects.filter(
                tecnico=tecnico_usuario,
                cliente=servicio_forzado.cliente,
                servicio=servicio_forzado,
                estado="PENDIENTE",
            ).order_by("-fecha", "-id")

        formulario_valido = form.is_valid()
        usos_solicitados = []

        if formulario_valido:
            _validar_remision_actividad(form)
            if not form.errors:
                usos_solicitados = _usos_accesorios_solicitados(
                    request,
                    form,
                )
            formulario_valido = not form.errors

        if formulario_valido:

            actividad = form.save(commit=False)

            # Seguridad adicional:
            # volvemos a imponer estos datos antes de guardar.
            if tecnico_usuario:
                actividad.tecnico = tecnico_usuario
                actividad.cliente = servicio_forzado.cliente
                actividad.servicio = servicio_forzado

            actividad.registrado_por = request.user
            actividad.save()

            detalles_afectados = {}

            for uso in usos_solicitados:
                AccesorioActividad.objects.create(
                    actividad=actividad,
                    accesorio=uso["accesorio"],
                    detalle_remision=uso["detalle_remision"],
                    es_otro=uso["es_otro"],
                    descripcion_otro=uso["descripcion_otro"],
                    cantidad=uso["cantidad"],
                    observacion=uso["observacion"],
                )

                detalle = uso["detalle_remision"]
                if detalle:
                    detalles_afectados[detalle.pk] = detalle

            for detalle in detalles_afectados.values():
                detalle.actualizar_utilizado_desde_informes()

            if actividad.remision_id:
                actividad.remision.refresh_from_db()
                actividad.remision.estado = (
                    "CONCILIADA"
                    if actividad.remision.esta_conciliada
                    else "PENDIENTE"
                )
                actividad.remision.save(
                    update_fields=["estado", "actualizado"]
                )

            asignar_comprobante(actividad)
            registrar_ejecucion_lavado(actividad)

            # Técnico vuelve al servicio que estaba atendiendo.
            if tecnico_usuario:
                return redirect(
                    "comprobante_actividad",
                    actividad_id=actividad.id,
                )

            # Personal interno conserva su flujo actual.
            return redirect("lista_actividades")

    # =====================================================
    # GET - MOSTRAR FORMULARIO
    # =====================================================
    else:

        if tecnico_usuario and servicio_forzado:

            form = ActividadTecnicoForm(
                initial={
                    "tecnico": tecnico_usuario,
                    "cliente": servicio_forzado.cliente,
                    "servicio": servicio_forzado,
                    "tipo_actividad": (
                        servicio_forzado.tipo_servicio
                        if servicio_forzado.tipo_servicio
                        in dict(ActividadTecnico.TIPO_ACTIVIDAD)
                        else "CORRECTIVO"
                    ),
                    "fecha": timezone.localdate(),
                },
                exigir_envio=True,
            )
            form.fields["remision"].queryset = RemisionTecnico.objects.filter(
                tecnico=tecnico_usuario,
                cliente=servicio_forzado.cliente,
                servicio=servicio_forzado,
                estado="PENDIENTE",
            ).order_by("-fecha", "-id")

        else:
            form = ActividadTecnicoForm()

    return render(
        request,
        "actividades/nueva.html",
        {
            "form": form,
            "es_tecnico": bool(tecnico_usuario),
            "servicio_forzado": servicio_forzado,
        },
    )
