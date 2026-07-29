from django import forms
from .models import DocumentoCliente


class DocumentoClienteForm(forms.ModelForm):

    class Meta:
        model = DocumentoCliente

        fields = [
            "cliente",
            "titulo",
            "tipo",
            "fecha_documento",
            "archivo",
            "estado",
            "observaciones",
        ]

        widgets = {

            "cliente": forms.Select(attrs={
                "class": "form-control"
            }),

            "titulo": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Título del documento"
            }),

            "tipo": forms.Select(attrs={
                "class": "form-control"
            }),

            "fecha_documento": forms.DateInput(attrs={
                "class": "form-control",
                "type": "date"
            }),

            "archivo": forms.ClearableFileInput(attrs={
                "class": "form-control"
            }),

            "estado": forms.Select(attrs={
                "class": "form-control"
            }),

            "observaciones": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 4
            }),

        }