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
            "diagnostico",
            "solucion_aplicada",
            "materiales_usados",
            "horas_trabajadas",
            "resultado_servicio",
            "requiere_regreso",
            "requiere_cotizacion",
            "cliente_conforme",
            "observacion_cierre",
            "observaciones_internas",
            "aprobada_por_gerencia",
        ]

        widgets = {
            "fecha_atencion": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "diagnostico": forms.Textarea(attrs={"rows": 4}),
            "solucion_aplicada": forms.Textarea(attrs={"rows": 4}),
            "materiales_usados": forms.Textarea(attrs={"rows": 3}),
            "observacion_cierre": forms.Textarea(attrs={"rows": 3}),
            "observaciones_internas": forms.Textarea(attrs={"rows": 3}),
        }