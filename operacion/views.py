import csv
import os
from datetime import timedelta

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
from reportlab.pdfgen import canvas

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
            # GESTIÓN COMERCIAL
            # Auxiliar, Coordinador y Facturación
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
        ],
    )
    .select_related("cliente")
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
    ]:
        return HttpResponseForbidden(
            "Este mantenimiento preventivo ya no puede iniciarse."
        )

    # Si ya existe una actividad asociada, la reutilizamos.
    if programacion.actividad:

        actividad = programacion.actividad

    else:

        actividad = ActividadTecnico.objects.create(
            tecnico=tecnico,
            cliente=programacion.cliente,
            servicio=None,
            tipo_actividad="PREVENTIVO",
            fecha=timezone.localdate(),
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

            if programacion.estado == "EJECUTADO":
                return redirect(
                    "panel_tecnico"
                )

            if not actividad.hora_salida:
                actividad.hora_salida = timezone.localtime().time()

                actividad.save(
                    update_fields=[
                        "hora_salida",
                        "actualizado",
                    ]
                )

            programacion.estado = "EJECUTADO"

            programacion.save(
                update_fields=[
                    "estado",
                    "actualizado",
                ]
            )

            return redirect(
                "panel_tecnico"
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
        .filter(estado="EJECUTADO")
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
    elif not request.user.is_staff:
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
        estado="EJECUTADO",
    )

    # Técnico: solo puede consultar sus propios preventivos.
    if tecnico and programacion.tecnico_id != tecnico.id:
        return HttpResponseForbidden(
            "No está autorizado para consultar este mantenimiento."
        )

    # Usuario externo que no sea técnico ni personal interno.
    if not tecnico and not request.user.is_staff:
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
        estado="EJECUTADO",
    )

    # =====================================================
    # SEGURIDAD
    # =====================================================
    if tecnico_usuario:

        if programacion.tecnico_id != tecnico_usuario.id:
            return HttpResponseForbidden(
                "No está autorizado para generar este informe."
            )

    elif not request.user.is_staff:

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

    response["Content-Disposition"] = (
        f'attachment; filename="mantenimiento_preventivo_{programacion.id}.pdf"'
    )

    pdf = canvas.Canvas(
        response,
        pagesize=letter,
    )

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
                height - 88,
                width=75,
                height=50,
                preserveAspectRatio=True,
                mask="auto",
            )

        # Bloque corporativo
        pdf.setFillColorRGB(*azul)

        pdf.roundRect(
            125,
            height - 87,
            width - 165,
            50,
            5,
            fill=True,
            stroke=False,
        )

        pdf.setFillColorRGB(1, 1, 1)

        pdf.setFont(
            "Helvetica-Bold",
            12,
        )

        pdf.drawString(
            140,
            height - 58,
            "D&S SOLUCIONES EN BOMBEO S.A.S.",
        )

        pdf.setFont(
            "Helvetica",
            8.5,
        )

        pdf.drawString(
            140,
            height - 72,
            "SIGOB 7x24 - Sistema Integral de Gestión Operativa",
        )

        # Título
        pdf.setFillColorRGB(0, 0, 0)

        pdf.setFont(
            "Helvetica-Bold",
            15,
        )

        pdf.drawCentredString(
            width / 2,
            height - 118,
            "INFORME DE MANTENIMIENTO PREVENTIVO",
        )

        pdf.setStrokeColorRGB(*azul)

        pdf.setLineWidth(1)

        pdf.line(
            margen,
            height - 128,
            width - margen,
            height - 128,
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

        pdf.setFillColorRGB(0, 0, 0)

    def nueva_pagina():

        pie()
        pdf.showPage()
        encabezado()

        return height - 150

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
            y - 17,
            ancho_util,
            21,
            4,
            fill=True,
            stroke=False,
        )

        pdf.setFillColorRGB(1, 1, 1)

        pdf.setFont(
            "Helvetica-Bold",
            9.5,
        )

        pdf.drawString(
            margen + 9,
            y - 9,
            titulo,
        )

        pdf.setFillColorRGB(0, 0, 0)

        return y - 24

    def envolver_texto(
        texto,
        x,
        y,
        ancho,
        tamano=8.2,
        interlineado=10.5,
        fuente="Helvetica",
    ):

        texto = limpiar(texto)

        palabras = texto.split()
        linea = ""

        pdf.setFont(
            fuente,
            tamano,
        )

        for palabra in palabras:

            prueba = (
                f"{linea} {palabra}".strip()
            )

            if pdf.stringWidth(
                prueba,
                fuente,
                tamano,
            ) <= ancho:

                linea = prueba

            else:

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
                linea = palabra

        if linea:

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
            7.3,
        )

        pdf.drawString(
            x + 7,
            y - 11,
            label,
        )

        pdf.setFillColorRGB(0, 0, 0)

        pdf.setFont(
            "Helvetica-Bold",
            8.5,
        )

        valor = limpiar(valor)

        if len(valor) > 40:
            valor = valor[:37] + "..."

        pdf.drawString(
            x + 7,
            y - 25,
            valor,
        )

    def encabezado_tabla(
        columnas,
        x,
        y,
        anchos,
    ):

        altura = 20

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
            7.5,
        )

        posicion = x

        for titulo, ancho in zip(
            columnas,
            anchos,
        ):

            pdf.drawString(
                posicion + 5,
                y - 13,
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

        y = asegurar_espacio(
            y,
            alto + 5,
        )

        pdf.setStrokeColorRGB(
            0.85,
            0.87,
            0.90,
        )

        posicion = x

        for valor, ancho in zip(
            valores,
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
                7.5,
            )

            texto = limpiar(valor)

            max_chars = max(
                8,
                int(ancho / 4.5),
            )

            if len(texto) > max_chars:
                texto = (
                    texto[:max_chars - 3]
                    + "..."
                )

            pdf.drawString(
                posicion + 5,
                y - 14,
                texto,
            )

            posicion += ancho

        return y - alto

    # =====================================================
    # INICIO DOCUMENTO
    # =====================================================

    encabezado()

    y = height - 142

    # =====================================================
    # 1. INFORMACIÓN GENERAL
    # =====================================================

    y = seccion(
        "1. INFORMACIÓN GENERAL",
        y,
    )

    espacio = 10

    ancho_caja = (
        ancho_util - espacio
    ) / 2

    campo_caja(
        "UNIDAD / CLIENTE",
        programacion.cliente.nombre,
        margen,
        y,
        ancho_caja,
    )

    campo_caja(
        "TÉCNICO",
        programacion.tecnico.nombre,
        margen + ancho_caja + espacio,
        y,
        ancho_caja,
    )

    y -= 37

    campo_caja(
        "FECHA DEL MANTENIMIENTO",
        programacion.fecha_programada.strftime(
            "%d/%m/%Y"
        ),
        margen,
        y,
        ancho_caja,
    )

    campo_caja(
        "ESTADO",
        programacion.get_estado_display(),
        margen + ancho_caja + espacio,
        y,
        ancho_caja,
    )

    y -= 42

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

    campo_caja(
        "HORA DE LLEGADA",
        hora_llegada,
        margen,
        y,
        ancho_caja,
    )

    campo_caja(
        "HORA DE SALIDA",
        hora_salida,
        margen + ancho_caja + espacio,
        y,
        ancho_caja,
    )

    y -= 39

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

        # Revisión general compacta en tres columnas
    ancho_revision = (ancho_util - 16) / 3

    campos_revision = [
        ("Control de nivel", revision_control),
        ("Tablero eléctrico", revision_tablero),
        ("Novedades", novedades),
    ]

    x_revision = margen

    for titulo, valor in campos_revision:

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
            x_revision,
            y - 38,
            ancho_revision,
            34,
            4,
            fill=True,
            stroke=True,
        )

        pdf.setFillColorRGB(*azul)

        pdf.setFont(
            "Helvetica-Bold",
            7.5,
        )

        pdf.drawString(
            x_revision + 6,
            y - 13,
            titulo,
        )

        pdf.setFillColorRGB(0, 0, 0)

        pdf.setFont(
            "Helvetica",
            7.5,
        )

        texto = limpiar(valor)

        if len(texto) > 28:
            texto = texto[:25] + "..."

        pdf.drawString(
            x_revision + 6,
            y - 27,
            texto,
        )

        x_revision += ancho_revision + 8

    y -= 46
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
        "4. COMPONENTES HIDRÁULICOS",
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
    # 6. RECIBIDO DEL SERVICIO
    # =====================================================

    y = seccion(
        "6. RECIBIDO DEL SERVICIO",
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

    usuario_cliente = UsuarioCliente.objects.filter(user=user).first()

    if not usuario_cliente:
        return False

    # Mantiene compatibilidad con la unidad original.
    if usuario_cliente.cliente_id == cliente_id:
        return True

    # Comprueba las unidades adicionales asignadas.
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
def portal_unidades(request):

    # Personal interno:
    # puede consultar todas las unidades activas.
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

    usuario_cliente = UsuarioCliente.objects.filter(
        user=request.user,
    ).first()

    if not usuario_cliente:
        return HttpResponseForbidden(
            "Este usuario no tiene unidades asignadas."
        )

    clientes_ids = set()

    # Unidad original.
    if usuario_cliente.cliente_id:
        clientes_ids.add(usuario_cliente.cliente_id)

    # Unidades adicionales.
    clientes_asignados = ClienteAsignado.objects.filter(
        usuario_cliente=usuario_cliente,
        activo=True,
    ).values_list(
        "cliente_id",
        flat=True,
    )

    clientes_ids.update(clientes_asignados)

    clientes = Cliente.objects.filter(
        id__in=clientes_ids,
        activo=True,
    ).order_by("nombre")

    # Cliente con una sola unidad:
    # entra directamente a su dashboard.
    if clientes.count() == 1:
        cliente = clientes.first()

        return redirect(
            "dashboard_cliente",
            cliente_id=cliente.id,
        )

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

    return render(request, "nueva_llamada.html", {"form": form})
@login_required
def levantamiento_equipo(request):

    if request.method == "POST":
        form = LevantamientoEquipoForm(request.POST)

        if form.is_valid():
            equipo = form.save()

            return redirect(
                 "levantamiento_equipo"
                
            )

    else:
        form = LevantamientoEquipoForm(
            initial={
                "ultima_revision": timezone.now().date(),
                "fecha_levantamiento": timezone.now().date(),
            }
        )

    return render(
        request,
        "levantamiento_equipo.html",
        {
            "form": form,
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

    context = {
        "total_noche": total_noche,
        "solucionados": solucionados,
        "pendientes": pendientes,
        "en_proceso": en_proceso,
        "cerrados": cerrados,
        "servicios_revision": servicios_revision,
        "inicio_noche": inicio_noche,
        "fin_noche": fin_noche,
    }

    return render(request, "escritorio_coordinador.html", context)
# =========================================
# BITÁCORA OPERATIVA
# =========================================

@login_required
def lista_bitacora(request):

    registros = (
        BitacoraOperativa.objects
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
            "registros": registros,
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
        },
    )

@login_required
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
def editar_bitacora(request, bitacora_id):

    registro = get_object_or_404(
        BitacoraOperativa,
        id=bitacora_id,
    )

    if request.method == "POST":
        form = BitacoraOperativaForm(
            request.POST,
            instance=registro,
        )

        if form.is_valid():
            form.save()
            return redirect("lista_bitacora")

    else:
        form = BitacoraOperativaForm(
            instance=registro,
        )

    return render(
        request,
        "bitacora/formulario.html",
        {
            "form": form,
            "registro": registro,
            "titulo_pagina": "Editar novedad",
        },
    )
# =========================================
# REMISIONES DE TÉCNICOS
# =========================================

@login_required
def lista_remisiones(request):

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
@login_required
def conciliar_remision(request, remision_id):

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

    return render(request, "dashboard_cliente.html", context)


# =========================================
# HOJA DE VIDA HTML
# =========================================
@login_required
def hoja_vida(request, cliente_id):
    cliente = get_object_or_404(Cliente, id=cliente_id)

    equipos = EquipoUnidad.objects.filter(cliente=cliente)
    tanques = TanqueUnidad.objects.filter(cliente=cliente)
    distribuciones = DistribucionUnidad.objects.filter(cliente=cliente)

    context = {
        "cliente": cliente,
        "equipos": equipos,
        "tanques": tanques,
        "distribuciones": distribuciones,
    }

    return render(request, "hoja_vida.html", context)


# =========================================
# HOJA DE VIDA PDF
# =========================================
@login_required
def hoja_vida_pdf(request, cliente_id):
    cliente = get_object_or_404(Cliente, id=cliente_id)

    equipos = EquipoUnidad.objects.filter(cliente=cliente)
    tanques = TanqueUnidad.objects.filter(cliente=cliente)
    distribuciones = DistribucionUnidad.objects.filter(cliente=cliente)

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
    fila_texto("Equipos:", equipos.count(), 40, y)
    fila_texto("Tanques:", tanques.count(), 200, y)
    fila_texto(
        "Distribuciones:",
        distribuciones.count(),
        360,
        y,
    )
    y -= 30

    y = seccion("EQUIPOS INSTALADOS", y)

    pdf.setFont("Helvetica-Bold", 8)
    columnas = [40, 145, 210, 275, 340, 405, 480]
    headers = [
        "Tipo",
        "Marca",
        "Modelo",
        "Potencia",
        "Voltaje",
        "Cantidad",
        "Estado",
    ]

    for x, header in zip(columnas, headers):
        pdf.drawString(x, y, header)

    y -= 10
    pdf.line(40, y, width - 40, y)
    y -= 12

    pdf.setFont("Helvetica", 8)

    for equipo in equipos:
        if y < 70:
            y = nueva_pagina()

        pdf.drawString(
            40,
            y,
            str(equipo.get_tipo_display() or "-")[:22],
        )
        pdf.drawString(
            145,
            y,
            str(equipo.marca or "-")[:12],
        )
        pdf.drawString(
            210,
            y,
            str(equipo.modelo or "-")[:12],
        )
        pdf.drawString(
            275,
            y,
            str(equipo.potencia or "-")[:12],
        )
        pdf.drawString(
            340,
            y,
            str(equipo.voltaje or "-")[:10],
        )
        pdf.drawString(
            405,
            y,
            str(equipo.cantidad or "-"),
        )
        pdf.drawString(
            480,
            y,
            str(equipo.get_estado_display() or "-")[:18],
        )
        y -= 14

    y -= 18
    y = seccion("TANQUES", y)

    pdf.setFont("Helvetica-Bold", 8)
    columnas = [40, 180, 255, 330, 430]
    headers = [
        "Tipo",
        "Material",
        "Capacidad",
        "Ubicación",
        "Cantidad",
    ]

    for x, header in zip(columnas, headers):
        pdf.drawString(x, y, header)

    y -= 10
    pdf.line(40, y, width - 40, y)
    y -= 12

    pdf.setFont("Helvetica", 8)

    for tanque in tanques:
        if y < 70:
            y = nueva_pagina()

        pdf.drawString(
            40,
            y,
            str(tanque.get_tipo_tanque_display() or "-")[:28],
        )
        pdf.drawString(
            180,
            y,
            str(tanque.material or "-")[:14],
        )
        pdf.drawString(
            255,
            y,
            str(tanque.capacidad or "-")[:14],
        )
        pdf.drawString(
            330,
            y,
            str(tanque.ubicacion or "-")[:18],
        )
        pdf.drawString(
            430,
            y,
            str(tanque.cantidad or "-"),
        )
        y -= 14

    y -= 18
    y = seccion("DISTRIBUCIÓN", y)

    pdf.setFont("Helvetica-Bold", 8)
    columnas = [40, 110, 190, 290, 400]
    headers = [
        "Torre",
        "Pisos",
        "Presión",
        "Gravedad",
        "Observaciones",
    ]

    for x, header in zip(columnas, headers):
        pdf.drawString(x, y, header)

    y -= 10
    pdf.line(40, y, width - 40, y)
    y -= 12

    pdf.setFont("Helvetica", 8)

    for distribucion in distribuciones:
        if y < 70:
            y = nueva_pagina()

        pdf.drawString(
            40,
            y,
            str(distribucion.torre or "-")[:10],
        )
        pdf.drawString(
            110,
            y,
            str(distribucion.cantidad_pisos or "-"),
        )
        pdf.drawString(
            190,
            y,
            f"{distribucion.presion_desde or '-'} - "
            f"{distribucion.presion_hasta or '-'}",
        )
        pdf.drawString(
            290,
            y,
            f"{distribucion.gravedad_desde or '-'} - "
            f"{distribucion.gravedad_hasta or '-'}",
        )
        pdf.drawString(
            400,
            y,
            str(distribucion.observaciones or "-")[:26],
        )
        y -= 14

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
        )

        if form.is_valid():

            servicio = form.save()

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
        "gestionar_servicio",
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
def casos_por_cliente(request):
    cliente_id = request.GET.get("cliente_id")

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
def remisiones_por_cliente(request):
    cliente_id = request.GET.get("cliente_id")
    servicio_id = request.GET.get("servicio_id")

    if not cliente_id:
        return JsonResponse({"remisiones": []})

    remisiones = RemisionTecnico.objects.filter(
        cliente_id=cliente_id
    )

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

    return JsonResponse({"casos": datos})

@login_required
def buscar_accesorios(request):
    texto = request.GET.get("q", "").strip()

    if len(texto) < 2:
        return JsonResponse({"resultados": []})

    accesorios = (
        Accesorio.objects
        .filter(
            descripcion__icontains=texto,
            activo=True,
        )
        .order_by("descripcion")[:20]
    )

    resultados = [
        {
            "id": accesorio.id,
            "descripcion": accesorio.descripcion,
        }
        for accesorio in accesorios
    ]

    return JsonResponse({
        "resultados": resultados,
    })
@login_required
def actividades_por_cliente(request):
    cliente_id = request.GET.get("cliente_id")
    servicio_id = request.GET.get("servicio_id")

    if not cliente_id:
        return JsonResponse({"actividades": []})

    actividades = (
        ActividadTecnico.objects
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
def detalle_actividad(request, actividad_id):

    actividad = get_object_or_404(
        ActividadTecnico.objects
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

@login_required
def nueva_actividad(request):

    # Técnico asociado al usuario conectado, si existe.
    tecnico_usuario = Tecnico.objects.filter(
        user=request.user,
        activo=True,
    ).first()

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

        form = ActividadTecnicoForm(datos_post)

        if form.is_valid():

            actividad = form.save(commit=False)

            # Seguridad adicional:
            # volvemos a imponer estos datos antes de guardar.
            if tecnico_usuario:
                actividad.tecnico = tecnico_usuario
                actividad.cliente = servicio_forzado.cliente
                actividad.servicio = servicio_forzado

            actividad.registrado_por = request.user
            actividad.save()

            # =================================================
            # ACCESORIOS UTILIZADOS
            # =================================================
            accesorios_ids = request.POST.getlist(
                "accesorio_id[]"
            )
            cantidades = request.POST.getlist(
                "cantidad[]"
            )
            es_otro_lista = request.POST.getlist(
                "es_otro[]"
            )
            descripciones_otro = request.POST.getlist(
                "descripcion_otro[]"
            )
            observaciones = request.POST.getlist(
                "observacion[]"
            )

            total_filas = max(
                len(accesorios_ids),
                len(cantidades),
                len(es_otro_lista),
                len(descripciones_otro),
                len(observaciones),
                0,
            )

            for i in range(total_filas):

                accesorio_id = (
                    accesorios_ids[i]
                    if i < len(accesorios_ids)
                    else ""
                )

                cantidad = (
                    cantidades[i]
                    if i < len(cantidades)
                    else ""
                )

                es_otro = (
                    es_otro_lista[i] == "1"
                    if i < len(es_otro_lista)
                    else False
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

                # Fila completamente vacía.
                if not accesorio_id and not descripcion_otro:
                    continue

                if not cantidad:
                    cantidad = 1

                if es_otro:

                    AccesorioActividad.objects.create(
                        actividad=actividad,
                        accesorio=None,
                        es_otro=True,
                        descripcion_otro=descripcion_otro,
                        cantidad=cantidad,
                        observacion=observacion,
                    )

                else:

                    accesorio = get_object_or_404(
                        Accesorio,
                        id=accesorio_id,
                    )

                    AccesorioActividad.objects.create(
                        actividad=actividad,
                        accesorio=accesorio,
                        es_otro=False,
                        descripcion_otro="",
                        cantidad=cantidad,
                        observacion=observacion,
                    )

            # Técnico vuelve al servicio que estaba atendiendo.
            if tecnico_usuario:
                return redirect(
                    "servicio_tecnico",
                    servicio_id=servicio_forzado.id,
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
                }
            )

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