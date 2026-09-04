"""Selección por cliente y filtrado sobre consultas ya autorizadas."""
from django import forms
from django.db.models import Subquery
from .models import SectorCliente


class FormularioSectorMixin:
    def __init__(self, *args, **kwargs):
        puede_cambiar_sector = kwargs.pop("puede_cambiar_sector", True)
        super().__init__(*args, **kwargs)
        campo = self.fields["sector"]
        campo.empty_label = "Sin sector / por identificar"
        campo.label = "Sector"
        campo.help_text = "Seleccione el sector cuando corresponda. Deje sin sector si aún no está identificado."
        campo.queryset = SectorCliente.objects.none()
        cliente_id = self.instance.cliente_id
        if "cliente" in self.fields:
            if self.is_bound:
                cliente_id = self.data.get(self.add_prefix("cliente"))
            else:
                cliente_id = self.initial.get("cliente", cliente_id)
                cliente_id = getattr(cliente_id, "pk", cliente_id)
        if cliente_id and str(cliente_id).isdecimal() and len(str(cliente_id)) < 19:
            campo.queryset = SectorCliente.objects.filter(cliente_id=cliente_id)
        if not puede_cambiar_sector:
            campo.disabled = True
        self.sectores_disponibles = []
        if "cliente" in self.fields:
            self.sectores_disponibles = list(SectorCliente.objects.filter(
                cliente_id__in=self.fields["cliente"].queryset.values("pk")
            ).values("id", "cliente_id", "nombre"))


def filtrar_sector(queryset, valor):
    if not valor:
        return queryset
    if valor == "sin_sector":
        return queryset.filter(sector__isnull=True)
    if valor.isdecimal() and len(valor) < 19:
        return queryset.filter(sector_id=int(valor))
    return queryset.none()


def sectores_en(queryset):
    return SectorCliente.objects.filter(pk__in=Subquery(queryset.order_by().values("sector_id"))).select_related("cliente")
