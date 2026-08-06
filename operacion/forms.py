from django import forms

from .models import Emergencia, EquipoUnidad
from django import forms

from .models import BitacoraOperativa


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
            "fecha_atencion": forms.DateTimeInput(
                attrs={"type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "diagnostico": forms.Textarea(attrs={"rows": 4}),
            "solucion_aplicada": forms.Textarea(attrs={"rows": 4}),
            "materiales_usados": forms.Textarea(attrs={"rows": 3}),
            "observacion_cierre": forms.Textarea(attrs={"rows": 3}),
            "observaciones_internas": forms.Textarea(attrs={"rows": 3}),
        }


class LevantamientoEquipoForm(forms.ModelForm):
    class Meta:
        model = EquipoUnidad
        fields = [
            "cliente",
            "tipo",
            "cantidad",
            "torre",
            "ubicacion",
            "marca",
            "modelo",
            "serie",
            "potencia",
            "voltaje",
            "control",
            "valor_comercial",
            "estado",
            "causa_fuera_servicio",
            "ultima_revision",
            "observaciones",
        ]

        widgets = {
            "cliente": forms.Select(attrs={"class": "form-control"}),
            "tipo": forms.Select(attrs={"class": "form-control"}),
            "cantidad": forms.NumberInput(attrs={
                "class": "form-control",
                "min": "1",
                "value": "1",
            }),
            "torre": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ejemplo: Torre 1",
            }),
            "ubicacion": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ejemplo: Cuarto de bombas, sótano",
            }),
            "marca": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Marca del equipo",
            }),
            "modelo": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Modelo",
            }),
            "serie": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Número de serie",
            }),
            "potencia": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ejemplo: 5 HP",
            }),
            "voltaje": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ejemplo: 220 V",
            }),
            "control": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ejemplo: Arranque directo, variador",
            }),
            "valor_comercial": forms.NumberInput(attrs={
                "class": "form-control",
                "step": "0.01",
                "min": "0",
                "placeholder": "Valor estimado, si se conoce",
            }),
            "estado": forms.Select(attrs={"class": "form-control"}),
            "causa_fuera_servicio": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Explique la causa si está en reparación o fuera de servicio",
            }),
            "ultima_revision": forms.DateInput(attrs={
                "class": "form-control",
                "type": "date",
            }),
            "observaciones": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 4,
                "placeholder": "Observaciones generales del levantamiento",
            }),
        }

        labels = {
            "cliente": "Unidad o cliente",
            "tipo": "Tipo de activo",
            "cantidad": "Cantidad",
            "torre": "Torre o bloque",
            "ubicacion": "Ubicación exacta",
            "marca": "Marca",
            "modelo": "Modelo",
            "serie": "Número de serie",
            "potencia": "Potencia",
            "voltaje": "Voltaje",
            "control": "Tipo de control",
            "valor_comercial": "Valor comercial estimado",
            "estado": "Estado actual",
            "causa_fuera_servicio": "Causa o novedad",
            "ultima_revision": "Fecha de levantamiento o última revisión",
            "observaciones": "Observaciones",
        }

    def clean(self):
        cleaned_data = super().clean()
        estado = cleaned_data.get("estado")
        causa = cleaned_data.get("causa_fuera_servicio")

        if estado in ["EN_REPARACION", "FUERA_SERVICIO"]:
            if not causa or not causa.strip():
                self.add_error(
                    "causa_fuera_servicio",
                    "Debe indicar la causa o novedad del equipo.",
                )

        return cleaned_data
class BitacoraOperativaForm(forms.ModelForm):

    class Meta:
        model = BitacoraOperativa

        fields = (
            "titulo",
            "tipo",
            "descripcion",
            "accion_pendiente",
            "cliente",
            "tecnico",
            "servicio",
            "responsable",
            "prioridad",
            "estado",
            "fecha_compromiso",
            "visible_cliente",
        )

        widgets = {
            "titulo": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ejemplo: Llamar al administrador",
                }
            ),

            "tipo": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),

            "descripcion": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "Describa la novedad o actividad realizada.",
                }
            ),

            "accion_pendiente": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Indique qué acción debe realizarse.",
                }
            ),

            "cliente": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),

            "tecnico": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),

            "servicio": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),

            "responsable": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),

            "prioridad": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),

            "estado": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),

            "fecha_compromiso": forms.DateTimeInput(
                attrs={
                    "class": "form-control",
                    "type": "datetime-local",
                }
            ),

            "visible_cliente": forms.CheckboxInput(
                attrs={
                    "class": "form-check-input",
                }
            ),
        }