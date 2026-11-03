from unittest.mock import patch
from django.contrib.auth.models import User
from django.http import HttpResponse
from django.test import TestCase, RequestFactory
from operacion.models import Cliente
from operacion.views import dashboard
from .models import Cotizacion, DetalleCotizacion


class CotizacionesPruebaTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="admin_cot_prueba", password="solo-test")
        self.unidad = Cliente.objects.create(nombre="Unidad prueba cotizaciones", tipo_contrato="SIN_CONTRATO")

    def panel(self):
        request = RequestFactory().get("/")
        request.user = self.user
        with patch("operacion.views.render", return_value=HttpResponse("OK")) as render:
            dashboard(request)
        return render.call_args.args[2]

    def cotizacion(self, **datos):
        return Cotizacion.objects.create(cliente=self.unidad, elaborado_por=self.user, asunto="Caso prueba", **datos)

    def test_grafica_excluye_pruebas_y_conserva_reales(self):
        self.cotizacion(estado="ENVIADA", es_prueba=True)
        self.cotizacion(estado="BORRADOR", es_prueba=True)
        self.cotizacion(estado="ENVIADA")
        contexto = self.panel()
        self.assertEqual(sum(contexto["data_cotizaciones"]), 1)
        self.assertEqual(contexto["data_cotizaciones"][0], 0)
        self.assertEqual(contexto["data_cotizaciones"][2], 1)
        self.assertEqual(contexto["clientes"], 1)

    def test_marca_reversible_conserva_estado_detalle_y_valores(self):
        cot = self.cotizacion(estado="ENVIADA")
        detalle = DetalleCotizacion.objects.create(cotizacion=cot, descripcion="Accesorio", cantidad=2, valor_unitario=100)
        cot.refresh_from_db()
        valor = cot.valor_total
        Cotizacion.objects.filter(pk=cot.pk).update(es_prueba=True)
        self.assertEqual(sum(self.panel()["data_cotizaciones"]), 0)
        cot.refresh_from_db()
        self.assertEqual(cot.estado, "ENVIADA")
        self.assertEqual(cot.valor_total, valor)
        self.assertTrue(DetalleCotizacion.objects.filter(pk=detalle.pk).exists())
        Cotizacion.objects.filter(pk=cot.pk).update(es_prueba=False)
        self.assertEqual(sum(self.panel()["data_cotizaciones"]), 1)
