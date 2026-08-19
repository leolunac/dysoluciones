from decimal import Decimal
from django import forms

from .models import (
    Emergencia,
    EquipoUnidad,
    BitacoraOperativa,
    RemisionTecnico,
    DetalleRemision,
    ActividadTecnico,
)

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
            "prioridad",
            "descripcion",
            "accion_pendiente",
            "cliente",
            "tecnico",
            "servicio",
            "actividad",
            "responsable",
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
                attrs={"class": "form-control"}
            ),

            "prioridad": forms.Select(
                attrs={"class": "form-control"}
            ),

            "descripcion": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "Describa la novedad o seguimiento realizado.",
                }
            ),

            "accion_pendiente": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Indique qué acción queda pendiente.",
                }
            ),

            "cliente": forms.Select(
                attrs={"class": "form-control"}
            ),

            "tecnico": forms.Select(
                attrs={"class": "form-control"}
            ),

            "servicio": forms.Select(
                attrs={"class": "form-control"}
            ),

            "actividad": forms.Select(
                attrs={"class": "form-control"}
            ),

            "responsable": forms.Select(
                attrs={"class": "form-control"}
            ),

            "estado": forms.Select(
                attrs={"class": "form-control"}
            ),

            "fecha_compromiso": forms.DateTimeInput(
                attrs={
                    "class": "form-control",
                    "type": "datetime-local",
                }
            ),

            "visible_cliente": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
        }

        labels = {
            "cliente": "Unidad / Cliente",
            "tecnico": "Técnico relacionado",
            "servicio": "Caso 7x24 relacionado",
            "actividad": "Actividad técnica relacionada",
            "responsable": "Responsable del seguimiento",
            "fecha_compromiso": "Fecha y hora del compromiso",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Inicialmente no mostramos todos los casos y actividades
        # de todas las unidades.
        self.fields["servicio"].queryset = Emergencia.objects.none()
        self.fields["actividad"].queryset = ActividadTecnico.objects.none()

        cliente_id = None
        servicio_id = None

        # Cuando el formulario viene por POST.
        if self.is_bound:
            cliente_id = self.data.get("cliente")
            servicio_id = self.data.get("servicio")

        # Cuando estamos editando una bitácora existente.
        elif self.instance and self.instance.pk:
            cliente_id = self.instance.cliente_id
            servicio_id = self.instance.servicio_id

        if cliente_id:
            self.fields["servicio"].queryset = (
                Emergencia.objects
                .filter(cliente_id=cliente_id)
                .order_by("-fecha_llamada")
            )

            actividades = (
                ActividadTecnico.objects
                .filter(cliente_id=cliente_id)
                .select_related(
                    "tecnico",
                    "cliente",
                    "servicio",
                )
                .order_by(
                    "-fecha",
                    "-hora_llegada",
                    "-id",
                )
            )

            # Si ya existe un caso seleccionado,
            # mostramos actividades de ese caso.
            if servicio_id:
                actividades = actividades.filter(
                    servicio_id=servicio_id
                )

            self.fields["actividad"].queryset = actividades
 # =========================================================
# REMISIONES DE ACCESORIOS A TÉCNICOS
# =========================================================

class RemisionTecnicoForm(forms.ModelForm):

    class Meta:
        model = RemisionTecnico

        fields = (
            "numero_remision",
            "fecha",
            "tecnico",
            "cliente",
            "servicio",
            "observaciones",
        )

        widgets = {
            "numero_remision": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Número de la remisión física",
            }),

            "fecha": forms.DateTimeInput(
                attrs={
                    "class": "form-control",
                    "type": "datetime-local",
                },
                format="%Y-%m-%dT%H:%M",
            ),

            "tecnico": forms.Select(attrs={
                "class": "form-control",
            }),

            "cliente": forms.Select(attrs={
                "class": "form-control",
            }),

            "servicio": forms.Select(attrs={
                "class": "form-control",
            }),

            "observaciones": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Observaciones de la entrega",
            }),
        }

        labels = {
            "numero_remision": "Número de remisión física",
            "fecha": "Fecha y hora de entrega",
            "tecnico": "Técnico",
            "cliente": "Unidad / cliente",
            "servicio": "Caso 7x24 relacionado",
            "observaciones": "Observaciones",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["fecha"].input_formats = [
            "%Y-%m-%dT%H:%M",
        ]

        self.fields["servicio"].required = False


class DetalleRemisionForm(forms.ModelForm):

    class Meta:
        model = DetalleRemision

        fields = (
            "codigo_accesorio",
            "descripcion_accesorio",
            "cantidad_entregada",
            "cantidad_utilizada",
            "cantidad_devuelta",
            "observaciones",
        )

        widgets = {
            "codigo_accesorio": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Código",
            }),

            "descripcion_accesorio": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Descripción del accesorio",
            }),

            "cantidad_entregada": forms.NumberInput(attrs={
                "class": "form-control",
                "min": "0",
                "step": "0.01",
            }),

            "cantidad_utilizada": forms.NumberInput(attrs={
                "class": "form-control",
                "min": "0",
                "step": "0.01",
            }),

            "cantidad_devuelta": forms.NumberInput(attrs={
                "class": "form-control",
                "min": "0",
                "step": "0.01",
            }),

            "observaciones": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Observaciones",
            }),
        }

        labels = {
            "codigo_accesorio": "Código",
            "descripcion_accesorio": "Accesorio",
            "cantidad_entregada": "Entregado",
            "cantidad_utilizada": "Utilizado",
            "cantidad_devuelta": "Devuelto",
            "observaciones": "Observaciones",
        }
    

    def clean(self):
        cleaned_data = super().clean()

        entregada = cleaned_data.get("cantidad_entregada") or Decimal("0")
        utilizada = cleaned_data.get("cantidad_utilizada") or Decimal("0")
        devuelta = cleaned_data.get("cantidad_devuelta") or Decimal("0")

        if entregada < 0 or utilizada < 0 or devuelta < 0:
            raise forms.ValidationError(
                "Las cantidades no pueden ser negativas."
            )

        if utilizada + devuelta > entregada:
            raise forms.ValidationError(
                "La cantidad utilizada más la devuelta "
                "no puede superar la cantidad entregada."
            )

        return cleaned_data


DetalleRemisionFormSet = forms.inlineformset_factory(
    RemisionTecnico,
    DetalleRemision,
    form=DetalleRemisionForm,
    extra=5,
    can_delete=True,
)
class DetalleConciliacionForm(forms.ModelForm):

    cantidad_utilizada = forms.DecimalField(
        required=False,
        initial=0,
        min_value=0,
        decimal_places=2,
        max_digits=10,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "min": "0",
            "step": "0.01",
        }),
    )

    cantidad_devuelta = forms.DecimalField(
        required=False,
        initial=0,
        min_value=0,
        decimal_places=2,
        max_digits=10,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "min": "0",
            "step": "0.01",
        }),
    )

    class Meta:
        model = DetalleRemision
        fields = (
            "cantidad_utilizada",
            "cantidad_devuelta",
            "observaciones",
        )
        widgets = {
            "observaciones": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Observaciones",
            }),
        }

    def clean(self):
        cleaned_data = super().clean()

        utilizada = cleaned_data.get("cantidad_utilizada") or Decimal("0")
        devuelta = cleaned_data.get("cantidad_devuelta") or Decimal("0")
        cleaned_data["cantidad_utilizada"] = utilizada
        cleaned_data["cantidad_devuelta"] = devuelta
        entregada = (
            self.instance.cantidad_entregada
            if self.instance and self.instance.pk
            else Decimal("0")
        )

        if utilizada < 0 or devuelta < 0:
            raise forms.ValidationError(
                "Las cantidades no pueden ser negativas."
            )

        if utilizada + devuelta > entregada:
            raise forms.ValidationError(
                "La cantidad utilizada más la devuelta "
                "no puede superar la cantidad entregada."
            )

        return cleaned_data


DetalleConciliacionFormSet = forms.inlineformset_factory(
    RemisionTecnico,
    DetalleRemision,
    form=DetalleConciliacionForm,
    extra=0,
    can_delete=False,
)
class ActividadTecnicoForm(forms.ModelForm):

    class Meta:
        model = ActividadTecnico

        fields = (
            "tecnico",
            "cliente",
            "servicio",
            "remision",
            "tipo_actividad",
            "fecha",
            "hora_llegada",
            "hora_salida",
            "diagnostico",
            "labor_realizada",
            "resultado",
            "requiere_regreso",
            "requiere_cotizacion",
            "observaciones",
            
        )

        widgets = {
            "tecnico": forms.Select(attrs={
                "class": "form-control",
            }),

            "cliente": forms.Select(attrs={
                "class": "form-control",
            }),

            "servicio": forms.Select(attrs={
                "class": "form-control",
            }),

            "tipo_actividad": forms.Select(attrs={
                "class": "form-control",
            }),

            "fecha": forms.DateInput(attrs={
                "class": "form-control",
                "type": "date",
            }),
            "hora_llegada": forms.TimeInput(attrs={
    "class": "form-control",
    "type": "time",
}),

"hora_salida": forms.TimeInput(attrs={
    "class": "form-control",
    "type": "time",
}),
            "hora_salida": forms.TimeInput(attrs={
                "class": "form-control",
                "type": "time",
            }),

            

            "diagnostico": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Diagnóstico encontrado en la unidad",
            }),

            "labor_realizada": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 4,
                "placeholder": "Describa la labor realizada por el técnico",
            }),

            "resultado": forms.Select(attrs={
                "class": "form-control",
            }),

            "requiere_regreso": forms.CheckboxInput(attrs={
                "class": "form-check-input",
            }),

            "requiere_cotizacion": forms.CheckboxInput(attrs={
                "class": "form-check-input",
            }),

            "observaciones": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Observaciones adicionales",
            }),
            "remision": forms.Select(attrs={
                "class": "form-control",
            }),
        }

        labels = {
            "tecnico": "Técnico",
            "cliente": "Unidad / Cliente",
            "servicio": "Caso 7x24 relacionado",
            "tipo_actividad": "Tipo de actividad",
            "fecha": "Fecha",
            "hora_llegada": "Hora de llegada a la unidad",
            "hora_salida": "Hora de salida de la unidad",
            "diagnostico": "Diagnóstico",
            "labor_realizada": "Labor realizada",
            "resultado": "Resultado",
            "requiere_regreso": "Requiere regresar",
            "requiere_cotizacion": "Requiere cotización",
            "observaciones": "Observaciones",
            "remision": "Remisión relacionada",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["servicio"].required = False
        self.fields["diagnostico"].required = False
        self.fields["resultado"].required = False
        self.fields["observaciones"].required = False
        self.fields["remision"].required = False
    def clean(self):
        cleaned_data = super().clean()

        fecha = cleaned_data.get("fecha")
        hora_llegada = cleaned_data.get("hora_llegada")
        hora_salida = cleaned_data.get("hora_salida")

        if fecha and hora_llegada and hora_salida:
            from datetime import datetime, timedelta

            llegada = datetime.combine(fecha, hora_llegada)
            salida = datetime.combine(fecha, hora_salida)

        # Permite servicios que terminan después de medianoche
        if salida < llegada:
            salida += timedelta(days=1)

        duracion = salida - llegada

        # Evita registros probablemente equivocados
        if duracion > timedelta(hours=12):
            raise forms.ValidationError(
                "La permanencia calculada supera las 12 horas. "
                "Revise la hora de llegada y la hora de salida."
            )

        return cleaned_data