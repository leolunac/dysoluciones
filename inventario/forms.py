from decimal import Decimal
import re

from django import forms

from gestion_comercial.models import CatalogoPrecio
from operacion.models import Accesorio

from .models import (
    ConsumoInventario,
    DetalleConsumoInventario,
    DetalleEntradaInventario,
    EntradaInventario,
    ProductoInventario,
    Proveedor,
    ReferenciaProveedor,
)


PREFIJOS_CODIGO = [(letra, letra) for letra in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"]


def siguiente_codigo_interno(prefijo="A"):
    prefijo = (prefijo or "A").strip().upper()[:1]
    patron = re.compile(rf"^{re.escape(prefijo)}(\d+)$")
    codigos = list(Accesorio.objects.values_list("codigo", flat=True))
    codigos += list(CatalogoPrecio.objects.values_list("codigo", flat=True))
    numeros = []
    for codigo in codigos:
        coincidencia = patron.match((codigo or "").strip().upper())
        if coincidencia:
            numeros.append(int(coincidencia.group(1)))
    return f"{prefijo}{max(numeros, default=0) + 1:03d}"


class ProveedorForm(forms.ModelForm):
    class Meta:
        model = Proveedor
        fields = ("nombre", "nit", "telefono", "correo", "direccion", "activo")


class NuevoProductoInventarioForm(forms.Form):
    prefijo = forms.ChoiceField(
        choices=PREFIJOS_CODIGO,
        initial="A",
        help_text="Seleccione la familia del código interno D&S.",
    )
    codigo = forms.CharField(
        label="Código interno D&S",
        max_length=50,
        help_text="SIGOB propone el siguiente código libre y valida que no esté ocupado.",
    )
    descripcion = forms.CharField(label="Descripción", max_length=250)
    unidad_medida = forms.CharField(label="Unidad de medida", max_length=30, initial="UNID")
    stock_minimo = forms.DecimalField(
        label="Stock mínimo",
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.00"),
        initial=Decimal("0.00"),
    )
    precio_referencia = forms.DecimalField(
        label="Valor unitario sin descuento",
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.00"),
        initial=Decimal("0.00"),
    )
    proveedor = forms.ModelChoiceField(
        queryset=Proveedor.objects.none(),
        required=False,
        help_text="Opcional. Permite guardar también la referencia usada por el proveedor.",
    )
    codigo_proveedor = forms.CharField(
        label="Código del proveedor",
        max_length=80,
        required=False,
    )
    descripcion_proveedor = forms.CharField(
        label="Descripción del proveedor",
        max_length=250,
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["proveedor"].queryset = Proveedor.objects.filter(activo=True)
        if not self.is_bound:
            prefijo = self.initial.get("prefijo", "A")
            self.initial.setdefault("codigo", siguiente_codigo_interno(prefijo))

    def clean_codigo(self):
        codigo = self.cleaned_data["codigo"].strip().upper()
        if not re.fullmatch(r"[A-Z]\d+", codigo):
            raise forms.ValidationError("Use una letra seguida de números, por ejemplo A884.")
        existente = Accesorio.objects.filter(codigo__iexact=codigo).first()
        if existente:
            raise forms.ValidationError(
                f"El código {codigo} ya pertenece a {existente.descripcion}."
            )
        precio = CatalogoPrecio.objects.filter(codigo__iexact=codigo).first()
        if precio:
            raise forms.ValidationError(
                f"El código {codigo} ya está reservado en Gestión Comercial para {precio.descripcion}."
            )
        return codigo

    def clean(self):
        datos = super().clean()
        prefijo = datos.get("prefijo")
        codigo = datos.get("codigo")
        if prefijo and codigo and not codigo.startswith(prefijo):
            self.add_error(
                "codigo",
                f"El código debe comenzar por el prefijo {prefijo} seleccionado.",
            )
        proveedor = datos.get("proveedor")
        codigo_proveedor = (datos.get("codigo_proveedor") or "").strip()
        if proveedor and not codigo_proveedor:
            self.add_error("codigo_proveedor", "Indique el código usado por el proveedor.")
        if codigo_proveedor and not proveedor:
            self.add_error("proveedor", "Seleccione el proveedor de esta referencia.")
        if proveedor and codigo_proveedor and ReferenciaProveedor.objects.filter(
            proveedor=proveedor,
            codigo_proveedor__iexact=codigo_proveedor,
        ).exists():
            self.add_error(
                "codigo_proveedor",
                "Este proveedor ya tiene registrada esa referencia.",
            )
        return datos


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
