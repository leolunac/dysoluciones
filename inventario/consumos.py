"""Consulta de consumos y corrección individual de sus cantidades."""
from decimal import Decimal
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods
from .correcciones import corregir_cantidad
from .models import ConsumoInventario, DetalleConsumoInventario
from .permisos import exigir_consulta, exigir_gestion, puede_gestionar_inventario


class FiltrosConsumos(forms.Form):
    q = forms.CharField(required=False, max_length=150, label="Unidad, NIT o número de consumo")
    estado = forms.ChoiceField(required=False, choices=[("", "Todos los estados"), ("BORRADOR", "Borrador"), ("CONFIRMADO", "Confirmado")])
    desde = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}), label="Desde")
    hasta = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}), label="Hasta")

    def clean(self):
        datos = super().clean()
        if datos.get("desde") and datos.get("hasta") and datos["desde"] > datos["hasta"]:
            raise ValidationError("La fecha inicial no puede ser posterior a la final.")
        return datos


class CorregirCantidadForm(forms.Form):
    cantidad = forms.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"), label="Cantidad correcta", widget=forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}))
    motivo = forms.CharField(min_length=5, max_length=1000, strip=True, label="Motivo de la corrección", widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Ejemplo: se digitó 10 y la cantidad utilizada fue 1."}))
    revision = forms.IntegerField(min_value=0, widget=forms.HiddenInput())


@login_required
@require_GET
def lista_consumos(request):
    exigir_consulta(request.user)
    form = FiltrosConsumos(request.GET)
    consumos = ConsumoInventario.objects.select_related("cliente", "ubicacion_origen", "creado_por").order_by("-fecha", "-pk")
    if form.is_valid():
        datos = form.cleaned_data
        if datos["q"]:
            filtro = Q(cliente__nombre__icontains=datos["q"]) | Q(cliente__nit__icontains=datos["q"])
            if datos["q"].isascii() and datos["q"].isdigit():
                # Evitar números fuera del rango bigint.
                if len(datos["q"]) <= 18:
                    filtro |= Q(pk=int(datos["q"]))
            consumos = consumos.filter(filtro)
        if datos["estado"]:
            consumos = consumos.filter(estado=datos["estado"])
        if datos["desde"]:
            consumos = consumos.filter(fecha__date__gte=datos["desde"])
        if datos["hasta"]:
            consumos = consumos.filter(fecha__date__lte=datos["hasta"])
    else:
        consumos = consumos.none()
    parametros = request.GET.copy()
    parametros.pop("page", None)
    return render(request, "inventario/consumos_lista.html", {
        "form": form, "pagina": Paginator(consumos, 25).get_page(request.GET.get("page")),
        "consulta": parametros.urlencode(), "puede_gestionar": puede_gestionar_inventario(request.user),
    })


@login_required
@require_GET
def detalle_consumo(request, consumo_id):
    exigir_consulta(request.user)
    consumo = get_object_or_404(ConsumoInventario.objects.select_related("cliente", "ubicacion_origen", "creado_por"), pk=consumo_id)
    detalles = consumo.detalles.select_related("producto__accesorio").prefetch_related("correcciones__registrado_por", "correcciones__movimiento")
    return render(request, "inventario/consumo_detalle.html", {
        "consumo": consumo, "detalles": detalles, "tecnicos": consumo.tecnicos.all(),
        "puede_gestionar": puede_gestionar_inventario(request.user),
    })


@login_required
@require_http_methods(["GET", "POST"])
def corregir_cantidad_vista(request, consumo_id, detalle_id):
    exigir_gestion(request.user)
    detalle = get_object_or_404(DetalleConsumoInventario.objects.select_related("consumo__cliente", "consumo__ubicacion_origen", "producto__accesorio"), pk=detalle_id, consumo_id=consumo_id)
    revision = detalle.correcciones.order_by("-pk").values_list("pk", flat=True).first() or 0
    form = CorregirCantidadForm(request.POST if request.method == "POST" else None,
                               initial={"cantidad": detalle.cantidad, "revision": revision})
    if request.method == "POST" and form.is_valid():
        try:
            corregir_cantidad(consumo_id=consumo_id, detalle_id=detalle_id, usuario=request.user, **form.cleaned_data)
        except ValidationError as exc:
            form.add_error(None, "; ".join(exc.messages))
            detalle.refresh_from_db()
        else:
            messages.success(request, "Cantidad corregida. El cambio quedó registrado en el historial.")
            return redirect("inventario:detalle_consumo", consumo_id=consumo_id)
    return render(request, "inventario/consumo_corregir.html", {"detalle": detalle, "consumo": detalle.consumo, "form": form})
