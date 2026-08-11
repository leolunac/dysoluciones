from django import forms

from .models import (
    Liquidacion,
    DetalleLiquidacion,
    CatalogoPrecio,
)


class LiquidacionForm(forms.ModelForm):

    class Meta:
        model = Liquidacion

        fields = [
            "cliente",
            "descripcion",
        ]

        widgets = {
            "cliente": forms.Select(
                attrs={
                    "class": "campo",
                }
            ),

            "descripcion": forms.Textarea(
                attrs={
                    "class": "campo",
                    "rows": 4,
                    "placeholder": (
                        "Describa el trabajo realizado "
                        "o concepto a liquidar..."
                    ),
                }
            ),
        }

        labels = {
            "cliente": "Unidad / Cliente",
            "descripcion": "Descripción del trabajo",
        }


class DetalleLiquidacionForm(forms.ModelForm):

    class Meta:
        model = DetalleLiquidacion

        fields = [
            "tipo",
            "catalogo",
            "descripcion",
            "cantidad",
            "valor_unitario",
            "observaciones",
        ]

        widgets = {
            "tipo": forms.Select(
                attrs={
                    "class": "campo",
                    "id": "id_tipo",
                }
            ),

            # Lo ocultamos porque el usuario usará
            # nuestro buscador.
            "catalogo": forms.HiddenInput(
                attrs={
                    "id": "id_catalogo",
                }
            ),

            "descripcion": forms.TextInput(
                attrs={
                    "class": "campo",
                    "id": "id_descripcion",
                    "placeholder": "Descripción del concepto",
                }
            ),

            "cantidad": forms.NumberInput(
                attrs={
                    "class": "campo",
                    "step": "0.01",
                    "min": "0.01",
                    "id": "id_cantidad",
                }
            ),

            "valor_unitario": forms.NumberInput(
                attrs={
                    "class": "campo",
                    "step": "0.01",
                    "min": "0",
                    "id": "id_valor_unitario",
                }
            ),

            "observaciones": forms.Textarea(
                attrs={
                    "class": "campo",
                    "rows": 2,
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["catalogo"].queryset = (
            CatalogoPrecio.objects
            .filter(activo=True)
            .order_by("descripcion")
        )

        self.fields["catalogo"].required = False

class CatalogoPrecioForm(forms.ModelForm):

    class Meta:
        model = CatalogoPrecio
        fields = [
            "codigo",
            "descripcion",
            "valor",
        ]
        widgets = {
            "codigo": forms.TextInput(
                attrs={
                    "class": "campo",
                    "id": "id_nuevo_catalogo_codigo",
                    "placeholder": "Ej.: A040",
                    "autocomplete": "off",
                }
            ),
            "descripcion": forms.TextInput(
                attrs={
                    "class": "campo",
                    "id": "id_nuevo_catalogo_descripcion",
                    "placeholder": "Descripción del accesorio",
                    "autocomplete": "off",
                }
            ),
            "valor": forms.NumberInput(
                attrs={
                    "class": "campo",
                    "id": "id_nuevo_catalogo_valor",
                    "step": "0.01",
                    "min": "0",
                    "placeholder": "Valor de catálogo",
                }
            ),
        }
        labels = {
            "codigo": "Código",
            "descripcion": "Descripción",
            "valor": "Valor de catálogo",
        }

    def clean_codigo(self):
        return self.cleaned_data["codigo"].strip().upper()

    def clean_descripcion(self):
        return self.cleaned_data["descripcion"].strip()
