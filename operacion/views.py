import csv
import os
from datetime import timedelta

import openpyxl

from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.http import HttpResponse, HttpResponseForbidden
from django.utils import timezone
from django.db.models import Count
from django.db.models.functions import TruncMonth

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from .forms import NuevaLlamadaForm, GestionServicioForm

from .models import (
    Cliente,
    Emergencia,
    EquipoUnidad,
    CotizacionEquipo,
    UsuarioCliente,
    TanqueUnidad,
    DistribucionUnidad,
)


# =========================================
# LOGIN
# =========================================
def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)

            if user.is_staff:
                return redirect("/gerencia/")

            uc = UsuarioCliente.objects.filter(user=user).first()
            if uc:
                return redirect(f"/cliente/{uc.cliente.id}/")

            return redirect("/")

        return render(request, "login.html", {
            "error": "Usuario o contraseña incorrectos"
        })

    return render(request, "login.html")


# =========================================
# LOGOUT
# =========================================
def logout_view(request):
    logout(request)
    return redirect("/login/")


# =========================================
# HOME
# =========================================
@login_required
def home(request):
    if request.user.is_staff:
        return redirect("/gerencia/")

    uc = UsuarioCliente.objects.filter(user=request.user).first()
    if uc:
        return redirect(f"/cliente/{uc.cliente.id}/")

    return redirect("/login/")

@login_required
def nueva_llamada(request):

    if request.method == "POST":
        form = NuevaLlamadaForm(request.POST)

        if form.is_valid():
            servicio = form.save()
            return redirect("/centro-operaciones/")

    else:
        form = NuevaLlamadaForm()

    return render(request, "nueva_llamada.html", {"form": form})
# =========================================
# DASHBOARD GERENCIAL
# =========================================
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

@login_required
def centro_operaciones(request):

    ahora = timezone.now()
    hoy = ahora.date()
    ayer = hoy - timedelta(days=1)

    inicio_noche = timezone.datetime.combine(
        ayer,
        timezone.datetime.min.time()
    ).replace(hour=17, minute=0)

    fin_noche = timezone.datetime.combine(
        hoy,
        timezone.datetime.min.time()
    ).replace(hour=7, minute=0)

    inicio_noche = timezone.make_aware(inicio_noche)
    fin_noche = timezone.make_aware(fin_noche)

    servicios = Emergencia.objects.all().order_by("-fecha_llamada")

    servicios_noche = Emergencia.objects.filter(
        fecha_llamada__gte=inicio_noche,
        fecha_llamada__lte=fin_noche
    )

    bandeja_cotizacion = servicios.filter(requiere_cotizacion=True).exclude(estado="CERRADA")
    bandeja_regreso = servicios.filter(requiere_regreso=True).exclude(estado="CERRADA")
    bandeja_llamar_cliente = servicios.filter(estado="ATENDIDA").filter(cliente_conforme__isnull=True)
    bandeja_no_conforme = servicios.filter(cliente_conforme=False).exclude(estado="CERRADA")

    context = {
        "total": servicios.count(),
        "pendientes": servicios.filter(estado="PENDIENTE").count(),
        "en_proceso": servicios.filter(estado="EN_PROCESO").count(),
        "atendidas": servicios.filter(estado="ATENDIDA").count(),
        "cerradas": servicios.filter(estado="CERRADA").count(),
        "ultimos_servicios": servicios[:20],

        "total_noche": servicios_noche.count(),
        "solucionados_noche": servicios_noche.filter(estado="ATENDIDA").count(),
        "pendientes_noche": servicios_noche.filter(estado="PENDIENTE").count(),
        "cerrados_noche": servicios_noche.filter(estado="CERRADA").count(),
        "en_proceso_noche": servicios_noche.filter(estado="EN_PROCESO").count(),

        "inicio_noche": inicio_noche,
        "fin_noche": fin_noche,

        "bandeja_cotizacion": bandeja_cotizacion[:5],
        "bandeja_regreso": bandeja_regreso[:5],
        "bandeja_llamar_cliente": bandeja_llamar_cliente[:5],
        "bandeja_no_conforme": bandeja_no_conforme[:5],

        "total_bandeja": (
            bandeja_cotizacion.count()
            + bandeja_regreso.count()
            + bandeja_llamar_cliente.count()
            + bandeja_no_conforme.count()
        ),
    }

    return render(request, "centro_operaciones.html", context)
@login_required
def escritorio_coordinador(request):

    ahora = timezone.now()
    hoy = ahora.date()
    ayer = hoy - timedelta(days=1)

    inicio_noche = timezone.datetime.combine(
        ayer,
        timezone.datetime.min.time()
    ).replace(hour=17, minute=0)

    fin_noche = timezone.datetime.combine(
        hoy,
        timezone.datetime.min.time()
    ).replace(hour=7, minute=0)

    inicio_noche = timezone.make_aware(inicio_noche)
    fin_noche = timezone.make_aware(fin_noche)

    servicios_noche = Emergencia.objects.filter(
        fecha_llamada__gte=inicio_noche,
        fecha_llamada__lte=fin_noche
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
# DASHBOARD CLIENTE
# =========================================
@login_required
def dashboard_cliente(request, cliente_id):
    if not request.user.is_staff:
        uc = UsuarioCliente.objects.filter(user=request.user).first()
        if not uc or uc.cliente.id != cliente_id:
            return HttpResponseForbidden("No autorizado")

    cliente = get_object_or_404(Cliente, id=cliente_id)

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
        fecha_llamada__month=hoy_dt.month
    ).count()

    cotizaciones = CotizacionEquipo.objects.filter(
        equipo__cliente=cliente
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

    data_dict = {x["mes"].strftime("%Y-%m"): x["total"] for x in qs}

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
        "labels_estado": ["Operativos", "En reparación", "Fuera de servicio"],
        "data_estado": [operativos_count, reparacion_count, fuera_count],
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

    logo = os.path.join(settings.BASE_DIR, "static", "img", "logo_dys.png")

    def encabezado():
        if os.path.exists(logo):
            pdf.drawImage(
                logo,
                40,
                height - 90,
                width=80,
                height=60,
                preserveAspectRatio=True
            )

        pdf.setFillColorRGB(0.0, 0.20, 0.40)
        pdf.rect(0, height - 120, width, 35, fill=True, stroke=False)

        pdf.setFillColorRGB(1, 1, 1)
        pdf.setFont("Helvetica-Bold", 13)
        pdf.drawString(140, height - 105, "D&S SOLUCIONES EN BOMBEO S.A.S.")

        pdf.setFillColorRGB(0, 0, 0)
        pdf.setFont("Helvetica-Bold", 16)
        pdf.drawString(190, height - 150, "HOJA DE VIDA TÉCNICA")

    def pie():
        pdf.setFont("Helvetica", 8)
        pdf.setFillColorRGB(0.35, 0.35, 0.35)
        pdf.drawString(40, 35, "Sistema 7x24 - Reporte generado automáticamente")
        pdf.drawRightString(width - 40, 35, "D&S Soluciones en Bombeo S.A.S.")

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
    fila_texto("Contrato:", cliente.get_tipo_contrato_display(), 330, y)
    y -= 16
    fila_texto("Dirección:", cliente.direccion, 40, y)
    y -= 16
    fila_texto("Administrador:", cliente.administrador, 40, y)
    fila_texto("Teléfono:", cliente.telefono_porteria, 330, y)
    y -= 28

    y = seccion("RESUMEN EJECUTIVO", y)
    fila_texto("Equipos:", equipos.count(), 40, y)
    fila_texto("Tanques:", tanques.count(), 200, y)
    fila_texto("Distribuciones:", distribuciones.count(), 360, y)
    y -= 30

    y = seccion("EQUIPOS INSTALADOS", y)

    pdf.setFont("Helvetica-Bold", 8)
    columnas = [40, 145, 210, 275, 340, 405, 480]
    headers = ["Tipo", "Marca", "Modelo", "Potencia", "Voltaje", "Cantidad", "Estado"]

    for x, h in zip(columnas, headers):
        pdf.drawString(x, y, h)

    y -= 10
    pdf.line(40, y, width - 40, y)
    y -= 12

    pdf.setFont("Helvetica", 8)

    for e in equipos:
        if y < 70:
            y = nueva_pagina()

        pdf.drawString(40, y, str(e.get_tipo_display() or "-")[:22])
        pdf.drawString(145, y, str(e.marca or "-")[:12])
        pdf.drawString(210, y, str(e.modelo or "-")[:12])
        pdf.drawString(275, y, str(e.potencia or "-")[:12])
        pdf.drawString(340, y, str(e.voltaje or "-")[:10])
        pdf.drawString(405, y, str(e.cantidad or "-"))
        pdf.drawString(480, y, str(e.get_estado_display() or "-")[:18])
        y -= 14

    y -= 18

    y = seccion("TANQUES", y)

    pdf.setFont("Helvetica-Bold", 8)
    columnas = [40, 180, 255, 330, 430]
    headers = ["Tipo", "Material", "Capacidad", "Ubicación", "Cantidad"]

    for x, h in zip(columnas, headers):
        pdf.drawString(x, y, h)

    y -= 10
    pdf.line(40, y, width - 40, y)
    y -= 12

    pdf.setFont("Helvetica", 8)

    for t in tanques:
        if y < 70:
            y = nueva_pagina()

        pdf.drawString(40, y, str(t.get_tipo_tanque_display() or "-")[:28])
        pdf.drawString(180, y, str(t.material or "-")[:14])
        pdf.drawString(255, y, str(t.capacidad or "-")[:14])
        pdf.drawString(330, y, str(t.ubicacion or "-")[:18])
        pdf.drawString(430, y, str(t.cantidad or "-"))
        y -= 14

    y -= 18

    y = seccion("DISTRIBUCIÓN", y)

    pdf.setFont("Helvetica-Bold", 8)
    columnas = [40, 110, 190, 290, 400]
    headers = ["Torre", "Pisos", "Presión", "Gravedad", "Observaciones"]

    for x, h in zip(columnas, headers):
        pdf.drawString(x, y, h)

    y -= 10
    pdf.line(40, y, width - 40, y)
    y -= 12

    pdf.setFont("Helvetica", 8)

    for d in distribuciones:
        if y < 70:
            y = nueva_pagina()

        pdf.drawString(40, y, str(d.torre or "-")[:10])
        pdf.drawString(110, y, str(d.cantidad_pisos or "-"))
        pdf.drawString(190, y, f"{d.presion_desde or '-'} - {d.presion_hasta or '-'}")
        pdf.drawString(290, y, f"{d.gravedad_desde or '-'} - {d.gravedad_hasta or '-'}")
        pdf.drawString(400, y, str(d.observaciones or "-")[:26])
        y -= 14

    pie()
    pdf.save()

    return response

@login_required
def gestionar_servicio(request, servicio_id):

    servicio = get_object_or_404(Emergencia, id=servicio_id)

    if request.method == "POST":
        form = GestionServicioForm(request.POST, instance=servicio)

        if form.is_valid():
            form.save()
            return redirect("/centro-operaciones/")

    else:
        form = GestionServicioForm(instance=servicio)

    return render(request, "gestionar_servicio.html", {
        "servicio": servicio,
        "form": form,
    })
# =========================================
# EXPORTAR CSV
# =========================================
@login_required
def export_csv(request, cliente_id):
    cliente = get_object_or_404(Cliente, id=cliente_id)
    equipos = EquipoUnidad.objects.filter(cliente=cliente)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="equipos.csv"'

    writer = csv.writer(response)
    writer.writerow(["Tipo", "Cantidad", "Estado"])

    for e in equipos:
        writer.writerow([
            e.get_tipo_display(),
            e.cantidad,
            e.get_estado_display()
        ])

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

    for e in equipos:
        ws.append([
            e.get_tipo_display(),
            e.cantidad,
            e.get_estado_display()
        ])

    response = HttpResponse(content_type="application/ms-excel")
    response["Content-Disposition"] = 'attachment; filename="equipos.xlsx"'

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
    response["Content-Disposition"] = f'attachment; filename="reporte_{cliente.nombre}.pdf"'

    p = canvas.Canvas(response, pagesize=letter)

    y = 750

    p.setFont("Helvetica-Bold", 16)
    p.drawString(200, y, "INFORME TECNICO")

    y -= 40

    p.setFont("Helvetica", 11)
    p.drawString(50, y, f"Cliente: {cliente.nombre}")

    y -= 20
    p.drawString(50, y, f"Dirección: {cliente.direccion}")

    y -= 30

    p.setFont("Helvetica-Bold", 10)
    p.drawString(50, y, "Equipo")
    p.drawString(200, y, "Cantidad")
    p.drawString(300, y, "Estado")

    y -= 15

    p.setFont("Helvetica", 10)

    for e in equipos:
        p.drawString(50, y, e.get_tipo_display())
        p.drawString(200, y, str(e.cantidad))
        p.drawString(300, y, e.get_estado_display())
        y -= 15

        if y < 100:
            p.showPage()
            p.setFont("Helvetica", 10)
            y = 750

    y -= 40
    p.setFont("Helvetica", 9)
    p.drawString(50, y, "Sistema D&S - Reporte generado automáticamente")

    p.save()
    return response