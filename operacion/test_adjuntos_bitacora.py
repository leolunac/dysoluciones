"""Acceso privado, confirmación, validación y conservación de adjuntos."""
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType
from unittest.mock import patch
from uuid import uuid4
from zipfile import ZipFile, ZIP_DEFLATED
import hashlib
import warnings

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.conf.urls.static import static
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import DatabaseError
from django.db.models.deletion import ProtectedError
from django.test import TestCase, RequestFactory, Client as HttpClient, override_settings
from django.urls import reverse
from PIL import Image

from .models import AdjuntoBitacora, BitacoraOperativa, SeguimientoBitacora
from .adjuntos_bitacora import MAX_BYTES, raiz_privada, almacenamiento_privado, nombre_seguro


def imagen_bytes(formato='PNG',color='blue'):
    data=BytesIO();Image.new('RGB',(12,12),color).save(data,format=formato);return data.getvalue()


def office_bytes(extension='docx',macro=False):
    principal='word/document.xml' if extension=='docx' else 'xl/workbook.xml'
    tipo=('application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml' if extension=='docx'
          else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml')
    data=BytesIO()
    with ZipFile(data,'w',ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml',f'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/{principal}" ContentType="{tipo}"/></Types>')
        z.writestr(principal,'<document/>')
        if macro:z.writestr('word/vbaProject.bin',b'macro')
    return data.getvalue()


class AdjuntosBitacoraTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from .test_historial_bitacora import HistorialBitacoraTests
        HistorialBitacoraTests.setUpTestData.__func__(cls)

    def setUp(self):
        temp=TemporaryDirectory();self.addCleanup(temp.cleanup);self.temp=Path(temp.name)
        self.enterContext(override_settings(
            BASE_DIR=self.temp/'proyecto',MEDIA_ROOT=self.temp/'media',MEDIA_URL='/media/',
            STATIC_ROOT=self.temp/'static',STATICFILES_DIRS=[],BITACORA_ADJUNTOS_ROOT=self.temp/'privado',
        ))
        self.client.force_login(self.coord)
        self.url=reverse('adjuntar_bitacora',args=[self.reg.pk])
        self.historial=reverse('historial_bitacora',args=[self.reg.pk])

    def token(self):
        r=self.client.get(self.url)
        self.assertEqual(r.status_code,200)
        return r.context['form_adjunto'].initial['solicitud']

    def subir(self,token=None,data=None,nombre='foto.png',**kwargs):
        datos={'solicitud':token or self.token(),'confirmar':'on','descripcion':'Soporte de prueba',
               'archivo':SimpleUploadedFile(nombre,imagen_bytes() if data is None else data,content_type='application/octet-stream')}
        datos.update(kwargs)
        return self.client.post(self.url,datos)

    def descarga_url(self,adjunto=None):
        return reverse('descargar_adjunto_bitacora',args=[(adjunto or AdjuntoBitacora.objects.get()).pk])

    def leer_descarga(self,adjunto=None):
        r=self.client.get(self.descarga_url(adjunto));self.assertEqual(r.status_code,200)
        # El cliente de Django cierra la respuesta al consumir el iterador.
        # Un cierre manual adicional emite request_finished fuera de su protección.
        return b''.join(r.streaming_content)

    def archivos(self):
        return [p for p in (self.temp/'privado').rglob('*') if p.is_file()]

    def test_solo_carga_confirmada_crea_original_e_historial(self):
        self.client.get(self.url);self.assertFalse(self.archivos())
        original=imagen_bytes()
        r=self.subir(data=original,confirmar='')
        self.assertEqual(r.status_code,400)
        self.assertFalse(AdjuntoBitacora.objects.exists());self.assertFalse(self.archivos())
        r=self.subir(data=original)
        self.assertRedirects(r,self.historial)
        a=AdjuntoBitacora.objects.get();entrada=a.seguimiento
        self.assertEqual(entrada.tipo,'ADJUNTO');self.assertEqual(entrada.autor,self.coord)
        self.assertEqual(entrada.autor_nombre,self.coord.username)
        self.assertEqual(entrada.comentario,'Soporte de prueba')
        self.assertEqual(a.sha256,hashlib.sha256(original).hexdigest())
        self.assertEqual(a.tamano,len(original));self.assertEqual(self.leer_descarga(),original)
        self.reg.refresh_from_db();self.assertEqual(self.reg.descripcion,'Descripción original')
        self.assertEqual(self.reg.estado,'PENDIENTE')

    def test_reenvio_y_mismo_contenido_no_duplican(self):
        token=self.token();self.assertEqual(self.subir(token).status_code,302)
        self.assertEqual(self.subir(token).status_code,302)
        r=self.subir(nombre='otro_nombre.png')
        self.assertContains(r,'ya está adjunto')
        self.assertEqual(AdjuntoBitacora.objects.count(),1)
        self.assertEqual(SeguimientoBitacora.objects.count(),1)
        self.assertEqual(len(self.archivos()),1)

    def test_mismos_nombres_distintos_contenidos_no_se_sobrescriben(self):
        self.subir(data=imagen_bytes(color='blue'))
        self.subir(data=imagen_bytes(color='red'))
        self.assertEqual(AdjuntoBitacora.objects.count(),2)
        self.assertEqual(len(set(AdjuntoBitacora.objects.values_list('ruta_privada',flat=True))),2)
        self.assertEqual(len(self.archivos()),2)

    def test_coordinador_supervisor_y_superusuario_pueden_subir(self):
        for user,color in [(self.coord,'blue'),(self.supervisor,'red'),(self.root,'green')]:
            self.client.force_login(user)
            self.assertEqual(self.subir(data=imagen_bytes(color=color)).status_code,302)
            self.assertEqual(AdjuntoBitacora.objects.first().seguimiento.autor,user)

    def test_consulta_descarga_solo_si_esta_autorizado(self):
        self.subir();url=self.descarga_url()
        for user in [self.coord,self.supervisor,self.gerencia,self.andy,self.root]:
            self.client.force_login(user);self.assertEqual(self.leer_descarga(),imagen_bytes())
        for user in [self.gerencia,self.andy]:
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.url).status_code,403)
            self.assertEqual(self.client.post(self.url,{}).status_code,403)
            r=self.client.get(self.historial)
            self.assertContains(r,'Descargar foto.png')
            self.assertNotContains(r,'>Adjuntar archivo<')
        self.reg.responsable=self.coord;self.reg.save()
        self.client.force_login(self.andy)
        self.assertEqual(self.client.get(url).status_code,404)

    def test_externos_sin_rol_e_inactivos_no_acceden(self):
        self.subir();url=self.descarga_url()
        for user in [self.externo,self.administracion,self.sin_rol]:
            self.client.force_login(user)
            self.assertEqual(self.client.get(url).status_code,403)
            self.assertEqual(self.client.post(self.url,{}).status_code,403)
        self.externo.is_superuser=True;self.externo.save()
        self.externo.groups.add(Group.objects.get(name='GESTION_COORDINADOR'))
        self.client.force_login(self.externo)
        self.assertEqual(self.client.get(url).status_code,403)
        self.coord.is_active=False;self.coord.save();self.client.force_login(self.coord)
        self.assertEqual(self.client.get(url).status_code,302)

    def test_anonimo_csrf_y_metodos(self):
        self.subir();url=self.descarga_url()
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code,302)
        self.assertEqual(self.client.get(self.url).status_code,302)
        csrf=HttpClient(enforce_csrf_checks=True);csrf.force_login(self.coord)
        self.assertEqual(csrf.post(self.url,{}).status_code,403)
        self.client.force_login(self.coord)
        self.assertEqual(self.client.post(url,{}).status_code,405)
        self.assertEqual(self.client.delete(self.url).status_code,405)

    def test_token_no_se_puede_alterar_ni_transferir(self):
        token=self.token()
        self.assertEqual(self.subir(token+'x').status_code,400)
        self.client.force_login(self.supervisor)
        self.assertEqual(self.subir(token).status_code,403)
        self.client.force_login(self.coord)
        original_url=self.url;self.url=reverse('adjuntar_bitacora',args=[self.privada.pk])
        self.assertEqual(self.subir(token).status_code,403)
        self.url=original_url
        self.assertFalse(AdjuntoBitacora.objects.exists());self.assertFalse(self.archivos())

    def test_token_caducado_se_renueva_sin_guardar(self):
        import time
        token=self.token()
        with patch('django.core.signing.time.time',return_value=time.time()+3602):
            r=self.subir(token)
        self.assertEqual(r.status_code,400)
        self.assertNotEqual(r.context['form_adjunto'].data['solicitud'],token)
        self.assertFalse(self.archivos())

    def test_formatos_permitidos_y_tipo_real(self):
        archivos=[('foto.jpg',imagen_bytes('JPEG')),('foto.webp',imagen_bytes('WEBP')),('soporte.pdf',b'%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF'),('soporte.docx',office_bytes()),('soporte.xlsx',office_bytes('xlsx'))]
        for nombre,data in archivos:
            with self.subTest(nombre=nombre):
                self.assertEqual(self.subir(nombre=nombre,data=data).status_code,302)
                a=AdjuntoBitacora.objects.get(nombre_original=nombre)
                self.assertEqual(self.leer_descarga(a),data)

    def test_archivos_vacios_excesivos_disfrazados_y_activos_se_rechazan(self):
        casos=[('vacio.png',b''),('grande.pdf',b'x'*(MAX_BYTES+1)),('falso.png',b'<script>alert(1)</script>'),('falso.pdf',b'<html>HTML</html>'),('falso.jpg',imagen_bytes('PNG')),('script.svg',b'<svg/>'),('programa.exe',b'MZ'),('script.html',b'html'),('macro.docm',b'zip')]
        for nombre,data in casos:
            with self.subTest(nombre=nombre):
                self.assertEqual(self.subir(nombre=nombre,data=data).status_code,400)
        self.assertFalse(AdjuntoBitacora.objects.exists());self.assertFalse(self.archivos())

    def test_documentos_macro_y_contenedores_peligrosos(self):
        datos=[office_bytes(macro=True),b'PK falso',office_bytes('xlsx')]
        for extra in ['../escape','/absoluta','[Content_Types].xml']:
            data=BytesIO(office_bytes())
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', UserWarning)
                with ZipFile(data,'a') as z:z.writestr(extra,b'contenido')
            datos.append(data.getvalue())
        data=BytesIO(office_bytes())
        with ZipFile(data,'a') as z:
            for n in range(2001):z.writestr(f'items/{n}',b'')
        datos.append(data.getvalue())
        for contenido in datos:
            self.assertEqual(self.subir(nombre='archivo.docx',data=contenido).status_code,400)
        self.assertFalse(self.archivos())

    def test_nombre_original_no_es_ruta_y_html_se_escapa(self):
        self.assertEqual(nombre_seguro('C:\\temporal\\foto.png'),'foto.png')
        self.assertEqual(nombre_seguro('../../foto.png'),'foto.png')
        self.assertEqual(nombre_seguro('foto\r\n.png'),'foto.png')
        self.subir(nombre='foto<script>.png')
        a=AdjuntoBitacora.objects.get()
        self.assertNotIn('foto',a.ruta_privada)
        r=self.client.get(self.historial)
        self.assertContains(r,'foto&lt;script&gt;.png')
        self.assertNotContains(r,'foto<script>.png')

    def test_descarga_tiene_cabeceras_privadas_y_no_ruta_publica(self):
        self.subir();a=AdjuntoBitacora.objects.get()
        r=self.client.get(self.descarga_url())
        try:
            self.assertTrue(r['Content-Disposition'].startswith('attachment;'))
            self.assertEqual(r['Cache-Control'],'private, no-store')
            self.assertEqual(r['X-Content-Type-Options'],'nosniff')
            self.assertIn('sandbox',r['Content-Security-Policy'])
        finally:
            # Consumir la descarga deja el cierre a cargo del cliente de pruebas.
            b''.join(r.streaming_content)
        with self.assertRaises(ValueError):almacenamiento_privado().url(a.ruta_privada)
        from . import urls as app_urls
        module=ModuleType('urls_adjuntos_prueba')
        with self.settings(DEBUG=True):
            module.urlpatterns=list(app_urls.urlpatterns)+static('/media/',document_root=self.temp/'media')
            with self.settings(ROOT_URLCONF=module):
                with self.assertLogs('django.request',level='WARNING'):
                    self.assertEqual(self.client.get('/media/'+a.ruta_privada).status_code,404)

    def test_carpeta_privada_no_puede_ser_publica(self):
        for raiz in [self.temp/'media',self.temp/'media/subcarpeta',self.temp,self.temp/'static',self.temp/'static/sub']:
            with self.settings(BITACORA_ADJUNTOS_ROOT=raiz):
                with self.assertRaises(ImproperlyConfigured):raiz_privada()
        with self.settings(STATICFILES_DIRS=[self.temp/'assets'],BITACORA_ADJUNTOS_ROOT=self.temp/'assets/privado'):
            with self.assertRaises(ImproperlyConfigured):raiz_privada()
        with self.settings(BITACORA_ADJUNTOS_ROOT=None):
            self.assertEqual(raiz_privada(),self.temp/'proyecto_adjuntos_privados')

    def test_archivo_ausente_o_ruta_alterada_devuelve_404(self):
        self.subir();a=AdjuntoBitacora.objects.get()
        self.archivos()[0].unlink()
        self.assertEqual(self.client.get(self.descarga_url()).status_code,404)
        AdjuntoBitacora.objects.filter(pk=a.pk).update(ruta_privada='../secreto.pdf')
        self.assertEqual(self.client.get(self.descarga_url()).status_code,404)
        self.assertEqual(self.client.get(reverse('descargar_adjunto_bitacora',args=[uuid4()])).status_code,404)

    def test_error_bd_no_deja_archivo_ni_entrada_huerfanos(self):
        token=self.token();antes=self.reg.actualizado
        with patch('operacion.views_adjuntos_bitacora.AdjuntoBitacora.save',side_effect=DatabaseError('fallo simulado')):
            with self.assertLogs('operacion.views_adjuntos_bitacora',level='ERROR'):
                r=self.subir(token)
        self.assertEqual(r.status_code,503)
        self.assertFalse(self.archivos());self.assertFalse(SeguimientoBitacora.objects.exists())
        self.reg.refresh_from_db();self.assertEqual(self.reg.actualizado,antes)

    def test_error_escritura_no_deja_registros(self):
        token=self.token()
        with patch('operacion.views_adjuntos_bitacora.guardar_archivo_privado',side_effect=OSError('disco')):
            with self.assertLogs('operacion.views_adjuntos_bitacora',level='ERROR'):r=self.subir(token)
        self.assertEqual(r.status_code,503)
        self.assertFalse(SeguimientoBitacora.objects.exists());self.assertFalse(AdjuntoBitacora.objects.exists())

    def test_solicitud_no_admite_varios_archivos(self):
        self.assertEqual(self.subir(archivo=[SimpleUploadedFile('a.png',imagen_bytes()),SimpleUploadedFile('b.png',imagen_bytes(color='red'))]).status_code,400)
        self.assertFalse(self.archivos())

    def test_admin_solo_consulta_y_misma_asignacion(self):
        self.subir();a=AdjuntoBitacora.objects.get();ma=admin.site._registry[AdjuntoBitacora]
        req=RequestFactory().get('/admin/')
        for user in [self.coord,self.gerencia,self.andy,self.root]:
            req.user=user
            self.assertTrue(ma.has_view_permission(req,a))
            self.assertFalse(ma.has_add_permission(req));self.assertFalse(ma.has_change_permission(req,a));self.assertFalse(ma.has_delete_permission(req,a))
        req.user=self.externo
        self.assertFalse(ma.has_view_permission(req,a));self.assertEqual(ma.get_queryset(req).count(),0)
        self.reg.responsable=self.coord;self.reg.save();req.user=self.andy
        self.assertFalse(ma.has_view_permission(req,a));self.assertEqual(ma.get_queryset(req).count(),0)
        with self.assertRaises(ProtectedError):a.seguimiento.delete()

    def test_comprobacion_almacen_no_modifica_bd_ni_conserva_archivo(self):
        from io import StringIO
        out=StringIO();call_command('comprobar_adjuntos_bitacora',stdout=out)
        self.assertIn('correctas',out.getvalue())
        self.assertFalse(self.archivos());self.assertFalse(SeguimientoBitacora.objects.exists())

    def test_misma_huella_en_otra_novedad_es_independiente(self):
        self.subir()
        self.url=reverse('adjuntar_bitacora',args=[self.privada.pk])
        self.assertEqual(self.subir().status_code,302)
        self.assertEqual(AdjuntoBitacora.objects.count(),2)
        privado=AdjuntoBitacora.objects.get(seguimiento__bitacora=self.privada)
        self.client.force_login(self.andy)
        self.assertEqual(self.client.get(self.descarga_url(privado)).status_code,404)
