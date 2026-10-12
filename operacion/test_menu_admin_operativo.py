from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from .templatetags.roles_sigob import rol_menu_sigob


class MenuAdminOperativoTests(TestCase):
    def setUp(self):
        self.administrador = User.objects.create_superuser(
            username="admin_menu_operativo",
            password="clave-segura",
            email="admin@example.com",
        )
        self.client.force_login(self.administrador)

    def test_menu_admin_enlaza_pantallas_operativas(self):
        respuesta = self.client.get(reverse("lista_actividades"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, reverse("portal_unidades"))
        self.assertContains(respuesta, reverse("centro_operaciones"))
        self.assertContains(respuesta, reverse("levantamiento_equipo"))
        self.assertContains(respuesta, reverse("tablero_lavados"))
        self.assertContains(respuesta, "/admin/")
        self.assertNotContains(respuesta, "/admin/operacion/cliente/")
        self.assertNotContains(respuesta, "/admin/operacion/emergencia/")
        self.assertNotContains(respuesta, "/admin/operacion/equipounidad/")

    def test_enlaces_operativos_responden_para_superusuario(self):
        for nombre_ruta in (
            "portal_unidades",
            "centro_operaciones",
            "levantamiento_equipo",
            "tablero_lavados",
        ):
            with self.subTest(ruta=nombre_ruta):
                respuesta = self.client.get(reverse(nombre_ruta))
                self.assertEqual(respuesta.status_code, 200)

    def test_rol_menu_funciona_para_usuario_interno_no_superusuario(self):
        coordinador = User.objects.create_user(
            username="coordinador_menu",
            password="clave-segura",
        )
        grupo = Group.objects.create(name="GESTION_COORDINADOR")
        coordinador.groups.add(grupo)

        self.assertEqual(rol_menu_sigob(coordinador), "COORDINADOR")
