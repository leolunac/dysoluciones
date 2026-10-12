from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import ActividadTecnico, Cliente, Emergencia, Tecnico


class PanelTecnicoServiciosTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username="tecnico_panel",
            password="prueba-segura",
        )
        self.tecnico = Tecnico.objects.create(
            user=self.usuario,
            nombre="Técnico Panel",
            telefono="3000000000",
            especialidad="Bombas",
            valor_hora_diurna=Decimal("1.00"),
            valor_hora_nocturna=Decimal("1.00"),
        )
        self.cliente = Cliente.objects.create(
            nombre="Unidad prueba panel",
            nit="PANEL-TECNICO-1",
            direccion="Dirección de prueba",
            telefono_porteria="0000000",
            administrador="Administración",
            email="panel@example.com",
            tipo_contrato="SIN_CONTRATO",
            frecuencia_lavado=6,
        )
        self.pendiente = self._servicio("PENDIENTE", "Pendiente visible")
        self.en_proceso = self._servicio("EN_PROCESO", "En proceso visible")
        self.atendida = self._servicio("ATENDIDA", "Atendida solo historial")
        self.cerrada = self._servicio("CERRADA", "Cerrada solo historial")
        self.informe = ActividadTecnico.objects.create(
            tecnico=self.tecnico,
            cliente=self.cliente,
            servicio=self.atendida,
            tipo_actividad="CORRECTIVO",
            labor_realizada="Trabajo terminado.",
            resultado="OPERATIVO",
            numero_informe="COR-2099-000001",
            enviado_en=timezone.now(),
            registrado_por=self.usuario,
        )

    def _servicio(self, estado, descripcion):
        return Emergencia.objects.create(
            cliente=self.cliente,
            tecnico=self.tecnico,
            estado=estado,
            tipo_servicio="CORRECTIVO",
            descripcion_falla=descripcion,
        )

    def test_separa_servicios_activos_de_realizados(self):
        self.client.force_login(self.usuario)

        respuesta = self.client.get(reverse("panel_tecnico"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertQuerySetEqual(
            respuesta.context["servicios"],
            [self.en_proceso, self.pendiente],
        )
        self.assertQuerySetEqual(
            respuesta.context["servicios_realizados"],
            [self.cerrada, self.atendida],
        )
        self.assertContains(respuesta, "Atendida solo historial")
        self.assertContains(
            respuesta,
            reverse("comprobante_actividad", args=[self.informe.pk]),
        )
        self.assertNotContains(
            respuesta,
            f'{reverse("nueva_actividad")}?servicio={self.atendida.pk}',
        )
