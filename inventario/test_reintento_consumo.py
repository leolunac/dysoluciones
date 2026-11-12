"""Consumos nuevos: reintentos después de rollback y errores de campos ocultos."""
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from . import test_cantidad_consumo as cantidad
from .forms import DetalleConsumoFormSet
from .models import ConsumoInventario, DetalleConsumoInventario, MovimientoInventario


class ReintentoConsumoTests(TestCase):
    setUpTestData = classmethod(cantidad.CantidadConsumoTests.setUpTestData.__func__)
    datos = cantidad.CantidadConsumoTests.datos

    def setUp(self):
        self.client.force_login(self.usuario)
        self.url = reverse('inventario:nuevo_consumo')
        self.prefijo = DetalleConsumoFormSet.get_default_prefix()

    def test_reproduce_error_oculto_de_padre_anterior(self):
        datos = self.datos('1')
        datos[f'{self.prefijo}-0-consumo'] = '126'
        formset = DetalleConsumoFormSet(datos, instance=ConsumoInventario())
        self.assertFalse(formset.is_valid())
        self.assertIn('consumo', formset.errors[0])

    def test_nuevo_consumo_ignora_padre_oculto_del_intento_anterior(self):
        datos = self.datos('1')
        datos[f'{self.prefijo}-0-consumo'] = '126'
        response = self.client.post(self.url, datos)
        self.assertEqual(response.status_code, 302)
        consumo = ConsumoInventario.objects.get()
        self.assertEqual(consumo.detalles.get().consumo_id, consumo.pk)

    def test_seis_filas_una_eliminada_y_ultima_con_padre_anterior(self):
        datos = self.datos('1')
        datos[f'{self.prefijo}-TOTAL_FORMS'] = '6'
        for i in range(6):
            datos[f'{self.prefijo}-{i}-producto'] = str(self.producto.pk)
            datos[f'{self.prefijo}-{i}-cantidad'] = '1'
        datos[f'{self.prefijo}-0-DELETE'] = 'on'
        datos[f'{self.prefijo}-5-consumo'] = '126'
        response = self.client.post(self.url, datos)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ConsumoInventario.objects.count(), 1)
        self.assertEqual(DetalleConsumoInventario.objects.count(), 5)

    def test_padre_enviado_no_modifica_consumo_existente(self):
        existente = ConsumoInventario.objects.create(cliente=self.cliente, ubicacion_origen=self.bodega,
                                                     creado_por=self.usuario, observaciones='ORIGINAL')
        datos = self.datos('2')
        datos[f'{self.prefijo}-0-consumo'] = str(existente.pk)
        response = self.client.post(self.url, datos)
        self.assertEqual(response.status_code, 302)
        existente.refresh_from_db()
        self.assertEqual(existente.observaciones, 'ORIGINAL')
        self.assertEqual(existente.detalles.count(), 0)
        self.assertEqual(ConsumoInventario.objects.count(), 2)

    @patch('inventario.views.confirmar_consumo', side_effect=ValidationError('Stock insuficiente de ZC001. Disponible: 0.'))
    def test_rollback_reconstruye_padre_y_filas_sin_ids(self, confirmar):
        datos = self.datos('1')
        datos['accion'] = 'confirmar_terminar'
        response = self.client.post(self.url, datos)
        self.assertEqual(response.status_code, 200)
        formset = response.context['formset']
        self.assertIsNone(response.context['form'].instance.pk)
        self.assertIsNone(formset.instance.pk)
        self.assertIsNone(formset.forms[0].instance.pk)
        self.assertIn(formset.empty_form['consumo'].value(), (None, ''))
        self.assertContains(response, 'Stock insuficiente')
        self.assertEqual(ConsumoInventario.objects.count(), 0)
        self.assertEqual(DetalleConsumoInventario.objects.count(), 0)
        self.assertEqual(MovimientoInventario.objects.count(), 0)

    @patch('inventario.views.confirmar_consumo', side_effect=ValidationError('Stock insuficiente'))
    def test_guardar_borrador_despues_de_confirmacion_fallida(self, confirmar):
        datos = self.datos('1')
        datos['accion'] = 'confirmar_terminar'
        self.assertEqual(self.client.post(self.url, datos).status_code, 200)
        datos['accion'] = 'borrador'
        self.assertEqual(self.client.post(self.url, datos).status_code, 302)
        self.assertEqual(ConsumoInventario.objects.get().estado, 'BORRADOR')

    def test_errores_de_campos_ocultos_aparecen_en_resumen(self):
        datos = self.datos('1')
        datos[f'{self.prefijo}-0-id'] = '99999999'
        response = self.client.post(self.url, datos)
        self.assertEqual(response.status_code, 200)
        self.assertIn('id', response.context['formset'].errors[0])
        self.assertContains(response, 'Revise los datos antes de guardar')
        self.assertContains(response, 'Material 1')
        self.assertEqual(ConsumoInventario.objects.count(), 0)
