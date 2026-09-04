"""Pruebas de autorización: ejecutar solo contra la BD de pruebas de desarrollo."""
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import Client as HttpClient, RequestFactory, TestCase
from django.urls import reverse

from .models import (
    ActividadTecnico, Administracion, BitacoraOperativa, Cliente,
    Emergencia, Tecnico, UsuarioAdministracion, UsuarioCliente,
)
from .permisos_bitacora import rol_bitacora


class PermisosBitacoraTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        def user(nombre, grupo=None, **kwargs):
            u = User.objects.create_user(username=nombre, password='solo-pruebas', **kwargs)
            if grupo:
                u.groups.add(Group.objects.get_or_create(name=grupo)[0])
            return u
        cls.coord = user('coordinador', 'GESTION_COORDINADOR')
        cls.supervisor = user('supervisor', 'GESTION_SUPERVISOR')
        cls.gerencia = user('gerencia', 'GESTION_GERENCIA')
        cls.sin_rol = user('sin_rol', is_staff=True)
        cls.superuser = user('administrador', is_staff=True, is_superuser=True)
        cls.auxiliar = user('auxiliar', 'GESTION_AUXILIAR')
        cls.tecnico_user = user('tecnico')
        cls.otro_user = user('otro_tecnico')
        cls.cliente_user = user('cliente')
        cls.admin_user = user('administracion')
        cls.unidad = Cliente.objects.create(nombre='Unidad de prueba', tipo_contrato='SIN_CONTRATO', frecuencia_lavado=4)
        UsuarioCliente.objects.create(user=cls.cliente_user, cliente=cls.unidad)
        adm = Administracion.objects.create(nombre='Administración de prueba')
        UsuarioAdministracion.objects.create(user=cls.admin_user, administracion=adm)
        def tecnico(u):
            return Tecnico.objects.create(user=u, nombre=u.username, valor_hora_diurna=0, valor_hora_nocturna=0)
        cls.tecnico = tecnico(cls.tecnico_user)
        cls.otro = tecnico(cls.otro_user)
        cls.caso = Emergencia.objects.create(cliente=cls.unidad, tecnico=cls.tecnico, numero_caso='PRUEBA-1', descripcion_falla='Falla')
        cls.otro_caso = Emergencia.objects.create(cliente=cls.unidad, tecnico=cls.otro, numero_caso='PRUEBA-2', descripcion_falla='Falla ajena')
        cls.act = ActividadTecnico.objects.create(cliente=cls.unidad, tecnico=cls.tecnico, servicio=cls.caso, labor_realizada='Labor asignada')
        cls.otra_act = ActividadTecnico.objects.create(cliente=cls.unidad, tecnico=cls.tecnico, servicio=cls.caso, labor_realizada='Labor reservada')
        cls.asignada = BitacoraOperativa.objects.create(titulo='ASIGNADA-TECNICO', descripcion='Asignada', responsable=cls.tecnico_user, actividad=cls.act, creado_por=cls.coord)
        cls.privada = BitacoraOperativa.objects.create(titulo='RESERVADA-COORDINACION', descripcion='Reservada', responsable=cls.coord, tecnico=cls.tecnico, actividad=cls.otra_act, creado_por=cls.tecnico_user, visible_cliente=True)

    def login(self, user):
        self.client.force_login(user)

    def datos(self, **extra):
        return dict(titulo='Nueva prueba', descripcion='Texto confirmado', tipo='NOTA_INTERNA', prioridad='MEDIA', estado='PENDIENTE', **extra)

    def test_anonimo_redirige_login(self):
        urls = [reverse('lista_bitacora'), reverse('nueva_bitacora'), reverse('editar_bitacora', args=[self.asignada.pk]), reverse('actividades_por_cliente'), reverse('detalle_actividad', args=[self.act.pk]), reverse('casos_por_cliente')]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 302)

    def test_clientes_y_sin_rol_no_acceden(self):
        for user in [self.cliente_user, self.admin_user, self.sin_rol, self.auxiliar]:
            self.login(user)
            for url in [reverse('lista_bitacora'), reverse('nueva_bitacora'), reverse('editar_bitacora', args=[self.privada.pk]), reverse('actividades_por_cliente'), reverse('detalle_actividad', args=[self.act.pk])]:
                with self.subTest(user=user.username, url=url):
                    self.assertEqual(self.client.get(url).status_code, 403)
                    self.assertEqual(self.client.post(url, self.datos()).status_code, 403 if 'editar' in url or 'nueva' in url else 405)

    def test_cliente_con_grupos_y_superusuario_sigue_bloqueado(self):
        for user in [self.cliente_user, self.admin_user]:
            user.groups.add(Group.objects.get(name='GESTION_COORDINADOR'))
            user.is_superuser = True
            user.save()
            self.login(user)
            self.assertEqual(self.client.get(reverse('lista_bitacora')).status_code, 403)

    def test_tecnico_solo_responsable_y_kpis_filtrados(self):
        self.login(self.tecnico_user)
        response = self.client.get(reverse('lista_bitacora'))
        self.assertContains(response, 'ASIGNADA-TECNICO')
        self.assertNotContains(response, 'RESERVADA-COORDINACION')
        self.assertEqual(response.context['total'], 1)
        self.assertEqual(response.context['pendientes'], 1)
        self.assertNotContains(response, reverse('nueva_bitacora'))
        self.assertNotContains(response, reverse('editar_bitacora', args=[self.asignada.pk]))
        response = self.client.get(reverse('lista_bitacora'), {'buscar':'RESERVADA'})
        self.assertEqual(response.context['total'], 0)
        self.assertNotContains(response, reverse('nueva_bitacora'))

    def test_gerencia_consulta_todo_sin_botones_edicion(self):
        self.login(self.gerencia)
        r = self.client.get(reverse('lista_bitacora'))
        self.assertContains(r, 'RESERVADA-COORDINACION')
        self.assertEqual(r.context['total'], 2)
        self.assertNotContains(r, reverse('nueva_bitacora'))
        self.assertNotContains(r, reverse('editar_bitacora', args=[self.asignada.pk]))

    def test_lectores_no_escriben_por_url_ni_post(self):
        inicial = BitacoraOperativa.objects.count()
        for user in [self.gerencia, self.tecnico_user, self.otro_user]:
            self.login(user)
            for url in [reverse('nueva_bitacora'), reverse('editar_bitacora', args=[self.asignada.pk]), reverse('editar_bitacora', args=[self.privada.pk])]:
                with self.subTest(user=user.username, url=url):
                    self.assertEqual(self.client.get(url).status_code, 403)
                    self.assertEqual(self.client.post(url, self.datos()).status_code, 403)
        self.assertEqual(BitacoraOperativa.objects.count(), inicial)
        self.asignada.refresh_from_db()
        self.assertEqual(self.asignada.titulo, 'ASIGNADA-TECNICO')

    def test_editores_crean_y_actualizan_preservando_autor(self):
        for user in [self.coord, self.supervisor, self.superuser]:
            self.login(user)
            self.assertEqual(self.client.get(reverse('nueva_bitacora')).status_code, 200)
            r = self.client.post(reverse('nueva_bitacora'), self.datos(visible_cliente='on', creado_por=self.otro_user.pk))
            self.assertEqual(r.status_code, 302)
            nueva = BitacoraOperativa.objects.latest('pk')
            self.assertEqual(nueva.creado_por, user)
            self.assertEqual(nueva.responsable, user)
            self.assertFalse(nueva.visible_cliente)
            r = self.client.post(reverse('editar_bitacora', args=[self.privada.pk]), self.datos(visible_cliente='on', creado_por=user.pk))
            self.assertEqual(r.status_code, 302)
            self.privada.refresh_from_db()
            self.assertEqual(self.privada.creado_por, self.tecnico_user)
            self.assertFalse(self.privada.visible_cliente)

    def test_gerencia_prevalece_sobre_grupo_editor(self):
        self.gerencia.groups.add(Group.objects.get(name='GESTION_COORDINADOR'))
        self.login(self.gerencia)
        self.assertEqual(self.client.post(reverse('nueva_bitacora'), self.datos()).status_code, 403)

    def test_permisos_django_sueltos_no_otorgan_rol(self):
        self.sin_rol.user_permissions.add(*Permission.objects.filter(content_type__model='bitacoraoperativa'))
        self.login(self.sin_rol)
        self.assertEqual(self.client.get(reverse('lista_bitacora')).status_code, 403)

    def test_tecnico_inactivo_y_usuario_inactivo_denegados(self):
        self.tecnico.activo = False
        self.tecnico.save()
        self.login(self.tecnico_user)
        self.assertEqual(self.client.get(reverse('lista_bitacora')).status_code, 403)
        self.coord.is_active = False
        self.assertIsNone(rol_bitacora(self.coord))

    def test_json_actividades_y_detalle_limitados_a_asignaciones(self):
        self.login(self.tecnico_user)
        r = self.client.get(reverse('actividades_por_cliente'), {'cliente_id':self.unidad.pk})
        self.assertEqual([a['id'] for a in r.json()['actividades']], [self.act.pk])
        self.assertEqual(self.client.get(reverse('detalle_actividad', args=[self.act.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('detalle_actividad', args=[self.otra_act.pk])).status_code, 404)
        self.asignada.responsable = self.otro_user
        self.asignada.save()
        self.assertEqual(self.client.get(reverse('detalle_actividad', args=[self.act.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('lista_bitacora')).context['total'], 0)

    def test_json_gerencia_y_editores_consultan(self):
        for user in [self.coord, self.supervisor, self.gerencia]:
            self.login(user)
            self.assertEqual(self.client.get(reverse('detalle_actividad', args=[self.otra_act.pk])).status_code, 200)
            r = self.client.get(reverse('actividades_por_cliente'), {'cliente_id':self.unidad.pk})
            self.assertEqual(len(r.json()['actividades']), 2)

    def test_casos_compartidos_preservan_roles_y_limitan_tecnicos(self):
        self.login(self.tecnico_user)
        r = self.client.get(reverse('casos_por_cliente'), {'cliente_id':self.unidad.pk})
        self.assertEqual([x['id'] for x in r.json()['casos']], [self.caso.pk])
        for user in [self.coord, self.supervisor, self.gerencia, self.auxiliar]:
            self.login(user)
            r = self.client.get(reverse('casos_por_cliente'), {'cliente_id':self.unidad.pk})
            self.assertEqual(len(r.json()['casos']), 2)
        for user in [self.cliente_user, self.admin_user, self.sin_rol]:
            self.login(user)
            self.assertEqual(self.client.get(reverse('casos_por_cliente')).status_code, 403)

    def test_responsables_externos_rechazados(self):
        self.login(self.coord)
        for user in [self.cliente_user, self.admin_user, self.gerencia, self.sin_rol]:
            r = self.client.post(reverse('nueva_bitacora'), self.datos(responsable=user.pk))
            self.assertEqual(r.status_code, 200)
            self.assertIn('responsable', r.context['form'].errors)
        self.assertEqual(BitacoraOperativa.objects.count(), 2)

    def test_identificadores_invalidos_no_generan_error_500(self):
        self.login(self.coord)
        for url in ['casos_por_cliente','actividades_por_cliente']:
            self.assertEqual(self.client.get(reverse(url), {'cliente_id':'abc'}).status_code, 400)
        r = self.client.post(reverse('nueva_bitacora'), self.datos(cliente='abc',servicio='abc'))
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.context['form'].errors)

    def test_csrf_sigue_exigido(self):
        client = HttpClient(enforce_csrf_checks=True)
        client.force_login(self.coord)
        self.assertEqual(client.post(reverse('nueva_bitacora'), self.datos()).status_code, 403)

    def test_admin_aplica_roles_y_filtro_por_objeto(self):
        model_admin = admin.site._registry[BitacoraOperativa]
        for user in [self.coord,self.supervisor,self.superuser,self.gerencia,self.tecnico_user,self.cliente_user,self.admin_user,self.sin_rol]:
            request = RequestFactory().get('/admin/')
            request.user = user
            editor = user in [self.coord,self.supervisor,self.superuser]
            lector = editor or user in [self.gerencia,self.tecnico_user]
            with self.subTest(user=user.username):
                self.assertEqual(model_admin.has_view_permission(request), lector)
                self.assertEqual(model_admin.has_add_permission(request), editor)
                self.assertEqual(model_admin.has_change_permission(request,self.asignada), editor)
                self.assertFalse(model_admin.has_delete_permission(request,self.asignada))
                self.assertEqual(model_admin.get_queryset(request).count(), 2 if editor or user==self.gerencia else 1 if user==self.tecnico_user else 0)
        request.user = self.tecnico_user
        self.assertFalse(model_admin.has_view_permission(request,self.privada))
        self.assertTrue(model_admin.has_view_permission(request,self.asignada))

    def test_admin_urls_bloquean_escritura_y_objetos_ajenos(self):
        for user in [self.gerencia,self.tecnico_user,self.cliente_user,self.sin_rol]:
            user.is_staff = True
            user.save()
            self.login(user)
            self.assertEqual(self.client.post(reverse('admin:operacion_bitacoraoperativa_add'), self.datos()).status_code, 403)
            self.assertEqual(self.client.post(reverse('admin:operacion_bitacoraoperativa_change',args=[self.asignada.pk]), self.datos()).status_code, 403)
            r = self.client.get(reverse('admin:operacion_bitacoraoperativa_changelist'))
            self.assertEqual(r.status_code, 200 if user in [self.gerencia,self.tecnico_user] else 403)
            if user == self.tecnico_user:
                self.assertNotContains(r,'RESERVADA-COORDINACION')
