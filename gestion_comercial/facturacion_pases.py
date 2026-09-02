from datetime import date
from decimal import Decimal

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from operacion.models import FacturacionPase


GRUPOS_PERMITIDOS = {
    "GESTION_COORDINADOR",
    "GESTION_FACTURACION",
    "GESTION_GERENCIA",
}


def _exigir_acceso(user):
    if not (
        user.is_superuser
        or user.groups.filter(name__in=GRUPOS_PERMITIDOS).exists()
    ):
        raise PermissionDenied


class RegistroFacturaPaseForm(forms.ModelForm):
    class Meta:
        model = FacturacionPase
        fields = [
            "estado",
            "numero_factura",
            "fecha_factura",
            "valor_facturado",
            "observaciones",
        ]
        widgets = {
            "estado": forms.Select(attrs={"class": "campo"}),
            "numero_factura": forms.TextInput(attrs={
                "class": "campo",
                "placeholder": "Numero generado en Siigo",
            }),
            "fecha_factura": forms.DateInput(attrs={
                "class": "campo",
                "type": "date",
            }),
            "valor_facturado": forms.NumberInput(attrs={
                "class": "campo",
                "step": "0.01",
                "min": "0",
            }),
            "observaciones": forms.Textarea(attrs={
                "class": "campo",
                "rows": 4,
            }),
        }

    def clean(self):
        datos = super().clean()
        if datos.get("estado") == "FACTURADA":
            faltantes = []
            if not datos.get("numero_factura"):
                faltantes.append("numero de factura de Siigo")
            if not datos.get("fecha_factura"):
                faltantes.append("fecha de factura")
            if datos.get("valor_facturado") is None:
                faltantes.append("valor facturado")
            if faltantes:
                raise forms.ValidationError(
                    "Para marcar como facturada complete: " + ", ".join(faltantes) + "."
                )
        return datos


def _periodo_solicitado(valor):
    hoy = timezone.localdate()
    if not valor:
        return hoy.replace(day=1)
    try:
        anio, mes = map(int, valor.split("-"))
        return date(anio, mes, 1)
    except (TypeError, ValueError):
        return hoy.replace(day=1)


@login_required
def consolidado_facturacion_pases(request, mes=None):
    _exigir_acceso(request.user)

    hoy = timezone.localdate()
    periodo = _periodo_solicitado(request.GET.get("mes", "") or mes)
    busqueda = request.GET.get("q", "").strip()
    estado = request.GET.get("estado", "").strip()

    base = (
        FacturacionPase.objects
        .filter(periodo=periodo)
        .select_related("contrato", "contrato__cliente", "registrado_por")
    )

    indicadores = {
        "programadas": base.count(),
        "pendientes": base.filter(estado="PENDIENTE").count(),
        "vencidas": base.filter(
            estado="PENDIENTE",
            fecha_limite__lt=hoy,
        ).count(),
        "facturadas": base.filter(estado="FACTURADA").count(),
        "por_confirmar": base.filter(estado="POR_CONFIRMAR").count(),
        "provisionales": base.filter(
            contrato__estado_valor="PROVISIONAL"
        ).count(),
        "proximas": FacturacionPase.objects.filter(
            periodo__gt=periodo,
            estado="PENDIENTE",
        ).count(),
    }

    totales = base.aggregate(
        programado=Sum("valor_programado"),
        facturado=Sum("valor_facturado"),
    )

    registros = base
    if busqueda:
        registros = registros.filter(
            Q(contrato__numero_pase__icontains=busqueda)
            | Q(contrato__cliente__nombre__icontains=busqueda)
            | Q(contrato__cliente__nit__icontains=busqueda)
            | Q(numero_factura__icontains=busqueda)
        )
    if estado:
        registros = registros.filter(estado=estado)

    registros = registros.order_by(
        "fecha_limite",
        "contrato__cliente__nombre",
        "contrato__numero_pase",
    )
    pagina = Paginator(registros, 50).get_page(request.GET.get("pagina"))

    contexto = {
        "pagina": pagina,
        "indicadores": indicadores,
        "total_programado": totales["programado"] or Decimal("0"),
        "total_facturado": totales["facturado"] or Decimal("0"),
        "periodo": periodo,
        "mes_valor": periodo.strftime("%Y-%m"),
        "busqueda": busqueda,
        "estado_filtro": estado,
        "estados": FacturacionPase.ESTADO,
        "hoy": hoy,
    }
    return render(
        request,
        "gestion_comercial/facturacion_pases/consolidado.html",
        contexto,
    )


@login_required
def registrar_factura_pase(request, facturacion_id):
    _exigir_acceso(request.user)
    registro = get_object_or_404(
        FacturacionPase.objects.select_related("contrato", "contrato__cliente"),
        id=facturacion_id,
    )

    if request.method == "POST":
        form = RegistroFacturaPaseForm(request.POST, instance=registro)
        if form.is_valid():
            registro = form.save(commit=False)
            registro.registrado_por = request.user
            registro.save()
            messages.success(request, "La informacion de facturacion se guardo correctamente.")
            return redirect(
                "gestion_comercial:consolidado_facturacion_pases_mes",
                mes=registro.periodo.strftime("%Y-%m"),
            )
    else:
        inicial = {}
        if registro.estado == "PENDIENTE" and registro.valor_facturado is None:
            inicial["valor_facturado"] = registro.valor_programado
        form = RegistroFacturaPaseForm(instance=registro, initial=inicial)

    return render(
        request,
        "gestion_comercial/facturacion_pases/registro.html",
        {"form": form, "registro": registro},
    )
