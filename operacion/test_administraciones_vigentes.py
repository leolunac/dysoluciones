"""Regresiones del portal multiunidad y sus límites de autorización."""
from datetime import date, datetime, timedelta, timezone as datetime_timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.utils import timezone

from .acceso_administraciones import asignaciones_administracion_vigentes
from .models import (
    Administracion, AdministracionUnidad, Cliente, ClienteAsignado,
    UsuarioAdministracion, UsuarioCliente,
)
from .views import dashboard_cliente, portal_unidades, usuario_puede_ver_cliente


class AdministracionesVigentesTests(TestCase):
    hoy = date(2026, 11, 9)

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.usuario = User.objects.create_user(username="administrador_prueba")
        cls.administracion = Administracion.objects.create(nombre="Administración de prueba")
        cls.perfil = UsuarioAdministracion.objects.create(
            user=cls.usuario, administracion=cls.administracion,
        )
        cls.unidades = []
        for i in range(13):
            unidad = Cliente.objects.create(nombre=f"Unidad {i:02}", tipo_contrato="SIN_CONTRATO")
            AdministracionUnidad.objects.create(
                administracion=cls.administracion, cliente=unidad,
                fecha_inicio=cls.hoy - timedelta(days=1),
                fecha_fin=None if i < 2 else date(2026, 12, 30),
            )
            cls.unidades.append(unidad)

    def setUp(self):
        self.factory = RequestFactory()
        self.zona = timezone.override("America/Bogota")
        self.zona.__enter__()
        self.addCleanup(self.zona.__exit__, None, None, None)
        # En UTC ya es el día siguiente; en Bogotá aún es 9 de noviembre.
        self.reloj = patch(
            "django.utils.timezone.now",
            return_value=datetime(2026, 11, 10, 2, tzinfo=datetime_timezone.utc),
        )
        self.reloj.start()
        self.addCleanup(self.reloj.stop)

    def contexto(self, user=None):
        request = self.factory.get("/mis-unidades/")
        request.user = user if user is not None else self.usuario
        with patch("operacion.views.render", return_value=HttpResponse()) as render:
            response = portal_unidades(request)
        self.assertEqual(response.status_code, 200)
        return render.call_args.args[2]

    def asignacion(self):
        return AdministracionUnidad.objects.get(
            administracion=self.administracion, cliente=self.unidades[2],
        )

    def comprobar_visible(self, esperado):
        unidad = self.unidades[2]
        visibles = set(self.contexto()["clientes"].values_list("pk", flat=True))
        self.assertEqual(unidad.pk in visibles, esperado)
        self.assertEqual(usuario_puede_ver_cliente(self.usuario, unidad.pk), esperado)

    def test_portal_muestra_las_trece_unidades_y_resumen(self):
        contexto = self.contexto()
        self.assertEqual(contexto["total_unidades"], 13)
        self.assertEqual(set(contexto["clientes"]), set(self.unidades))
        self.assertEqual(len(contexto["resumen_unidades"]), 13)
        for campo in ["total_correctivos", "total_preventivos", "total_cotizaciones"]:
            self.assertEqual(contexto[campo], 0)

    def test_permiso_incluye_fecha_final_futura(self):
        self.comprobar_visible(True)

    def test_sin_fecha_final_sigue_visible(self):
        self.assertTrue(usuario_puede_ver_cliente(self.usuario, self.unidades[0].pk))
        self.assertIn(self.unidades[0], self.contexto()["clientes"])

    def test_fecha_final_hoy_es_inclusiva(self):
        a = self.asignacion(); a.fecha_fin = self.hoy; a.save()
        self.comprobar_visible(True)

    def test_fecha_inicio_hoy_es_inclusiva(self):
        a = self.asignacion(); a.fecha_inicio = self.hoy; a.save()
        self.comprobar_visible(True)

    def test_asignacion_vencida_no_se_muestra_ni_autoriza(self):
        a = self.asignacion(); a.fecha_fin = self.hoy - timedelta(days=1); a.save()
        self.comprobar_visible(False)

    def test_inicio_futuro_no_se_muestra_con_o_sin_fin(self):
        for fin in [None, date(2026, 12, 30)]:
            with self.subTest(fin=fin):
                a = self.asignacion()
                a.fecha_inicio = self.hoy + timedelta(days=1); a.fecha_fin = fin; a.save()
                self.comprobar_visible(False)

    def test_asignacion_inactiva_no_se_muestra_ni_autoriza(self):
        a = self.asignacion(); a.activo = False; a.save()
        self.comprobar_visible(False)

    def test_unidad_inactiva_no_se_muestra_ni_autoriza(self):
        unidad = self.unidades[2]; unidad.activo = False; unidad.save()
        self.comprobar_visible(False)

    def test_otra_administracion_no_obtiene_acceso(self):
        a = self.asignacion()
        a.administracion = Administracion.objects.create(nombre="Administración ajena")
        a.save()
        self.comprobar_visible(False)

    def test_perfil_inactivo_no_autoriza(self):
        self.perfil.activo = False; self.perfil.save()
        self.assertFalse(usuario_puede_ver_cliente(self.usuario, self.unidades[0].pk))
        request = self.factory.get("/mis-unidades/"); request.user = self.usuario
        self.assertEqual(portal_unidades(request).status_code, 403)

    def test_cliente_tradicional_conserva_sus_asignaciones(self):
        user = get_user_model().objects.create_user(username="cliente_tradicional")
        perfil = UsuarioCliente.objects.create(user=user, cliente=self.unidades[0])
        ClienteAsignado.objects.create(usuario_cliente=perfil, cliente=self.unidades[1])
        self.assertEqual(set(self.contexto(user)["clientes"]), set(self.unidades[:2]))
        self.assertTrue(usuario_puede_ver_cliente(user, self.unidades[0].pk))
        self.assertTrue(usuario_puede_ver_cliente(user, self.unidades[1].pk))
        self.assertFalse(usuario_puede_ver_cliente(user, self.unidades[2].pk))

    def test_personal_interno_conserva_acceso(self):
        user = get_user_model().objects.create_user(username="interno", is_staff=True)
        self.assertEqual(self.contexto(user)["clientes"].count(), 13)
        self.assertTrue(usuario_puede_ver_cliente(user, self.unidades[2].pk))

    def test_sin_asignaciones_no_autoriza(self):
        user = get_user_model().objects.create_user(username="sin_asignaciones")
        self.assertFalse(usuario_puede_ver_cliente(user, self.unidades[2].pk))

    def test_vigencia_usa_la_fecha_local_y_no_la_fecha_utc(self):
        self.assertEqual(timezone.localdate(), self.hoy)
        a = self.asignacion(); a.fecha_fin = self.hoy; a.save()
        self.assertTrue(asignaciones_administracion_vigentes(self.administracion).filter(pk=a.pk).exists())
        self.comprobar_visible(True)

    def test_acceso_directo_a_unidad_vencida_devuelve_403(self):
        a = self.asignacion(); a.fecha_fin = self.hoy - timedelta(days=1); a.save()
        request = self.factory.get(f"/cliente/{a.cliente_id}/"); request.user = self.usuario
        self.assertEqual(dashboard_cliente(request, a.cliente_id).status_code, 403)

    def test_acceso_directo_a_unidad_vigente_permitido(self):
        unidad = self.unidades[2]
        request = self.factory.get(f"/cliente/{unidad.pk}/"); request.user = self.usuario
        with patch("operacion.views.render", return_value=HttpResponse()) as render:
            self.assertEqual(dashboard_cliente(request, unidad.pk).status_code, 200)
        self.assertEqual(render.call_args.args[2]["cliente"], unidad)

    def test_acceso_directo_a_unidad_ajena_devuelve_403(self):
        unidad = Cliente.objects.create(nombre="Unidad ajena", tipo_contrato="SIN_CONTRATO")
        request = self.factory.get(f"/cliente/{unidad.pk}/"); request.user = self.usuario
        self.assertEqual(dashboard_cliente(request, unidad.pk).status_code, 403)

    def test_documentos_solo_publicados_y_unicamente_durante_vigencia(self):
        from django.core.exceptions import PermissionDenied
        from portal_cliente.models import DocumentoCliente
        from portal_cliente.views import mis_documentos
        unidad = self.unidades[2]
        publicado = DocumentoCliente.objects.create(
            cliente=unidad, titulo="Publicado", fecha_documento=self.hoy,
            archivo="prueba.pdf", estado="PUBLICADO",
        )
        DocumentoCliente.objects.create(
            cliente=unidad, titulo="Borrador", fecha_documento=self.hoy,
            archivo="prueba.pdf", estado="BORRADOR",
        )
        request = self.factory.get("/documentos/"); request.user = self.usuario
        with patch("portal_cliente.views.render", return_value=HttpResponse()) as render:
            self.assertEqual(mis_documentos(request, unidad.pk).status_code, 200)
        self.assertEqual(list(render.call_args.args[2]["documentos"]), [publicado])
        a = self.asignacion(); a.fecha_fin = self.hoy - timedelta(days=1); a.save()
        with self.assertRaises(PermissionDenied):
            mis_documentos(request, unidad.pk)

    def test_asignaciones_repetidas_no_duplican_tarjetas(self):
        AdministracionUnidad.objects.create(
            administracion=self.administracion, cliente=self.unidades[2],
            fecha_inicio=self.hoy, fecha_fin=self.hoy,
        )
        contexto = self.contexto()
        self.assertEqual(contexto["total_unidades"], 13)
        self.assertEqual(len(contexto["resumen_unidades"]), 13)
