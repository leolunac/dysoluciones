"""Regresión: cantidades incompletas deben mostrar errores, no provocar un 500."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from operacion.models import Accesorio, Cliente
from .forms import DetalleConsumoFormSet
from .models import ConsumoInventario, DetalleConsumoInventario, MovimientoInventario, ProductoInventario, UbicacionInventario


class CantidadConsumoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(
            username="cantidad_consumo_prueba", is_superuser=True, is_staff=True,
        )
        cls.cliente = Cliente.objects.create(nombre="UNIDAD CANTIDAD PRUEBA", activo=True)
        accesorio = Accesorio.objects.create(codigo="ZC001", descripcion="ACCESORIO CANTIDAD PRUEBA", activo=True)
        cls.producto = ProductoInventario.objects.create(accesorio=accesorio, precio_referencia=Decimal("1000"))
        cls.bodega = UbicacionInventario.objects.create(nombre="Bodega cantidad prueba", tipo="BODEGA", activa=True)

    def datos(self, cantidad):
        prefijo = DetalleConsumoFormSet.get_default_prefix()
        return {
            "cliente": str(self.cliente.pk), "ubicacion_origen": str(self.bodega.pk),
            "fecha": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
            "observaciones": "Regresión de validación", "accion": "borrador",
            f"{prefijo}-TOTAL_FORMS": "1", f"{prefijo}-INITIAL_FORMS": "0",
            f"{prefijo}-0-producto": str(self.producto.pk), f"{prefijo}-0-cantidad": cantidad,
        }

    def test_cantidad_vacia_muestra_error_de_campo(self):
        formset = DetalleConsumoFormSet(self.datos(""), instance=ConsumoInventario())
        self.assertFalse(formset.is_valid())
        self.assertIn("cantidad", formset.errors[0])

    def test_cantidades_invalidas_muestran_error(self):
        for cantidad in ("abc", "NaN", "Infinity", "1.234", "99999999999999999", "0", "-1"):
            with self.subTest(cantidad=cantidad):
                formset = DetalleConsumoFormSet(self.datos(cantidad), instance=ConsumoInventario())
                self.assertFalse(formset.is_valid())
                self.assertIn("cantidad", formset.errors[0])

    def test_cantidades_positivas_validas(self):
        for cantidad in ("1", "0.01", "2.50"):
            with self.subTest(cantidad=cantidad):
                formset = DetalleConsumoFormSet(self.datos(cantidad), instance=ConsumoInventario())
                self.assertTrue(formset.is_valid(), formset.errors)

    def test_modelo_sin_cantidad_emite_validationerror(self):
        detalle = DetalleConsumoInventario(producto=self.producto, cantidad=None)
        with self.assertRaises(ValidationError) as error:
            detalle.full_clean(exclude=["consumo"])
        self.assertIn("cantidad", error.exception.message_dict)

    def test_fila_extra_totalmente_vacia_se_ignora(self):
        prefijo = DetalleConsumoFormSet.get_default_prefix()
        datos = self.datos("2")
        datos.update({f"{prefijo}-TOTAL_FORMS": "2", f"{prefijo}-1-producto": "", f"{prefijo}-1-cantidad": ""})
        formset = DetalleConsumoFormSet(datos, instance=ConsumoInventario())
        self.assertTrue(formset.is_valid(), formset.errors)

    def test_fila_incompleta_marcada_para_eliminar_se_ignora(self):
        prefijo = DetalleConsumoFormSet.get_default_prefix()
        datos = self.datos("2")
        datos.update({f"{prefijo}-TOTAL_FORMS": "2", f"{prefijo}-1-producto": str(self.producto.pk),
                      f"{prefijo}-1-cantidad": "", f"{prefijo}-1-DELETE": "on"})
        formset = DetalleConsumoFormSet(datos, instance=ConsumoInventario())
        self.assertTrue(formset.is_valid(), formset.errors)

    def test_post_invalido_no_guarda_ni_descontabiliza(self):
        self.client.force_login(self.usuario)
        for accion in ("borrador", "confirmar_continuar", "confirmar_terminar"):
            for cantidad in ("", "abc", "0", "-1"):
                with self.subTest(accion=accion, cantidad=cantidad):
                    datos = self.datos(cantidad)
                    datos["accion"] = accion
                    response = self.client.post(reverse("inventario:nuevo_consumo"), datos)
                    self.assertEqual(response.status_code, 200)
                    self.assertIn("cantidad", response.context["formset"].errors[0])
        self.assertEqual(ConsumoInventario.objects.count(), 0)
        self.assertEqual(DetalleConsumoInventario.objects.count(), 0)
        self.assertEqual(MovimientoInventario.objects.count(), 0)

    def test_post_valido_guarda_borrador(self):
        self.client.force_login(self.usuario)
        response = self.client.post(reverse("inventario:nuevo_consumo"), self.datos("2.50"))
        self.assertEqual(response.status_code, 302)
        consumo = ConsumoInventario.objects.get()
        self.assertEqual(consumo.estado, "BORRADOR")
        self.assertEqual(consumo.detalles.get().cantidad, Decimal("2.50"))
        self.assertEqual(MovimientoInventario.objects.count(), 0)
