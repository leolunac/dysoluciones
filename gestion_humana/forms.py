from django import forms

from .models import (
    AfiliacionSeguridadSocial,
    CertificacionEmpleado,
    ContratoLaboral,
    DocumentoEmpleado,
    Empleado,
)


class FechaInput(forms.DateInput):
    input_type = "date"


class EmpleadoForm(forms.ModelForm):
    class Meta:
        model = Empleado
        exclude = ["creado_por", "actualizado_por"]
        widgets = {
            "fecha_nacimiento": FechaInput(),
            "fecha_ingreso": FechaInput(),
            "fecha_retiro": FechaInput(),
            "observaciones": forms.Textarea(attrs={"rows": 3}),
        }


class ContratoLaboralForm(forms.ModelForm):
    class Meta:
        model = ContratoLaboral
        exclude = ["empleado", "creado_por"]
        widgets = {
            "fecha_inicio": FechaInput(),
            "fecha_fin": FechaInput(),
            "observaciones": forms.Textarea(attrs={"rows": 2}),
        }


class AfiliacionSeguridadSocialForm(forms.ModelForm):
    class Meta:
        model = AfiliacionSeguridadSocial
        exclude = ["empleado", "creado_por"]
        widgets = {
            "fecha_inicio": FechaInput(),
            "fecha_fin": FechaInput(),
            "observaciones": forms.Textarea(attrs={"rows": 2}),
        }


class CertificacionEmpleadoForm(forms.ModelForm):
    class Meta:
        model = CertificacionEmpleado
        exclude = ["empleado", "creado_por"]
        widgets = {
            "fecha_expedicion": FechaInput(),
            "fecha_vencimiento": FechaInput(),
            "observaciones": forms.Textarea(attrs={"rows": 2}),
        }


class DocumentoEmpleadoForm(forms.ModelForm):
    class Meta:
        model = DocumentoEmpleado
        exclude = ["empleado", "creado_por"]
        widgets = {
            "fecha_documento": FechaInput(),
            "fecha_vencimiento": FechaInput(),
            "observaciones": forms.Textarea(attrs={"rows": 2}),
        }
