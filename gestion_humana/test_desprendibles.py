import tempfile
from datetime import date
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from operacion.models import Tecnico
from .models import DesprendiblePago, Empleado


class DesprendiblesTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        field = DesprendiblePago._meta.get_field('archivo')
        patcher = patch.object(field, 'storage', FileSystemStorage(location=self.tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.rrhh = User.objects.create_user('rrhh', password='x')
        self.rrhh.groups.add(Group.objects.get_or_create(name='GESTION_HUMANA')[0])
        self.gerente = User.objects.create_user('gerente', password='x')
        self.gerente.groups.add(Group.objects.get_or_create(name='GESTION_GERENCIA')[0])
        self.tecnico_user = User.objects.create_user('tecnico', password='x')
        self.otro = User.objects.create_user('otro', password='x')
        tecnico = Tecnico.objects.create(user=self.tecnico_user, nombre='Carlos', telefono='3000000000', especialidad='Prueba', valor_hora_diurna=1, valor_hora_nocturna=1)
        self.empleado = Empleado.objects.create(tecnico=tecnico, tipo_empleado='TECNICO', numero_documento='123', nombres='Carlos', apellidos='Prueba', cargo='Tecnico', fecha_ingreso=date(2020, 1, 1), creado_por=self.rrhh, actualizado_por=self.rrhh)

    def archivo(self, contenido=b'%PDF-1.4\nprueba'):
        return SimpleUploadedFile('prueba.pdf', contenido, content_type='application/pdf')

    def datos(self, archivo=None):
        return {'empleado': self.empleado.pk, 'periodo_inicio': '2026-10-01', 'periodo_fin': '2026-10-15', 'archivo': archivo or self.archivo()}

    def test_carga_y_acceso_privado(self):
        self.client.force_login(self.rrhh)
        url = reverse('gestion_humana:desprendibles_administrar')
        self.assertEqual(self.client.post(url, self.datos()).status_code, 302)
        registro = DesprendiblePago.objects.get()
        descarga = reverse('gestion_humana:desprendibles_descargar', args=[registro.pk])
        self.client.force_login(self.tecnico_user)
        self.assertContains(self.client.get(reverse('gestion_humana:mis_desprendibles')), '15/10/2026')
        response = self.client.get(descarga)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(b''.join(response.streaming_content).startswith(b'%PDF-'))
        response.close()
        self.client.force_login(self.otro)
        self.assertEqual(self.client.get(descarga).status_code, 404)
        self.client.force_login(self.gerente)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.get(descarga).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(descarga).status_code, 302)

    def test_valida_pdf_fechas_y_duplicados(self):
        self.client.force_login(self.rrhh)
        url = reverse('gestion_humana:desprendibles_administrar')
        self.assertEqual(self.client.post(url, self.datos(self.archivo(b'no es pdf'))).status_code, 200)
        datos = self.datos()
        datos['periodo_fin'] = '2026-09-01'
        self.assertEqual(self.client.post(url, datos).status_code, 200)
        self.assertEqual(DesprendiblePago.objects.count(), 0)
        self.assertEqual(self.client.post(url, self.datos()).status_code, 302)
        self.assertEqual(self.client.post(url, self.datos()).status_code, 200)
        self.assertEqual(DesprendiblePago.objects.count(), 1)

    def test_vista_previa_respeta_permisos(self):
        self.client.force_login(self.rrhh)
        self.client.post(
            reverse('gestion_humana:desprendibles_administrar'),
            self.datos(),
        )
        registro = DesprendiblePago.objects.get()
        url = reverse('gestion_humana:desprendibles_descargar', args=[registro.pk])

        self.client.force_login(self.tecnico_user)
        respuesta = self.client.get(url + '?ver=1')
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta['Content-Disposition'].startswith('inline'))
        respuesta.close()

        self.client.force_login(self.otro)
        self.assertEqual(self.client.get(url + '?ver=1').status_code, 404)


    def test_retiro_y_reemplazo(self):
        self.client.force_login(self.rrhh)
        admin = reverse('gestion_humana:desprendibles_administrar')
        self.assertEqual(self.client.post(admin, self.datos()).status_code, 302)
        registro = DesprendiblePago.objects.get()
        retirar = reverse('gestion_humana:desprendibles_retirar', args=[registro.pk])
        archivo = reverse('gestion_humana:desprendibles_descargar', args=[registro.pk])
        self.client.force_login(self.tecnico_user)
        self.assertEqual(self.client.post(retirar).status_code, 403)
        self.client.force_login(self.rrhh)
        self.assertEqual(self.client.get(retirar).status_code, 405)
        self.assertEqual(self.client.post(retirar).status_code, 302)
        registro.refresh_from_db()
        self.assertFalse(registro.activo)
        self.assertEqual(registro.retirado_por, self.rrhh)
        self.assertIsNotNone(registro.retirado)
        self.client.force_login(self.tecnico_user)
        self.assertEqual(self.client.get(archivo).status_code, 404)
        self.assertEqual(self.client.get(archivo + '?ver=1').status_code, 404)
        self.assertNotContains(self.client.get(reverse('gestion_humana:mis_desprendibles')), '15/10/2026')
        self.client.force_login(self.rrhh)
        self.assertEqual(self.client.post(admin, self.datos()).status_code, 302)
        self.assertEqual(DesprendiblePago.objects.filter(activo=True).count(), 1)
