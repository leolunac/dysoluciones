"""Reporte interno, exportación y permisos de administraciones y unidades."""
from datetime import date, datetime, timedelta, timezone as datetime_timezone
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from .models import Administracion, AdministracionUnidad, Cliente


class ReporteAdministracionesTests(TestCase):
    hoy = date(2026, 11, 9)

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.supervisor = User.objects.create_user(username="reporte_superusuario", is_staff=True, is_superuser=True)
        cls.lector = User.objects.create_user(username="reporte_lector", is_staff=True)
        cls.lector.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="operacion", codename__in=["view_administracion", "view_administracionunidad"],
        ))
        cls.sin_permiso = User.objects.create_user(username="reporte_sin_permiso", is_staff=True)
        cls.externo = User.objects.create_user(username="reporte_externo")
        cls.administracion = Administracion.objects.create(nombre="ABELARDO YEPES", nit="100", telefono="123")
        cls.otra = Administracion.objects.create(nombre="OTRA ADMINISTRACION", nit="200")
        cls.vacia = Administracion.objects.create(nombre="SIN UNIDADES", nit="300")
        cls.unidades = []
        for i in range(13):
            unidad = Cliente.objects.create(
                nombre=f"UNIDAD ADICIONAL {i:02}", nit=f"800{i:03}", direccion=f"CALLE PRUEBA {i}",
                tipo_contrato="PREVENTIVO", activo=True,
            )
            AdministracionUnidad.objects.create(
                administracion=cls.administracion, cliente=unidad,
                fecha_inicio=cls.hoy - timedelta(days=5),
                fecha_fin=None if i < 2 else date(2026, 12, 30),
            )
            cls.unidades.append(unidad)
        for nombre, inicio, fin, asignacion_activa, unidad_activa in [
            ("UNIDAD FINALIZADA", cls.hoy-timedelta(days=30), cls.hoy-timedelta(days=1), True, True),
            ("UNIDAD FUTURA", cls.hoy+timedelta(days=1), None, True, True),
            ("ASIGNACION INACTIVA", cls.hoy, None, False, True),
            ("UNIDAD INACTIVA", cls.hoy, None, True, False),
        ]:
            unidad = Cliente.objects.create(nombre=nombre, tipo_contrato="SIN_CONTRATO", activo=unidad_activa)
            AdministracionUnidad.objects.create(
                administracion=cls.administracion, cliente=unidad,
                fecha_inicio=inicio, fecha_fin=fin, activo=asignacion_activa,
            )
        cls.unidad_ajena = Cliente.objects.create(nombre="UNIDAD AJENA", tipo_contrato="SIN_CONTRATO")
        AdministracionUnidad.objects.create(
            administracion=cls.otra, cliente=cls.unidad_ajena, fecha_inicio=cls.hoy,
        )

    def setUp(self):
        self.client.force_login(self.supervisor)
        self.url = reverse("admin:operacion_usuarioadministracion_reporte_unidades")
        self.zona = timezone.override("America/Bogota")
        self.zona.__enter__()
        self.addCleanup(self.zona.__exit__, None, None, None)
        reloj = patch("django.utils.timezone.now", return_value=datetime(2026, 11, 10, 2, tzinfo=datetime_timezone.utc))
        reloj.start(); self.addCleanup(reloj.stop)

    def libro(self, parametros=None):
        response = self.client.get(self.url, {**(parametros or {}), "formato": "excel"})
        self.assertEqual(response.status_code, 200)
        return response, load_workbook(BytesIO(response.content))

    def test_vigentes_incluye_trece_unidades_y_administracion_sin_asignaciones(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["resumen"], {"administraciones": 3, "unidades": 14, "asignaciones": 14})
        grupo = next(g for g in response.context["grupos"] if g["administracion"] == self.administracion)
        self.assertEqual(grupo["total"], 13)
        self.assertContains(response, "SIN UNIDADES")
        for nombre in ["UNIDAD FINALIZADA", "UNIDAD FUTURA", "ASIGNACION INACTIVA", "UNIDAD INACTIVA"]:
            self.assertNotContains(response, nombre)

    def test_historial_incluye_situaciones_y_fechas(self):
        response = self.client.get(self.url, {"estado": "todas"})
        self.assertEqual(response.context["resumen"]["asignaciones"], 18)
        for texto in ["Finalizada", "Inicio futuro", "Asignación inactiva", "Unidad inactiva", "30/12/2026"]:
            self.assertContains(response, texto)

    def test_busqueda_por_administracion(self):
        response = self.client.get(self.url, {"q": "ABELARDO"})
        self.assertEqual(response.context["resumen"], {"administraciones": 1, "unidades": 13, "asignaciones": 13})
        self.assertNotContains(response, "UNIDAD AJENA")

    def test_busqueda_por_unidad_filtra_filas(self):
        response = self.client.get(self.url, {"q": "ADICIONAL 05"})
        self.assertEqual(response.context["resumen"]["asignaciones"], 1)
        self.assertContains(response, "UNIDAD ADICIONAL 05")
        self.assertNotContains(response, "UNIDAD ADICIONAL 06")

    def test_busqueda_por_nit_o_direccion(self):
        for q in ["800005", "CALLE PRUEBA 5"]:
            with self.subTest(q=q):
                response = self.client.get(self.url, {"q": q})
                self.assertEqual(response.context["resumen"]["unidades"], 1)

    def test_selector_administracion(self):
        response = self.client.get(self.url, {"administracion": self.otra.pk})
        self.assertEqual(response.context["resumen"]["unidades"], 1)
        self.assertContains(response, "UNIDAD AJENA")
        self.assertNotContains(response, "UNIDAD ADICIONAL 05")

    def test_busqueda_administracion_vacia(self):
        response = self.client.get(self.url, {"q": "SIN UNIDADES"})
        self.assertEqual(response.context["resumen"], {"administraciones": 1, "unidades": 0, "asignaciones": 0})

    def test_sin_resultados(self):
        response = self.client.get(self.url, {"q": "NO EXISTE ESTA ADMINISTRACION"})
        self.assertContains(response, "No se encontraron administraciones")
        self.assertEqual(response.context["resumen"]["administraciones"], 0)

    def test_excel_respeta_filtros_y_conserva_fecha_y_nit(self):
        response, wb = self.libro({"administracion": self.administracion.pk, "q": "ADICIONAL 05"})
        ws = wb.active
        self.assertIn(".xlsx", response["Content-Disposition"])
        self.assertEqual(ws.max_row, 8)
        self.assertEqual(ws["D8"].value, "UNIDAD ADICIONAL 05")
        self.assertEqual(ws["E8"].value, "800005")
        self.assertEqual(ws["J8"].value.date(), date(2026, 12, 30))
        self.assertEqual(ws["L8"].value, "Vigente")
        self.assertEqual(ws.freeze_panes, "D8")
        self.assertEqual(ws.auto_filter.ref, "A7:L8")

    def test_excel_historial_con_todas_las_filas(self):
        _, wb = self.libro({"estado": "todas", "administracion": self.administracion.pk})
        self.assertEqual(wb.active.max_row, 24)
        situaciones = {wb.active.cell(row, 12).value for row in range(8, 25)}
        self.assertEqual(situaciones, {"Vigente", "Finalizada", "Inicio futuro", "Asignación inactiva", "Unidad inactiva"})

    def test_excel_no_interpreta_textos_como_formulas(self):
        self.administracion.nombre = "=SUM(1,1)"; self.administracion.save()
        self.unidades[0].nombre = "=HYPERLINK(1)"; self.unidades[0].save()
        _, wb = self.libro({"administracion": self.administracion.pk, "q": "=SUM(1,1)"})
        ws = wb.active
        for fila in ws:
            for celda in fila:
                self.assertNotEqual(celda.data_type, "f")
        self.assertEqual(ws["B4"].value, "=SUM(1,1)")
        self.assertEqual(ws["B4"].data_type, "s")

    def test_excel_administracion_sin_unidades(self):
        _, wb = self.libro({"administracion": self.vacia.pk})
        self.assertEqual(wb.active["A8"].value, "SIN UNIDADES")
        self.assertIsNone(wb.active["D8"].value)
        self.assertEqual(wb.active["L8"].value, "Sin asignaciones para estos filtros")

    def test_filtros_invalidos_no_exportan_todo(self):
        for parametros in [{"estado": "invalid"}, {"administracion": "no-es-id"}, {"administracion": "999999"}, {"q": "x"*151}, {"formato": "csv"}]:
            with self.subTest(parametros=parametros):
                self.assertEqual(self.client.get(self.url, parametros).status_code, 400)
                self.assertEqual(self.client.get(self.url, {**parametros, "formato": parametros.get("formato", "excel")}).status_code, 400)

    def test_anonimo_y_externo_no_acceden(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.client.force_login(self.externo)
        self.assertEqual(self.client.get(self.url, {"formato": "excel"}).status_code, 302)

    def test_staff_sin_permisos_no_accede_ni_exporta(self):
        self.client.force_login(self.sin_permiso)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.get(self.url, {"formato": "excel"}).status_code, 403)

    def test_permiso_solo_usuarios_administracion_no_basta(self):
        self.sin_permiso.user_permissions.add(Permission.objects.get(content_type__app_label="operacion", codename="view_usuarioadministracion"))
        self.client.force_login(self.sin_permiso)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        response = self.client.get(reverse("admin:operacion_usuarioadministracion_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Administraciones y unidades</a>")

    def test_lector_autorizado_consulta_y_exporta(self):
        self.client.force_login(self.lector)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(self.client.get(self.url, {"formato": "excel"}).status_code, 200)

    def test_boton_y_ruta_en_los_tres_listados(self):
        for modelo in ["administracion", "administracionunidad", "usuarioadministracion"]:
            with self.subTest(modelo=modelo):
                url = reverse(f"admin:operacion_{modelo}_reporte_unidades")
                response = self.client.get(reverse(f"admin:operacion_{modelo}_changelist"))
                self.assertContains(response, url)
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_fecha_local_y_limites_inclusivos(self):
        asignacion = AdministracionUnidad.objects.get(cliente=self.unidades[2])
        asignacion.fecha_inicio = self.hoy; asignacion.fecha_fin = self.hoy; asignacion.save()
        response = self.client.get(self.url, {"q": "ADICIONAL 02"})
        self.assertEqual(response.context["hoy"], self.hoy)
        self.assertEqual(response.context["resumen"]["unidades"], 1)

    def test_historial_no_duplica_conteo_de_unidades(self):
        AdministracionUnidad.objects.create(
            administracion=self.administracion, cliente=self.unidades[0],
            fecha_inicio=self.hoy-timedelta(days=90), fecha_fin=self.hoy-timedelta(days=60),
        )
        response = self.client.get(self.url, {"estado": "todas", "administracion": self.administracion.pk})
        self.assertEqual(response.context["resumen"]["asignaciones"], 18)
        self.assertEqual(response.context["resumen"]["unidades"], 17)

    def test_textos_se_escapan_en_html(self):
        self.administracion.nombre = '<script>alert("prueba")</script>'; self.administracion.save()
        response = self.client.get(self.url, {"administracion": self.administracion.pk})
        self.assertNotContains(response, '<script>alert("prueba")</script>')
        self.assertContains(response, '&lt;script&gt;')

    def test_consulta_no_modifica_asignaciones(self):
        anteriores = list(AdministracionUnidad.objects.order_by("pk").values())
        self.client.get(self.url)
        self.client.get(self.url, {"formato": "excel", "estado": "todas"})
        self.assertEqual(anteriores, list(AdministracionUnidad.objects.order_by("pk").values()))

    def test_post_no_permitido(self):
        self.assertEqual(self.client.post(self.url).status_code, 405)
