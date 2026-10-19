from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from operacion.models import Tecnico

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
            "tipo_empleado": "ADMINISTRATIVO",
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
                "tipo_empleado": "ADMINISTRATIVO",
                "fecha_ingreso": timezone.localdate().isoformat(),
                "estado": "ACTIVO",
            },
        )
        empleado = Empleado.objects.get(numero_documento="10000002")
        self.assertRedirects(respuesta, reverse("gestion_humana:detalle", args=[empleado.pk]))
        self.assertEqual(empleado.creado_por, self.administrativa)
        self.assertTrue(HistorialEmpleado.objects.filter(empleado=empleado, accion="Creación").exists())

    def crear_tecnico(self, nombre="Andy Técnico"):
        return Tecnico.objects.create(
            nombre=nombre,
            telefono="3001234567",
            especialidad="Mantenimiento",
            valor_hora_diurna=Decimal("10000.00"),
            valor_hora_nocturna=Decimal("15000.00"),
        )

    def test_panel_muestra_tecnico_sin_ficha_y_precarga_formulario(self):
        tecnico = self.crear_tecnico()
        self.client.force_login(self.administrativa)

        panel = self.client.get(reverse("gestion_humana:panel"))
        self.assertContains(panel, "Técnicos pendientes de ficha laboral")
        self.assertContains(panel, tecnico.nombre)

        respuesta = self.client.get(
            reverse("gestion_humana:crear"),
            {"tecnico": tecnico.pk},
        )
        self.assertEqual(respuesta.context["form"].initial["tipo_empleado"], "TECNICO")
        self.assertEqual(respuesta.context["form"].initial["tecnico"], tecnico)

    def test_nuevo_empleado_sin_tecnico_abre_formulario(self):
        self.client.force_login(self.administrativa)
        respuesta = self.client.get(reverse("gestion_humana:crear"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context["form"].initial, {})

    def test_empleado_tecnico_exige_perfil_existente(self):
        self.client.force_login(self.administrativa)
        respuesta = self.client.post(
            reverse("gestion_humana:crear"),
            {
                "tipo_empleado": "TECNICO",
                "tipo_documento": "CC",
                "numero_documento": "10000003",
                "nombres": "Técnico",
                "apellidos": "Sin perfil",
                "cargo": "Técnico",
                "fecha_ingreso": timezone.localdate().isoformat(),
                "estado": "ACTIVO",
            },
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertFormError(
            respuesta.context["form"],
            "tecnico",
            "Seleccione el perfil técnico existente de este empleado.",
        )
        self.assertFalse(Empleado.objects.filter(numero_documento="10000003").exists())

    def test_vincula_ficha_sin_crear_otro_tecnico(self):
        tecnico = self.crear_tecnico()
        cantidad_inicial = Tecnico.objects.count()
        self.client.force_login(self.administrativa)
        respuesta = self.client.post(
            reverse("gestion_humana:crear"),
            {
                "tipo_empleado": "TECNICO",
                "tecnico": tecnico.pk,
                "tipo_documento": "CC",
                "numero_documento": "10000004",
                "nombres": "Andy",
                "apellidos": "Empleado",
                "cargo": "Técnico",
                "fecha_ingreso": timezone.localdate().isoformat(),
                "estado": "ACTIVO",
            },
        )
        empleado = Empleado.objects.get(numero_documento="10000004")
        self.assertRedirects(respuesta, reverse("gestion_humana:detalle", args=[empleado.pk]))
        self.assertEqual(empleado.tecnico, tecnico)
        self.assertEqual(Tecnico.objects.count(), cantidad_inicial)

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
