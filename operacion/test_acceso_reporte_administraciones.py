"""Permisos y consulta del reporte fuera del administrador de Django."""
from datetime import date
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.test import TestCase, override_settings
from django.urls import include, path, reverse
from openpyxl import load_workbook

from .models import Administracion, AdministracionUnidad, Cliente, Tecnico, UsuarioAdministracion, UsuarioCliente
from .reporte_administraciones_panel import GRUPOS_INTERNOS, puede_ver_reporte_interno, reporte_administraciones_panel


def inicio_prueba(request):
    return HttpResponse("Panel interno")


# URLConf aislado: no depende de servicios externos ni de datos de producción.
urlpatterns = [
    path("administraciones/unidades/", reporte_administraciones_panel, name="reporte_administraciones_panel"),
    path("", inicio_prueba, name="home"),
]
for nombre in ("escritorio_coordinador", "centro_operaciones", "lista_bitacora", "lista_remisiones",
               "lista_actividades", "portal_unidades", "levantamiento_equipo", "tablero_lavados",
               "panel_tecnico", "historial_preventivos", "logout", "bandeja_revision_preventivos",
               "nueva_llamada", "lista_documentos"):
    urlpatterns.append(path("prueba/" + nombre + "/", inicio_prueba, name=nombre))
for espacio, nombres in {
    "gestion_comercial": ["panel", "lista_cotizaciones", "consolidado_facturacion", "nueva_liquidacion",
                           "nueva_cotizacion", "lista_contratos_pases", "consolidado_facturacion_pases",
                           "lista_materiales_utilizados"],
    "gestion_humana": ["panel"], "inventario": ["tablero"],
}.items():
    rutas = [path(nombre + "/", inicio_prueba, name=nombre) for nombre in nombres]
    urlpatterns.append(path(espacio + "/", include((rutas, espacio))))


@override_settings(ROOT_URLCONF=__name__)
class AccesoReporteAdministracionesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.facturacion = User.objects.create_user(username="reporte_facturacion")
        cls.facturacion.groups.add(Group.objects.create(name="GESTION_FACTURACION"))
        cls.externo = User.objects.create_user(username="reporte_cliente")
        cls.staff = User.objects.create_user(username="reporte_interno_staff", is_staff=True)
        cls.admin = Administracion.objects.create(nombre="ADMINISTRACION PRUEBA", nit="100")
        cls.unidad = Cliente.objects.create(nombre="UNIDAD VIGENTE", nit="001234", activo=True)
        cls.otra = Cliente.objects.create(nombre="UNIDAD VENCIDA", activo=True)
        AdministracionUnidad.objects.create(administracion=cls.admin, cliente=cls.unidad,
                                            activo=True, fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 30))
        AdministracionUnidad.objects.create(administracion=cls.admin, cliente=cls.otra,
                                            activo=True, fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 1, 2))

    def setUp(self):
        self.client.force_login(self.facturacion)
        self.url = reverse("reporte_administraciones_panel")
        fecha = patch("operacion.reporte_administraciones_panel.timezone.localdate", return_value=date(2026, 11, 9))
        fecha.start()
        self.addCleanup(fecha.stop)

    def test_facturacion_sin_staff_ni_permisos_admin_consulta(self):
        self.assertFalse(self.facturacion.is_staff)
        response = self.client.get(self.url)
        self.assertContains(response, "UNIDAD VIGENTE")
        self.assertNotContains(response, "UNIDAD VENCIDA")
        self.assertNotContains(response, 'href="/admin/')
        self.assertIn("no-store", response["Cache-Control"])

    def test_roles_internos_tienen_acceso(self):
        for nombre in GRUPOS_INTERNOS:
            with self.subTest(rol=nombre):
                self.facturacion.groups.set([Group.objects.get_or_create(name=nombre)[0]])
                self.assertEqual(self.client.get(self.url).status_code, 200)
                self.assertEqual(self.client.get(self.url, {"formato": "excel"}).status_code, 200)

    def test_staff_interno_consulta(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_anonimo_requiere_login(self):
        self.client.logout()
        for params in ({}, {"formato": "excel"}):
            self.assertEqual(self.client.get(self.url, params).status_code, 302)

    def test_usuario_sin_rol_no_consulta_ni_exporta(self):
        self.client.force_login(self.externo)
        for params in ({}, {"formato": "excel"}):
            self.assertEqual(self.client.get(self.url, params).status_code, 403)

    def test_administracion_externa_bloqueada_incluso_staff_y_grupo(self):
        UsuarioAdministracion.objects.create(user=self.facturacion, administracion=self.admin)
        self.facturacion.is_staff = True
        self.facturacion.save()
        for params in ({}, {"formato": "excel"}):
            self.assertEqual(self.client.get(self.url, params).status_code, 403)

    def test_cliente_externo_bloqueado_incluso_staff(self):
        UsuarioCliente.objects.create(user=self.staff, cliente=self.unidad)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.get(self.url, {"formato": "excel"}).status_code, 403)

    def test_tecnico_sin_rol_interno_bloqueado_incluso_staff(self):
        Tecnico.objects.create(user=self.staff, nombre="TECNICO", telefono="1", especialidad="BOMBAS",
                               valor_hora_diurna=1, valor_hora_nocturna=1, activo=False)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.get(self.url, {"formato": "excel"}).status_code, 403)

    def test_superusuario_consulta(self):
        self.staff.is_superuser = True
        self.staff.save()
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_inactivo_no_autorizado(self):
        self.facturacion.is_active = False
        self.assertFalse(puede_ver_reporte_interno(self.facturacion))

    def test_historial_y_filtros(self):
        self.assertContains(self.client.get(self.url, {"estado": "todas"}), "UNIDAD VENCIDA")
        response = self.client.get(self.url, {"q": "NO EXISTE"})
        self.assertNotContains(response, "UNIDAD VIGENTE")
        response = self.client.get(self.url, {"administracion": self.admin.pk})
        self.assertContains(response, "UNIDAD VIGENTE")
        self.assertIn("administracion=" + str(self.admin.pk), response.context_data["excel_url"])

    def test_excel_filtrado_conserva_nit(self):
        response = self.client.get(self.url, {"formato": "excel", "q": "VIGENTE"})
        self.assertEqual(response.status_code, 200)
        ws = load_workbook(BytesIO(response.content)).active
        self.assertEqual(ws["D8"].value, "UNIDAD VIGENTE")
        self.assertEqual(ws["E8"].value, "001234")
        self.assertEqual(ws.max_row, 8)

    def test_filtros_invalidos_no_amplian_consulta(self):
        for datos in ({"estado": "invalido"}, {"administracion": "9999999"}, {"formato": "pdf"}):
            self.assertEqual(self.client.get(self.url, datos).status_code, 400)

    def test_solo_lectura_y_no_post(self):
        antes = list(AdministracionUnidad.objects.values())
        self.client.get(self.url)
        self.client.get(self.url, {"formato": "excel"})
        self.assertEqual(list(AdministracionUnidad.objects.values()), antes)
        self.assertEqual(self.client.post(self.url).status_code, 405)

    def test_botones_en_paneles_y_ocultos_para_externo(self):
        from django.test import RequestFactory
        for plantilla in ("base.html", "dashboard.html", "menu_principal.html", "escritorio_coordinador.html", "gestion_comercial/panel.html"):
            for usuario, visible in ((self.facturacion, True), (self.externo, False)):
                with self.subTest(plantilla=plantilla, visible=visible):
                    request = RequestFactory().get("/")
                    request.user = usuario
                    html = render_to_string(plantilla, {"request": request})
                    self.assertEqual(('href="' + self.url + '"') in html, visible)
