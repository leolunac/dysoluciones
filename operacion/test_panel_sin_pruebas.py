from unittest.mock import patch
from django.contrib.auth.models import User
from django.http import HttpResponse
from django.test import TestCase, RequestFactory
from django.utils import timezone
from .models import Cliente, Emergencia
from .views import dashboard


class PanelSinPruebasTests(TestCase):
    def setUp(self):
        self.unidad = Cliente.objects.create(nombre="Unidad test panel", tipo_contrato="SIN_CONTRATO")
        self.user = User.objects.create_superuser(username="admin_panel", password="solo-test")

    def panel(self):
        request = RequestFactory().get("/")
        request.user = self.user
        with patch("operacion.views.render", return_value=HttpResponse("OK")) as render:
            dashboard(request)
        return render.call_args.args[2]

    def servicio(self, **datos):
        return Emergencia.objects.create(cliente=self.unidad, descripcion_falla="Prueba de panel", **datos)

    def test_excluye_pruebas_de_contadores_y_grafica(self):
        prueba = self.servicio(es_prueba=True, estado="ATENDIDA", tipo_servicio="CORRECTIVO")
        contexto = self.panel()
        self.assertEqual(contexto["total_servicios"], 0)
        self.assertEqual(contexto["atendidas"], 0)
        self.assertEqual(contexto["correctivos"], 0)
        self.assertEqual(sum(contexto["data_servicios"]), 0)
        self.assertTrue(Emergencia.objects.filter(pk=prueba.pk).exists())

    def test_conserva_servicios_reales_y_su_unidad(self):
        self.servicio(es_prueba=True, estado="ATENDIDA", tipo_servicio="CORRECTIVO")
        self.servicio(estado="PENDIENTE", tipo_servicio="EMERGENCIA")
        contexto = self.panel()
        self.assertEqual(contexto["total_servicios"], 1)
        self.assertEqual(contexto["pendientes"], 1)
        self.assertEqual(contexto["emergencias"], 1)
        self.assertEqual(contexto["clientes"], 1)
        self.assertEqual(sum(contexto["data_servicios"]), 1)

    def test_marca_reversible_sin_eliminar_servicio(self):
        servicio = self.servicio(estado="ATENDIDA", tipo_servicio="CORRECTIVO")
        Emergencia.objects.filter(pk=servicio.pk).update(es_prueba=True)
        self.assertEqual(self.panel()["total_servicios"], 0)
        Emergencia.objects.filter(pk=servicio.pk).update(es_prueba=False)
        self.assertEqual(self.panel()["total_servicios"], 1)
