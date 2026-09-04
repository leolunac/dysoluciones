"""Permisos, conservación de cambios y confirmación del historial interno."""
from unittest.mock import patch
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import signing
from django.db.models.deletion import ProtectedError
from django.test import Client as HttpClient, RequestFactory, TestCase
from django.urls import reverse
from .models import BitacoraOperativa, SeguimientoBitacora, Tecnico, Cliente, UsuarioCliente, Administracion, UsuarioAdministracion


class HistorialBitacoraTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        for atributo, grupo in [('coord','GESTION_COORDINADOR'),('supervisor','GESTION_SUPERVISOR'),('gerencia','GESTION_GERENCIA'),('andy',None),('externo',None),('administracion',None),('sin_rol',None)]:
            user = User.objects.create_user(username='hist_'+atributo, is_staff=True)
            if grupo:
                user.groups.add(Group.objects.get_or_create(name=grupo)[0])
            setattr(cls,atributo,user)
        cls.root = User.objects.create_superuser(username='hist_root',password='solo-pruebas')
        Tecnico.objects.create(user=cls.andy,nombre='Andy',valor_hora_diurna=0,valor_hora_nocturna=0)
        unidad=Cliente.objects.create(nombre='Unidad historial',tipo_contrato='SIN_CONTRATO',frecuencia_lavado=4)
        UsuarioCliente.objects.create(user=cls.externo,cliente=unidad)
        adm=Administracion.objects.create(nombre='Administración historial')
        UsuarioAdministracion.objects.create(user=cls.administracion,administracion=adm)
        cls.reg = BitacoraOperativa.objects.create(titulo='Mantenimiento',descripcion='Descripción original',responsable=cls.andy,creado_por=cls.coord)
        cls.privada = BitacoraOperativa.objects.create(titulo='Solo coordinación',descripcion='Texto reservado',responsable=cls.coord,creado_por=cls.coord)

    def setUp(self):
        self.client.force_login(self.coord)
        self.url=reverse('historial_bitacora',args=[self.reg.pk])

    def revisar(self, comentario='Se solicitó el repuesto', estado='', **extras):
        return self.client.post(self.url,dict(accion='revisar',comentario=comentario,estado=estado,**extras))

    def confirmar(self, token, **extras):
        return self.client.post(self.url,dict(accion='confirmar',revision=token,**extras))

    def token(self, **kwargs):
        r=self.revisar(**kwargs)
        self.assertEqual(r.status_code,200)
        return r.context['token_revision']

    def editar_datos(self, **extras):
        return dict(titulo=self.reg.titulo,descripcion=self.reg.descripcion,tipo='NOTA_INTERNA',prioridad='MEDIA',estado='PENDIENTE',responsable=self.andy.pk,**extras)

    def test_revision_no_escribe_y_confirmacion_conserva_autor_y_original(self):
        r=self.revisar(estado='EN_SEGUIMIENTO',autor=self.root.pk,bitacora=self.privada.pk)
        self.assertContains(r,'todavía no se ha guardado')
        self.assertFalse(SeguimientoBitacora.objects.exists())
        self.reg.refresh_from_db();self.assertEqual(self.reg.estado,'PENDIENTE')
        result=self.confirmar(r.context['token_revision'],comentario='Texto manipulado',estado='CERRADO')
        self.assertRedirects(result,self.url)
        entrada=SeguimientoBitacora.objects.get()
        self.assertEqual(entrada.autor,self.coord)
        self.assertEqual(entrada.autor_nombre,self.coord.username)
        self.assertEqual(entrada.bitacora,self.reg)
        self.assertEqual(entrada.comentario,'Se solicitó el repuesto')
        self.reg.refresh_from_db()
        self.assertEqual(self.reg.descripcion,'Descripción original')
        self.assertEqual(self.reg.estado,'EN_SEGUIMIENTO')
        self.assertEqual(entrada.cambios[0]['anterior'],'Pendiente')

    def test_doble_envio_no_duplica_ni_reaplica_estado_antiguo(self):
        token=self.token(estado='CERRADO')
        self.assertEqual(self.confirmar(token).status_code,302)
        nueva=self.token(comentario='Se requiere revisar nuevamente',estado='EN_SEGUIMIENTO')
        self.confirmar(nueva)
        self.assertEqual(self.confirmar(token).status_code,302)
        self.assertEqual(SeguimientoBitacora.objects.count(),2)
        self.reg.refresh_from_db();self.assertEqual(self.reg.estado,'EN_SEGUIMIENTO')

    def test_correccion_no_guarda_y_conserva_el_texto(self):
        token=self.token()
        r=self.client.post(self.url,{'accion':'corregir','revision':token})
        self.assertContains(r,'Se solicitó el repuesto')
        self.assertFalse(SeguimientoBitacora.objects.exists())
        self.assertIsNone(r.context['revision'])

    def test_rechaza_vacios_estado_invalido_y_comentario_excesivo(self):
        for comentario,estado in [('   ',''),('Texto','INVALIDO'),('x'*8001,'')]:
            with self.subTest(estado=estado,longitud=len(comentario)):
                self.assertEqual(self.revisar(comentario,estado).status_code,400)
        self.assertFalse(SeguimientoBitacora.objects.exists())

    def test_requiere_revision_valida_y_no_permite_manipular_token(self):
        self.assertEqual(self.confirmar('').status_code,400)
        token=self.token()
        self.assertEqual(self.confirmar(token+'x').status_code,400)
        self.assertEqual(self.client.post(self.url,{'comentario':'Sin revisión'}).status_code,400)
        self.assertFalse(SeguimientoBitacora.objects.exists())

    def test_revision_caducada_se_rechaza(self):
        token=self.token()
        import time
        with patch('django.core.signing.time.time',return_value=time.time()+3602):
            self.assertEqual(self.confirmar(token).status_code,400)
        self.assertFalse(SeguimientoBitacora.objects.exists())

    def test_token_vinculado_a_usuario_y_novedad(self):
        token=self.token()
        otra=reverse('historial_bitacora',args=[self.privada.pk])
        self.assertEqual(self.client.post(otra,{'accion':'confirmar','revision':token}).status_code,403)
        self.client.force_login(self.supervisor)
        self.assertEqual(self.confirmar(token).status_code,403)
        self.assertFalse(SeguimientoBitacora.objects.exists())

    def test_conflicto_conserva_comentario_y_no_sobrescribe(self):
        token=self.token(estado='CERRADO')
        self.reg.estado='EN_SEGUIMIENTO';self.reg.save()
        r=self.confirmar(token)
        self.assertEqual(r.status_code,409)
        self.assertContains(r,'Se solicitó el repuesto',status_code=409)
        self.reg.refresh_from_db();self.assertEqual(self.reg.estado,'EN_SEGUIMIENTO')
        self.assertFalse(SeguimientoBitacora.objects.exists())

    def test_cierre_y_reapertura_conservan_historia(self):
        self.confirmar(self.token(estado='CERRADO'))
        self.reg.refresh_from_db();self.assertIsNotNone(self.reg.fecha_cierre)
        self.confirmar(self.token(comentario='Reabrir por nueva observación',estado='PENDIENTE'))
        self.reg.refresh_from_db();self.assertIsNone(self.reg.fecha_cierre)
        self.assertEqual(SeguimientoBitacora.objects.count(),2)
        self.assertTrue(any(c['campo']=='Fecha de cierre' for c in SeguimientoBitacora.objects.last().cambios))

    def test_supervisor_y_superusuario_pueden_agregar(self):
        for user in (self.supervisor,self.root):
            self.client.force_login(user)
            self.assertEqual(self.confirmar(self.token()).status_code,302)
            self.assertEqual(SeguimientoBitacora.objects.first().autor,user)

    def test_gerencia_y_tecnico_solo_consultan(self):
        self.confirmar(self.token())
        for user in (self.gerencia,self.andy):
            self.client.force_login(user)
            r=self.client.get(self.url)
            self.assertContains(r,'Se solicitó el repuesto')
            self.assertNotContains(r,'Revisar seguimiento')
            self.assertNotContains(r,'Editar datos')
            self.assertEqual(self.revisar().status_code,403)
        self.assertEqual(self.client.get(reverse('historial_bitacora',args=[self.privada.pk])).status_code,404)
        self.reg.responsable=self.coord;self.reg.save()
        self.assertEqual(self.client.get(self.url).status_code,404)

    def test_externos_mixtos_sin_rol_e_inactivos_bloqueados(self):
        for user in (self.externo,self.administracion,self.sin_rol):
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.url).status_code,403)
            self.assertEqual(self.revisar().status_code,403)
        self.externo.groups.add(Group.objects.get(name='GESTION_COORDINADOR'))
        self.externo.is_superuser=True;self.externo.save()
        self.client.force_login(self.externo)
        self.assertEqual(self.client.get(self.url).status_code,403)
        self.coord.is_active=False;self.coord.save();self.client.force_login(self.coord)
        self.assertEqual(self.client.get(self.url).status_code,302)

    def test_gerencia_con_grupo_editor_permanece_consulta(self):
        self.gerencia.groups.add(Group.objects.get(name='GESTION_COORDINADOR'))
        self.client.force_login(self.gerencia)
        self.assertEqual(self.revisar().status_code,403)

    def test_anonimo_csrf_y_metodos_http(self):
        self.client.logout();self.assertEqual(self.client.get(self.url).status_code,302)
        csrf=HttpClient(enforce_csrf_checks=True);csrf.force_login(self.coord)
        self.assertEqual(csrf.post(self.url,{'accion':'revisar','comentario':'Texto'}).status_code,403)
        self.client.force_login(self.coord)
        self.assertEqual(self.client.delete(self.url).status_code,405)

    def test_editar_preserva_valores_anteriores_y_autor(self):
        data=self.editar_datos();data['descripcion']='Descripción corregida'
        r=self.client.post(reverse('editar_bitacora',args=[self.reg.pk]),data)
        self.assertEqual(r.status_code,302)
        entrada=SeguimientoBitacora.objects.get()
        self.assertEqual(entrada.tipo,'EDICION')
        self.assertEqual(entrada.autor,self.coord)
        cambio=next(c for c in entrada.cambios if c['campo']=='Descripción')
        self.assertEqual(cambio['anterior'],'Descripción original')
        self.assertEqual(cambio['nuevo'],'Descripción corregida')
        self.assertEqual(self.client.post(reverse('editar_bitacora',args=[self.reg.pk]),data).status_code,302)
        self.assertEqual(SeguimientoBitacora.objects.count(),1)

    def test_error_historial_revierte_edicion_y_estado(self):
        data=self.editar_datos();data['descripcion']='No debe persistir'
        with patch('operacion.historial_bitacora.SeguimientoBitacora.objects.create',side_effect=RuntimeError('simulado')):
            with self.assertRaises(RuntimeError):
                self.client.post(reverse('editar_bitacora',args=[self.reg.pk]),data)
        self.reg.refresh_from_db();self.assertEqual(self.reg.descripcion,'Descripción original')
        token=self.token(estado='CERRADO')
        with patch('operacion.views_historial_bitacora.SeguimientoBitacora.objects.create',side_effect=RuntimeError('simulado')):
            with self.assertRaises(RuntimeError):self.confirmar(token)
        self.reg.refresh_from_db();self.assertEqual(self.reg.estado,'PENDIENTE')
        self.assertFalse(SeguimientoBitacora.objects.exists())

    def test_admin_registra_edicion_y_solo_permite_lectura_del_historial(self):
        req=RequestFactory().get('/admin/');req.user=self.coord
        self.reg.descripcion='Corregido desde administrador'
        admin.site._registry[BitacoraOperativa].save_model(req,self.reg,None,True)
        entrada=SeguimientoBitacora.objects.get()
        self.assertEqual(entrada.autor,self.coord)
        ma=admin.site._registry[SeguimientoBitacora]
        for user in (self.coord,self.gerencia,self.andy,self.root):
            req.user=user
            self.assertTrue(ma.has_view_permission(req,entrada))
            self.assertFalse(ma.has_add_permission(req))
            self.assertFalse(ma.has_change_permission(req,entrada))
            self.assertFalse(ma.has_delete_permission(req,entrada))
        req.user=self.externo;self.assertFalse(ma.has_view_permission(req,entrada))
        self.assertEqual(ma.get_queryset(req).count(),0)
        self.reg.responsable=self.coord;self.reg.save()
        req.user=self.andy;self.assertFalse(ma.has_view_permission(req,entrada))
        self.assertEqual(ma.get_queryset(req).count(),0)

    def test_xss_se_muestra_como_texto_y_historial_pagina(self):
        self.confirmar(self.token(comentario='<script>alert(1)</script>'))
        r=self.client.get(self.url)
        self.assertContains(r,'&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertNotContains(r,'<script>alert(1)</script>')
        SeguimientoBitacora.objects.bulk_create([SeguimientoBitacora(bitacora=self.reg,autor=self.coord,autor_nombre='coord',comentario=f'Entrada {i}') for i in range(25)])
        r=self.client.get(self.url);self.assertEqual(len(r.context['pagina']),25)
        r=self.client.get(self.url,{'pagina':2});self.assertEqual(len(r.context['pagina']),1)
        self.assertContains(r,'&lt;script&gt;alert(1)&lt;/script&gt;')

    def test_nombre_autor_se_conserva_y_no_se_borra_novedad_con_historial(self):
        self.client.force_login(self.supervisor)
        self.confirmar(self.token())
        nombre=self.supervisor.username;self.supervisor.delete()
        entrada=SeguimientoBitacora.objects.get()
        self.assertIsNone(entrada.autor)
        self.assertEqual(entrada.autor_nombre,nombre)
        with self.assertRaises(ProtectedError):self.reg.delete()


    def test_misma_fecha_en_utc_y_hora_local_no_genera_edicion(self):
        from datetime import datetime, timezone as dt_timezone
        from django.utils import timezone
        self.reg.fecha_compromiso=datetime(2026,9,5,15,30,tzinfo=dt_timezone.utc)
        self.reg.save()
        data=self.editar_datos();data['fecha_compromiso']='2026-09-05T10:30'
        with timezone.override('America/Bogota'):
            r=self.client.post(reverse('editar_bitacora',args=[self.reg.pk]),data)
        self.assertEqual(r.status_code,302)
        self.assertFalse(SeguimientoBitacora.objects.exists())
