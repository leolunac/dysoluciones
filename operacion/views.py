from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.http import HttpResponseForbidden
from django.utils import timezone

from datetime import timedelta
from django.db.models import Count
from django.db.models.functions import TruncMonth

from .models import Cliente, Emergencia, EquipoUnidad, CotizacionEquipo, UsuarioCliente
import csv
from django.http import HttpResponse
import openpyxl
from django.http import HttpResponse
from reportlab.pdfgen import canvas


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

    # Equipos
    equipos = EquipoUnidad.objects.filter(cliente=cliente)

    total_equipos = equipos.count()
    operativos = equipos.filter(estado="OPERATIVO").count()
    fuera_servicio = equipos.exclude(estado="OPERATIVO").count()
    equipos_fuera = equipos.exclude(estado="OPERATIVO")

    # 🔥 GRAFICA ESTADOS
    operativos_count = equipos.filter(estado="OPERATIVO").count()
    reparacion_count = equipos.filter(estado="EN_REPARACION").count()
    fuera_count = equipos.filter(estado="FUERA_SERVICIO").count()

    # Emergencias del mes
    hoy_dt = timezone.now()
    emergencias_mes = Emergencia.objects.filter(
        cliente=cliente,
        fecha_llamada__year=hoy_dt.year,
        fecha_llamada__month=hoy_dt.month
    ).count()

    # Cotizaciones
    cotizaciones = CotizacionEquipo.objects.filter(
        equipo__cliente=cliente
    ).order_by("-creado_en")[:10]

    # Gráfica mensual
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

        # 🔥 NUEVO
        "labels_estado": ["Operativos", "En reparación", "Fuera de servicio"],
        "data_estado": [operativos_count, reparacion_count, fuera_count],
    }

    return render(request, "dashboard_cliente.html", context)

# =========================================
# EXPORTAR CSV
# =========================================
def export_csv(request, cliente_id):

    cliente = Cliente.objects.get(id=cliente_id)
    equipos = EquipoUnidad.objects.filter(cliente=cliente)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="equipos.csv"'

    writer = csv.writer(response)
    writer.writerow(['Tipo', 'Cantidad', 'Estado'])

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
def export_excel(request, cliente_id):

    cliente = Cliente.objects.get(id=cliente_id)
    equipos = EquipoUnidad.objects.filter(cliente=cliente)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Equipos"

    ws.append(['Tipo', 'Cantidad', 'Estado'])

    for e in equipos:
        ws.append([
            e.get_tipo_display(),
            e.cantidad,
            e.get_estado_display()
        ])

    response = HttpResponse(content_type='application/ms-excel')
    response['Content-Disposition'] = 'attachment; filename="equipos.xlsx"'

    wb.save(response)
    return response

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from django.http import HttpResponse

def reporte_pdf(request, cliente_id):

    cliente = Cliente.objects.get(id=cliente_id)
    equipos = EquipoUnidad.objects.filter(cliente=cliente)

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="reporte_{cliente.nombre}.pdf"'

    p = canvas.Canvas(response, pagesize=letter)

    y = 750

    # =========================
    # TITULO
    # =========================
    p.setFont("Helvetica-Bold", 16)
    p.drawString(200, y, "INFORME TECNICO")

    y -= 40

    # =========================
    # DATOS CLIENTE
    # =========================
    p.setFont("Helvetica", 11)
    p.drawString(50, y, f"Cliente: {cliente.nombre}")

    y -= 20
    p.drawString(50, y, f"Dirección: {cliente.direccion}")

    y -= 30

    # =========================
    # ENCABEZADO TABLA
    # =========================
    p.setFont("Helvetica-Bold", 10)
    p.drawString(50, y, "Equipo")
    p.drawString(200, y, "Cantidad")
    p.drawString(300, y, "Estado")

    y -= 15

    # =========================
    # DATOS TABLA
    # =========================
    p.setFont("Helvetica", 10)

    for e in equipos:
        p.drawString(50, y, e.get_tipo_display())
        p.drawString(200, y, str(e.cantidad))
        p.drawString(300, y, e.get_estado_display())

        y -= 15

        # salto de página automático
        if y < 100:
            p.showPage()
            p.setFont("Helvetica", 10)
            y = 750

    # =========================
    # PIE DE PAGINA
    # =========================
    y -= 40
    p.setFont("Helvetica", 9)
    p.drawString(50, y, "Sistema 7x24 - Reporte generado automáticamente")

    p.save()

    return response
