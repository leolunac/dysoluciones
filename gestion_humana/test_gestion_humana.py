from datetime import timedelta

from django.contrib.auth.models import Group, User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import CertificacionEmpleado, Empleado, HistorialEmpleado


@override_settings(PRIVATE_MEDIA_ROOT="/tmp/sigob_test_private_media")
class GestionHumanaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.grupo = Group.objects.get_or_create(name="GESTION_ADMINISTRATIVA")[0]
        cls.administrativa = User.objects.create_user("administrativa", password="clave")
        cls.administrativa.groups.add(cls.grupo)
        cls.gerencia = User.objects.create_user("gerencia_rrhh", password="clave")
        cls.gerencia.groups.add(Group.objects.get_or_create(name="GESTION_GERENCIA")[0])
        cls.no_autorizado = User.objects.create_user("tecnico_sin_rrhh", password="clave")

    def crear_empleado(self, **cambios):
        datos = {
            "tipo_documento": "CC",
            "numero_documento": "10000001",
            "nombres": "Ana",
            "apellidos": "Prueba",
            "cargo": "Auxiliar administrativa",
            "fecha_ingreso": timezone.localdate(),
            "creado_por": self.administrativa,
            "actualizado_por": self.administrativa,
        }
        datos.update(cambios)
        return Empleado.objects.create(**datos)

    def test_solo_roles_autorizados_acceden(self):
        self.client.force_login(self.no_autorizado)
        self.assertEqual(self.client.get(reverse("gestion_humana:panel")).status_code, 403)

        self.client.force_login(self.administrativa)
        self.assertEqual(self.client.get(reverse("gestion_humana:panel")).status_code, 200)

        self.client.force_login(self.gerencia)
        self.assertEqual(self.client.get(reverse("gestion_humana:panel")).status_code, 200)

    def test_crear_empleado_registra_auditoria(self):
        self.client.force_login(self.administrativa)
        respuesta = self.client.post(
            reverse("gestion_humana:crear"),
            {
                "tipo_documento": "CC",
                "numero_documento": "10000002",
                "nombres": "Carlos",
                "apellidos": "Empleado",
                "cargo": "Técnico",
                "fecha_ingreso": timezone.localdate().isoformat(),
                "estado": "ACTIVO",
            },
        )
        empleado = Empleado.objects.get(numero_documento="10000002")
        self.assertRedirects(respuesta, reverse("gestion_humana:detalle", args=[empleado.pk]))
        self.assertEqual(empleado.creado_por, self.administrativa)
        self.assertTrue(HistorialEmpleado.objects.filter(empleado=empleado, accion="Creación").exists())

    def test_panel_muestra_certificacion_proxima_a_vencer(self):
        empleado = self.crear_empleado()
        CertificacionEmpleado.objects.create(
            empleado=empleado,
            tipo="ALTURAS",
            nombre="Curso de alturas",
            fecha_vencimiento=timezone.localdate() + timedelta(days=15),
            creado_por=self.administrativa,
        )
        self.client.force_login(self.administrativa)
        respuesta = self.client.get(reverse("gestion_humana:panel"))
        self.assertContains(respuesta, "Curso de alturas")
        self.assertEqual(respuesta.context["total_proximos"], 1)

    def test_fotografia_privada_exige_autorizacion(self):
        empleado = self.crear_empleado(foto="gestion_humana/empleado/foto.jpg")
        url = reverse("gestion_humana:descargar_archivo", args=["foto", empleado.pk])
        self.client.force_login(self.no_autorizado)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_menu_no_expone_gestion_humana_a_usuario_no_autorizado(self):
        self.client.force_login(self.no_autorizado)
        respuesta = self.client.get(reverse("gestion_humana:panel"))
        self.assertEqual(respuesta.status_code, 403)
