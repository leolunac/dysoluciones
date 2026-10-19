from django import forms
from django.db.models import Q

from operacion.models import Tecnico

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
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        tecnico_actual = self.instance.tecnico_id if self.instance.pk else None
        disponibles = Tecnico.objects.filter(
            Q(activo=True) | Q(pk=tecnico_actual)
        ).filter(
            Q(ficha_empleado__isnull=True) | Q(pk=tecnico_actual)
        ).order_by("nombre")
        self.fields["tecnico"].queryset = disponibles
        self.fields["tecnico"].label = "Perfil técnico existente"
        self.fields["tecnico"].help_text = (
            "Obligatorio si el tipo de empleado es Técnico. "
            "No crea otro técnico: vincula la ficha laboral con el registro existente."
        )
        self.fields["tipo_empleado"].label = "Tipo de empleado"

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
