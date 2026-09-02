from django import forms

from operacion.models import Cliente, ContratoPase

from .models import (
    Liquidacion,
    DetalleLiquidacion,
    CatalogoPrecio,
    Cotizacion,
    DetalleCotizacion,
)


class LiquidacionForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cliente"].empty_label = "Seleccione una unidad"

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
                    "id": "id_cliente",
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


# =========================================================
# COTIZACIONES
# =========================================================

class CotizacionForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cliente"].empty_label = "Seleccione una unidad / cliente"

    class Meta:
        model = Cotizacion
        fields = [
            "cliente",
            "origen",
            "asunto",
            "descripcion",
            "porcentaje_utilidad",
            "porcentaje_iva",
            "vigencia_dias",
            "forma_pago",
            "observaciones",
        ]
        widgets = {
            "cliente": forms.Select(
                attrs={
                    "class": "campo",
                    "id": "id_cotizacion_cliente",
                }
            ),
            "origen": forms.Select(
                attrs={
                    "class": "campo",
                    "id": "id_cotizacion_origen",
                }
            ),
            "asunto": forms.TextInput(
                attrs={
                    "class": "campo",
                    "placeholder": (
                        "Ej.: Suministro e instalación de equipo de bombeo"
                    ),
                }
            ),
            "descripcion": forms.Textarea(
                attrs={
                    "class": "campo",
                    "rows": 4,
                    "placeholder": (
                        "Describa el servicio, suministro o trabajo a cotizar..."
                    ),
                }
            ),
            "porcentaje_utilidad": forms.NumberInput(
                attrs={
                    "class": "campo",
                    "step": "0.01",
                    "min": "0",
                }
            ),
            "porcentaje_iva": forms.NumberInput(
                attrs={
                    "class": "campo",
                    "step": "0.01",
                    "min": "0",
                }
            ),
            "vigencia_dias": forms.NumberInput(
                attrs={
                    "class": "campo",
                    "min": "1",
                    "step": "1",
                    "placeholder": "Ej.: 30",
                }
            ),
            "forma_pago": forms.Textarea(
                attrs={
                    "class": "campo",
                    "rows": 3,
                    "placeholder": (
                        "Ej.: 50% anticipo y 50% contra entrega."
                    ),
                }
            ),
            "observaciones": forms.Textarea(
                attrs={
                    "class": "campo",
                    "rows": 3,
                    "placeholder": (
                        "Observaciones adicionales de la cotización..."
                    ),
                }
            ),
        }
        labels = {
            "cliente": "Unidad / Cliente",
            "origen": "Origen de la cotización",
            "asunto": "Asunto / Concepto",
            "descripcion": "Descripción",
            "porcentaje_utilidad": "Utilidad (%)",
            "porcentaje_iva": "IVA (%)",
            "vigencia_dias": "Validez de la oferta (días)",
            "forma_pago": "Forma de pago",
            "observaciones": "Observaciones",
        }


# =========================================================
# DATOS COMERCIALES DE COTIZACIÓN
# =========================================================

class DatosComercialesCotizacionForm(forms.ModelForm):

    class Meta:
        model = Cotizacion

        fields = [
            "descripcion",
            "concepto_comercial",
            "alcance_tecnico",
            "vigencia_dias",
            "forma_pago",
        ]

        widgets = {
            "descripcion": forms.Textarea(
                attrs={
                    "class": "campo",
                    "rows": 4,
                    "placeholder": (
                        "Describa el objeto de la propuesta que verá el cliente."
                    ),
                }
            ),
            "concepto_comercial": forms.Textarea(
                attrs={
                    "class": "campo",
                    "rows": 3,
                    "placeholder": (
                        "Descripción global del trabajo que verá el cliente."
                    ),
                }
            ),
            "alcance_tecnico": forms.Textarea(
                attrs={
                    "class": "campo",
                    "rows": 7,
                    "placeholder": (
                        "Escriba una actividad por línea.\n"
                        "Ej.: Revisión del área de trabajo.\n"
                        "Cerrar válvula de paso.\n"
                        "Realizar pruebas de funcionamiento."
                    ),
                }
            ),
            "vigencia_dias": forms.NumberInput(
                attrs={
                    "class": "campo",
                    "min": "1",
                    "step": "1",
                    "placeholder": "Ej.: 30",
                }
            ),
            "forma_pago": forms.Textarea(
                attrs={
                    "class": "campo",
                    "rows": 3,
                    "placeholder": (
                        "Ej.: 50% de anticipo y 50% contra entrega."
                    ),
                }
            ),
        }

        labels = {
            "descripcion": "Objeto de la propuesta",
            "concepto_comercial": "Concepto comercial",
            "alcance_tecnico": "Alcance técnico",
            "vigencia_dias": "Validez de la oferta (días)",
            "forma_pago": "Forma de pago",
        }


# =========================================================
# DETALLE DE COTIZACIÓN
# =========================================================

class DetalleCotizacionForm(forms.ModelForm):

    class Meta:
        model = DetalleCotizacion
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
                    "id": "id_cotizacion_tipo",
                }
            ),
            "catalogo": forms.HiddenInput(
                attrs={
                    "id": "id_cotizacion_catalogo",
                }
            ),
            "descripcion": forms.TextInput(
                attrs={
                    "class": "campo",
                    "id": "id_cotizacion_descripcion",
                    "placeholder": "Descripción del artículo o servicio",
                    "autocomplete": "off",
                }
            ),
            "cantidad": forms.NumberInput(
                attrs={
                    "class": "campo",
                    "id": "id_cotizacion_cantidad",
                    "step": "0.01",
                    "min": "0.01",
                }
            ),
            "valor_unitario": forms.NumberInput(
                attrs={
                    "class": "campo",
                    "id": "id_cotizacion_valor_unitario",
                    "step": "0.01",
                    "min": "0",
                }
            ),
            "observaciones": forms.Textarea(
                attrs={
                    "class": "campo",
                    "rows": 2,
                    "placeholder": "Observación del artículo (opcional)",
                }
            ),
        }
        labels = {
            "tipo": "Tipo de concepto",
            "descripcion": "Artículo / Descripción",
            "cantidad": "Cantidad",
            "valor_unitario": "Valor unitario / costo",
            "observaciones": "Observaciones",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["catalogo"].queryset = (
            CatalogoPrecio.objects
            .filter(activo=True)
            .order_by("descripcion")
        )
        self.fields["catalogo"].required = False

    def clean_descripcion(self):
        descripcion = self.cleaned_data.get(
            "descripcion",
            ""
        )
        return descripcion.strip()

# =========================================================
# CONTRATOS / PASES
# =========================================================

class ContratoPaseForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cliente"].queryset = (
            Cliente.objects.filter(activo=True).order_by("nombre")
        )
        self.fields["cliente"].empty_label = "Seleccione una unidad / cliente"

    class Meta:
        model = ContratoPase
        fields = [
            "cliente",
            "numero_pase",
            "nombre_servicio",
            "tipo",
            "valor_cuota",
            "periodicidad",
            "estado_valor",
            "direccion_servicio",
            "observaciones",
            "fecha_inicio_facturacion",
            "dia_limite_facturacion",
            "activo",
        ]
        widgets = {
            "cliente": forms.Select(attrs={"class": "campo"}),
            "numero_pase": forms.TextInput(
                attrs={"class": "campo", "placeholder": "Ej.: PASE260"}
            ),
            "nombre_servicio": forms.TextInput(
                attrs={
                    "class": "campo",
                    "placeholder": "Nombre de la unidad o servicio contratado",
                }
            ),
            "tipo": forms.Select(attrs={"class": "campo"}),
            "valor_cuota": forms.NumberInput(
                attrs={"class": "campo", "step": "0.01", "min": "0"}
            ),
            "periodicidad": forms.Select(attrs={"class": "campo"}),
            "estado_valor": forms.Select(attrs={"class": "campo"}),
            "direccion_servicio": forms.TextInput(
                attrs={"class": "campo", "placeholder": "Opcional"}
            ),
            "observaciones": forms.Textarea(
                attrs={"class": "campo", "rows": 3}
            ),
            "fecha_inicio_facturacion": forms.DateInput(
                attrs={"class": "campo", "type": "date"},
                format="%Y-%m-%d",
            ),
            "dia_limite_facturacion": forms.NumberInput(
                attrs={"class": "campo", "min": "1", "max": "31"}
            ),
            "activo": forms.CheckboxInput(attrs={"class": "check"}),
        }
        labels = {
            "cliente": "Unidad / Cliente",
            "numero_pase": "Número de pase",
            "nombre_servicio": "Nombre del servicio",
            "tipo": "Tipo de contrato",
            "valor_cuota": "Valor de la cuota",
            "periodicidad": "Periodicidad de facturación",
            "estado_valor": "Estado del valor",
            "direccion_servicio": "Dirección del servicio",
            "observaciones": "Observaciones",
            "fecha_inicio_facturacion": "Fecha base de facturación",
            "dia_limite_facturacion": "Día límite mensual",
            "activo": "Contrato activo",
        }

    def clean_numero_pase(self):
        return self.cleaned_data["numero_pase"].strip().upper()

    def clean_dia_limite_facturacion(self):
        dia = self.cleaned_data["dia_limite_facturacion"]
        if dia < 1 or dia > 31:
            raise forms.ValidationError("El día límite debe estar entre 1 y 31.")
        return dia
