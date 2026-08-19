import csv
import os
from datetime import timedelta

import openpyxl

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.db.models.functions import TruncMonth
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from django.db.models import Q
from .forms import (
    NuevaLlamadaForm,
    GestionServicioForm,
    LevantamientoEquipoForm,
    BitacoraOperativaForm,
    RemisionTecnicoForm,
    DetalleRemisionFormSet,
    DetalleConciliacionFormSet,
    ActividadTecnicoForm,
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
)                    

from .utils import registrar_evento



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
            # GESTIÓN COMERCIAL
            # Auxiliar, Coordinador y Facturación
            # =========================================
            if es_usuario_gestion_comercial(user):
                return redirect("/gestion-comercial/")

            # Otros usuarios internos
            if user.is_staff:
                return redirect("/")

            # Usuarios cliente
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
    # GESTIÓN COMERCIAL
    # =========================================
    if es_usuario_gestion_comercial(request.user):
        return redirect("/gestion-comercial/")

    # Otros usuarios internos
    if request.user.is_staff:
        return render(request, "menu_principal.html")

    # Usuarios cliente
    return redirect("/mis-unidades/")

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
    # Con una sola unidad entra directamente.
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
        },
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
                "dashboard_cliente",
                cliente_id=equipo.cliente_id
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
    total_emergencias = Emergencia.objects.count()
    pendientes = Emergencia.objects.filter(estado="PENDIENTE").count()
    atendidas = Emergencia.objects.filter(estado="ATENDIDA").count()
    clientes = Cliente.objects.count()

    context = {
        "total_emergencias": total_emergencias,
        "pendientes": pendientes,
        "atendidas": atendidas,
        "clientes": clientes,
    }

    return render(request, "dashboard.html", context)


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
@login_required
def gestionar_servicio(request, servicio_id):
    servicio = get_object_or_404(
        Emergencia,
        id=servicio_id,
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

            return redirect("/centro-operaciones/")
    else:
        form = GestionServicioForm(instance=servicio)

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


# =========================================
# ACCIONES DEL SERVICIO
# =========================================
@login_required
def accion_servicio(request, servicio_id, accion):
    servicio = get_object_or_404(
        Emergencia,
        id=servicio_id,
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

        if accion in ["salida", "llegada", "reparando"]:
            servicio.estado = "EN_PROCESO"

        if accion == "terminado":
            servicio.estado = "ATENDIDA"

        servicio.save()

    return redirect(
        "gestionar_servicio",
        servicio_id=servicio.id,
    )
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

    if request.method == "POST":
        form = ActividadTecnicoForm(request.POST)

        if form.is_valid():
            actividad = form.save(commit=False)
            actividad.registrado_por = request.user
            actividad.save()

            # ==============================
            # ACCESORIOS UTILIZADOS
            # ==============================

            accesorios_ids = request.POST.getlist("accesorio_id[]")
            cantidades = request.POST.getlist("cantidad[]")
            es_otro_lista = request.POST.getlist("es_otro[]")
            descripciones_otro = request.POST.getlist("descripcion_otro[]")
            observaciones = request.POST.getlist("observacion[]")

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

                # Si la fila está completamente vacía, no hacemos nada.
                if not accesorio_id and not descripcion_otro:
                    continue

                # Si no hay cantidad, usamos 1.
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

            return redirect("lista_actividades")

    else:
        form = ActividadTecnicoForm()

    return render(
        request,
        "actividades/nueva.html",
        {
            "form": form,
        },
    )