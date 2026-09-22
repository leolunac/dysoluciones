from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from .lavados import registrar_ejecucion_lavado
from .models import ActividadTecnico, Cliente, Emergencia, LavadoTanque, Tecnico


class TableroLavadosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cliente = Cliente.objects.create(
            nombre="Unidad lavado", direccion="Calle 1", telefono_porteria="1",
            administrador="Admin", email="unidad@example.com",
            tipo_contrato="PREVENTIVO", frecuencia_lavado=6,
        )
        cls.usuario_tecnico = User.objects.create_user("tecnico_lavado", password="clave")
        cls.tecnico = Tecnico.objects.create(
            user=cls.usuario_tecnico, nombre="Técnico lavado", telefono="300",
            especialidad="Bombas", valor_hora_diurna=Decimal("1"),
            valor_hora_nocturna=Decimal("1"),
        )
        cls.coordinador = User.objects.create_user("coord_lavado", password="clave", is_staff=True)
        cls.coordinador.groups.add(Group.objects.get_or_create(name="GESTION_COORDINADOR")[0])
        cls.gerencia = User.objects.create_user("gerencia_lavado", password="clave")
        cls.gerencia.groups.add(Group.objects.get_or_create(name="GESTION_GERENCIA")[0])
        cls.externo = User.objects.create_user("externo_lavado", password="clave")

    def test_permisos_del_tablero(self):
        self.client.force_login(self.gerencia)
        self.assertEqual(self.client.get(reverse("tablero_lavados")).status_code, 200)
        self.client.force_login(self.externo)
        self.assertEqual(self.client.get(reverse("tablero_lavados")).status_code, 403)

    def test_programar_crea_servicio_asignado(self):
        self.client.force_login(self.coordinador)
        fecha = date.today() + timedelta(days=10)
        respuesta = self.client.post(reverse("programar_lavado"), {
            "cliente": self.cliente.pk,
            "fecha_programada": fecha.isoformat(),
            "tecnico": self.tecnico.pk,
            "observaciones": "Programación de prueba",
        })
        self.assertRedirects(respuesta, reverse("tablero_lavados"))
        lavado = LavadoTanque.objects.get(cliente=self.cliente)
        self.assertEqual(lavado.servicio.tipo_servicio, "LAVADO")
        self.assertEqual(lavado.servicio.tecnico, self.tecnico)

    def test_informe_marca_programacion_como_ejecutada(self):
        servicio = Emergencia.objects.create(
            cliente=self.cliente, tecnico=self.tecnico, tipo_servicio="LAVADO",
            descripcion_falla="Lavado programado",
        )
        lavado = LavadoTanque.objects.create(
            cliente=self.cliente, fecha_programada=date.today(), servicio=servicio,
        )
        actividad = ActividadTecnico.objects.create(
            tecnico=self.tecnico, cliente=self.cliente, servicio=servicio,
            tipo_actividad="LAVADO", fecha=date.today(), labor_realizada="Lavado ejecutado",
        )
        registrar_ejecucion_lavado(actividad)
        lavado.refresh_from_db()
        self.cliente.refresh_from_db()
        self.assertTrue(lavado.ejecutado)
        self.assertEqual(lavado.actividad, actividad)
        self.assertEqual(self.cliente.fecha_ultimo_lavado, actividad.fecha)

    def test_generador_simula_sin_inventar_fechas(self):
        call_command("generar_lavados")
        self.assertEqual(LavadoTanque.objects.count(), 0)
