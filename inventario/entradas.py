"""Consulta de entradas por compra y corrección de sus cantidades."""
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from .consumos import CorregirCantidadForm
from .correcciones_entradas import corregir_cantidad_entrada
from .models import DetalleEntradaInventario, EntradaInventario
from .permisos import exigir_consulta, exigir_gestion, puede_gestionar_inventario


class FiltrosEntradas(forms.Form):
    q = forms.CharField(required=False, max_length=150, label="Proveedor, NIT, factura o número de entrada")
    estado = forms.ChoiceField(required=False, choices=[("", "Todos los estados"), ("BORRADOR", "Borrador"), ("CONFIRMADA", "Confirmada")])
    desde = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}), label="Factura desde")
    hasta = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}), label="Factura hasta")

    def clean(self):
        datos = super().clean()
        if datos.get("desde") and datos.get("hasta") and datos["desde"] > datos["hasta"]:
            raise ValidationError("La fecha inicial no puede ser posterior a la final.")
        return datos


@login_required
@require_GET
def lista_entradas(request):
    exigir_consulta(request.user)
    form = FiltrosEntradas(request.GET)
    entradas = EntradaInventario.objects.select_related("proveedor", "creado_por").order_by("-fecha_factura", "-pk")
    if form.is_valid():
        datos = form.cleaned_data
        q = datos["q"]
        if q:
            filtro = Q(proveedor__nombre__icontains=q) | Q(proveedor__nit__icontains=q) | Q(numero_factura__icontains=q)
            if q.isascii() and q.isdigit() and len(q) <= 18:
                filtro |= Q(pk=int(q))
            entradas = entradas.filter(filtro)
        if datos["estado"]:
            entradas = entradas.filter(estado=datos["estado"])
        if datos["desde"]:
            entradas = entradas.filter(fecha_factura__gte=datos["desde"])
        if datos["hasta"]:
            entradas = entradas.filter(fecha_factura__lte=datos["hasta"])
    else:
        entradas = entradas.none()
    parametros = request.GET.copy()
    parametros.pop("page", None)
    return render(request, "inventario/entradas_lista.html", {
        "form": form, "pagina": Paginator(entradas, 25).get_page(request.GET.get("page")),
        "consulta": parametros.urlencode(), "puede_gestionar": puede_gestionar_inventario(request.user),
    })


@login_required
@require_GET
def detalle_entrada(request, entrada_id):
    exigir_consulta(request.user)
    entrada = get_object_or_404(EntradaInventario.objects.select_related("proveedor", "creado_por"), pk=entrada_id)
    detalles = entrada.detalles.select_related("producto__accesorio").prefetch_related("correcciones__registrado_por", "correcciones__movimiento")
    return render(request, "inventario/entrada_detalle.html", {
        "entrada": entrada, "detalles": detalles,
        "puede_gestionar": puede_gestionar_inventario(request.user),
    })


@login_required
@require_http_methods(["GET", "POST"])
def corregir_cantidad_vista(request, entrada_id, detalle_id):
    exigir_gestion(request.user)
    detalle = get_object_or_404(
        DetalleEntradaInventario.objects.select_related("entrada__proveedor", "producto__accesorio"),
        pk=detalle_id, entrada_id=entrada_id,
    )
    revision = detalle.correcciones.order_by("-pk").values_list("pk", flat=True).first() or 0
    form = CorregirCantidadForm(request.POST if request.method == "POST" else None,
                               initial={"cantidad": detalle.cantidad, "revision": revision})
    form.fields["motivo"].widget.attrs["placeholder"] = "Ejemplo: se registraron 10 unidades y se recibieron 8."
    if request.method == "POST" and form.is_valid():
        try:
            corregir_cantidad_entrada(entrada_id=entrada_id, detalle_id=detalle_id, usuario=request.user, **form.cleaned_data)
        except ValidationError as exc:
            form.add_error(None, "; ".join(exc.messages))
            detalle.refresh_from_db()
        else:
            messages.success(request, "Cantidad de la entrada corregida. El cambio quedó registrado en el historial.")
            return redirect("inventario:detalle_entrada", entrada_id=entrada_id)
    return render(request, "inventario/entrada_corregir.html", {"detalle": detalle, "entrada": detalle.entrada, "form": form})
