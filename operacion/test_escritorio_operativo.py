from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse


class EscritorioOperativoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.coordinador = User.objects.create_user(
            "coordinador_escritorio", password="clave-segura"
        )
        cls.supervisor = User.objects.create_user(
            "supervisor_escritorio", password="clave-segura"
        )
        cls.sin_rol = User.objects.create_user(
            "sin_rol_escritorio", password="clave-segura"
        )
        cls.coordinador.groups.add(
            Group.objects.get_or_create(name="GESTION_COORDINADOR")[0]
        )
        cls.supervisor.groups.add(
            Group.objects.get_or_create(name="GESTION_SUPERVISOR")[0]
        )

    def test_home_envia_coordinador_y_supervisor_al_escritorio(self):
        for usuario in (self.coordinador, self.supervisor):
            self.client.force_login(usuario)
            respuesta = self.client.get(reverse("home"))
            self.assertRedirects(
                respuesta,
                reverse("escritorio_coordinador"),
                fetch_redirect_response=False,
            )

    def test_login_envia_supervisor_al_escritorio(self):
        respuesta = self.client.post(
            reverse("login"),
            {"username": self.supervisor.username, "password": "clave-segura"},
        )
        self.assertRedirects(
            respuesta,
            reverse("escritorio_coordinador"),
            fetch_redirect_response=False,
        )

    def test_supervisor_accede_a_operacion_y_cotizaciones(self):
        self.client.force_login(self.supervisor)
        rutas = [
            "escritorio_coordinador",
            "centro_operaciones",
            "nueva_llamada",
            "tablero_lavados",
            "lista_remisiones",
            "bandeja_revision_preventivos",
            "lista_actividades",
            "gestion_comercial:lista_cotizaciones",
        ]
        for nombre in rutas:
            with self.subTest(ruta=nombre):
                self.assertEqual(self.client.get(reverse(nombre)).status_code, 200)

    def test_escritorio_muestra_enlaces_segun_el_rol(self):
        self.client.force_login(self.supervisor)
        respuesta = self.client.get(reverse("escritorio_coordinador"))
        self.assertContains(respuesta, "Escritorio Operativo")
        self.assertContains(
            respuesta, reverse("gestion_comercial:lista_cotizaciones")
        )
        self.assertNotContains(respuesta, "Gestión Comercial / Liquidaciones")

        self.client.force_login(self.coordinador)
        respuesta = self.client.get(reverse("escritorio_coordinador"))
        self.assertContains(respuesta, reverse("gestion_comercial:lista_cotizaciones"))
        self.assertContains(respuesta, reverse("gestion_comercial:panel"))

    def test_usuario_sin_rol_no_accede_al_escritorio(self):
        self.client.force_login(self.sin_rol)
        self.assertEqual(
            self.client.get(reverse("escritorio_coordinador")).status_code,
            403,
        )
