from decimal import Decimal

from django import forms

from .models import (
    ConsumoInventario,
    DetalleConsumoInventario,
    DetalleEntradaInventario,
    EntradaInventario,
    ProductoInventario,
    Proveedor,
)


class ProveedorForm(forms.ModelForm):
    class Meta:
        model = Proveedor
        fields = ("nombre", "nit", "telefono", "correo", "direccion", "activo")


class EntradaInventarioForm(forms.ModelForm):
    class Meta:
        model = EntradaInventario
        fields = ("proveedor", "numero_factura", "fecha_factura", "observaciones")
        widgets = {
            "fecha_factura": forms.DateInput(attrs={"type": "date"}),
            "observaciones": forms.Textarea(attrs={"rows": 2}),
        }


class DetalleEntradaInventarioForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["producto"].queryset = ProductoInventario.objects.filter(
            activo=True,
        ).select_related("accesorio")

    class Meta:
        model = DetalleEntradaInventario
        fields = (
            "producto",
            "referencia_proveedor",
            "cantidad",
            "precio_unitario_lista",
            "porcentaje_descuento",
        )


DetalleEntradaFormSet = forms.inlineformset_factory(
    EntradaInventario,
    DetalleEntradaInventario,
    form=DetalleEntradaInventarioForm,
    extra=1,
    can_delete=True,
)


class ConsumoInventarioForm(forms.ModelForm):
    class Meta:
        model = ConsumoInventario
        fields = ("cliente", "ubicacion_origen", "fecha", "observaciones")
        widgets = {
            "fecha": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "observaciones": forms.Textarea(attrs={"rows": 2}),
        }


class DetalleConsumoInventarioForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["producto"].queryset = ProductoInventario.objects.filter(
            activo=True,
        ).select_related("accesorio")

    class Meta:
        model = DetalleConsumoInventario
        fields = ("producto", "cantidad")


DetalleConsumoFormSet = forms.inlineformset_factory(
    ConsumoInventario,
    DetalleConsumoInventario,
    form=DetalleConsumoInventarioForm,
    extra=1,
    can_delete=True,
)


class AjusteExistenciaForm(forms.Form):
    MOTIVOS = [
        ("CONTEO_FISICO", "Conteo físico de inventario"),
        ("DIFERENCIA_ANTERIOR", "Corrección de diferencia anterior"),
        ("DAÑO", "Producto dañado o deteriorado"),
        ("PERDIDA", "Pérdida o faltante"),
        ("OTRO", "Otro motivo"),
    ]

    cantidad_fisica = forms.DecimalField(
        label="Existencia física real",
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.00"),
    )
    motivo = forms.ChoiceField(choices=MOTIVOS)
    observaciones = forms.CharField(
        label="Detalle del ajuste",
        widget=forms.Textarea(attrs={"rows": 3}),
        required=True,
        help_text="Explique brevemente la razón de la diferencia encontrada.",
    )
