"""Identificación por QR y ajuste explícito del conteo total por bodega."""
from decimal import Decimal
import re

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods

from .models import ExistenciaInventario, ProductoInventario, UbicacionInventario
from .permisos import exigir_consulta, exigir_gestion, puede_gestionar_inventario
from .servicios import ajustar_existencia

SALT_REVISION = "inventario.conteo-qr.revision.v1"
SALT_CONFIRMAR = "inventario.conteo-qr.confirmar.v1"
VIGENCIA = 30 * 60
CODIGO = re.compile(r"[A-Z0-9][A-Z0-9._-]{0,39}\Z", re.ASCII)


class BuscarCodigoForm(forms.Form):
    codigo = forms.CharField(max_length=40, label="Código del accesorio", widget=forms.TextInput(attrs={"placeholder": "Ejemplo: A012", "autocapitalize": "characters", "autocomplete": "off"}))

    def clean_codigo(self):
        codigo = self.cleaned_data["codigo"].strip().upper()
        if not CODIGO.fullmatch(codigo):
            raise ValidationError("Use el código interno del accesorio, por ejemplo A012.")
        return codigo


class ConteoFisicoForm(forms.Form):
    cantidad_fisica = forms.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0"), label="Cantidad física total en esta bodega", widget=forms.NumberInput(attrs={"min": "0", "step": "0.01", "inputmode": "decimal"}))
    motivo = forms.CharField(min_length=5, max_length=1000, strip=True, label="Motivo / explicación del conteo", widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Ejemplo: diferencia encontrada al contar las cajas de este accesorio."}))
    revision = forms.CharField(max_length=2000, widget=forms.HiddenInput())


def _producto(producto_id):
    return get_object_or_404(ProductoInventario.objects.select_related("accesorio"), pk=producto_id, activo=True, accesorio__activo=True)


def _bodega(ubicacion_id):
    return get_object_or_404(UbicacionInventario, pk=ubicacion_id, tipo="BODEGA", activa=True)


def _version(existencia):
    return {"id": existencia.pk, "cantidad": str(existencia.cantidad), "actualizado": existencia.actualizado.isoformat()} if existencia else {"id": None, "cantidad": "0.00", "actualizado": None}


def _leer(token, salt, usuario, producto_id, ubicacion_id):
    try:
        datos = signing.loads(token, salt=salt, max_age=VIGENCIA)
    except (signing.BadSignature, TypeError, ValueError):
        raise ValidationError("El conteo venció o no es válido. Vuelva a consultar la existencia y repita el conteo.")
    if not isinstance(datos, dict) or datos.get("usuario") != usuario.pk or datos.get("producto") != producto_id or datos.get("bodega") != ubicacion_id:
        raise ValidationError("El conteo no corresponde a este usuario, accesorio o bodega. Vuelva a consultar.")
    return datos


def _comprobar_version(datos, existencia):
    if datos.get("version") != _version(existencia):
        raise ValidationError("La existencia cambió desde que abrió el conteo. Vuelva a consultar y cuente nuevamente antes de ajustar.")


def confirmar_conteo(*, token, producto_id, ubicacion_id, usuario):
    exigir_gestion(usuario)
    if not usuario.is_active:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    datos = _leer(token, SALT_CONFIRMAR, usuario, producto_id, ubicacion_id)
    cantidad = forms.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0")).clean(datos.get("cantidad"))
    motivo = forms.CharField(min_length=5, max_length=1000, strip=True).clean(datos.get("motivo"))
    with transaction.atomic():
        producto = get_object_or_404(ProductoInventario.objects.select_for_update(), pk=producto_id, activo=True, accesorio__activo=True)
        bodega = _bodega(ubicacion_id)
        existencia = ExistenciaInventario.objects.select_for_update().filter(producto=producto, ubicacion=bodega).first()
        _comprobar_version(datos, existencia)
        anterior = existencia.cantidad if existencia else Decimal("0.00")
        if cantidad == anterior:
            return None
        if existencia is None:
            existencia = ExistenciaInventario.objects.create(producto=producto, ubicacion=bodega, cantidad=0)
        return ajustar_existencia(
            existencia_id=existencia.pk, cantidad_fisica=cantidad, motivo=motivo,
            observaciones=f"Conteo físico por QR. Código {producto.accesorio.codigo}. Conteo total del accesorio en {bodega.nombre}.",
            usuario=usuario,
        )


@login_required
@never_cache
@require_GET
def lector(request):
    exigir_consulta(request.user)
    form = BuscarCodigoForm(request.GET if request.GET else None)
    producto = None
    bodegas = []
    if form.is_bound and form.is_valid():
        productos = list(ProductoInventario.objects.select_related("accesorio").filter(accesorio__codigo__iexact=form.cleaned_data["codigo"], activo=True, accesorio__activo=True)[:2])
        if len(productos) != 1:
            form.add_error("codigo", "No se encontró un accesorio activo con ese código, o el código es ambiguo.")
        else:
            producto = productos[0]
            bodegas = list(UbicacionInventario.objects.filter(tipo="BODEGA", activa=True).order_by("nombre", "pk"))
            if len(bodegas) == 1:
                return redirect("inventario:conteo_qr_producto", producto_id=producto.pk, ubicacion_id=bodegas[0].pk)
    return render(request, "inventario/lector_qr.html", {"form": form, "producto": producto, "bodegas": bodegas})


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def conteo(request, producto_id, ubicacion_id):
    exigir_consulta(request.user)
    producto = _producto(producto_id)
    bodega = _bodega(ubicacion_id)
    existencia = ExistenciaInventario.objects.filter(producto=producto, ubicacion=bodega).first()
    saldo = existencia.cantidad if existencia else Decimal("0.00")
    datos_revision = {"usuario": request.user.pk, "producto": producto.pk, "bodega": bodega.pk, "version": _version(existencia)}
    form = ConteoFisicoForm(initial={"revision": signing.dumps(datos_revision, salt=SALT_REVISION, compress=True)})
    error = None
    if request.method == "POST":
        exigir_gestion(request.user)
        accion = request.POST.get("accion")
        if accion == "confirmar":
            try:
                movimiento = confirmar_conteo(token=request.POST.get("confirmacion", ""), producto_id=producto_id, ubicacion_id=ubicacion_id, usuario=request.user)
            except ValidationError as exc:
                error = "; ".join(exc.messages)
            else:
                messages.success(request, f"Inventario ajustado. Movimiento #{movimiento.pk} registrado con su usuario y motivo." if movimiento else "El conteo coincide con la existencia: no se realizó ningún ajuste ni se creó movimiento.")
                return redirect("inventario:conteo_qr_producto", producto_id=producto_id, ubicacion_id=ubicacion_id)
        elif accion == "revisar":
            form = ConteoFisicoForm(request.POST)
            if form.is_valid():
                try:
                    revision = _leer(form.cleaned_data["revision"], SALT_REVISION, request.user, producto_id, ubicacion_id)
                    _comprobar_version(revision, existencia)
                except ValidationError as exc:
                    form.add_error(None, "; ".join(exc.messages))
                else:
                    fisico = form.cleaned_data["cantidad_fisica"]
                    confirmacion = signing.dumps({**revision, "cantidad": str(fisico), "motivo": form.cleaned_data["motivo"]}, salt=SALT_CONFIRMAR, compress=True)
                    return render(request, "inventario/conteo_qr_confirmar.html", {
                        "producto": producto, "bodega": bodega, "saldo": saldo, "fisico": fisico,
                        "diferencia": fisico - saldo, "motivo": form.cleaned_data["motivo"], "confirmacion": confirmacion,
                    })
        else:
            error = "Acción no válida. Vuelva a consultar y revise el conteo antes de confirmar."
    return render(request, "inventario/conteo_qr.html", {
        "producto": producto, "bodega": bodega, "saldo": saldo, "form": form,
        "puede_gestionar": puede_gestionar_inventario(request.user), "error": error,
    })
