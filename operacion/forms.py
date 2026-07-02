from django import forms
from .models import Emergencia


class NuevaLlamadaForm(forms.ModelForm):

    class Meta:
        model = Emergencia
        fields = [
            "cliente",
            "tipo_servicio",
            "persona_llama",
            "telefono_llama",
            "recibido_por",
            "prioridad",
            "descripcion_falla",
            "tecnico",
        ]

        widgets = {
            "descripcion_falla": forms.Textarea(attrs={"rows": 4}),
        }

    def save(self, commit=True):
        servicio = super().save(commit=False)
        servicio.estado = "EN_PROCESO"

        if commit:
            servicio.save()

        return servicio
class GestionServicioForm(forms.ModelForm):

    class Meta:
        model = Emergencia
        fields = [
            "estado",
            "fecha_atencion",
            "solucion_aplicada",
            "horas_trabajadas",
            "observaciones_internas",
            "aprobada_por_gerencia",
        ]

        widgets = {
            "fecha_atencion": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "solucion_aplicada": forms.Textarea(attrs={"rows": 4}),
            "observaciones_internas": forms.Textarea(attrs={"rows": 4}),
        }