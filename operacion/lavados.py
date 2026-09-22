from calendar import month_name
from datetime import date, datetime, time, timedelta

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import ActividadTecnico, Cliente, Emergencia, LavadoTanque, Tecnico


GRUPOS_CONSULTA = {
    "GESTION_COORDINADOR",
    "GESTION_SUPERVISOR",
    "GESTION_GERENCIA",
}
GRUPOS_GESTION = {"GESTION_COORDINADOR", "GESTION_SUPERVISOR"}


def _tiene_grupo(user, grupos):
    return user.is_superuser or user.groups.filter(name__in=grupos).exists()


def puede_ver_lavados(user):
    return user.is_authenticated and user.is_active and _tiene_grupo(user, GRUPOS_CONSULTA)


def puede_gestionar_lavados(user):
    return user.is_authenticated and user.is_active and _tiene_grupo(user, GRUPOS_GESTION)


class ProgramarLavadoForm(forms.Form):
    cliente = forms.ModelChoiceField(
        queryset=Cliente.objects.none(),
        label="Unidad / cliente",
    )
    fecha_programada = forms.DateField(
        label="Fecha programada",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    tecnico = forms.ModelChoiceField(
        queryset=Tecnico.objects.none(),
        required=False,
        label="Técnico (opcional)",
        help_text="Puede programarse primero y asignar el técnico después.",
    )
    observaciones = forms.CharField(
        required=False,
        label="Observaciones",
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cliente"].queryset = Cliente.objects.filter(activo=True).order_by("nombre")
        self.fields["tecnico"].queryset = Tecnico.objects.filter(activo=True).order_by("nombre")

    def clean(self):
        datos = super().clean()
        cliente = datos.get("cliente")
        fecha = datos.get("fecha_programada")
        if cliente and fecha:
            pendientes = LavadoTanque.objects.filter(cliente=cliente, ejecutado=False)
            if pendientes.exists():
                self.add_error("cliente", "Esta unidad ya tiene un lavado pendiente o programado.")
            if LavadoTanque.objects.filter(cliente=cliente, fecha_programada=fecha).exists():
                self.add_error("fecha_programada", "Ya existe una programación para esta unidad y fecha.")
        return datos


def _fecha_atencion(fecha):
    valor = datetime.combine(fecha, time(hour=8))
    return timezone.make_aware(valor, timezone.get_current_timezone())


def _crear_servicio(programacion, tecnico):
    if not tecnico:
        return None
    servicio = Emergencia.objects.create(
        cliente=programacion.cliente,
        tecnico=tecnico,
        tipo_servicio="LAVADO",
        fecha_atencion=_fecha_atencion(programacion.fecha_vigente),
        descripcion_falla="Lavado de tanques programado desde el tablero de lavados.",
        estado="PENDIENTE",
        recibido_por="Tablero de lavados",
    )
    programacion.servicio = servicio
    programacion.save(update_fields=["servicio", "actualizado_en"])
    return servicio


@login_required
def tablero_lavados(request):
    if not puede_ver_lavados(request.user):
        return HttpResponseForbidden("No está autorizado para consultar el tablero de lavados.")

    hoy = timezone.localdate()
    try:
        anio = int(request.GET.get("anio", hoy.year))
    except (TypeError, ValueError):
        anio = hoy.year
    buscar = request.GET.get("buscar", "").strip()
    estado = request.GET.get("estado", "").strip()

    qs = LavadoTanque.objects.select_related(
        "cliente", "servicio", "servicio__tecnico", "actividad"
    ).all()
    if buscar:
        qs = qs.filter(
            Q(cliente__nombre__icontains=buscar)
            | Q(cliente__nit__icontains=buscar)
            | Q(servicio__tecnico__nombre__icontains=buscar)
        )

    programaciones = []
    for lavado in qs:
        fecha_vigente = lavado.fecha_vigente
        if lavado.ejecutado:
            estado_calculado = "EJECUTADO"
        elif fecha_vigente < hoy:
            estado_calculado = "VENCIDO"
        elif lavado.reprogramado:
            estado_calculado = "REPROGRAMADO"
        elif fecha_vigente <= hoy + timedelta(days=30):
            estado_calculado = "PROXIMO"
        else:
            estado_calculado = "PROGRAMADO"
        lavado.estado_calculado = estado_calculado
        lavado.fecha_tablero = fecha_vigente
        if not estado or estado == estado_calculado:
            programaciones.append(lavado)
    programaciones.sort(key=lambda item: (item.fecha_tablero, item.cliente.nombre))

    historico = ActividadTecnico.objects.filter(
        tipo_actividad="LAVADO", fecha__year=anio
    ).select_related("cliente", "tecnico", "servicio").order_by("-fecha", "-id")
    if buscar:
        historico = historico.filter(
            Q(cliente__nombre__icontains=buscar)
            | Q(tecnico__nombre__icontains=buscar)
            | Q(numero_informe__icontains=buscar)
        )

    todos = list(qs)
    ejecutados_anio = ActividadTecnico.objects.filter(
        tipo_actividad="LAVADO", fecha__year=anio
    ).count()
    vencidos = sum(1 for item in todos if not item.ejecutado and item.fecha_vigente < hoy)
    proximos = sum(
        1 for item in todos
        if not item.ejecutado and hoy <= item.fecha_vigente <= hoy + timedelta(days=30)
    )
    pendientes = sum(1 for item in todos if not item.ejecutado)
    reprogramados = sum(1 for item in todos if item.reprogramado and not item.ejecutado)
    meses = []
    for mes in range(1, 13):
        total = ActividadTecnico.objects.filter(
            tipo_actividad="LAVADO", fecha__year=anio, fecha__month=mes
        ).count()
        meses.append({"numero": mes, "nombre": month_name[mes][:3], "total": total})

    return render(request, "lavados/tablero.html", {
        "programaciones": programaciones,
        "historico": historico[:100],
        "form": ProgramarLavadoForm(),
        "puede_gestionar": puede_gestionar_lavados(request.user),
        "buscar": buscar,
        "estado": estado,
        "anio": anio,
        "anios": range(hoy.year, hoy.year - 6, -1),
        "pendientes": pendientes,
        "proximos": proximos,
        "vencidos": vencidos,
        "reprogramados": reprogramados,
        "ejecutados_anio": ejecutados_anio,
        "meses": meses,
        "max_mensual": max([item["total"] for item in meses] + [1]),
        "tecnicos": Tecnico.objects.filter(activo=True).order_by("nombre"),
    })


@login_required
@require_POST
@transaction.atomic
def programar_lavado(request):
    if not puede_gestionar_lavados(request.user):
        return HttpResponseForbidden("No está autorizado para programar lavados.")
    form = ProgramarLavadoForm(request.POST)
    if not form.is_valid():
        for errores in form.errors.values():
            for error in errores:
                messages.error(request, error)
        return redirect("tablero_lavados")
    lavado = LavadoTanque.objects.create(
        cliente=form.cleaned_data["cliente"],
        fecha_programada=form.cleaned_data["fecha_programada"],
        motivo_no_ejecucion=form.cleaned_data["observaciones"],
        creado_por=request.user,
    )
    _crear_servicio(lavado, form.cleaned_data["tecnico"])
    messages.success(request, "El lavado fue programado correctamente.")
    return redirect("tablero_lavados")


@login_required
@require_POST
@transaction.atomic
def gestionar_lavado(request, lavado_id):
    if not puede_gestionar_lavados(request.user):
        return HttpResponseForbidden("No está autorizado para gestionar lavados.")
    lavado = get_object_or_404(LavadoTanque, pk=lavado_id)
    if lavado.ejecutado:
        messages.error(request, "Un lavado ejecutado no puede reprogramarse ni reasignarse.")
        return redirect("tablero_lavados")
    accion = request.POST.get("accion")
    if accion == "asignar":
        tecnico = get_object_or_404(Tecnico, pk=request.POST.get("tecnico"), activo=True)
        if lavado.servicio_id:
            lavado.servicio.tecnico = tecnico
            lavado.servicio.fecha_atencion = _fecha_atencion(lavado.fecha_vigente)
            lavado.servicio.save(update_fields=["tecnico", "fecha_atencion"])
        else:
            _crear_servicio(lavado, tecnico)
        messages.success(request, "El técnico fue asignado correctamente.")
    elif accion == "reprogramar":
        try:
            nueva_fecha = date.fromisoformat(request.POST.get("fecha_reprogramada", ""))
        except ValueError:
            messages.error(request, "Seleccione una fecha válida para reprogramar.")
            return redirect("tablero_lavados")
        motivo = request.POST.get("motivo_reprogramacion", "").strip()
        if not motivo:
            messages.error(request, "Debe indicar el motivo de la reprogramación.")
            return redirect("tablero_lavados")
        lavado.reprogramado = True
        lavado.fecha_reprogramada = nueva_fecha
        lavado.motivo_reprogramacion = motivo
        lavado.save(update_fields=[
            "reprogramado", "fecha_reprogramada", "motivo_reprogramacion", "actualizado_en"
        ])
        if lavado.servicio_id:
            lavado.servicio.fecha_atencion = _fecha_atencion(nueva_fecha)
            lavado.servicio.save(update_fields=["fecha_atencion"])
        messages.success(request, "El lavado fue reprogramado correctamente.")
    else:
        messages.error(request, "La acción solicitada no es válida.")
    return redirect("tablero_lavados")


def registrar_ejecucion_lavado(actividad):
    if actividad.tipo_actividad != "LAVADO":
        return None
    programacion = None
    if actividad.servicio_id:
        programacion = LavadoTanque.objects.filter(servicio_id=actividad.servicio_id).first()
    if programacion is None:
        programacion = (
            LavadoTanque.objects.filter(cliente=actividad.cliente, ejecutado=False)
            .order_by("fecha_programada", "id")
            .first()
        )
    if programacion:
        programacion.ejecutado = True
        programacion.fecha_ejecucion = actividad.fecha
        programacion.actividad = actividad
        programacion.save(update_fields=[
            "ejecutado", "fecha_ejecucion", "actividad", "actualizado_en"
        ])
    cliente = actividad.cliente
    if not cliente.fecha_ultimo_lavado or actividad.fecha > cliente.fecha_ultimo_lavado:
        cliente.fecha_ultimo_lavado = actividad.fecha
        cliente.save(update_fields=["fecha_ultimo_lavado"])
    if actividad.servicio_id and actividad.servicio.estado != "ATENDIDA":
        actividad.servicio.estado = "ATENDIDA"
        actividad.servicio.fecha_atencion = timezone.now()
        actividad.servicio.save(update_fields=["estado", "fecha_atencion"])
    return programacion
